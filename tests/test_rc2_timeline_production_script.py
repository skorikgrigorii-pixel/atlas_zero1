import json
from pathlib import Path

from az_enterprise.core.database import Database
from az_enterprise.core.project_config_rc2 import (
    ProjectConfigRC2,
)
from az_enterprise.core.timeline_engine_rc2 import (
    TimelineEngineRC2,
)


def production_script():
    return {
        "project_id": "sample",
        "duration_sec": 20.0,
        "scenes": [
            {
                "scene_id": "SC01",
                "act_id": "ACT01",
                "order": 1,
                "title": "Начало",
                "duration_sec": 12.0,
                "video": {
                    "asset_ids": [
                        "asset_1",
                        "asset_2",
                    ],
                    "visual_strategy":
                        "Общие и средние планы.",
                },
                "voiceover": {
                    "text":
                        "Текст первой сцены.",
                },
                "transition": {
                    "type": "dissolve",
                    "to_scene_id": "SC02",
                },
                "narrative_goal":
                    "Открыть фильм.",
                "emotional_goal":
                    "ожидание",
            },
            {
                "scene_id": "SC02",
                "act_id": "ACT02",
                "order": 2,
                "title": "Финал",
                "duration_sec": 8.0,
                "video": {
                    "asset_ids": [
                        "asset_3",
                    ],
                    "visual_strategy":
                        "Кульминационные планы.",
                },
                "voiceover": {
                    "text":
                        "Текст второй сцены.",
                },
                "transition": {
                    "type": "end",
                    "to_scene_id": None,
                },
                "narrative_goal":
                    "Завершить фильм.",
                "emotional_goal":
                    "кульминация",
            },
        ],
    }


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

    for index in range(1, 4):
        media_path = (
            tmp_path
            / f"asset_{index}.mp4"
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
                f"asset_{index}",
                "sample",
                str(media_path),
                media_path.name,
                "video",
                0.9,
            ),
        )

    return db


def test_builds_from_production_script(
    tmp_path,
):
    db = prepare_db(tmp_path)

    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    result = TimelineEngineRC2(
        db,
        config,
    ).run_from_production_script(
        production_script(),
        average_shot_duration_sec=5.0,
    )

    assert result["authority"] == (
        "TimelineEngineRC2"
    )
    assert result["mode"] == (
        "production_script"
    )
    assert result["scenes"] == 2
    assert result["duration_sec"] == 20.0
    assert result["incomplete"] == 0
    assert result["items"] >= 3


def test_timeline_contains_scene_assets(
    tmp_path,
):
    db = prepare_db(tmp_path)

    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    result = TimelineEngineRC2(
        db,
        config,
    ).run_from_production_script(
        production_script(),
        average_shot_duration_sec=5.0,
    )

    rows = json.loads(
        Path(
            result["artifact_json"]
        ).read_text(
            encoding="utf-8"
        )
    )

    assert rows[0]["scene_id"] == "SC01"
    assert rows[0]["asset_id"] == "asset_1"
    assert rows[1]["asset_id"] == "asset_2"
    assert rows[-1]["scene_id"] == "SC02"
    assert rows[-1]["end_sec"] == 20.0


def test_missing_asset_marks_incomplete(
    tmp_path,
):
    db = prepare_db(tmp_path)

    payload = production_script()
    payload["scenes"][0]["video"][
        "asset_ids"
    ] = [
        "missing_asset",
    ]

    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    result = TimelineEngineRC2(
        db,
        config,
    ).run_from_production_script(
        payload
    )

    assert result["state"] == (
        "TIMELINE_INCOMPLETE"
    )
    assert result["incomplete"] > 0
