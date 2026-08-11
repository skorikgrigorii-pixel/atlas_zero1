import sqlite3
from pathlib import Path

from az_enterprise.core.youtube_channel_runtime_rc1 import (
    YouTubeChannelRuntimeRC1,
)


class DB:

    def __init__(self):
        self.conn = sqlite3.connect(
            ":memory:"
        )

    def init(self):
        return None

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


class ConnectorStub:

    def my_channel(self):

        return {
            "items": [{
                "id": "CHANNEL",

                "snippet": {
                    "title":
                        "ATLAS ZERO",
                },

                "contentDetails": {
                    "relatedPlaylists": {
                        "uploads":
                            "UPLOADS",
                    },
                },

                "statistics": {
                    "videoCount":
                        "1",
                },
            }]
        }

    def playlist_items(
        self,
        *,
        playlist_id,
        page_token=None,
        max_results=50,
    ):

        return {
            "items": [{
                "contentDetails": {
                    "videoId":
                        "VIDEO_1",
                },
            }]
        }

    def videos(
        self,
        video_ids,
    ):

        return {
            "items": [{
                "id":
                    "VIDEO_1",

                "snippet": {
                    "title":
                        "Film",

                    "publishedAt":
                        "2026-01-01T00:00:00Z",

                    "channelId":
                        "CHANNEL",
                },

                "contentDetails": {
                    "duration":
                        "PT20M",
                },

                "statistics": {
                    "viewCount":
                        "100",

                    "likeCount":
                        "10",

                    "commentCount":
                        "2",
                },

                "status": {
                    "privacyStatus":
                        "public",
                },
            }]
        }

    def analytics_report(
        self,
        **kwargs,
    ):

        return {
            "columnHeaders": [
                {"name": "views"},
                {
                    "name":
                        "estimatedMinutesWatched"
                },
                {
                    "name":
                        "averageViewDuration"
                },
                {
                    "name":
                        "averageViewPercentage"
                },
                {"name": "likes"},
                {"name": "comments"},
                {"name": "shares"},
                {
                    "name":
                        "subscribersGained"
                },
                {
                    "name":
                        "subscribersLost"
                },
            ],

            "rows": [[
                100,
                500,
                300,
                30,
                10,
                2,
                2,
                3,
                0,
            ]],
        }


def test_channel_runtime(
    tmp_path: Path,
):

    db = DB()

    runtime = (
        YouTubeChannelRuntimeRC1(
            db=db,
            connector=ConnectorStub(),
            root=tmp_path,
        )
    )

    result = runtime.run(
        start_date="2026-01-01",
        end_date="2026-08-08",
    )

    assert (
        result["state"]
        == "YOUTUBE_CHANNEL_RUNTIME_COMPLETE"
    )

    assert (
        result["snapshot"][
            "video_count"
        ]
        == 1
    )

    assert (
        result["intelligence"][
            "channel_report"
        ][
            "video_count"
        ]
        == 1
    )
