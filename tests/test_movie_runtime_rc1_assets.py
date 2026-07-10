from pathlib import Path
import json

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
            '{"artifact": "%s", "status": "ready"}' % str(script_path).replace("\\", "/"),
        ),
    )


def test_movie_runtime_rc1_detects_franklin_assets_and_creates_manual_edit_package(tmp_path: Path):
    project_id = "franklin"
    db = Database(tmp_path / "franklin_movie_runtime.sqlite")
    db.init()

    script_path = tmp_path / "production_script.txt"
    script_path.write_text("Scene 1\nScene 2\nScene 3\n", encoding="utf-8")
    _seed_script_step(db, project_id, script_path)

    result = run_movie(project_id, db=db)

    runtime_dir = Path(result["package_dir"])
    asset_inventory = runtime_dir / "asset_inventory.json"
    timeline_json = runtime_dir / "timeline.json"
    timeline_csv = runtime_dir / "timeline.csv"
    manual_edit_md = runtime_dir / "manual_edit_package.md"
    missing_assets_md = runtime_dir / "missing_assets.md"

    assert result["final_state"] == "READY_FOR_MANUAL_EDIT"
    assert asset_inventory.exists()
    assert timeline_json.exists()
    assert timeline_csv.exists()
    assert manual_edit_md.exists()
    assert missing_assets_md.exists()

    inventory = json.loads(asset_inventory.read_text(encoding="utf-8"))
    assert inventory["counts"]["audio"] > 0
    assert inventory["counts"]["image"] > 0
    assert inventory["counts"]["video"] > 0

    timeline = timeline_json.read_text(encoding="utf-8")
    assert '"shot_index"' in timeline
    assert '"media_type"' in timeline
