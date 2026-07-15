from az_enterprise.core.narrative_writer_rc2 import (
    NarrativeWriterRC2,
)


def strategy_payload():
    return {
        "project_id": "hogueras",
        "strategy": {
            "language": "ru",
            "target_duration_sec": 120.0,
        },
        "scenes": [
            {
                "scene_id": "SC01",
                "title_ru": "Город готовится",
                "narrative_goal_ru":
                    "Показать начало праздника.",
                "emotional_goal_ru": "ожидание",
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
                "title_ru": "Ночь огня",
                "narrative_goal_ru":
                    "Показать финал праздника.",
                "emotional_goal_ru":
                    "кульминация",
                "duration_sec": 60.0,
                "cluster_ids": (
                    "cluster-crema-night",
                ),
                "asset_ids": (
                    "asset-3",
                ),
            },
        ],
        "transitions": [
            {
                "from_scene_id": "SC01",
                "to_scene_id": "SC02",
                "rationale_ru":
                    "Перейти от дня к ночной кульминации.",
            },
        ],
    }


def test_writer_builds_narration():
    result = NarrativeWriterRC2(
        project_id="hogueras",
    ).run(strategy_payload())

    payload = result.to_dict()

    assert payload["project_id"] == "hogueras"
    assert payload["language"] == "ru"
    assert len(payload["scenes"]) == 2
    assert payload["total_target_words"] > 0
    assert payload["full_narration_ru"]


def test_scene_timing_is_continuous():
    result = NarrativeWriterRC2(
        project_id="hogueras",
    ).run(strategy_payload())

    first, second = result.scenes

    assert first.start_sec == 0.0
    assert first.end_sec == 60.0
    assert second.start_sec == 60.0
    assert second.end_sec == 120.0


def test_each_scene_references_source_assets():
    result = NarrativeWriterRC2(
        project_id="hogueras",
    ).run(strategy_payload())

    assert result.scenes[0].source_asset_ids
    assert result.scenes[1].source_asset_ids


def test_target_words_follow_duration():
    result = NarrativeWriterRC2(
        project_id="hogueras",
        words_per_minute=120.0,
    ).run(strategy_payload())

    assert result.scenes[0].target_words == 120
    assert result.scenes[1].target_words == 120


def test_empty_strategy_is_rejected():
    writer = NarrativeWriterRC2(
        project_id="hogueras",
    )

    try:
        writer.run({
            "strategy": {
                "language": "ru",
                "target_duration_sec": 120,
            },
            "scenes": [],
        })
    except ValueError as exc:
        assert "no scenes" in str(exc)
    else:
        raise AssertionError(
            "ValueError was not raised"
        )
