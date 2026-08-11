from __future__ import annotations

import ast
from pathlib import Path

from az_enterprise.core.control_layer_rc2 import RC2ControlLayer, RC2ReadinessPlanner
from az_enterprise.core.project_config_rc2 import ProjectConfigRC2

ROOT = Path(__file__).resolve().parents[1]


def rc1_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(a.name for a in node.names if "rc1" in a.name.lower())
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "rc1" in module.lower():
                result.append(module)
    return result


def test_active_control_files_have_no_rc1_imports():
    paths = [
        ROOT / "src" / "az_enterprise" / "cli.py",
        ROOT / "src" / "az_enterprise" / "ui" / "app.py",
        ROOT / "src" / "az_enterprise" / "core" / "control_layer_rc2.py",
    ]
    assert all(not rc1_imports(path) for path in paths)


def test_control_layer_imports():
    assert RC2ControlLayer.__name__ == "RC2ControlLayer"
    assert RC2ReadinessPlanner.__name__ == "RC2ReadinessPlanner"


def test_canonical_paths_are_rc2():
    config = ProjectConfigRC2(project_id="phase8-test")
    assert "rc2" in config.timeline_path.as_posix().lower()
    assert "rc2" in config.canonical_render_path.as_posix().lower()


