from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


RC1_PATTERNS = [
    re.compile(r"\brc1\b", re.IGNORECASE),
    re.compile(r"_rc1\b", re.IGNORECASE),
    re.compile(r"\bRC1\b"),
]

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "workspace/backups", "dist", "build", "node_modules",
}

TEXT_SUFFIXES = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".md", ".txt", ".ps1", ".bat", ".sh",
}


@dataclass
class Finding:
    severity: str
    category: str
    file: str
    line: int
    text: str


def repo_root() -> Path:
    here = Path.cwd().resolve()
    candidates = [here, *here.parents]
    for candidate in candidates:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


def excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(rel == item or rel.startswith(item + "/") for item in EXCLUDED_DIRS)


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or excluded(path, root):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def scan_text(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(lines, start=1):
            if any(pattern.search(line) for pattern in RC1_PATTERNS):
                category = "rc1_reference"
                severity = "high" if path.suffix == ".py" else "medium"
                findings.append(Finding(severity, category, rel, number, line.strip()[:500]))
    return findings


def scan_python_ast(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in root.rglob("*.py"):
        if excluded(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as exc:
            findings.append(Finding("high", "python_parse_error", rel, getattr(exc, "lineno", 0) or 0, str(exc)))
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "rc1" in alias.name.lower():
                        findings.append(Finding("critical", "rc1_import", rel, node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported = ", ".join(alias.name for alias in node.names)
                if "rc1" in module.lower() or "rc1" in imported.lower():
                    findings.append(Finding("critical", "rc1_import", rel, node.lineno, f"from {module} import {imported}"))
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    try:
                        name = ast.unparse(base)
                    except Exception:
                        name = ""
                    if "rc1" in name.lower():
                        findings.append(Finding("critical", "rc1_inheritance", rel, node.lineno, f"{node.name}({name})"))
    return findings


def required_rc2_modules(root: Path) -> dict[str, bool]:
    core = root / "src" / "az_enterprise" / "core"
    names = [
        "render_engine_rc2.py",
        "visual_renderer_rc2.py",
        "camera_motion_rc2.py",
        "transition_engine_rc2.py",
        "audio_timeline_rc2.py",
        "ducking_engine_rc2.py",
        "loudness_engine_rc2.py",
        "audio_renderer_rc2.py",
        "mux_engine_rc2.py",
        "audio_composer_rc2.py",
    ]
    return {name: (core / name).exists() for name in names}


def run_import_smoke(root: Path) -> dict:
    env = os.environ.copy()
    src = str(root / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    code = (
        "from az_enterprise.core.camera_motion_rc2 import CameraMotionEngine;"
        "from az_enterprise.core.transition_engine_rc2 import TransitionEngineRC2;"
        "from az_enterprise.core.visual_renderer_rc2 import VisualRendererRC2;"
        "from az_enterprise.core.audio_composer_rc2 import NativeAudioComposerRC2;"
        "from az_enterprise.core.render_engine_rc2 import RenderEngineRC2;"
        "print('RC2_IMPORT_SMOKE_OK')"
    )
    process = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "passed": process.returncode == 0,
        "returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
    }


def run_phase_tests(root: Path) -> dict:
    candidates = [
        root / "tests" / "test_transition_engine_rc2.py",
        root / "tests" / "test_audio_phase7_rc2.py",
    ]
    existing = [str(p.relative_to(root)) for p in candidates if p.exists()]
    if not existing:
        return {"passed": False, "skipped": True, "reason": "Phase 6/7 tests were not found"}

    process = subprocess.run(
        [sys.executable, "-m", "pytest", *existing, "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "passed": process.returncode == 0,
        "skipped": False,
        "returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
        "tests": existing,
    }


def score_report(findings: list[Finding], modules: dict[str, bool], smoke: dict, tests: dict) -> tuple[int, str]:
    score = 100
    score -= sum(20 for f in findings if f.severity == "critical")
    score -= sum(8 for f in findings if f.severity == "high")
    score -= sum(2 for f in findings if f.severity == "medium")
    score -= 10 * sum(1 for exists in modules.values() if not exists)
    if not smoke.get("passed"):
        score -= 25
    if not tests.get("passed"):
        score -= 15
    score = max(0, min(100, score))
    if score >= 95:
        status = "READY_FOR_HOGUERAS"
    elif score >= 80:
        status = "READY_WITH_WARNINGS"
    elif score >= 60:
        status = "NOT_READY_REQUIRES_FIXES"
    else:
        status = "BLOCKED"
    return score, status


def write_markdown(path: Path, payload: dict) -> None:
    findings = payload["findings"]
    lines = [
        "# ATLAS ZERO RC2 Readiness Report",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Repository: `{payload['repository']}`",
        f"- Score: **{payload['score']}/100**",
        f"- Status: **{payload['status']}**",
        "",
        "## Core RC2 modules",
        "",
    ]
    for name, exists in payload["required_modules"].items():
        lines.append(f"- {'✅' if exists else '❌'} `{name}`")
    lines += [
        "",
        "## Import smoke test",
        "",
        f"- Passed: **{payload['import_smoke']['passed']}**",
        f"- Output: `{payload['import_smoke'].get('stdout', '')}`",
        "",
        "## Phase tests",
        "",
        f"- Passed: **{payload['phase_tests'].get('passed')}**",
        f"- Output: `{payload['phase_tests'].get('stdout', '')}`",
        "",
        "## RC1 findings",
        "",
        f"Total findings: **{len(findings)}**",
        "",
    ]
    if not findings:
        lines.append("No RC1 references were detected in scanned project files.")
    else:
        lines.append("| Severity | Category | File | Line | Text |")
        lines.append("|---|---|---|---:|---|")
        for item in findings[:300]:
            text = item["text"].replace("|", "\\|")
            lines.append(
                f"| {item['severity']} | {item['category']} | `{item['file']}` | "
                f"{item['line']} | `{text}` |"
            )
        if len(findings) > 300:
            lines.append("")
            lines.append(f"Only first 300 of {len(findings)} findings are shown.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = repo_root()
    output = root / "workspace" / "audits" / "rc2_final"
    output.mkdir(parents=True, exist_ok=True)

    findings = scan_python_ast(root)
    seen = {(f.category, f.file, f.line, f.text) for f in findings}
    for finding in scan_text(root):
        key = (finding.category, finding.file, finding.line, finding.text)
        if key not in seen:
            findings.append(finding)
            seen.add(key)

    findings.sort(key=lambda f: (
        {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f.severity, 9),
        f.file, f.line,
    ))

    modules = required_rc2_modules(root)
    smoke = run_import_smoke(root)
    tests = run_phase_tests(root)
    score, status = score_report(findings, modules, smoke, tests)

    payload = {
        "schema": "atlas_zero.rc2_readiness_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(root),
        "score": score,
        "status": status,
        "required_modules": modules,
        "import_smoke": smoke,
        "phase_tests": tests,
        "finding_counts": {
            severity: sum(1 for f in findings if f.severity == severity)
            for severity in ("critical", "high", "medium", "low")
        },
        "findings": [asdict(f) for f in findings],
    }

    json_path = output / "dependency_audit_rc2.json"
    md_path = output / "dependency_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, payload)

    print("=" * 72)
    print("ATLAS ZERO — RC2 FINAL READINESS AUDIT")
    print("=" * 72)
    print(f"Repository: {root}")
    print(f"Score: {score}/100")
    print(f"Status: {status}")
    print(f"Critical findings: {payload['finding_counts']['critical']}")
    print(f"High findings: {payload['finding_counts']['high']}")
    print(f"Medium findings: {payload['finding_counts']['medium']}")
    print(f"Import smoke: {'PASS' if smoke['passed'] else 'FAIL'}")
    print(f"Phase tests: {'PASS' if tests.get('passed') else 'FAIL'}")
    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")

    if status in {"BLOCKED", "NOT_READY_REQUIRES_FIXES"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
