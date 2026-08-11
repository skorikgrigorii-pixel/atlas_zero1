import json
from pathlib import Path

from az_enterprise.core.database import Database
from az_enterprise.core.project_config_rc2 import ProjectConfigRC2
from az_enterprise.core.timeline_engine_rc2 import TimelineEngineRC2


def test_timeline_engine_rc2_is_write_owner():
    source = Path(
        "src/az_enterprise/core/timeline_engine_rc2.py"
    ).read_text(encoding="utf-8")

    assert "MovieRuntimeRC1" not in source
    assert "write_text" in source
    assert "artifact_csv" in source


def test_retired_movie_runtime_rc1_is_absent():
    assert not Path(
        "src/az_enterprise/core/movie_runtime_rc1.py"
    ).exists()

def test_timeline_engine_builds_canonical_artifacts(
    tmp_path,
):
    db_path = tmp_path / "timeline.sqlite3"
    db = Database(db_path)
    db.init()

    project_id = "timeline_test"

    db.execute(
        """
        INSERT INTO projects(id, title, status)
        VALUES(?,?,?)
        """,
        (project_id, project_id, "NEW"),
    )

    db.execute(
        """
        INSERT INTO assets(
            id,
            project_id,
            path,
            filename,
            media_type,
            category,
            quality
        )
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            "asset_1",
            project_id,
            str(tmp_path / "image.jpg"),
            "image.jpg",
            "image",
            "image",
            1.0,
        ),
    )

    db.execute(
        """
        INSERT INTO shots(
            id,
            project_id,
            idx,
            start_sec,
            end_sec,
            visual_need,
            story_goal,
            emotion,
            status,
            assigned_asset_id
        )
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "shot_1",
            project_id,
            1,
            0.0,
            5.0,
            "ice detail",
            "opening",
            "cold",
            "assigned",
            "asset_1",
        ),
    )

    config = ProjectConfigRC2(
        project_id=project_id,
        root_dir=tmp_path,
    )

    result = TimelineEngineRC2(
        db,
        config,
    ).run()

    assert result["items"] == 1
    assert result["incomplete"] == 0
    assert result["authority"] == "TimelineEngineRC2"

    json_path = Path(result["artifact_json"])
    csv_path = Path(result["artifact_csv"])

    assert json_path.exists()
    assert csv_path.exists()

    rows = json.loads(
        json_path.read_text(encoding="utf-8")
    )

    assert rows[0]["shot_id"] == "shot_1"
    assert rows[0]["asset_name"] == "image.jpg"
    assert rows[0]["duration_sec"] == 5.0

