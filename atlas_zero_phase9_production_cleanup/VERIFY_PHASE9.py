from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path


def find_repo_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("Repository root was not found")


def imports_rc1(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names if "rc1" in a.name.lower())
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "rc1" in module.lower():
                found.append(module)
    return found


repo = find_repo_root()
active = []
for path in (repo / "src" / "az_enterprise").rglob("*.py"):
    try:
        found = imports_rc1(path)
    except SyntaxError:
        continue
    if found:
        active.append((str(path.relative_to(repo)), found))

assert not active, f"Active RC1 imports remain: {active}"

for legacy in (
    "test_movie_runtime_rc1.py",
    "test_movie_runtime_rc1_assets.py",
    "test_render_engine_rc1.py",
):
    assert not (repo / "tests" / legacy).exists()
    assert (repo / "tests" / "legacy_rc1" / legacy).exists()

audit = repo / "atlas_zero_rc2_final_audit" / "RC2_DEPENDENCY_AUDIT.py"
text = audit.read_text(encoding="utf-8-sig")
assert "PHASE9_PRODUCTION_SCOPE" in text
assert "phase9_should_scan" in text

env = os.environ.copy()
env["PYTHONPATH"] = str(repo / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
command = [
    sys.executable,
    "-c",
    "from az_enterprise.core.control_layer_rc2 import RC2ControlLayer, RC2ReadinessPlanner;"
    "from az_enterprise.core.render_engine_rc2 import RenderEngineRC2;"
    "from az_enterprise.core.timeline_engine_rc2 import TimelineEngineRC2;"
    "print('PHASE9_IMPORT_SMOKE_OK')",
]
result = subprocess.run(command, cwd=repo, env=env, check=False)
raise SystemExit(result.returncode)
