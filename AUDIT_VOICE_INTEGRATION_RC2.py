from __future__ import annotations

import ast
import importlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_NAME = "ATLAS ZERO Voice Integration Audit"
KEY_MODULES = {
    "pipeline_runtime": "src/az_enterprise/core/pipeline_runtime.py",
    "production_director": "src/az_enterprise/core/production_director.py",
    "director_core_rc2": "src/az_enterprise/core/director_core_rc2.py",
    "narrative_writer_rc2": "src/az_enterprise/core/narrative_writer_rc2.py",
    "voice_production_engine_rc2": "src/az_enterprise/core/voice_production_engine_rc2.py",
    "audio_timeline_rc2": "src/az_enterprise/core/audio_timeline_rc2.py",
    "audio_renderer_rc2": "src/az_enterprise/core/audio_renderer_rc2.py",
    "audio_composer_rc2": "src/az_enterprise/core/audio_composer_rc2.py",
    "mux_engine_rc2": "src/az_enterprise/core/mux_engine_rc2.py",
    "render_engine_rc2": "src/az_enterprise/core/render_engine_rc2.py",
    "project_config_rc2": "src/az_enterprise/core/project_config_rc2.py",
}

TARGET_SYMBOLS = {
    "NarrativeWriterRC2",
    "VoiceProductionEngineRC2",
    "AudioTimelineBuilderRC2",
    "AudioTimelineValidatorRC2",
    "AudioRendererRC2",
    "NativeAudioComposerRC2",
    "MuxEngineRC2",
    "RenderEngineRC2",
    "PipelineRunManager",
    "ProductionDirector",
}

VOICE_TERMS = (
    "voice",
    "narrat",
    "audio",
    "speech",
    "tts",
    "mux",
    "duck",
    "loudness",
)

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "workspace",
    "audit_output",
    "atlas_zero_phase7_native_audio_composer",
    "atlas_zero_rc2_1_patch",
    "atlas_zero_rc2_2_patch",
    "atlas_zero_rc2_stage2_patch",
    "atlas_zero_rc2_final_audit",
    "atlas_zero_rc2_production_audit",
    "atlas_zero_rc2_finalization",
}


@dataclass
class ParseResult:
    path: str
    exists: bool
    syntax_ok: bool
    syntax_error: str | None
    imports: list[str]
    imported_symbols: list[str]
    classes: list[str]
    functions: list[str]
    calls: list[str]
    assignments: list[str]
    string_markers: list[str]


@dataclass
class ImportResult:
    module: str
    ok: bool
    error: str | None


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def is_excluded(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def call_name(node: ast.Call) -> str:
    name = dotted_name(node.func)
    return name or "<dynamic_call>"


def assignment_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return dotted_name(node)
    return None


def parse_python_file(root: Path, path: Path) -> ParseResult:
    relative = rel(root, path)
    if not path.exists():
        return ParseResult(
            path=relative,
            exists=False,
            syntax_ok=False,
            syntax_error="File not found",
            imports=[],
            imported_symbols=[],
            classes=[],
            functions=[],
            calls=[],
            assignments=[],
            string_markers=[],
        )

    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return ParseResult(
            path=relative,
            exists=True,
            syntax_ok=False,
            syntax_error=f"{type(exc).__name__}: {exc}",
            imports=[],
            imported_symbols=[],
            classes=[],
            functions=[],
            calls=[],
            assignments=[],
            string_markers=[],
        )

    imports: set[str] = set()
    imported_symbols: set[str] = set()
    classes: set[str] = set()
    functions: set[str] = set()
    calls: set[str] = set()
    assignments: set[str] = set()
    markers: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.add(module)
            for alias in node.names:
                imported_symbols.add(alias.name)
        elif isinstance(node, ast.ClassDef):
            classes.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        elif isinstance(node, ast.Call):
            calls.add(call_name(node))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                name = assignment_name(target)
                if name:
                    assignments.add(name)
        elif isinstance(node, ast.AnnAssign):
            name = assignment_name(node.target)
            if name:
                assignments.add(name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            low = value.lower()
            if value and any(term in low for term in VOICE_TERMS):
                markers.add(value[:240])

    return ParseResult(
        path=relative,
        exists=True,
        syntax_ok=True,
        syntax_error=None,
        imports=sorted(imports),
        imported_symbols=sorted(imported_symbols),
        classes=sorted(classes),
        functions=sorted(functions),
        calls=sorted(calls),
        assignments=sorted(assignments),
        string_markers=sorted(markers),
    )


def find_symbol_references(root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for path in root.rglob("*.py"):
        if is_excluded(path, root):
            continue

        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="latin-1")
            except OSError:
                continue
        except OSError:
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            matched = sorted(symbol for symbol in TARGET_SYMBOLS if symbol in line)
            if matched:
                results.append(
                    {
                        "path": rel(root, path),
                        "line_number": line_number,
                        "symbols": matched,
                        "text": line.strip()[:320],
                    }
                )

    return results


def module_name_from_path(path: str) -> str:
    return path.removeprefix("src/").removesuffix(".py").replace("/", ".")


def import_check(root: Path) -> list[ImportResult]:
    src = root / "src"
    sys.path.insert(0, str(src))

    results: list[ImportResult] = []
    seen: set[str] = set()

    for path in KEY_MODULES.values():
        module = module_name_from_path(path)
        if module in seen:
            continue
        seen.add(module)

        try:
            importlib.import_module(module)
        except Exception as exc:  # audit must record all import failures
            results.append(
                ImportResult(
                    module=module,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        else:
            results.append(ImportResult(module=module, ok=True, error=None))

    return results


def find_edges(
    parsed: dict[str, ParseResult],
    references: list[dict[str, Any]],
) -> list[dict[str, str]]:
    edges: set[tuple[str, str, str]] = set()

    symbol_to_module = {
        "NarrativeWriterRC2": "narrative_writer_rc2",
        "VoiceProductionEngineRC2": "voice_production_engine_rc2",
        "AudioTimelineBuilderRC2": "audio_timeline_rc2",
        "AudioTimelineValidatorRC2": "audio_timeline_rc2",
        "AudioRendererRC2": "audio_renderer_rc2",
        "NativeAudioComposerRC2": "audio_composer_rc2",
        "MuxEngineRC2": "mux_engine_rc2",
        "RenderEngineRC2": "render_engine_rc2",
        "PipelineRunManager": "pipeline_runtime",
        "ProductionDirector": "production_director",
    }

    path_to_key = {value: key for key, value in KEY_MODULES.items()}

    for source_key, result in parsed.items():
        for imported in result.imported_symbols:
            target_key = symbol_to_module.get(imported)
            if target_key:
                edges.add((source_key, target_key, f"imports {imported}"))

        for imported_module in result.imports:
            for target_key in KEY_MODULES:
                if imported_module.endswith(target_key):
                    edges.add((source_key, target_key, f"imports {imported_module}"))

        for call in result.calls:
            base = call.split(".")[-1]
            target_key = symbol_to_module.get(base)
            if target_key:
                edges.add((source_key, target_key, f"calls {call}"))

    for ref in references:
        source_key = path_to_key.get(ref["path"])
        if not source_key:
            continue
        for symbol in ref["symbols"]:
            target_key = symbol_to_module.get(symbol)
            if target_key and target_key != source_key:
                edges.add((source_key, target_key, f"references {symbol}"))

    return [
        {"source": source, "target": target, "evidence": evidence}
        for source, target, evidence in sorted(edges)
    ]


def evaluate_chain(
    parsed: dict[str, ParseResult],
    imports: list[ImportResult],
    edges: list[dict[str, str]],
) -> dict[str, Any]:
    edge_pairs = {(edge["source"], edge["target"]) for edge in edges}
    import_map = {item.module: item.ok for item in imports}

    def module_import_ok(key: str) -> bool:
        module = module_name_from_path(KEY_MODULES[key])
        return import_map.get(module, False)

    stages = [
        {
            "stage": "narrative",
            "module": "narrative_writer_rc2",
            "present": parsed["narrative_writer_rc2"].exists,
            "syntax_ok": parsed["narrative_writer_rc2"].syntax_ok,
            "import_ok": module_import_ok("narrative_writer_rc2"),
        },
        {
            "stage": "voice_generation",
            "module": "voice_production_engine_rc2",
            "present": parsed["voice_production_engine_rc2"].exists,
            "syntax_ok": parsed["voice_production_engine_rc2"].syntax_ok,
            "import_ok": module_import_ok("voice_production_engine_rc2"),
        },
        {
            "stage": "audio_timeline",
            "module": "audio_timeline_rc2",
            "present": parsed["audio_timeline_rc2"].exists,
            "syntax_ok": parsed["audio_timeline_rc2"].syntax_ok,
            "import_ok": module_import_ok("audio_timeline_rc2"),
        },
        {
            "stage": "audio_render",
            "module": "audio_renderer_rc2",
            "present": parsed["audio_renderer_rc2"].exists,
            "syntax_ok": parsed["audio_renderer_rc2"].syntax_ok,
            "import_ok": module_import_ok("audio_renderer_rc2"),
        },
        {
            "stage": "audio_compose",
            "module": "audio_composer_rc2",
            "present": parsed["audio_composer_rc2"].exists,
            "syntax_ok": parsed["audio_composer_rc2"].syntax_ok,
            "import_ok": module_import_ok("audio_composer_rc2"),
        },
        {
            "stage": "mux",
            "module": "mux_engine_rc2",
            "present": parsed["mux_engine_rc2"].exists,
            "syntax_ok": parsed["mux_engine_rc2"].syntax_ok,
            "import_ok": module_import_ok("mux_engine_rc2"),
        },
        {
            "stage": "final_render",
            "module": "render_engine_rc2",
            "present": parsed["render_engine_rc2"].exists,
            "syntax_ok": parsed["render_engine_rc2"].syntax_ok,
            "import_ok": module_import_ok("render_engine_rc2"),
        },
    ]

    expected_links = [
        ("pipeline_runtime", "narrative_writer_rc2"),
        ("pipeline_runtime", "voice_production_engine_rc2"),
        ("production_director", "narrative_writer_rc2"),
        ("production_director", "voice_production_engine_rc2"),
        ("voice_production_engine_rc2", "audio_timeline_rc2"),
        ("audio_composer_rc2", "audio_renderer_rc2"),
        ("audio_composer_rc2", "audio_timeline_rc2"),
        ("audio_composer_rc2", "mux_engine_rc2"),
        ("render_engine_rc2", "audio_composer_rc2"),
        ("render_engine_rc2", "mux_engine_rc2"),
    ]

    link_results = [
        {
            "source": source,
            "target": target,
            "detected": (source, target) in edge_pairs,
        }
        for source, target in expected_links
    ]

    active_entry_links = [
        item
        for item in link_results
        if item["source"] in {"pipeline_runtime", "production_director", "director_core_rc2"}
        and item["detected"]
    ]

    downstream_links = [
        item
        for item in link_results
        if item["source"]
        in {
            "voice_production_engine_rc2",
            "audio_composer_rc2",
            "render_engine_rc2",
        }
        and item["detected"]
    ]

    all_stage_modules_healthy = all(
        stage["present"] and stage["syntax_ok"] and stage["import_ok"]
        for stage in stages
    )

    if all_stage_modules_healthy and active_entry_links and downstream_links:
        status = "INTEGRATION_PRESENT_REQUIRES_RUNTIME_PROOF"
    elif all_stage_modules_healthy and downstream_links:
        status = "COMPONENTS_HEALTHY_ENTRY_CHAIN_NOT_PROVEN"
    elif all_stage_modules_healthy:
        status = "COMPONENTS_HEALTHY_INTEGRATION_NOT_PROVEN"
    else:
        status = "COMPONENT_OR_IMPORT_FAILURE"

    return {
        "status": status,
        "stages": stages,
        "expected_links": link_results,
        "detected_active_entry_links": len(active_entry_links),
        "detected_downstream_links": len(downstream_links),
        "all_stage_modules_healthy": all_stage_modules_healthy,
        "runtime_execution_proven": False,
        "note": (
            "This audit performs static analysis and import checks. "
            "It does not synthesize speech or render a final movie."
        ),
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines: list[str] = []

    lines.append("# ATLAS ZERO - Voice Integration Audit")
    lines.append("")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"- Status: {report['evaluation']['status']}")
    lines.append(
        f"- Active entry links detected: "
        f"{report['evaluation']['detected_active_entry_links']}"
    )
    lines.append(
        f"- Downstream links detected: "
        f"{report['evaluation']['detected_downstream_links']}"
    )
    lines.append(
        f"- All stage modules healthy: "
        f"{report['evaluation']['all_stage_modules_healthy']}"
    )
    lines.append("- Runtime execution proven: False")
    lines.append("")
    lines.append("## Key module health")
    lines.append("")

    for key, item in report["key_modules"].items():
        lines.append(
            f"- {key}: exists={item['exists']}, "
            f"syntax_ok={item['syntax_ok']}, "
            f"classes={len(item['classes'])}, "
            f"functions={len(item['functions'])}, "
            f"calls={len(item['calls'])}"
        )
        if item["syntax_error"]:
            lines.append(f"  - error: {item['syntax_error']}")

    lines.append("")
    lines.append("## Import checks")
    lines.append("")

    for item in report["import_checks"]:
        lines.append(
            f"- {item['module']}: "
            f"{'OK' if item['ok'] else 'FAIL'}"
        )
        if item["error"]:
            lines.append(f"  - {item['error']}")

    lines.append("")
    lines.append("## Detected integration edges")
    lines.append("")

    if report["edges"]:
        for edge in report["edges"]:
            lines.append(
                f"- {edge['source']} -> {edge['target']} "
                f"| {edge['evidence']}"
            )
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Expected links")
    lines.append("")

    for item in report["evaluation"]["expected_links"]:
        lines.append(
            f"- {item['source']} -> {item['target']}: "
            f"{'DETECTED' if item['detected'] else 'NOT DETECTED'}"
        )

    lines.append("")
    lines.append("## External symbol references")
    lines.append("")

    if report["symbol_references"]:
        for item in report["symbol_references"]:
            symbols = ", ".join(item["symbols"])
            lines.append(
                f"- {item['path']}:{item['line_number']} "
                f"| {symbols} | {item['text']}"
            )
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Interpretation rule")
    lines.append("")
    lines.append(
        "- Static imports and references prove architectural presence only."
    )
    lines.append(
        "- A separate controlled runtime smoke test is required to prove the "
        "full narrator-to-final-mux execution path."
    )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    root = Path.cwd().resolve()
    output_dir = root / "workspace" / "audits" / "voice_integration"
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed: dict[str, ParseResult] = {}
    for key, relative_path in KEY_MODULES.items():
        parsed[key] = parse_python_file(root, root / relative_path)

    references = find_symbol_references(root)
    import_results = import_check(root)
    edges = find_edges(parsed, references)
    evaluation = evaluate_chain(parsed, import_results, edges)

    report = {
        "audit_name": AUDIT_NAME,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "repository_root": str(root),
        "key_modules": {
            key: asdict(value) for key, value in parsed.items()
        },
        "import_checks": [asdict(item) for item in import_results],
        "edges": edges,
        "symbol_references": references,
        "evaluation": evaluation,
    }

    json_path = output_dir / "voice_integration_audit.json"
    markdown_path = output_dir / "voice_integration_audit.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(markdown_path, report)

    print("")
    print("ATLAS ZERO - VOICE INTEGRATION AUDIT")
    print("=" * 72)
    print(f"Repository:                  {root}")
    print(f"Status:                      {evaluation['status']}")
    print(
        "Healthy stage modules:       "
        f"{evaluation['all_stage_modules_healthy']}"
    )
    print(
        "Active entry links detected: "
        f"{evaluation['detected_active_entry_links']}"
    )
    print(
        "Downstream links detected:   "
        f"{evaluation['detected_downstream_links']}"
    )
    print("Runtime execution proven:    False")
    print("")
    print(f"JSON: {json_path}")
    print(f"MD:   {markdown_path}")

    failed_imports = [item for item in import_results if not item.ok]
    syntax_failures = [
        item for item in parsed.values() if not item.syntax_ok
    ]

    return 1 if failed_imports or syntax_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
