import json
from pathlib import Path

import pytest

from az_enterprise.core.database import Database
from az_enterprise.core.project_config_rc2 import (
    ProjectConfigRC2,
)
from az_enterprise.core.timeline_engine_rc2 import (
    TimelineEngineRC2,
)


def prepare_db(tmp_path):
    db = Database(
        tmp_path / "timeline.sqlite3"
    )
    db.init()

    db.execute(
        """
        INSERT INTO projects(
            id,
            title,
            status
        )
        VALUES(?,?,?)
        """,
        (
            "sample",
            "Sample",
            "NEW",
        ),
    )

    media_path = (
        tmp_path
        / "asset_1.mp4"
    )
    media_path.write_bytes(
        b"video"
    )

    db.execute(
        """
        INSERT INTO assets(
            id,
            project_id,
            path,
            filename,
            media_type,
            quality
        )
        VALUES(?,?,?,?,?,?)
        """,
        (
            "asset_1",
            "sample",
            str(media_path),
            media_path.name,
            "video",
            0.9,
        ),
    )

    return db


def production_script():
    return {
        "project_id": "sample",
        "duration_sec": 10.0,
        "scenes": [
            {
                "scene_id": "SC01",
                "act_id": "ACT01",
                "order": 1,
                "title": "Начало",
                "duration_sec": 10.0,
                "video": {
                    "asset_ids": [
                        "asset_1",
                    ],
                    "visual_strategy":
                        "Общий план.",
                },
                "voiceover": {
                    "text":
                        "Текст первой сцены.",
                },
                "transition": {
                    "type": "end",
                    "to_scene_id": None,
                },
                "narrative_goal":
                    "Открыть фильм.",
                "emotional_goal":
                    "ожидание",
            },
        ],
    }


def test_run_from_project_discovers_canonical_script(
    tmp_path,
):
    db = prepare_db(tmp_path)

    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    script_dir = (
        config.project_dir
        / "script"
    )
    script_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    script_path = (
        script_dir
        / "production_script.json"
    )

    script_path.write_text(
        json.dumps(
            production_script(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = TimelineEngineRC2(
        db,
        config,
    ).run_from_project(
        average_shot_duration_sec=5.0,
    )

    assert result["state"] == (
        "TIMELINE_READY"
    )
    assert result["mode"] == (
        "production_script"
    )
    assert result["discovery_mode"] == (
        "project_auto_discovery"
    )
    assert (
        Path(
            result[
                "production_script_path"
            ]
        )
        == script_path
    )


def test_versioned_script_is_discovered(
    tmp_path,
):
    db = prepare_db(tmp_path)

    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    script_dir = (
        config.project_dir
        / "script"
    )
    script_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    versioned_path = (
        script_dir
        / "production_script_final_v2.json"
    )

    versioned_path.write_text(
        json.dumps(
            production_script(),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    engine = TimelineEngineRC2(
        db,
        config,
    )

    assert (
        engine
        ._discover_production_script_path()
        == versioned_path
    )


def test_missing_project_script_is_rejected(
    tmp_path,
):
    db = prepare_db(tmp_path)

    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    with pytest.raises(
        FileNotFoundError,
        match="Production script JSON",
    ):
        TimelineEngineRC2(
            db,
            config,
        ).run_from_project()
