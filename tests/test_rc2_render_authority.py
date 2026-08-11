from __future__ import annotations

import ast
from pathlib import Path


RENDER_ENGINE = Path(
    "src/az_enterprise/core/render_engine_rc2.py"
)


def _rc1_runtime_references() -> list[str]:
    source = RENDER_ENGINE.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    references: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if "render_engine_rc1" in item.name.lower():
                    references.append(item.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "render_engine_rc1" in module.lower():
                references.append(module)

    return references


def test_render_engine_rc2_is_canonical_authority():
    source = RENDER_ENGINE.read_text(encoding="utf-8-sig")

    assert '"authority": "RenderEngineRC2"' in source
    assert "RENDER_COMPLETE" in source
    assert "self.probe(partial)" in source
    assert "os.replace(partial, destination)" in source


def test_render_engine_rc2_does_not_import_retired_rc1_backend():
    assert _rc1_runtime_references() == []


def test_cli_uses_rc2_control_layer():
    source = Path(
        "src/az_enterprise/cli.py"
    ).read_text(encoding="utf-8-sig")

    assert "RC2ControlLayer" in source


def test_retired_render_engine_rc1_is_absent():
    assert not Path(
        "src/az_enterprise/core/render_engine_rc1.py"
    ).exists()
