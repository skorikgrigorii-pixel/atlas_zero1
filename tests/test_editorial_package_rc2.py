from az_enterprise.core.editorial_package_rc2 import (
    EditorialPackageRC2,
)


def test_editorial_package_builds():
    builder = EditorialPackageRC2(
        project_id="hogueras",
        title="Hogueras",
    )

    package = builder.build(
        story_strategy={
            "strategy": {
                "film_type": "documentary",
                "narrative_strategy":
                    "event_progression",
                "target_duration_sec": 1500,
                "target_audience": "18-55",
            },
            "acts": [
                {
                    "act_id": "ACT01",
                    "title_ru": "Начало",
                },
            ],
            "scenes": [
                {
                    "scene_id": "SC01",
                    "act_id": "ACT01",
                    "order": 1,
                    "title_ru": "Город",
                    "duration_sec": 1500,
                    "narrative_goal_ru":
                        "Открыть фильм.",
                    "emotional_goal_ru":
                        "ожидание",
                    "visual_strategy_ru":
                        "Общие планы.",
                    "cluster_ids": [
                        "cluster-1",
                    ],
                    "asset_ids": [
                        "asset-1",
                    ],
                },
            ],
            "transitions": [],
        },
        event_discovery={
            "included_assets_total": 1,
            "event_clusters": [
                {
                    "cluster_id": "cluster-1",
                    "event_type": "monument",
                    "time_period": "day",
                    "confidence": 0.9,
                    "story_value": 0.9,
                    "description_ru":
                        "Праздничные фигуры.",
                    "asset_ids": [
                        "asset-1",
                    ],
                },
            ],
            "off_topic_assets": [],
            "review_assets": [],
        },
        semantic_analysis={
            "assets_analyzed": 1,
            "results": [],
        },
    )

    assert package["project"][
        "project_id"
    ] == "hogueras"

    assert len(package["scenes"]) == 1
    assert len(
        package["event_clusters"]
    ) == 1

    assert package[
        "production_constraints"
    ]["allow_generated_visuals"] is False


def test_empty_scenes_are_rejected():
    builder = EditorialPackageRC2(
        project_id="hogueras",
        title="Hogueras",
    )

    try:
        builder.build(
            story_strategy={
                "scenes": [],
            },
            event_discovery={
                "event_clusters": [
                    {
                        "cluster_id": "cluster-1",
                    },
                ],
            },
            semantic_analysis={},
        )
    except ValueError as exc:
        assert "no scenes" in str(exc)
    else:
        raise AssertionError(
            "ValueError was not raised"
        )
