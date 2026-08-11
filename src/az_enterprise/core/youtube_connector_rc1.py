from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .youtube_oauth_rc1 import (
    YouTubeOAuthRC1,
)


class YouTubeConnectorRC1:
    """
    ATLAS ZERO — canonical YouTube connector.

    Provides authenticated GET access to:

    - YouTube Data API v3
    - YouTube Analytics API v2

    Does not own business analytics logic.
    MarketingIntelligenceRC1 consumes normalized results later.
    """

    DATA_API_BASE = (
        "https://www.googleapis.com/youtube/v3"
    )

    ANALYTICS_API_BASE = (
        "https://youtubeanalytics.googleapis.com/v2"
    )

    def __init__(
        self,
        *,
        oauth: YouTubeOAuthRC1 | None = None,
        timeout_sec: int = 20,
    ) -> None:

        self.oauth = (
            oauth
            if oauth is not None
            else YouTubeOAuthRC1()
        )

        self.timeout_sec = int(timeout_sec)

    def credential_status(
        self,
    ) -> dict[str, Any]:

        return self.oauth.credential_status()

    def get(
        self,
        *,
        api: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        api = str(api).strip().lower()

        if api == "data":
            base = self.DATA_API_BASE

        elif api == "analytics":
            base = self.ANALYTICS_API_BASE

        else:
            raise ValueError(
                f"Unsupported YouTube API: {api}"
            )

        normalized_path = "/" + str(
            path
        ).lstrip("/")

        query = urllib.parse.urlencode(
            {
                key: value
                for key, value
                in (params or {}).items()
                if value is not None
            },
            doseq=True,
        )

        url = base + normalized_path

        if query:
            url += "?" + query

        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization":
                    self.oauth.authorization_header(),

                "Accept":
                    "application/json",

                "User-Agent":
                    "ATLAS-ZERO-RC2/YouTubeConnector",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_sec,
            ) as response:

                raw = response.read()

        except Exception as exc:

            raise RuntimeError(
                f"YouTube API request failed: "
                f"{api}:{normalized_path}"
            ) from exc

        try:
            return json.loads(
                raw.decode("utf-8")
            )

        except Exception as exc:
            raise RuntimeError(
                "YouTube API returned invalid JSON"
            ) from exc

    # ------------------------------------------------------------------
    # Data API helpers
    # ------------------------------------------------------------------

    def my_channel(
        self,
    ) -> dict[str, Any]:

        return self.get(
            api="data",
            path="/channels",
            params={
                "part":
                    "id,snippet,contentDetails,statistics",

                "mine":
                    "true",
            },
        )

    def video(
        self,
        video_id: str,
    ) -> dict[str, Any]:

        video_id = str(
            video_id
        ).strip()

        if not video_id:
            raise ValueError(
                "video_id is required"
            )

        return self.get(
            api="data",
            path="/videos",
            params={
                "part":
                    "id,snippet,contentDetails,statistics",

                "id":
                    video_id,
            },
        )

    def playlist_items(
        self,
        *,
        playlist_id: str,
        page_token: str | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:

        playlist_id = str(
            playlist_id
        ).strip()

        if not playlist_id:
            raise ValueError(
                "playlist_id is required"
            )

        return self.get(
            api="data",
            path="/playlistItems",
            params={
                "part":
                    "snippet,contentDetails",

                "playlistId":
                    playlist_id,

                "maxResults":
                    min(
                        50,
                        max(
                            1,
                            int(max_results),
                        ),
                    ),

                "pageToken":
                    page_token,
            },
        )

    def videos(
        self,
        video_ids: list[str],
    ) -> dict[str, Any]:

        normalized = [
            str(video_id).strip()
            for video_id in video_ids
            if str(video_id).strip()
        ]

        if not normalized:
            raise ValueError(
                "video_ids are required"
            )

        if len(normalized) > 50:
            raise ValueError(
                "YouTube Data API supports "
                "maximum 50 video IDs per request"
            )

        return self.get(
            api="data",
            path="/videos",
            params={
                "part":
                    "id,snippet,contentDetails,statistics,status",

                "id":
                    ",".join(normalized),
            },
        )

    # ------------------------------------------------------------------
    # Analytics API helper
    # ------------------------------------------------------------------

    def analytics_report(
        self,
        *,
        start_date: str,
        end_date: str,
        metrics: str,
        dimensions: str | None = None,
        filters: str | None = None,
        sort: str | None = None,
        max_results: int | None = None,
    ) -> dict[str, Any]:

        if not start_date:
            raise ValueError(
                "start_date is required"
            )

        if not end_date:
            raise ValueError(
                "end_date is required"
            )

        if not metrics:
            raise ValueError(
                "metrics is required"
            )

        return self.get(
            api="analytics",
            path="/reports",
            params={
                "ids":
                    "channel==MINE",

                "startDate":
                    start_date,

                "endDate":
                    end_date,

                "metrics":
                    metrics,

                "dimensions":
                    dimensions,

                "filters":
                    filters,

                "sort":
                    sort,

                "maxResults":
                    max_results,
            },
        )
