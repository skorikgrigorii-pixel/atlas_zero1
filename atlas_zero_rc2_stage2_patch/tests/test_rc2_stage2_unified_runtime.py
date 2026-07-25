from pathlib import Path

from az_enterprise.core.production_state_rc2 import ProductionStateStoreRC2
from az_enterprise.core.project_config_rc2 import ProjectConfigRC2
from az_enterprise.core.runtime_governance_rc2 import governance_report


def test_single_orchestration_authority():
    report = governance_report()
    assert report["orchestration_authorities"] == 1
    assert report["canonical_authority"]["name"] == "DirectorCoreRC2"
    assert all(not row["may_advance_pipeline"] for row in report["legacy_authorities"])


def test_state_revision_and_atomic_persistence(tmp_path: Path):
    path = tmp_path / "production_state.json"
    store = ProductionStateStoreRC2(path, "demo")
    state = store.load()
    assert state.revision == 0
    store.reset_for_run(state, force=True)
    assert path.exists()
    reloaded = store.load()
    assert reloaded.revision >= 1
    assert reloaded.status == "RUNNING"


def test_project_paths_are_project_agnostic(tmp_path: Path):
    config = ProjectConfigRC2(project_id="another_film", root_dir=tmp_path)
    assert "another_film" in str(config.project_dir)
    assert config.canonical_render_path.name == "another_film_RC2.mp4"
    assert "franklin" not in str(config.canonical_render_path)
