from __future__ import annotations

import json
from pathlib import Path

from az_enterprise.core.production_state_rc2 import (
    ProductionStateRC2,
    ProductionStateStoreRC2,
)
from az_enterprise.core.project_config_rc2 import ProjectConfigRC2


def test_project_config_is_project_generic(tmp_path: Path) -> None:
    config = ProjectConfigRC2(project_id="second_film", root_dir=tmp_path)
    assert config.project_dir == tmp_path / "workspace" / "projects" / "second_film"
    assert config.canonical_render_path.name == "second_film_RC2.mp4"


def test_state_store_writes_and_reads_atomically(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = ProductionStateStoreRC2(path, project_id="demo")
    state = ProductionStateRC2(schema_version="2.0", project_id="demo")
    store.start_stage(state, "assets")
    store.complete_stage(state, "assets", {"assets_total": 4})

    loaded = store.load()
    assert loaded.project_id == "demo"
    assert loaded.stages["assets"].status == "COMPLETED"
    assert loaded.stages["assets"].details["assets_total"] == 4
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "2.0"
