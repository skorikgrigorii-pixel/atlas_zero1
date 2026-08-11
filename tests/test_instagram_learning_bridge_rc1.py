from pathlib import Path

from az_enterprise.core.instagram_learning_bridge_rc1 import (
    InstagramLearningBridgeRC1,
)


def make_bridge(
    tmp_path: Path,
):
    return InstagramLearningBridgeRC1(
        project_id="franklin",
        root=tmp_path,
    )


def test_rate_calculation(
    tmp_path: Path,
):

    bridge = make_bridge(
        tmp_path
    )

    signal = bridge.build_signal({
        "candidate_id":
            "promo_001",
        "media_id":
            "media_001",
        "views":
            10,
        "likes":
            2,
        "comments":
            0,
        "shares":
            0,
        "saved":
            0,
        "total_interactions":
            2,
    })

    assert (
        signal.engagement_per_view
        == 0.2
    )

    assert (
        signal.like_rate
        == 0.2
    )

    assert (
        signal.confidence
        == "LOW"
    )

    assert (
        signal.learning_enabled
        is False
    )


def test_medium_confidence(
    tmp_path: Path,
):

    bridge = make_bridge(
        tmp_path
    )

    signal = bridge.build_signal({
        "candidate_id": "x",
        "media_id": "y",
        "views": 150,
    })

    assert (
        signal.confidence
        == "MEDIUM"
    )

    assert (
        signal.learning_enabled
        is True
    )


def test_high_confidence(
    tmp_path: Path,
):

    bridge = make_bridge(
        tmp_path
    )

    signal = bridge.build_signal({
        "candidate_id": "x",
        "media_id": "y",
        "views": 500,
    })

    assert (
        signal.confidence
        == "HIGH"
    )


def test_latest_snapshot_only(
    tmp_path: Path,
):

    bridge = make_bridge(
        tmp_path
    )

    path = bridge.analytics_path

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        '{"media_id":"m1",'
        '"candidate_id":"p1",'
        '"views":10,'
        '"collected_at":"2026-01-01T10:00:00Z"}\n'
        '{"media_id":"m1",'
        '"candidate_id":"p1",'
        '"views":20,'
        '"collected_at":"2026-01-01T11:00:00Z"}\n',
        encoding="utf-8",
    )

    latest = (
        bridge.latest_snapshots()
    )

    assert len(latest) == 1

    assert (
        latest[0]["views"]
        == 20
    )


def test_build_latest_signals(
    tmp_path: Path,
):

    bridge = make_bridge(
        tmp_path
    )

    path = bridge.analytics_path

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        '{"media_id":"m1",'
        '"candidate_id":"p1",'
        '"views":100,'
        '"likes":10,'
        '"total_interactions":10,'
        '"collected_at":"2026-01-01T10:00:00Z"}\n',
        encoding="utf-8",
    )

    signals = (
        bridge.build_latest_signals()
    )

    assert len(signals) == 1

    assert (
        signals[0].learning_enabled
        is True
    )

    assert (
        bridge.learning_path
        .is_file()
    )
