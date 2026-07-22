from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PIPELINE_STAGE_HINTS = (
    "asset", "visual", "semantic", "event", "story_strategy", "story",
    "assignment", "timeline", "voice", "audio", "render", "quality", "director",
)
STATE_PATTERN = re.compile(r'["\']([A-Z][A-Z0-9_]{3,})["\']')
JSON_PATTERN = re.compile(r'["\']([^"\']+\.json)["\']')
IMPORT_FROM_PATTERN = re.compile(r'^\s*from\s+([.\w]+)\s+import\s+', re.MULTILINE)
IMPORT_PATTERN = re.compile(r'^\s*import\s+([.\w]+)', re.MULTILINE)

@dataclass
class SyntaxErrorRecord:
    path: str
    line: int | None
    column: int | None
    message: str

@dataclass
class ModuleRecord:
    path: str
    module: str
    lines: int
    classes: list[str]
    functions: list[str]
    imports: list[str]
    states: list[str]
    json_literals: list[str]
    pipeline_hints: list[str]
    writes_json: bool
    reads_json: bool
    uses_database: bool
    uses_subprocess: bool
    has_main: bool

@dataclass
class DuplicateRecord:
    kind: str
    name: str
    count: int
    locations: list[str]

def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)

def module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)

def iter_python_files(root: Path) -> Iterable[Path]:
    ignored = {".git", ".venv", "venv", "__pycache__", "node_modules", "workspace", "dist", "build"}
    for path in root.rglob("*.py"):
        if any(part in ignored for part in path.parts):
            continue
        yield path

def extract_imports(source: str) -> list[str]:
    imports = set(IMPORT_FROM_PATTERN.findall(source))
    imports.update(IMPORT_PATTERN.findall(source))
    return sorted(imports)

def analyze_python(path: Path, root: Path):
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return None, SyntaxErrorRecord(rel(path, root), exc.lineno, exc.offset, exc.msg)
    classes, functions = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
    lowered = source.lower()
    hints = [h for h in PIPELINE_STAGE_HINTS if h in path.stem.lower() or h in lowered]
    record = ModuleRecord(
        path=rel(path, root), module=module_name(path, root), lines=source.count("\n") + 1,
        classes=sorted(set(classes)), functions=sorted(set(functions)), imports=extract_imports(source),
        states=sorted(set(STATE_PATTERN.findall(source))), json_literals=sorted(set(JSON_PATTERN.findall(source))),
        pipeline_hints=hints,
        writes_json=(".write_text(" in source or "json.dump(" in source or ("json.dumps(" in source and "write" in lowered)),
        reads_json=((".read_text(" in source and "json.loads(" in source) or "json.load(" in source),
        uses_database=("Database(" in source or "self.db" in source),
        uses_subprocess=("subprocess." in source), has_main=('if __name__ == "__main__"' in source),
    )
    return record, None

def collect_duplicates(modules: list[ModuleRecord]) -> list[DuplicateRecord]:
    locations = defaultdict(list)
    for module in modules:
        for name in module.classes:
            locations[("class", name)].append(module.path)
        for name in module.functions:
            if not name.startswith("_"):
                locations[("function", name)].append(module.path)
    rows = [DuplicateRecord(k, n, len(p), sorted(p)) for (k, n), p in locations.items() if len(p) > 1]
    return sorted(rows, key=lambda r: (-r.count, r.kind, r.name))

def run_command(command: list[str], cwd: Path, timeout: int = 180) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return {"returncode": result.returncode, "output": (result.stdout + "\n" + result.stderr).strip()[-30000:]}
    except subprocess.TimeoutExpired as exc:
        return {"returncode": None, "output": ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip(), "timeout": True}
    except OSError as exc:
        return {"returncode": None, "output": str(exc)}

def inspect_git(root: Path) -> dict[str, Any]:
    def call(*args: str):
        result = run_command(["git", *args], root, 30)
        return result["output"] if result.get("returncode") == 0 else None
    return {"branch": call("branch", "--show-current"), "head": call("rev-parse", "HEAD"), "status": call("status", "--short"), "remote": call("remote", "-v")}

def build_pipeline_findings(modules: list[ModuleRecord]) -> dict[str, Any]:
    stage_modules = defaultdict(list)
    for module in modules:
        for hint in module.pipeline_hints:
            stage_modules[hint].append(module.path)
    suspicious = []
    required = {"visual_semantic_analyzer_rc2", "event_discovery_engine_rc2", "story_strategy_engine_rc2", "director_core_rc2", "assignment_engine_rc2", "timeline_engine_rc2", "render_engine_rc2", "quality_gate_rc2"}
    stems = {Path(m.path).stem for m in modules}
    missing = sorted(required - stems)
    if missing:
        suspicious.append("Missing canonical RC2 modules: " + ", ".join(missing))
    director = next((m for m in modules if Path(m.path).stem == "director_core_rc2"), None)
    if director:
        imports = " ".join(director.imports)
        for name in ("visual_semantic_analyzer_rc2", "event_discovery_engine_rc2", "story_strategy_engine_rc2"):
            if name not in imports:
                suspicious.append(f"DirectorCoreRC2 does not import {name}; upstream RC2 chain may be disconnected.")
    return {
        "stage_modules": {k: sorted(v) for k, v in sorted(stage_modules.items())},
        "json_writers": sorted(m.path for m in modules if m.writes_json),
        "json_readers": sorted(m.path for m in modules if m.reads_json),
        "suspicious_findings": suspicious,
    }

def make_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# ATLAS ZERO — Full Repository Audit", "", f"Generated: `{report['generated_at']}`", f"Root: `{report['root']}`", "",
        "## Executive summary", "", f"- Python modules: **{s['python_modules']}**", f"- Python lines: **{s['python_lines']}**",
        f"- Syntax errors: **{s['syntax_errors']}**", f"- Duplicate public symbols: **{s['duplicate_symbols']}**",
        f"- JSON readers: **{s['json_readers']}**", f"- JSON writers: **{s['json_writers']}**", "", "## Critical findings", "",
    ]
    findings = report["pipeline"]["suspicious_findings"]
    lines.extend([f"- {x}" for x in findings] or ["- No automatic critical pipeline findings."])
    lines += ["", "## Syntax errors", ""]
    lines.extend([f"- `{x['path']}:{x['line']}:{x['column']}` — {x['message']}" for x in report["syntax_errors"]] or ["- None."])
    lines += ["", "## Duplicate public symbols", ""]
    if report["duplicates"]:
        for x in report["duplicates"][:100]:
            lines.append(f"- **{x['kind']} `{x['name']}`** × {x['count']}: " + ", ".join(f"`{p}`" for p in x["locations"]))
    else:
        lines.append("- None.")
    lines += ["", "## Pipeline stage coverage", ""]
    for stage, paths in report["pipeline"]["stage_modules"].items():
        lines += [f"### {stage}"] + [f"- `{p}`" for p in paths] + [""]
    lines += ["## Compile check", "", f"- Return code: `{report['compileall']['returncode']}`", "```text", report['compileall']['output'], "```", "", "## Tests", "", f"- State: **{report['pytest']['state']}**", "```text", report['pytest']['output'], "```", "", "## Git state", "", f"- Branch: `{report['git']['branch']}`", f"- HEAD: `{report['git']['head']}`", "```text", report['git']['status'] or "clean or unavailable", "```", "", "## Recommended remediation order", "", "1. Fix syntax errors.", "2. Restore one canonical RC2 chain from assets through quality.", "3. Define every intermediate artifact in ProjectConfigRC2.", "4. Persist outputs atomically and validate project/state at every boundary.", "5. Quarantine duplicate orchestrators and legacy fallbacks.", "6. Add contract tests for every stage boundary.", "7. Run a clean-workspace end-to-end test.", ""]
    return "\n".join(lines)

def main() -> int:
    parser = argparse.ArgumentParser(description="Full static/runtime audit for ATLAS ZERO")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--output-dir", default="audit_output")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Repository root not found: {root}", file=sys.stderr)
        return 2
    modules, syntax_errors = [], []
    for path in iter_python_files(root):
        module, error = analyze_python(path, root)
        if module: modules.append(module)
        if error: syntax_errors.append(error)
    modules.sort(key=lambda x: x.path)
    syntax_errors.sort(key=lambda x: x.path)
    duplicates = collect_duplicates(modules)
    pipeline = build_pipeline_findings(modules)
    compileall = run_command([sys.executable, "-m", "compileall", "-q", str(root)], root)
    if args.skip_tests:
        pytest = {"state": "SKIPPED", "returncode": None, "output": ""}
    elif any(root.rglob("test_*.py")) or any(root.rglob("*_test.py")):
        result = run_command([sys.executable, "-m", "pytest", "-q", "--disable-warnings", "--maxfail=20"], root)
        pytest = {"state": "PASSED" if result.get("returncode") == 0 else "FAILED", **result}
    else:
        pytest = {"state": "NOT_FOUND", "returncode": None, "output": "No test files found."}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
        "summary": {"python_modules": len(modules), "python_lines": sum(m.lines for m in modules), "syntax_errors": len(syntax_errors), "duplicate_symbols": len(duplicates), "json_readers": len(pipeline["json_readers"]), "json_writers": len(pipeline["json_writers"])},
        "syntax_errors": [asdict(x) for x in syntax_errors], "modules": [asdict(x) for x in modules], "duplicates": [asdict(x) for x in duplicates], "pipeline": pipeline, "compileall": compileall, "pytest": pytest, "git": inspect_git(root),
    }
    output_dir = (root / args.output_dir).resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "atlas_zero_full_audit.json"; md_path = output_dir / "atlas_zero_full_audit.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(make_markdown(report), encoding="utf-8")
    print("=" * 78); print("ATLAS ZERO — FULL REPOSITORY AUDIT"); print("=" * 78)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2)); print(f"JSON report: {json_path}"); print(f"Markdown report: {md_path}")
    return 1 if syntax_errors or compileall.get("returncode") != 0 else 0

if __name__ == "__main__":
    raise SystemExit(main())
