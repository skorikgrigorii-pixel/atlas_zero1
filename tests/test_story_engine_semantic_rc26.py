from az_enterprise.core.database import Database
from az_enterprise.core.story_engine import StoryEngine


def strategy_payload():
    return {
        "project_id": "hogueras",
        "strategy": {
            "target_duration_sec": 120.0,
            "use_existing_assets_only": True,
        },
        "scenes": [
            {
                "scene_id": "SC01",
                "act_id": "ACT01",
                "title_ru": "Город готовится",
                "narrative_goal_ru": "Показать начало праздника.",
                "emotional_goal_ru": "ожидание",
                "visual_strategy_ru": "Общие планы города.",
                "duration_sec": 60.0,
                "cluster_ids": (
                    "cluster-monument-day",
                ),
                "asset_ids": (
                    "asset-1",
                    "asset-2",
                ),
            },
            {
                "scene_id": "SC02",
                "act_id": "ACT02",
                "title_ru": "Ночь огня",
                "narrative_goal_ru": "Показать финал.",
                "emotional_goal_ru": "кульминация",
                "visual_strategy_ru": "Огонь и фейерверки.",
                "duration_sec": 60.0,
                "cluster_ids": (
                    "cluster-crema-night",
                ),
                "asset_ids": (
                    "asset-3",
                ),
            },
        ],
    }


def prepare_db(tmp_path):
    db = Database(tmp_path / "story.sqlite3")
    db.init()

    db.execute(
        """
        INSERT OR IGNORE INTO projects(
            id,
            title,
            duration_sec
        )
        VALUES(?,?,?)
        """,
        (
            "hogueras",
            "Hogueras",
            120,
        ),
    )

    for asset_id in (
        "asset-1",
        "asset-2",
        "asset-3",
    ):
        db.execute(
            """
            INSERT INTO assets(
                id,
                project_id,
                path,
                filename,
                media_type
            )
            VALUES(?,?,?,?,?)
            """,
            (
                asset_id,
                "hogueras",
                str(tmp_path / f"{asset_id}.jpg"),
                f"{asset_id}.jpg",
                "image",
            ),
        )

    return db


def test_story_engine_builds_from_strategy(
    tmp_path,
):
    db = prepare_db(tmp_path)

    result = StoryEngine(
        db,
        "hogueras",
    ).build_from_strategy(
        strategy_payload(),
        target_count=12,
    )

    assert result["version"] == "2.6"
    assert result["mode"] == "semantic_strategy"
    assert result["scenes"] == 2
    assert result["shots"] == 12
    assert result["assigned_shots"] == 12
    assert result["missing_shots"] == 0
    assert result["duration_sec"] == 120.0


def test_dynamic_scenes_are_written(
    tmp_path,
):
    db = prepare_db(tmp_path)

    StoryEngine(
        db,
        "hogueras",
    ).build_from_strategy(
        strategy_payload(),
        target_count=8,
    )

    scenes = db.rows(
        """
        SELECT *
        FROM story_scenes
        WHERE project_id='hogueras'
        ORDER BY idx
        """
    )

    assert len(scenes) == 2
    assert scenes[0]["title"] == (
        "Город готовится"
    )
    assert scenes[1]["title"] == (
        "Ночь огня"
    )


def test_shots_reference_existing_assets(
    tmp_path,
):
    db = prepare_db(tmp_path)

    StoryEngine(
        db,
        "hogueras",
    ).build_from_strategy(
        strategy_payload(),
        target_count=10,
    )

    missing = db.one(
        """
        SELECT COUNT(*) AS count
        FROM shots
        WHERE project_id='hogueras'
          AND assigned_asset_id IS NULL
        """
    )

    assert missing["count"] == 0
