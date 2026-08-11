import sqlite3

from az_enterprise.core.marketing_intelligence_rc1 import (
    MarketingIntelligenceRC1,
)


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")


def test_marketing_intelligence_rc1():
    db = DB()

    engine = MarketingIntelligenceRC1(
        db=db,
        project_id="test_movie",
    )

    package = engine.build_publication_package(
        title="Test documentary",
        description="Description",
        tags=["history", "documentary"],
        hashtags=["history", "#documentary"],
    )

    assert set(package["platforms"]) == {
        "youtube",
        "instagram",
        "tiktok",
    }

    for platform in package["platforms"]:
        result = engine.save_publication_package(
            platform,
            package["platforms"][platform],
        )

        assert (
            result["state"]
            == "MARKETING_PACKAGE_READY"
        )

    engine.record_snapshot(
        platform="youtube",
        metrics={
            "views": 100,
            "impressions": 1000,
            "ctr": 0.05,
            "watch_time_sec": 5000,
            "avg_view_duration_sec": 50,
            "likes": 10,
            "comments": 3,
            "shares": 2,
            "subscribers_delta": 4,
        },
        captured_at="2026-01-01T00:00:00+00:00",
    )

    engine.record_snapshot(
        platform="youtube",
        metrics={
            "views": 200,
            "impressions": 2000,
            "ctr": 0.06,
            "watch_time_sec": 11000,
            "avg_view_duration_sec": 55,
            "likes": 25,
            "comments": 5,
            "shares": 4,
            "subscribers_delta": 8,
        },
        captured_at="2026-01-02T00:00:00+00:00",
    )

    report = engine.performance_summary(
        "youtube"
    )

    assert (
        report["state"]
        == "PERFORMANCE_SUMMARY_READY"
    )

    assert report["deltas"]["views"] == 100
    assert report["engagement_rate"] > 0
