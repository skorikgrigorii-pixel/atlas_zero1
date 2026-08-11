import sqlite3

from az_enterprise.core.youtube_channel_intelligence_rc1 import (
    YouTubeChannelIntelligenceRC1,
)


class DB:

    def __init__(self):
        self.conn = sqlite3.connect(
            ":memory:"
        )

    def execute(
        self,
        sql,
        params=(),
    ):
        cursor = self.conn.execute(
            sql,
            params,
        )
        self.conn.commit()
        return cursor

    def executemany(
        self,
        sql,
        params,
    ):
        cursor = self.conn.executemany(
            sql,
            params,
        )
        self.conn.commit()
        return cursor

    def executescript(
        self,
        sql,
    ):
        cursor = self.conn.executescript(
            sql
        )
        self.conn.commit()
        return cursor


def test_channel_intelligence_pending_guard():

    db = DB()

    intelligence = (
        YouTubeChannelIntelligenceRC1(
            db=db,
        )
    )

    intelligence.link_project(
        video_id="VIDEO_READY",
        project_id="movie_ready",
    )

    snapshot = {
        "state":
            "YOUTUBE_CHANNEL_SNAPSHOT_READY",

        "captured_at":
            "2026-08-08T00:00:00+00:00",

        "videos": [
            {
                "video_id":
                    "VIDEO_READY",

                "title":
                    "Ready Film",

                "privacy_status":
                    "public",

                "analytics_state":
                    "ANALYTICS_READY",

                "data_api_statistics": {
                    "views": 1000,
                    "likes": 100,
                    "comments": 20,
                },

                "analytics": {
                    "views": 1000,
                    "estimatedMinutesWatched":
                        5000,

                    "averageViewDuration":
                        300,

                    "averageViewPercentage":
                        40,

                    "likes": 100,
                    "comments": 20,
                    "shares": 10,

                    "subscribersGained":
                        20,

                    "subscribersLost":
                        2,
                },
            },

            {
                "video_id":
                    "VIDEO_PENDING",

                "title":
                    "Fresh Film",

                "privacy_status":
                    "public",

                "analytics_state":
                    "ANALYTICS_PENDING",

                "data_api_statistics": {
                    "views": 90,
                    "likes": 5,
                    "comments": 1,
                },

                "analytics": {
                    "views": 0,
                    "estimatedMinutesWatched": 0,
                    "averageViewDuration": 0,
                    "averageViewPercentage": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "subscribersGained": 0,
                    "subscribersLost": 0,
                },
            },
        ],
    }

    result = (
        intelligence
        .ingest_channel_snapshot(
            snapshot
        )
    )

    report = result[
        "channel_report"
    ]

    assert report["video_count"] == 2
    assert report["analytics_ready_count"] == 1
    assert report["analytics_pending_count"] == 1

    pending = next(
        item
        for item in report["ranking"]
        if item["video_id"]
        == "VIDEO_PENDING"
    )

    assert pending["views"] == 90

    assert (
        pending[
            "average_view_percentage"
        ]
        is None
    )

    assert (
        pending["score_mode"]
        == "views_only_pending_analytics"
    )

    learning_count = db.conn.execute(
        """
        SELECT COUNT(*)
        FROM learning_profiles
        WHERE project_id='__channel_youtube__'
        """
    ).fetchone()[0]

    assert learning_count >= 2
