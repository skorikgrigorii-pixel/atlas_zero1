from pathlib import Path

from az_enterprise.core.youtube_channel_collector_rc1 import (
    YouTubeChannelCollectorRC1,
)


class ConnectorStub:

    def my_channel(self):

        return {
            "items": [{
                "id": "CHANNEL",
                "snippet": {
                    "title": "ATLAS ZERO",
                },
                "contentDetails": {
                    "relatedPlaylists": {
                        "uploads":
                            "UPLOADS",
                    },
                },
                "statistics": {
                    "videoCount": "3",
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

        assert playlist_id == "UPLOADS"

        return {
            "items": [
                {
                    "contentDetails": {
                        "videoId":
                            "VIDEO_1",
                    },
                },
                {
                    "contentDetails": {
                        "videoId":
                            "VIDEO_2",
                    },
                },
                {
                    "contentDetails": {
                        "videoId":
                            "VIDEO_3",
                    },
                },
            ]
        }

    def videos(self, video_ids):

        return {
            "items": [
                {
                    "id": video_id,

                    "snippet": {
                        "title":
                            f"Movie {video_id}",

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
                }
                for video_id
                in video_ids
            ]
        }

    def analytics_report(
        self,
        *,
        start_date,
        end_date,
        metrics,
        dimensions=None,
        filters=None,
        sort=None,
        max_results=None,
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
                25.0,
                10,
                2,
                3,
                5,
                1,
            ]],
        }


def test_youtube_channel_collector(
    tmp_path: Path,
):

    collector = (
        YouTubeChannelCollectorRC1(
            connector=ConnectorStub(),
            root=tmp_path,
        )
    )

    result = collector.collect(
        start_date="2026-01-01",
        end_date="2026-01-31",
    )

    assert (
        result["state"]
        == "YOUTUBE_CHANNEL_SNAPSHOT_READY"
    )

    assert result["video_count"] == 3

    assert len(
        result["videos"]
    ) == 3

    assert (
        result["videos"][0]
        ["analytics"]
        ["views"]
        == 100
    )

    latest = (
        tmp_path
        / "workspace"
        / "channel"
        / "youtube"
        / "channel_latest.json"
    )

    assert latest.is_file()
