from az_enterprise.core.story_strategy_engine_rc2 import (
    StoryStrategyEngineRC2,
)


def cluster(
    cluster_id,
    event_type,
    time_period,
    assets,
    story_value=0.8,
):
    return {
        "cluster_id": cluster_id,
        "event_type": event_type,
        "title_ru": event_type,
        "description_ru": "????????",
        "asset_ids": tuple(assets),
        "confidence": 0.8,
        "time_period": time_period,
        "chronology_order": 1,
        "total_duration_sec": 30.0,
        "story_value": story_value,
    }


def make_report():
    return {
        "project_id": "hogueras",
        "event_clusters": [
            cluster(
                "cluster-monument-day",
                "monument",
                "day",
                ("asset-1", "asset-2"),
                0.9,
            ),
            cluster(
                "cluster-parade-day",
                "parade",
                "day",
                ("asset-3",),
                0.8,
            ),
            cluster(
                "cluster-fireworks-night",
                "fireworks",
                "night",
                ("asset-4",),
                0.95,
            ),
            cluster(
                "cluster-crema-night",
                "crema",
                "night",
                ("asset-5",),
                1.0,
            ),
        ],
    }


def test_engine_builds_strategy():
    result = StoryStrategyEngineRC2(
        project_id="hogueras",
        target_duration_sec=1500.0,
    ).run(make_report())

    payload = result.to_dict()

    assert payload["project_id"] == "hogueras"
    assert (
        payload["strategy"]
        ["narrative_strategy"]
        == "event_progression"
    )
    assert len(payload["acts"]) >= 1
    assert len(payload["scenes"]) == 4
    assert len(payload["transitions"]) == 3


def test_engine_uses_existing_assets_only():
    result = StoryStrategyEngineRC2(
        project_id="hogueras",
        use_existing_assets_only=True,
        allow_generated_visuals=False,
    ).run(make_report())

    assert (
        result.strategy
        .use_existing_assets_only
        is True
    )
    assert (
        result.strategy
        .allow_generated_visuals
        is False
    )


def test_scene_order_follows_event_progression():
    result = StoryStrategyEngineRC2(
        project_id="hogueras",
    ).run(make_report())

    event_titles = [
        scene.title_ru
        for scene in result.scenes
    ]

    assert event_titles[0] == (
        "Город праздничных фигур"
    )

    assert event_titles[-1] == (
        "Крема — ночь огня"
    )


def test_duration_matches_target():
    result = StoryStrategyEngineRC2(
        project_id="hogueras",
        target_duration_sec=1500.0,
    ).run(make_report())

    total = sum(
        scene.duration_sec
        for scene in result.scenes
    )

    assert abs(total - 1500.0) <= 0.001


def test_empty_clusters_are_rejected():
    engine = StoryStrategyEngineRC2(
        project_id="hogueras",
    )

    try:
        engine.run({
            "project_id": "hogueras",
            "event_clusters": [],
        })
    except ValueError as exc:
        assert "no clusters" in str(exc)
    else:
        raise AssertionError(
            "ValueError was not raised"
        )
