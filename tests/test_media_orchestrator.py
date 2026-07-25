from pathlib import Path

from az_enterprise.core.database import Database
from az_enterprise.core.media_orchestrator import run_project
from az_enterprise.core.project_state import ProjectState


def test_run_project_advances_through_pipeline(tmp_path: Path):
    db = Database(tmp_path / "movie.sqlite")
    db.init()

    result = run_project("movie-1", db=db)

    assert result["status"] == "ANALYTICS"
    assert result["completed"] is True

    steps = db.rows(
        "SELECT step_key, status FROM workflow_steps WHERE project_id=? ORDER BY id",
        ("movie-1",),
    )
    step_keys = [row["step_key"] for row in steps]
    assert "research" in step_keys
    assert "analytics" in step_keys


def test_run_project_resumes_from_existing_state(tmp_path: Path):
    db = Database(tmp_path / "movie-resume.sqlite")
    db.init()

    state = ProjectState(db, "movie-2")
    state.advance("RESEARCH", {"note": "seeded"})

    result = run_project("movie-2", db=db)

    assert result["status"] == "ANALYTICS"
    assert result["completed"] is True

    steps = db.rows(
        "SELECT step_key, status FROM workflow_steps WHERE project_id=? ORDER BY id",
        ("movie-2",),
    )
    step_keys = [row["step_key"] for row in steps]
    assert step_keys.count("research") == 1
    assert "script_ready" in step_keys
