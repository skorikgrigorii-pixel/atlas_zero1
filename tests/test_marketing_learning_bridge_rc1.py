import sqlite3

from az_enterprise.core.marketing_learning_bridge_rc1 import (
    MarketingLearningBridgeRC1,
)


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")


class EventBusStub:
    def __init__(self):
        self.events = []

    def emit(self, event_name, payload):
        self.events.append(
            (event_name, payload)
        )


def test_marketing_learning_bridge_rc1():

    db = DB()
    bus = EventBusStub()

    bridge = MarketingLearningBridgeRC1(
        db=db,
        project_id="movie_test",
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
        captured_at="2026-01-01T00:00:00+00:00",
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
        captured_at="2026-01-02T00:00:00+00:00",
    )

    result = bridge.process_platform(
        "youtube"
    )

    assert (
        result["analytics_state"]
        == "PERFORMANCE_SUMMARY_READY"
    )

    assert (
        result["learning_state"]
        == "LEARNING_UPDATED"
    )

    assert "ANALYTICS_RECEIVED" in result[
        "events_emitted"
    ]

    assert "LEARNING_UPDATED" in result[
        "events_emitted"
    ]

    advisory = bridge.director_advisory_payload()

    assert advisory["mode"] == "advisory_only"
    assert advisory["may_override_director"] is False
    assert advisory["profile_count"] > 0

    names = [
        event[0]
        for event in bus.events
    ]

    assert "ANALYTICS_RECEIVED" in names
    assert "LEARNING_UPDATED" in names
