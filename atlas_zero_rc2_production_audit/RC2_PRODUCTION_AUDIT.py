from __future__ import annotations

import ast
import importlib
import inspect
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


AUDIT_VERSION = "1.0.0"

RC2_MODULES = [
    "az_enterprise.core.control_layer_rc2",
    "az_enterprise.core.project_config_rc2",
    "az_enterprise.core.render_engine_rc2",
    "az_enterprise.core.timeline_engine_rc2",
    "az_enterprise.core.visual_renderer_rc2",
    "az_enterprise.core.camera_motion_rc2",
    "az_enterprise.core.transition_engine_rc2",
    "az_enterprise.core.audio_timeline_rc2",
    "az_enterprise.core.ducking_engine_rc2",
    "az_enterprise.core.loudness_engine_rc2",
    "az_enterprise.core.audio_renderer_rc2",
    "az_enterprise.core.mux_engine_rc2",
    "az_enterprise.core.audio_composer_rc2",
]

RC2_TEST_CANDIDATES = [
    "tests/test_transition_engine_rc2.py",
    "tests/test_audio_phase7_rc2.py",
    "tests/test_control_layer_rc2.py",
    "tests/test_render_engine_rc2.py",
    "tests/test_timeline_engine_rc2.py",
]

ARTIFACT_RULES = {
    "story": [
        "**/story_strategy_result.json",
        "**/story*.json",
        "**/script*.json",
    ],
    "timeline": [
        "**/rc2/timeline/timeline.json",
        "**/timeline.json",
        "**/native_timeline_model.json",
    ],
    "voice": [
        "**/voice_master.wav",
        "**/voice_master.m4a",
        "**/*narration*.wav",
    ],
    "render": [
        "**/rc2/render/*.mp4",
        "**/final_movie.mp4",
        "**/*_RC2.mp4",
    ],
    "quality": [
        "**/rc2/quality_report.json",
        "**/quality_report.json",
    ],
    "state": [
        "**/rc2/production_state.json",
        "**/production_state.json",
    ],
    "package": [
        "**/FINAL_ASSEMBLY_PACK/index.html",
        "**/package_manifest.json",
        "**/release_center.html",
    ],
}

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "workspace/backups",
    "atlas_zero_rc2_production_audit",
}

LEGACY_DIR_HINTS = {
    "atlas_zero_rc2_1_patch",
    "atlas_zero_rc2_2_patch",
    "atlas_zero_rc2_stage2_patch",
    "atlas_zero_phase8_rc2_control_layer",
    "atlas_zero_phase9_production_cleanup",
    "atlas_zero_rc2_final_audit",
    "audit_rc2_production",
    "tests/legacy_rc1",
    "tools/legacy_rc1",
}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    duration_sec: float = 0.0
    data: dict[str, Any] | None = None


def find_repo_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_excluded(path: Path, root: Path) -> bool:
    rp = rel(path, root)
    return any(rp == item or rp.startswith(item + "/") for item in EXCLUDED_PARTS)


def active_python_files(root: Path) -> Iterable[Path]:
    active_roots = [
        root / "src" / "az_enterprise",
        root / "tests",
        root / "tools",
    ]
    for scan_root in active_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*.py"):
            if is_excluded(path, root):
                continue
            rp = rel(path, root)
            if any(rp == hint or rp.startswith(hint + "/") for hint in LEGACY_DIR_HINTS):
                continue
            yield path


def architecture_audit(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    checks: list[Check] = []

    env = os.environ.copy()
    src = str(root / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    imported = {}
    for module_name in RC2_MODULES:
        t0 = time.perf_counter()
        process = subprocess.run(
            [sys.executable, "-c", f"import {module_name}; print('OK')"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        ok = process.returncode == 0
        imported[module_name] = {
            "passed": ok,
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
        }
        checks.append(Check(
            name=f"import:{module_name}",
            passed=ok,
            detail="Imported successfully" if ok else process.stderr.strip()[-1200:],
            duration_sec=round(time.perf_counter() - t0, 3),
        ))

    # Compile all active production Python files.
    compile_errors = []
    for path in active_python_files(root):
        process = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            compile_errors.append({
                "file": rel(path, root),
                "error": process.stderr.strip() or process.stdout.strip(),
            })
    checks.append(Check(
        name="active_python_compile",
        passed=not compile_errors,
        detail=f"{len(compile_errors)} compile errors",
        data={"errors": compile_errors[:100]},
    ))

    # Validate presence of principal RC2 classes without instantiating unknown constructors.
    class_expectations = {
        "az_enterprise.core.control_layer_rc2": ["RC2ControlLayer", "RC2ReadinessPlanner"],
        "az_enterprise.core.render_engine_rc2": ["RenderEngineRC2"],
        "az_enterprise.core.timeline_engine_rc2": ["TimelineEngineRC2"],
    }
    class_results = {}
    sys.path.insert(0, str(root / "src"))
    try:
        for module_name, names in class_expectations.items():
            try:
                module = importlib.import_module(module_name)
                present = {name: hasattr(module, name) for name in names}
                class_results[module_name] = present
                checks.append(Check(
                    name=f"classes:{module_name}",
                    passed=all(present.values()),
                    detail=json.dumps(present, ensure_ascii=False),
                ))
            except Exception as exc:
                class_results[module_name] = {"error": repr(exc)}
                checks.append(Check(
                    name=f"classes:{module_name}",
                    passed=False,
                    detail=repr(exc),
                ))
    finally:
        try:
            sys.path.remove(str(root / "src"))
        except ValueError:
            pass

    passed = all(c.passed for c in checks)
    return {
        "passed": passed,
        "duration_sec": round(time.perf_counter() - started, 3),
        "checks": [asdict(c) for c in checks],
        "imported_modules": imported,
        "class_presence": class_results,
    }


def runtime_audit(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    env = os.environ.copy()
    src = str(root / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    existing_tests = [p for p in RC2_TEST_CANDIDATES if (root / p).exists()]
    result: dict[str, Any] = {
        "selected_tests": existing_tests,
        "pytest": None,
        "smoke": None,
    }

    smoke_code = (
        "from az_enterprise.core.control_layer_rc2 import RC2ControlLayer, RC2ReadinessPlanner;"
        "from az_enterprise.core.render_engine_rc2 import RenderEngineRC2;"
        "from az_enterprise.core.timeline_engine_rc2 import TimelineEngineRC2;"
        "from az_enterprise.core.visual_renderer_rc2 import VisualRendererRC2;"
        "from az_enterprise.core.audio_composer_rc2 import NativeAudioComposerRC2;"
        "print('RC2_RUNTIME_SMOKE_OK')"
    )
    smoke = subprocess.run(
        [sys.executable, "-c", smoke_code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    result["smoke"] = {
        "passed": smoke.returncode == 0,
        "returncode": smoke.returncode,
        "stdout": smoke.stdout.strip(),
        "stderr": smoke.stderr.strip(),
    }

    if existing_tests:
        test_process = subprocess.run(
            [sys.executable, "-m", "pytest", *existing_tests, "-q"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        result["pytest"] = {
            "passed": test_process.returncode == 0,
            "returncode": test_process.returncode,
            "stdout": test_process.stdout.strip(),
            "stderr": test_process.stderr.strip(),
        }
    else:
        result["pytest"] = {
            "passed": False,
            "skipped": True,
            "reason": "No known RC2 tests found",
        }

    result["passed"] = bool(
        result["smoke"]["passed"]
        and result["pytest"].get("passed")
    )
    result["duration_sec"] = round(time.perf_counter() - started, 3)
    return result


def artifact_audit(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    search_roots = [
        root / "workspace" / "exports",
        root / "workspace" / "projects",
    ]
    categories = {}
    for category, patterns in ARTIFACT_RULES.items():
        found = []
        for search_root in search_roots:
            if not search_root.exists():
                continue
            for pattern in patterns:
                for path in search_root.glob(pattern):
                    if path.is_file():
                        try:
                            size = path.stat().st_size
                        except OSError:
                            size = 0
                        found.append({
                            "file": rel(path, root),
                            "size_bytes": size,
                            "non_empty": size > 0,
                        })
        # deduplicate
        unique = {item["file"]: item for item in found}
        items = sorted(unique.values(), key=lambda x: x["file"])
        categories[category] = {
            "passed": any(item["non_empty"] for item in items),
            "files": items[:100],
        }

    required = ["timeline", "render", "quality", "state"]
    passed = all(categories[name]["passed"] for name in required)
    final_movies = categories["render"]["files"]
    return {
        "passed": passed,
        "duration_sec": round(time.perf_counter() - started, 3),
        "required_categories": required,
        "categories": categories,
        "final_movie_candidates": final_movies,
    }


def rc1_removal_simulation(root: Path) -> dict[str, Any]:
    started = time.perf_counter()

    rc1_files = []
    for path in root.rglob("*"):
        if not path.is_file() or is_excluded(path, root):
            continue
        if "rc1" in path.name.lower():
            rc1_files.append(path)

    rc1_modules = set()
    for path in rc1_files:
        if path.suffix == ".py":
            try:
                rp = path.relative_to(root / "src").with_suffix("")
            except ValueError:
                continue
            rc1_modules.add(".".join(rp.parts))

    critical_dependencies = []
    compatibility_references = []
    historical_references = []

    for path in active_python_files(root):
        rp = rel(path, root)
        try:
            source = path.read_text(encoding="utf-8-sig", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except Exception as exc:
            critical_dependencies.append({
                "file": rp,
                "line": 0,
                "type": "parse_error",
                "detail": str(exc),
            })
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "rc1" in alias.name.lower() or alias.name in rc1_modules:
                        critical_dependencies.append({
                            "file": rp,
                            "line": node.lineno,
                            "type": "import",
                            "detail": alias.name,
                        })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [a.name for a in node.names]
                if "rc1" in module.lower() or any("rc1" in n.lower() for n in names):
                    critical_dependencies.append({
                        "file": rp,
                        "line": node.lineno,
                        "type": "import_from",
                        "detail": f"from {module} import {', '.join(names)}",
                    })
            elif isinstance(node, ast.Call):
                try:
                    called = ast.unparse(node.func)
                except Exception:
                    called = ""
                if "evaluate_rc1" in called.lower():
                    critical_dependencies.append({
                        "file": rp,
                        "line": getattr(node, "lineno", 0),
                        "type": "runtime_call",
                        "detail": called,
                    })

        for line_no, line in enumerate(source.splitlines(), start=1):
            low = line.lower()
            if "legacy_" in low and ("rc1" in low or "render" in low or "timeline" in low or "audio" in low):
                compatibility_references.append({
                    "file": rp,
                    "line": line_no,
                    "detail": line.strip()[:500],
                })
            elif "rc1" in low:
                # Names and output labels are historical unless used as active import/call.
                historical_references.append({
                    "file": rp,
                    "line": line_no,
                    "detail": line.strip()[:500],
                })

    # Deduplicate critical findings.
    dedup = {}
    for item in critical_dependencies:
        key = (item["file"], item["line"], item["type"], item["detail"])
        dedup[key] = item
    critical_dependencies = list(dedup.values())

    safe = len(critical_dependencies) == 0
    return {
        "passed": safe,
        "safe_to_delete_rc1": safe,
        "duration_sec": round(time.perf_counter() - started, 3),
        "rc1_named_files": sorted(rel(p, root) for p in rc1_files)[:500],
        "critical_dependencies": sorted(
            critical_dependencies,
            key=lambda x: (x["file"], x["line"], x["type"]),
        ),
        "compatibility_references": compatibility_references[:500],
        "historical_references_count": len(historical_references),
        "decision": (
            "SAFE_TO_REMOVE_RC1"
            if safe
            else "NOT_SAFE_TO_REMOVE_RC1"
        ),
    }


def calculate_score(architecture: dict, runtime: dict, artifacts: dict, removal: dict) -> tuple[int, str]:
    score = 0
    score += 25 if architecture["passed"] else 0
    score += 35 if runtime["passed"] else 0
    score += 25 if artifacts["passed"] else 0
    score += 15 if removal["passed"] else 0

    if score == 100:
        status = "RC2_PRODUCTION_READY"
    elif score >= 75:
        status = "RC2_READY_WITH_LIMITATIONS"
    elif score >= 50:
        status = "RC2_PARTIALLY_OPERATIONAL"
    else:
        status = "RC2_NOT_PRODUCTION_READY"
    return score, status


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    architecture = payload["architecture"]
    runtime = payload["runtime"]
    artifacts = payload["artifacts"]
    removal = payload["rc1_removal"]

    lines = [
        "# ATLAS ZERO RC2 Production Audit",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Audit version: `{payload['audit_version']}`",
        f"- Repository: `{payload['repository']}`",
        f"- Score: **{payload['score']}/100**",
        f"- Status: **{payload['status']}**",
        "",
        "## Four production questions",
        "",
        f"1. Architecture loads: **{'YES' if architecture['passed'] else 'NO'}**",
        f"2. RC2 runtime passes: **{'YES' if runtime['passed'] else 'NO'}**",
        f"3. Final movie or equivalent artifacts exist: **{'YES' if artifacts['passed'] else 'NO'}**",
        f"4. RC1 can be removed safely: **{'YES' if removal['safe_to_delete_rc1'] else 'NO'}**",
        "",
        "## Architecture",
        "",
    ]

    for check in architecture["checks"]:
        lines.append(
            f"- {'✅' if check['passed'] else '❌'} `{check['name']}` — {check['detail']}"
        )

    lines += [
        "",
        "## Runtime",
        "",
        f"- Import/runtime smoke: **{'PASS' if runtime['smoke']['passed'] else 'FAIL'}**",
        f"- RC2 tests: **{'PASS' if runtime['pytest'].get('passed') else 'FAIL'}**",
        "",
        "```text",
        runtime["pytest"].get("stdout", "")[-5000:],
        runtime["pytest"].get("stderr", "")[-3000:],
        "```",
        "",
        "## Artifacts",
        "",
    ]

    for category, info in artifacts["categories"].items():
        lines.append(f"- {'✅' if info['passed'] else '❌'} **{category}**")
        for item in info["files"][:10]:
            lines.append(f"  - `{item['file']}` — {item['size_bytes']} bytes")

    lines += [
        "",
        "## RC1 removal simulation",
        "",
        f"- Decision: **{removal['decision']}**",
        f"- Critical dependencies: **{len(removal['critical_dependencies'])}**",
        f"- Compatibility references: **{len(removal['compatibility_references'])}**",
        "",
    ]

    if removal["critical_dependencies"]:
        lines.append("| File | Line | Type | Dependency |")
        lines.append("|---|---:|---|---|")
        for item in removal["critical_dependencies"][:200]:
            detail = item["detail"].replace("|", "\\|")
            lines.append(
                f"| `{item['file']}` | {item['line']} | {item['type']} | `{detail}` |"
            )
    else:
        lines.append("No active RC1 import or runtime-call dependency was detected.")

    lines += [
        "",
        "## Interpretation",
        "",
        "- A `YES` for RC1 removal means no active RC1 import or explicit RC1 runtime call was detected.",
        "- Compatibility paths may still exist for old projects and should be archived or migrated before physical deletion.",
        "- This audit does not delete, rename, or modify any repository file.",
        "",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = find_repo_root()
    output = root / "workspace" / "audits" / "rc2_production"
    output.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("ATLAS ZERO — RC2 PRODUCTION AUDIT")
    print("=" * 76)
    print("Repository:", root)

    print("\n[1/4] Architecture audit...")
    architecture = architecture_audit(root)

    print("[2/4] Runtime audit...")
    runtime = runtime_audit(root)

    print("[3/4] Artifact audit...")
    artifacts = artifact_audit(root)

    print("[4/4] RC1 removal simulation...")
    removal = rc1_removal_simulation(root)

    score, status = calculate_score(architecture, runtime, artifacts, removal)
    payload = {
        "schema": "atlas_zero.rc2_production_audit.v1",
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(root),
        "score": score,
        "status": status,
        "answers": {
            "architecture_loads": architecture["passed"],
            "runtime_passes": runtime["passed"],
            "final_artifacts_exist": artifacts["passed"],
            "safe_to_remove_rc1": removal["safe_to_delete_rc1"],
        },
        "architecture": architecture,
        "runtime": runtime,
        "artifacts": artifacts,
        "rc1_removal": removal,
    }

    json_path = output / "rc2_production_audit.json"
    md_path = output / "rc2_production_audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, payload)

    print("\n" + "=" * 76)
    print("RESULT")
    print("=" * 76)
    print(f"Architecture loads:        {'YES' if architecture['passed'] else 'NO'}")
    print(f"RC2 runtime passes:        {'YES' if runtime['passed'] else 'NO'}")
    print(f"Final artifacts exist:     {'YES' if artifacts['passed'] else 'NO'}")
    print(f"Safe to remove RC1:        {'YES' if removal['safe_to_delete_rc1'] else 'NO'}")
    print(f"Score:                     {score}/100")
    print(f"Status:                    {status}")
    print(f"JSON:                      {json_path}")
    print(f"Report:                    {md_path}")

    raise SystemExit(0 if score == 100 else 2)


if __name__ == "__main__":
    main()
