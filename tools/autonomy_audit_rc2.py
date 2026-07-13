from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
SRC_DIR = ROOT / "src"
TOOLS_DIR = ROOT / "tools"
DOCS_DIR = ROOT / "docs"

OUTPUT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / "_system"
    / "autonomy_hardening_rc2"
)

REPORT_JSON = OUTPUT_DIR / "architecture_audit.json"
REPORT_MD = OUTPUT_DIR / "architecture_audit.md"


ORCHESTRATOR_WORDS = {
    "run",
    "pipeline",
    "workflow",
    "runtime",
    "director",
    "core",
    "production",
}

DOMAIN_PATTERNS = {
    "asset_analysis": [
        r"visual[_ ]intelligence",
        r"scan_project_assets",
        r"_scan_project_assets",
        r"semantic_catalog",
        r"clip",
        r"perceptual_hash",
        r"difference_hash",
    ],
    "asset_assignment": [
        r"assign_assets",
        r"semantic_director",
        r"assigned_asset_id",
        r"director_decisions",
        r"temporal_compatible",
        r"group_bonus",
    ],
    "timeline": [
        r"_build_timeline",
        r"export_timeline",
        r"timeline\.json",
        r"TimelineStudio",
    ],
    "render": [
        r"_render_movie",
        r"RenderEngine",
        r"render_rc1",
        r"ffmpeg",
        r"mux_voice",
        r"concat_segments",
    ],
    "quality_control": [
        r"ffprobe",
        r"quality",
        r"validate",
        r"verify",
        r"readiness",
        r"temporal_violations",
    ],
    "state_management": [
        r"state\.json",
        r"report\.json",
        r"workflow_jobs",
        r"production_state",
        r"director_core_state",
        r"status=",
        r"final_state",
    ],
    "media_factory": [
        r"MediaFactory",
        r"media_factory",
        r"temporary_fill",
        r"missing_prompt",
        r"generation",
    ],
}

STATE_FILENAME_PATTERNS = [
    "*.json",
]

HARDCODE_PATTERNS = {
    "franklin_literal": re.compile(
        r"""(?i)(["']franklin["']|franklin_)"""
    ),
    "fixed_149_shots": re.compile(
        r"""(?<!\d)149(?!\d)"""
    ),
    "fixed_workspace_path": re.compile(
        r"""workspace[\\/](projects|exports)[\\/]franklin"""
    ),
    "fixed_windows_user_path": re.compile(
        r"""C:\\Users\\|C:/Users/"""
    ),
}

DANGEROUS_SUCCESS_PATTERNS = [
    re.compile(
        r"""state["']?\s*[:=]\s*["'](?:RENDERED|COMPLETED|DONE)["']""",
        re.IGNORECASE,
    ),
    re.compile(
        r"""status["']?\s*[:=]\s*["'](?:done|completed|rendered)["']""",
        re.IGNORECASE,
    ),
]


def iter_python_files() -> list[Path]:
    paths: list[Path] = []

    for root in (SRC_DIR, TOOLS_DIR):
        if not root.exists():
            continue

        paths.extend(
            path
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )

    return sorted(paths)


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_python(path: Path) -> dict[str, Any]:
    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    result: dict[str, Any] = {
        "path": relative(path),
        "lines": len(text.splitlines()),
        "classes": [],
        "functions": [],
        "imports": [],
        "syntax_error": None,
        "hardcoded": {},
        "domains": [],
        "success_markers": [],
    }

    try:
        tree = ast.parse(
            text,
            filename=str(path),
        )
    except SyntaxError as exc:
        result["syntax_error"] = str(exc)
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Import, ast.ImportFrom),
            ):
                if isinstance(node, ast.Import):
                    names = [
                        alias.name
                        for alias in node.names
                    ]
                else:
                    module = node.module or ""
                    names = [
                        f"{module}.{alias.name}"
                        for alias in node.names
                    ]

                result["imports"].extend(names)

            elif isinstance(node, ast.ClassDef):
                result["classes"].append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "methods": [
                            child.name
                            for child in node.body
                            if isinstance(
                                child,
                                (
                                    ast.FunctionDef,
                                    ast.AsyncFunctionDef,
                                ),
                            )
                        ],
                    }
                )

            elif isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                result["functions"].append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                    }
                )

    for name, pattern in HARDCODE_PATTERNS.items():
        matches = list(
            pattern.finditer(text)
        )

        if matches:
            result["hardcoded"][name] = len(
                matches
            )

    lower_text = text.lower()

    for domain, patterns in DOMAIN_PATTERNS.items():
        if any(
            re.search(
                pattern,
                lower_text,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        ):
            result["domains"].append(domain)

    for pattern in DANGEROUS_SUCCESS_PATTERNS:
        for match in pattern.finditer(text):
            line = (
                text.count(
                    "\n",
                    0,
                    match.start(),
                )
                + 1
            )

            result["success_markers"].append(
                {
                    "line": line,
                    "text": match.group(0),
                }
            )

    return result


def find_duplicate_function_names(
    modules: list[dict[str, Any]],
) -> dict[str, list[str]]:
    locations: defaultdict[
        str,
        list[str],
    ] = defaultdict(list)

    for module in modules:
        path = module["path"]

        for function in module["functions"]:
            locations[
                function["name"]
            ].append(
                f"{path}:{function['line']}"
            )

        for cls in module["classes"]:
            for method in cls["methods"]:
                locations[
                    method
                ].append(
                    f"{path}::{cls['name']}.{method}"
                )

    return {
        name: values
        for name, values in locations.items()
        if len(values) > 1
    }


def find_orchestrators(
    modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = []

    for module in modules:
        path_name = Path(
            module["path"]
        ).stem.lower()

        score = sum(
            1
            for word in ORCHESTRATOR_WORDS
            if word in path_name
        )

        class_names = [
            item["name"]
            for item in module["classes"]
        ]

        function_names = [
            item["name"]
            for item in module["functions"]
        ]

        has_run = any(
            name in {
                "run",
                "run_movie",
                "run_render",
                "main",
            }
            for name in function_names
        ) or any(
            "run" in cls["methods"]
            for cls in module["classes"]
        )

        if score or has_run:
            candidates.append(
                {
                    "path": module["path"],
                    "score": score,
                    "classes": class_names,
                    "domains": module["domains"],
                    "has_run": has_run,
                }
            )

    return sorted(
        candidates,
        key=lambda item: (
            item["score"],
            len(item["domains"]),
        ),
        reverse=True,
    )


def scan_state_files() -> list[dict[str, Any]]:
    workspace = ROOT / "workspace"

    if not workspace.exists():
        return []

    results = []

    for path in workspace.rglob("*.json"):
        name = path.name.lower()

        if not any(
            token in name
            for token in (
                "state",
                "report",
                "manifest",
                "timeline",
                "catalog",
                "assignment",
                "result",
            )
        ):
            continue

        try:
            size = path.stat().st_size
            modified = datetime.fromtimestamp(
                path.stat().st_mtime
            ).isoformat()
        except OSError:
            continue

        results.append(
            {
                "path": relative(path),
                "size": size,
                "modified": modified,
                "type": (
                    "state"
                    if "state" in name
                    else "report"
                    if "report" in name
                    else "timeline"
                    if "timeline" in name
                    else "manifest"
                    if "manifest" in name
                    else "catalog"
                    if "catalog" in name
                    else "artifact"
                ),
            }
        )

    return sorted(
        results,
        key=lambda item: item["modified"],
        reverse=True,
    )


def identify_tools_to_promote(
    modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = []

    for module in modules:
        path = module["path"]

        if not path.startswith("tools"):
            continue

        important_domains = [
            domain
            for domain in module["domains"]
            if domain in {
                "asset_analysis",
                "asset_assignment",
                "timeline",
                "render",
                "quality_control",
                "state_management",
            }
        ]

        if important_domains:
            candidates.append(
                {
                    "path": path,
                    "domains": important_domains,
                    "lines": module["lines"],
                    "reason": (
                        "Core production logic is "
                        "implemented as an external tool."
                    ),
                }
            )

    return candidates


def build_recommendations(
    modules: list[dict[str, Any]],
    duplicates: dict[str, list[str]],
    orchestrators: list[dict[str, Any]],
    state_files: list[dict[str, Any]],
    tools_to_promote: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations = []

    if len(orchestrators) > 1:
        recommendations.append(
            {
                "priority": "critical",
                "code": "ONE_ORCHESTRATOR",
                "title": "Keep one orchestration authority",
                "action": (
                    "Director Core must be the only module "
                    "allowed to advance production stages. "
                    "Other runtimes must become services."
                ),
            }
        )

    state_types = Counter(
        item["type"]
        for item in state_files
    )

    if len(state_files) > 5:
        recommendations.append(
            {
                "priority": "critical",
                "code": "SINGLE_SOURCE_OF_TRUTH",
                "title": "Create one canonical ProductionState",
                "action": (
                    "Store active asset revision, timeline revision, "
                    "render revision, QC result and release decision "
                    "in one transactional state object."
                ),
                "evidence": dict(state_types),
            }
        )

    if tools_to_promote:
        recommendations.append(
            {
                "priority": "critical",
                "code": "PROMOTE_TO_CORE",
                "title": "Move production logic out of tools",
                "action": (
                    "Convert Visual Intelligence, Assignment, "
                    "Temporal Guard, Release Gate and recovery "
                    "scripts into src/az_enterprise/core services."
                ),
                "count": len(tools_to_promote),
            }
        )

    if duplicates:
        recommendations.append(
            {
                "priority": "high",
                "code": "UNIFIED_SERVICE_INTERFACES",
                "title": "Consolidate duplicated service functions",
                "action": (
                    "Create unified AssetEngine, AssignmentEngine, "
                    "TimelineEngine, RenderEngine and QualityGate."
                ),
                "duplicate_names": len(duplicates),
            }
        )

    recommendations.extend(
        [
            {
                "priority": "critical",
                "code": "RELEASE_GATE",
                "title": "Block publication without verified release artifact",
                "action": (
                    "YouTube Publisher may accept only an artifact "
                    "whose technical, semantic, temporal, audio and "
                    "rights gates are passed."
                ),
            },
            {
                "priority": "high",
                "code": "RENDER_ATOMICITY",
                "title": "Make render output atomic",
                "action": (
                    "Write to a temporary output, verify with ffprobe, "
                    "then atomically rename to the final MP4. Never "
                    "publish RENDERED before verification."
                ),
            },
            {
                "priority": "high",
                "code": "PROJECT_CONFIG",
                "title": "Remove Franklin-specific constants",
                "action": (
                    "Move project id, expected duration, shot policy, "
                    "timeline count and media requirements into a "
                    "versioned project configuration."
                ),
            },
            {
                "priority": "high",
                "code": "ASSET_SUFFICIENCY_GATE",
                "title": "Evaluate library sufficiency before render",
                "action": (
                    "Estimate repetition, class coverage, video share "
                    "and semantic gaps before allowing release render."
                ),
            },
            {
                "priority": "medium",
                "code": "SUPERVISED_YOUTUBE",
                "title": "Use supervised YouTube publishing first",
                "action": (
                    "Upload automatically as private. Public release "
                    "requires Release Gate plus explicit approval "
                    "during the next two universal production tests."
                ),
            },
        ]
    )

    return recommendations


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# ATLAS ZERO — Autonomy Hardening RC2 Audit",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Python modules: {report['summary']['python_modules']}",
        f"- Orchestrator candidates: {report['summary']['orchestrators']}",
        f"- Duplicate function/method names: {report['summary']['duplicate_names']}",
        f"- State/report artifacts: {report['summary']['state_artifacts']}",
        f"- Franklin-specific modules: {report['summary']['franklin_specific_modules']}",
        f"- Core logic still in tools: {report['summary']['tools_to_promote']}",
        "",
        "## Orchestrator candidates",
        "",
    ]

    for item in report["orchestrators"]:
        lines.append(
            f"- `{item['path']}` — "
            f"classes={item['classes']}, "
            f"domains={item['domains']}"
        )

    lines.extend(
        [
            "",
            "## Modules with hardcoded project assumptions",
            "",
        ]
    )

    for item in report["hardcoded_modules"]:
        lines.append(
            f"- `{item['path']}` — {item['hardcoded']}"
        )

    lines.extend(
        [
            "",
            "## Core production logic in tools",
            "",
        ]
    )

    for item in report["tools_to_promote"]:
        lines.append(
            f"- `{item['path']}` — "
            f"{', '.join(item['domains'])}"
        )

    lines.extend(
        [
            "",
            "## Priority recommendations",
            "",
        ]
    )

    priority_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    recommendations = sorted(
        report["recommendations"],
        key=lambda item: priority_order.get(
            item["priority"],
            9,
        ),
    )

    for index, item in enumerate(
        recommendations,
        start=1,
    ):
        lines.extend(
            [
                f"### {index}. {item['title']}",
                "",
                f"Priority: **{item['priority']}**",
                "",
                item["action"],
                "",
            ]
        )

    REPORT_MD.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = iter_python_files()
    modules = [
        parse_python(path)
        for path in files
    ]

    duplicates = (
        find_duplicate_function_names(
            modules
        )
    )

    orchestrators = find_orchestrators(
        modules
    )

    state_files = scan_state_files()

    tools_to_promote = (
        identify_tools_to_promote(
            modules
        )
    )

    hardcoded_modules = [
        {
            "path": module["path"],
            "hardcoded": module["hardcoded"],
        }
        for module in modules
        if module["hardcoded"]
    ]

    recommendations = build_recommendations(
        modules,
        duplicates,
        orchestrators,
        state_files,
        tools_to_promote,
    )

    report = {
        "version": "2.0",
        "generated_at": (
            datetime.now().isoformat()
        ),
        "root": str(ROOT),
        "summary": {
            "python_modules": len(modules),
            "syntax_errors": sum(
                1
                for module in modules
                if module["syntax_error"]
            ),
            "orchestrators": len(
                orchestrators
            ),
            "duplicate_names": len(
                duplicates
            ),
            "state_artifacts": len(
                state_files
            ),
            "franklin_specific_modules": sum(
                1
                for module
                in hardcoded_modules
                if (
                    "franklin_literal"
                    in module["hardcoded"]
                    or
                    "fixed_workspace_path"
                    in module["hardcoded"]
                )
            ),
            "tools_to_promote": len(
                tools_to_promote
            ),
        },
        "orchestrators": orchestrators,
        "duplicate_functions": duplicates,
        "hardcoded_modules": (
            hardcoded_modules
        ),
        "tools_to_promote": (
            tools_to_promote
        ),
        "state_artifacts": (
            state_files
        ),
        "modules": modules,
        "recommendations": (
            recommendations
        ),
    }

    REPORT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    write_markdown(report)

    print("=" * 76)
    print("ATLAS ZERO — AUTONOMY HARDENING RC2 AUDIT")
    print("=" * 76)
    print(
        json.dumps(
            report["summary"],
            ensure_ascii=False,
            indent=2,
        )
    )
    print()
    print("TOP ORCHESTRATORS")

    for item in orchestrators[:12]:
        print(
            f"- {item['path']} | "
            f"domains={len(item['domains'])} | "
            f"classes={item['classes']}"
        )

    print()
    print("REPORT JSON =", REPORT_JSON)
    print("REPORT MD   =", REPORT_MD)
    print("=" * 76)


if __name__ == "__main__":
    main()
