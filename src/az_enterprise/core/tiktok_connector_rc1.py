from __future__ import annotations

import json
import mimetypes
import os
import urllib.request
from pathlib import Path
from typing import Any

from .tiktok_oauth_rc1 import TikTokOAuthRC1


API_BASE = "https://open.tiktokapis.com"
CREATOR_INFO_URL = API_BASE + "/v2/post/publish/creator_info/query/"
DIRECT_POST_INIT_URL = API_BASE + "/v2/post/publish/video/init/"
STATUS_URL = API_BASE + "/v2/post/publish/status/fetch/"


class TikTokConnectorRC1:
    """
    ATLAS ZERO — TikTok Content Posting Connector RC1.

    Responsibilities:
    - query creator posting capabilities
    - initialize Direct Post
    - upload local video files
    - query publish status

    Video production remains outside this connector.
    """

    def __init__(
        self,
        *,
        oauth: TikTokOAuthRC1 | None = None,
        timeout_sec: int = 60,
    ) -> None:
        self.oauth = oauth or TikTokOAuthRC1()
        self.timeout_sec = int(timeout_sec)

    def credential_status(self) -> dict[str, Any]:
        return self.oauth.credential_status()

    def creator_info(self) -> dict[str, Any]:
        return self._post_json(
            CREATOR_INFO_URL,
            {},
        )

    def init_direct_post(
        self,
        *,
        video_path: str | Path,
        title: str,
        privacy_level: str,
        disable_comment: bool = False,
        disable_duet: bool = False,
        disable_stitch: bool = False,
        video_cover_timestamp_ms: int = 1000,
    ) -> dict[str, Any]:

        path = Path(video_path)

        if not path.is_file():
            raise FileNotFoundError(path)

        video_size = path.stat().st_size

        payload = {
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
                "disable_comment": bool(disable_comment),
                "disable_duet": bool(disable_duet),
                "disable_stitch": bool(disable_stitch),
                "video_cover_timestamp_ms":
                    int(video_cover_timestamp_ms),
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": video_size,
                "total_chunk_count": 1,
            },
        }

        return self._post_json(
            DIRECT_POST_INIT_URL,
            payload,
        )

    def upload_video(
        self,
        *,
        upload_url: str,
        video_path: str | Path,
    ) -> int:

        path = Path(video_path)

        if not path.is_file():
            raise FileNotFoundError(path)

        payload = path.read_bytes()
        size = len(payload)

        mime_type = (
            mimetypes.guess_type(path.name)[0]
            or "video/mp4"
        )

        request = urllib.request.Request(
            upload_url,
            data=payload,
            method="PUT",
            headers={
                "Content-Type": mime_type,
                "Content-Length": str(size),
                "Content-Range":
                    f"bytes 0-{size - 1}/{size}",
                "User-Agent":
                    "ATLAS-ZERO-RC2/TikTokConnector",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout_sec,
        ) as response:
            return int(response.status)

    def publish_status(
        self,
        publish_id: str,
    ) -> dict[str, Any]:

        return self._post_json(
            STATUS_URL,
            {
                "publish_id": publish_id,
            },
        )

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        body = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization":
                    self.oauth.authorization_header(),
                "Content-Type":
                    "application/json; charset=UTF-8",
                "Accept": "application/json",
                "User-Agent":
                    "ATLAS-ZERO-RC2/TikTokConnector",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout_sec,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        error = result.get("error") or {}

        if error.get("code") not in (
            None,
            "",
            "ok",
        ):
            raise RuntimeError(
                "TikTok API error: "
                + json.dumps(
                    error,
                    ensure_ascii=False,
                )
            )

        return result
