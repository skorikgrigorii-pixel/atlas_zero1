from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ACTIVE_ROOTS = ("src", "tools", "tests")
IGNORED_PARTS = {
    ".git", "__pycache__", "legacy_rc1", "workspace", "backups",
    "atlas_zero_rc2_production_audit", "atlas_zero_remove_rc1",
}


def find_repo_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


def ignored(path: Path, repo: Path) -> bool:
    rel = path.relative_to(repo)
    return any(part in IGNORED_PARTS for part in rel.parts)


def main() -> int:
    repo = find_repo_root()
    failures: list[str] = []

    forbidden = [
        repo / "src/az_enterprise/core/movie_runtime_rc1.py",
        repo / "src/az_enterprise/core/render_engine_rc1.py",
        repo / "src/az_enterprise/core/rc1_completion_planner.py",
        repo / "tests/legacy_rc1",
        repo / "tools/legacy_rc1",
    ]
    for path in forbidden:
        if path.exists():
            failures.append(f"Still exists: {path.relative_to(repo)}")

    active_refs: list[str] = []
    for root_name in ACTIVE_ROOTS:
        root = repo / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if ignored(path, repo):
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            try:
                tree = ast.parse(text, filename=str(path))
            except SyntaxError as exc:
                failures.append(f"Syntax error: {path.relative_to(repo)}:{exc.lineno}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = (node.module or "").lower()
                    if "movie_runtime_rc1" in module or "render_engine_rc1" in module:
                        active_refs.append(f"{path.relative_to(repo)}:{node.lineno} -> {module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.name.lower()
                        if "movie_runtime_rc1" in name or "render_engine_rc1" in name:
                            active_refs.append(f"{path.relative_to(repo)}:{node.lineno} -> {name}")

    failures.extend(f"Active RC1 import: {item}" for item in active_refs)

    process = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "src", "tools"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        failures.append("compileall failed:\n" + process.stderr)

    smoke = subprocess.run(
        [
            sys.executable, "-c",
            (
                "from az_enterprise.core.control_layer_rc2 import RC2ControlLayer;"
                "from az_enterprise.core.render_engine_rc2 import RenderEngineRC2;"
                "from az_enterprise.core.timeline_engine_rc2 import TimelineEngineRC2;"
                "print('RC2_AFTER_RC1_REMOVAL_OK')"
            ),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if smoke.returncode != 0:
        failures.append("RC2 import smoke failed:\n" + smoke.stderr)

    print("=" * 76)
    print("ATLAS ZERO — VERIFY RC1 REMOVAL")
    print("=" * 76)
    if failures:
        print("FAIL")
        for item in failures:
            print("-", item)
        return 2

    print("PASS")
    print(smoke.stdout.strip())
    print("No active imports of MovieRuntimeRC1 or RenderEngineRC1 were found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
