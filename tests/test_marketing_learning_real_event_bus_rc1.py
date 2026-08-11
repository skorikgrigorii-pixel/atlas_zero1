import sqlite3

from az_enterprise.core.events import EventBus

from az_enterprise.core.marketing_learning_bridge_rc1 import (
    MarketingLearningBridgeRC1,
)


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")


def test_bridge_with_real_event_bus():

    db = DB()

    bus = EventBus(
        db=None,
        project_id="movie",
    )

    received = []

    bus.on(
        "ANALYTICS_RECEIVED",
        lambda payload:
            received.append(
                (
                    "analytics",
                    payload,
                )
            ),
    )

    bus.on(
        "LEARNING_UPDATED",
        lambda payload:
            received.append(
                (
                    "learning",
                    payload,
                )
            ),
    )

    bridge = MarketingLearningBridgeRC1(
        db=db,
        project_id="movie",
        event_bus=bus,
    )

    bridge.marketing.record_snapshot(
        platform="youtube",
        metrics={
            "views": 100,
            "impressions": 1000,
            "ctr": 0.05,
            "watch_time_sec": 5000,
            "avg_view_duration_sec": 50,
            "likes": 10,
            "comments": 2,
            "shares": 1,
            "subscribers_delta": 3,
        },
        captured_at=
            "2026-01-01T00:00:00+00:00",
    )

    bridge.marketing.record_snapshot(
        platform="youtube",
        metrics={
            "views": 250,
            "impressions": 2000,
            "ctr": 0.065,
            "watch_time_sec": 13000,
            "avg_view_duration_sec": 52,
            "likes": 30,
            "comments": 6,
            "shares": 4,
            "subscribers_delta": 8,
        },
        captured_at=
            "2026-01-02T00:00:00+00:00",
    )

    result = bridge.process_platform(
        "youtube"
    )

    assert (
        result["learning_state"]
        == "LEARNING_UPDATED"
    )

    names = [
        item[0]
        for item in received
    ]

    assert "analytics" in names
    assert "learning" in names
