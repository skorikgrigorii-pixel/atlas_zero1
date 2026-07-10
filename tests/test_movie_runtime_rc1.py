from pathlib import Path

import pytest

from az_enterprise.core.database import Database
from az_enterprise.core.movie_runtime_rc1 import run_movie


def _seed_script_step(db: Database, project_id: str, script_path: Path) -> None:
    db.execute(
        "INSERT INTO workflow_steps(project_id, step_key, title, status, result_json) VALUES(?,?,?,?,?)",
        (
            project_id,
            "script_ready",
            "Production Script",
            "done",
            '{"artifact": "%s", "status": "ready"}' % str(script_path).replace('\\', '/'),
        ),
    )


def _seed_voice_asset(db: Database, project_id: str) -> None:
    db.execute(
        "INSERT INTO assets(id, project_id, path, filename, media_type, sha256, category, tags, emotion, quality, duration_sec) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            f"{project_id}-voice-1",
            project_id,
            f"./assets/{project_id}/narration.wav",
            "narration.wav",
            "audio",
            "voice-sha",
            "audio",
            "['voice','narration']",
            "neutral",
            0.98,
            180.0,
        ),
    )


def _seed_visual_asset(db: Database, project_id: str, idx: int) -> None:
    db.execute(
        "INSERT INTO assets(id, project_id, path, filename, media_type, sha256, category, tags, emotion, quality) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            f"{project_id}-img-{idx}",
            project_id,
            f"./assets/{project_id}/image_{idx}.jpg",
            f"image_{idx}.jpg",
            "image",
            f"img-sha-{idx}",
            "image",
            "['arctic','ship','ice']",
            "cold",
            0.92,
        ),
    )


def test_run_movie_builds_ready_for_manual_edit_package(tmp_path: Path):
    project_id = "movie-rc1"
    db = Database(tmp_path / "movie_rc1.sqlite")
    db.init()

    script_path = tmp_path / "final_script.txt"
    script_path.write_text("Scene 1\nScene 2\nScene 3\nScene 4\n", encoding="utf-8")
    _seed_script_step(db, project_id, script_path)
    _seed_voice_asset(db, project_id)
    _seed_visual_asset(db, project_id, 1)
    _seed_visual_asset(db, project_id, 2)

    result = run_movie(project_id, db=db)

    assert result["final_state"] == "READY_FOR_MANUAL_EDIT"
    assert result["networking"] is False
    assert Path(result["package_zip"]).exists()

    stage_jobs = db.one(
        "SELECT COUNT(*) c FROM workflow_jobs WHERE project_id=? AND stage LIKE 'movie_runtime_stage_%' AND status='done'",
        (project_id,),
    )["c"]
    assert int(stage_jobs) == 11

    state = db.one("SELECT status FROM projects WHERE id=?", (project_id,))["status"]
    assert state == "READY_FOR_MANUAL_EDIT"


def test_run_movie_requires_existing_production_script(tmp_path: Path):
    db = Database(tmp_path / "movie_rc1_no_script.sqlite")
    db.init()
    _seed_voice_asset(db, "movie-no-script")

    with pytest.raises(ValueError, match="Production Script"):
        run_movie("movie-no-script", db=db)


def test_run_movie_requires_existing_voice_assets(tmp_path: Path):
    project_id = "movie-no-voice"
    db = Database(tmp_path / "movie_rc1_no_voice.sqlite")
    db.init()

    script_path = tmp_path / "final_script.txt"
    script_path.write_text("Only script\n", encoding="utf-8")
    _seed_script_step(db, project_id, script_path)

    with pytest.raises(ValueError, match="Voice assets"):
        run_movie(project_id, db=db)
