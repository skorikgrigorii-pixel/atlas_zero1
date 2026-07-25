from az_enterprise.core.event_discovery_engine_rc2 import (
    EventDiscoveryEngineRC2,
)


def row(
    asset_id,
    event_type,
    confidence,
    status,
    off_topic,
    time_period="day",
):
    return {
        "asset_id": asset_id,
        "filename": f"{asset_id}.mp4",
        "media_type": "video",
        "event_type": event_type,
        "event_confidence": confidence,
        "relevance_status": status,
        "relevance_score": 1.0 - off_topic,
        "off_topic_score": off_topic,
        "time_period": time_period,
        "description": "test",
        "story_value": 0.8,
        "evidence": {},
    }


def test_clear_private_content_is_excluded():
    report = {
        "project_id": "hogueras",
        "results": [
            row(
                "private-1",
                "unrelated_private_content",
                0.9,
                "OFF_TOPIC",
                0.95,
            ),
        ],
    }

    result = EventDiscoveryEngineRC2().run(
        report
    )

    assert result["excluded_assets_total"] == 1
    assert result["included_assets_total"] == 0
    assert (
        result["off_topic_assets"][0]
        ["recommended_action"]
        == "EXCLUDE"
    )


def test_conflicting_event_is_reviewed_not_excluded():
    report = {
        "project_id": "hogueras",
        "results": [
            row(
                "monument-1",
                "monument",
                0.8,
                "OFF_TOPIC",
                0.82,
            ),
        ],
    }

    engine = EventDiscoveryEngineRC2(
        off_topic_exclude_threshold=0.90,
    )

    result = engine.run(report)

    assert result["excluded_assets_total"] == 0
    assert result["review_assets_total"] == 1
    assert result["included_assets_total"] == 1


def test_low_confidence_material_is_reviewed():
    report = {
        "project_id": "hogueras",
        "results": [
            row(
                "street-1",
                "street_festival",
                0.3,
                "RELEVANT",
                0.1,
            ),
        ],
    }

    result = EventDiscoveryEngineRC2().run(
        report
    )

    assert result["review_assets_total"] == 1
    assert result["included_assets_total"] == 1


def test_clusters_split_by_event_and_time():
    report = {
        "project_id": "hogueras",
        "results": [
            row(
                "fireworks-day",
                "fireworks",
                0.8,
                "RELEVANT",
                0.02,
                "day",
            ),
            row(
                "fireworks-night",
                "fireworks",
                0.9,
                "RELEVANT",
                0.01,
                "night",
            ),
            row(
                "parade-day",
                "parade",
                0.75,
                "RELEVANT",
                0.01,
                "day",
            ),
        ],
    }

    result = EventDiscoveryEngineRC2().run(
        report
    )

    cluster_ids = {
        cluster["cluster_id"]
        for cluster in result[
            "event_clusters"
        ]
    }

    assert (
        "cluster-fireworks-day"
        in cluster_ids
    )
    assert (
        "cluster-fireworks-night"
        in cluster_ids
    )
    assert (
        "cluster-parade-day"
        in cluster_ids
    )


def test_excluded_assets_do_not_enter_clusters():
    report = {
        "project_id": "hogueras",
        "results": [
            row(
                "private-1",
                "unrelated_private_content",
                0.95,
                "OFF_TOPIC",
                0.98,
            ),
            row(
                "parade-1",
                "parade",
                0.8,
                "RELEVANT",
                0.01,
            ),
        ],
    }

    result = EventDiscoveryEngineRC2().run(
        report
    )

    clustered_ids = {
        asset_id
        for cluster in result[
            "event_clusters"
        ]
        for asset_id in cluster["asset_ids"]
    }

    assert "private-1" not in clustered_ids
    assert "parade-1" in clustered_ids
