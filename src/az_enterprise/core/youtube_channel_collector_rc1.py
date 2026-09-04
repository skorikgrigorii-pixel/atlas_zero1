from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .youtube_connector_rc1 import (
    YouTubeConnectorRC1,
)


class YouTubeChannelCollectorRC1:
    """
    ATLAS ZERO — YouTube Channel Collector RC1.

    Channel-level collector.

    Responsibilities:
    - discover authenticated channel;
    - discover uploads playlist;
    - enumerate all uploaded videos;
    - fetch Data API statistics;
    - fetch Analytics API performance per video;
    - emit normalized channel snapshot artifact.

    It is NOT bound to one film/project.
    """

    ANALYTICS_METRICS = ",".join((
        "views",
        "estimatedMinutesWatched",
        "averageViewDuration",
        "averageViewPercentage",
        "likes",
        "comments",
        "shares",
        "subscribersGained",
        "subscribersLost",
    ))

    def __init__(
        self,
        *,
        connector: YouTubeConnectorRC1,
        root: Path | None = None,
    ) -> None:

        self.connector = connector

        self.root = (
            Path(root)
            if root is not None
            else Path.cwd()
        )

        self.output_dir = (
            self.root
            / "workspace"
            / "channel"
            / "youtube"
        )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ------------------------------------------------------------------
    # Channel discovery
    # ------------------------------------------------------------------

    def discover_channel(
        self,
    ) -> dict[str, Any]:

        payload = self.connector.my_channel()

        items = payload.get("items") or []

        if not items:
            raise RuntimeError(
                "Authenticated YouTube channel "
                "was not found"
            )

        channel = items[0]

        content_details = (
            channel.get("contentDetails")
            or {}
        )

        related = (
            content_details.get(
                "relatedPlaylists"
            )
            or {}
        )

        uploads_playlist = str(
            related.get("uploads", "")
        ).strip()

        if not uploads_playlist:
            raise RuntimeError(
                "YouTube uploads playlist "
                "was not found"
            )

        return {
            "channel_id":
                channel.get("id"),

            "title":
                (
                    channel.get("snippet")
                    or {}
                ).get("title"),

            "uploads_playlist_id":
                uploads_playlist,

            "statistics":
                channel.get("statistics")
                or {},
        }

    # ------------------------------------------------------------------
    # Enumerate uploaded videos
    # ------------------------------------------------------------------

    def discover_video_ids(
        self,
        uploads_playlist_id: str,
    ) -> list[str]:

        ids: list[str] = []

        page_token: str | None = None

        while True:

            payload = (
                self.connector.playlist_items(
                    playlist_id=
                        uploads_playlist_id,

                    page_token=
                        page_token,

                    max_results=50,
                )
            )

            for item in (
                payload.get("items")
                or []
            ):

                video_id = str(
                    (
                        item.get(
                            "contentDetails"
                        )
                        or {}
                    ).get(
                        "videoId",
                        "",
                    )
                ).strip()

                if (
                    video_id
                    and video_id not in ids
                ):
                    ids.append(video_id)

            page_token = (
                payload.get(
                    "nextPageToken"
                )
            )

            if not page_token:
                break

        return ids

    # ------------------------------------------------------------------
    # Data API metadata
    # ------------------------------------------------------------------

    def fetch_video_metadata(
        self,
        video_ids: list[str],
    ) -> dict[str, dict[str, Any]]:

        result: dict[
            str,
            dict[str, Any],
        ] = {}

        for index in range(
            0,
            len(video_ids),
            50,
        ):

            chunk = video_ids[
                index:index + 50
            ]

            payload = self.connector.videos(
                chunk
            )

            for item in (
                payload.get("items")
                or []
            ):

                video_id = str(
                    item.get("id", "")
                ).strip()

                if not video_id:
                    continue

                snippet = (
                    item.get("snippet")
                    or {}
                )

                statistics = (
                    item.get("statistics")
                    or {}
                )

                status = (
                    item.get("status")
                    or {}
                )

                content = (
                    item.get("contentDetails")
                    or {}
                )

                result[video_id] = {
                    "video_id":
                        video_id,

                    "title":
                        snippet.get("title"),

                    "description":
                        snippet.get(
                            "description"
                        ),

                    "published_at":
                        snippet.get(
                            "publishedAt"
                        ),

                    "channel_id":
                        snippet.get(
                            "channelId"
                        ),

                    "duration_iso8601":
                        content.get(
                            "duration"
                        ),

                    "privacy_status":
                        status.get(
                            "privacyStatus"
                        ),

                    "data_api_statistics": {
                        "views":
                            self._integer(
                                statistics.get(
                                    "viewCount"
                                )
                            ),

                        "likes":
                            self._integer(
                                statistics.get(
                                    "likeCount"
                                )
                            ),

                        "comments":
                            self._integer(
                                statistics.get(
                                    "commentCount"
                                )
                            ),
                    },
                }

        return result

    # ------------------------------------------------------------------
    # Analytics API
    # ------------------------------------------------------------------

    def fetch_video_analytics(
        self,
        *,
        video_id: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:

        payload = (
            self.connector.analytics_report(
                start_date=start_date,
                end_date=end_date,

                metrics=
                    self.ANALYTICS_METRICS,

                filters=
                    f"video=={video_id}",
            )
        )

        columns = [
            str(
                column.get(
                    "name",
                    "",
                )
            )
            for column in (
                payload.get(
                    "columnHeaders"
                )
                or []
            )
        ]

        rows = (
            payload.get("rows")
            or []
        )

        if not rows:
            return {}

        row = rows[0]

        return {
            columns[index]:
                row[index]

            for index
            in range(
                min(
                    len(columns),
                    len(row),
                )
            )
        }


    # ------------------------------------------------------------------
    # AZ_CHANNEL_ANALYTICS_RC1
    # Channel-level Analytics API breakdowns
    # ------------------------------------------------------------------

    @staticmethod
    def _analytics_rows(
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:

        columns = [
            str(
                column.get(
                    "name",
                    "",
                )
            )
            for column in (
                payload.get(
                    "columnHeaders"
                )
                or []
            )
        ]

        result = []

        for row in (
            payload.get("rows")
            or []
        ):

            result.append({
                columns[index]:
                    row[index]

                for index
                in range(
                    min(
                        len(columns),
                        len(row),
                    )
                )
            })

        return result


    def fetch_channel_analytics(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> tuple[
        dict[str, Any],
        list[dict[str, str]],
    ]:

        specs = {
            "traffic_source": {
                "metrics":
                    "views,estimatedMinutesWatched",
                "dimensions":
                    "insightTrafficSourceType",
            },

            "device_type": {
                "metrics":
                    "views,estimatedMinutesWatched",
                "dimensions":
                    "deviceType",
            },

            "geography": {
                "metrics":
                    "views,estimatedMinutesWatched",
                "dimensions":
                    "country",
            },

            "subscribed_status": {
                "metrics":
                    "views,estimatedMinutesWatched",
                "dimensions":
                    "subscribedStatus",
            },

            "day_timeseries": {
                "metrics": (
                    "views,"
                    "estimatedMinutesWatched,"
                    "subscribersGained,"
                    "subscribersLost"
                ),
                "dimensions":
                    "day",
            },
        }

        result = {}
        failures = []

        for name, spec in specs.items():

            try:

                payload = (
                    self.connector
                    .analytics_report(
                        start_date=start_date,
                        end_date=end_date,
                        metrics=spec["metrics"],
                        dimensions=
                            spec["dimensions"],
                    )
                )

                result[name] = (
                    self._analytics_rows(
                        payload
                    )
                )

            except Exception as exc:

                result[name] = []

                failures.append({
                    "breakdown":
                        name,

                    "error":
                        str(exc),
                })

        return (
            result,
            failures,
        )


    # ------------------------------------------------------------------
    # Full channel collection
    # ------------------------------------------------------------------

    def collect(
        self,
        *,
        start_date: str = "2005-01-01",
        end_date: str | None = None,
        include_private: bool = False,
    ) -> dict[str, Any]:

        end_date = (
            end_date
            or date.today().isoformat()
        )

        channel = (
            self.discover_channel()
        )

        video_ids = (
            self.discover_video_ids(
                channel[
                    "uploads_playlist_id"
                ]
            )
        )

        metadata = (
            self.fetch_video_metadata(
                video_ids
            )
        )

        videos: list[
            dict[str, Any]
        ] = []

        analytics_failures = []

        (
            channel_analytics,
            channel_analytics_failures,
        ) = self.fetch_channel_analytics(
            start_date=start_date,
            end_date=end_date,
        )

        for video_id in video_ids:

            item = metadata.get(
                video_id,
                {
                    "video_id":
                        video_id
                },
            )

            if (
                not include_private
                and item.get(
                    "privacy_status"
                )
                not in (
                    None,
                    "public",
                )
            ):
                continue

            try:
                analytics = (
                    self.fetch_video_analytics(
                        video_id=video_id,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )

            except Exception as exc:

                analytics = {}

                analytics_failures.append({
                    "video_id":
                        video_id,

                    "error":
                        str(exc),
                })

            item = dict(item)

            data_views = (
                (
                    item.get(
                        "data_api_statistics"
                    )
                    or {}
                ).get("views")
            )

            analytics_views = (
                analytics.get("views")
                if analytics
                else None
            )

            analytics_pending = bool(
                data_views is not None
                and int(data_views) > 0
                and (
                    analytics_views is None
                    or int(analytics_views) == 0
                )
            )

            item[
                "analytics"
            ] = analytics

            item[
                "analytics_state"
            ] = (
                "ANALYTICS_PENDING"
                if analytics_pending
                else "ANALYTICS_READY"
            )

            videos.append(item)

        result = {
            "schema":
                "atlas_zero.youtube_channel_snapshot.rc1",

            "state":
                "YOUTUBE_CHANNEL_SNAPSHOT_READY",

            "captured_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "period": {
                "start_date":
                    start_date,

                "end_date":
                    end_date,
            },

            "channel":
                channel,

            "video_count":
                len(videos),

            "videos":
                videos,

            "analytics_failures":
                analytics_failures,

            "channel_analytics":
                channel_analytics,

            "channel_analytics_failures":
                channel_analytics_failures,
        }

        self._save(
            result
        )

        return result

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def _save(
        self,
        payload: dict[str, Any],
    ) -> None:

        latest = (
            self.output_dir
            / "channel_latest.json"
        )

        latest.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        history = (
            self.output_dir
            / "channel_history.jsonl"
        )

        with history.open(
            "a",
            encoding="utf-8",
        ) as stream:

            stream.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    @staticmethod
    def _integer(
        value: Any,
    ) -> int | None:

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None
