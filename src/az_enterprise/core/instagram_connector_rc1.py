from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_GRAPH_URL = "https://graph.instagram.com"
DEFAULT_API_VERSION = "v23.0"


@dataclass(frozen=True)
class InstagramProfileRC1:
    user_id: str
    username: str
    account_type: str | None = None
    media_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "account_type": self.account_type,
            "media_count": self.media_count,
        }


class InstagramConnectorRC1:
    """
    ATLAS ZERO ? Instagram Connector RC1.

    Uses Instagram API with Instagram Login.

    Canonical credentials:
        INSTAGRAM_ACCESS_TOKEN
        INSTAGRAM_USER_ID

    Rules:
        - token is never logged;
        - no publishing side effects in profile/capability checks;
        - graph.instagram.com is the canonical host for this login mode.
    """

    def __init__(
        self,
        *,
        access_token: str | None = None,
        user_id: str | None = None,
        graph_url: str = DEFAULT_GRAPH_URL,
        api_version: str = DEFAULT_API_VERSION,
        timeout_sec: int = 20,
        env_path: Path | str | None = None,
    ) -> None:

        self.env_path = (
            Path(env_path)
            if env_path is not None
            else Path.cwd() / ".env"
        )

        local_env = self._read_env_file(
            self.env_path
        )

        self.access_token = (
            access_token
            or os.getenv(
                "INSTAGRAM_ACCESS_TOKEN",
                "",
            ).strip()
            or local_env.get(
                "INSTAGRAM_ACCESS_TOKEN",
                "",
            )
        ).strip()

        self.user_id = (
            user_id
            or os.getenv(
                "INSTAGRAM_USER_ID",
                "",
            ).strip()
            or local_env.get(
                "INSTAGRAM_USER_ID",
                "",
            )
        ).strip()

        self.graph_url = (
            str(graph_url)
            .rstrip("/")
        )

        self.api_version = (
            str(api_version)
            .strip("/")
        )

        self.timeout_sec = int(
            timeout_sec
        )

    @staticmethod
    def _read_env_file(
        path: Path,
    ) -> dict[str, str]:
        """
        Read ATLAS ZERO local .env without mutating
        process environment.

        Explicit constructor values and non-empty
        OS environment variables always have priority.
        """

        if not path.is_file():
            return {}

        values: dict[str, str] = {}

        for raw in path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        ).splitlines():

            line = raw.strip()

            if (
                not line
                or line.startswith("#")
                or "=" not in line
            ):
                continue

            key, value = line.split(
                "=",
                1,
            )

            key = key.strip()
            value = value.strip()

            if key:
                values[key] = value

        return values

    def credential_status(
        self,
    ) -> dict[str, Any]:

        return {
            "service": "instagram",
            "login_mode":
                "instagram_login",
            "access_token_present":
                bool(self.access_token),
            "user_id_present":
                bool(self.user_id),
            "ready":
                bool(
                    self.access_token
                    and self.user_id
                ),
        }

    def _require_credentials(
        self,
    ) -> None:

        if not self.access_token:
            raise RuntimeError(
                "INSTAGRAM_ACCESS_TOKEN "
                "is not configured"
            )

        if not self.user_id:
            raise RuntimeError(
                "INSTAGRAM_USER_ID "
                "is not configured"
            )

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        self._require_credentials()

        values = dict(
            params or {}
        )

        values[
            "access_token"
        ] = self.access_token

        encoded = urllib.parse.urlencode(
            values
        )

        url = (
            f"{self.graph_url}/"
            f"{self.api_version}/"
            f"{path.lstrip('/')}"
        )

        data = None

        if method.upper() == "GET":
            if encoded:
                url += "?" + encoded
        else:
            data = encoded.encode(
                "utf-8"
            )

        request = urllib.request.Request(
            url,
            data=data,
            method=method.upper(),
            headers={
                "Accept":
                    "application/json",
                "Content-Type":
                    "application/"
                    "x-www-form-urlencoded",
                "User-Agent":
                    "ATLAS-ZERO-RC2/"
                    "InstagramConnector",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_sec,
            ) as response:

                payload = json.loads(
                    response.read().decode(
                        "utf-8"
                    )
                )

        except urllib.error.HTTPError as exc:

            body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            # Never include request URL because
            # access_token may be present in it.
            raise RuntimeError(
                "Instagram API request failed "
                f"with HTTP {exc.code}: "
                f"{body[:1000]}"
            ) from exc

        except Exception as exc:
            raise RuntimeError(
                "Instagram API request failed"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise RuntimeError(
                "Instagram API returned "
                "unexpected payload"
            )

        return payload

    def profile(
        self,
    ) -> InstagramProfileRC1:

        payload = self._request_json(
            method="GET",
            path="me",
            params={
                "fields":
                    "user_id,username,"
                    "account_type,media_count",
            },
        )

        actual_user_id = str(
            payload.get(
                "user_id",
                payload.get(
                    "id",
                    "",
                ),
            )
        ).strip()

        username = str(
            payload.get(
                "username",
                "",
            )
        ).strip()

        if not actual_user_id:
            raise RuntimeError(
                "Instagram profile response "
                "contains no user id"
            )

        if not username:
            raise RuntimeError(
                "Instagram profile response "
                "contains no username"
            )

        media_count = payload.get(
            "media_count"
        )

        if media_count is not None:
            media_count = int(
                media_count
            )

        return InstagramProfileRC1(
            user_id=actual_user_id,
            username=username,
            account_type=payload.get(
                "account_type"
            ),
            media_count=media_count,
        )

    def verify_identity(
        self,
    ) -> dict[str, Any]:

        profile = self.profile()

        matches = (
            profile.user_id
            == self.user_id
        )

        if not matches:
            raise RuntimeError(
                "Instagram identity mismatch: "
                "configured user id does not "
                "match token identity"
            )

        return {
            "connected": True,
            "identity_match": True,
            "profile":
                profile.to_dict(),
        }

    def create_reel_container(
        self,
        *,
        video_url: str,
        caption: str = "",
        share_to_feed: bool = True,
    ) -> str:
        """
        Create a Reel publishing container.

        This does NOT publish the Reel.
        Instagram must be able to fetch
        video_url from the public internet.
        """

        value = str(
            video_url
        ).strip()

        if not (
            value.startswith("https://")
            or value.startswith("http://")
        ):
            raise ValueError(
                "video_url must be a public "
                "http(s) URL"
            )

        payload = self._request_json(
            method="POST",
            path=f"{self.user_id}/media",
            params={
                "media_type":
                    "REELS",
                "video_url":
                    value,
                "caption":
                    str(caption),
                "share_to_feed":
                    (
                        "true"
                        if share_to_feed
                        else "false"
                    ),
            },
        )

        container_id = str(
            payload.get(
                "id",
                "",
            )
        ).strip()

        if not container_id:
            raise RuntimeError(
                "Instagram container response "
                "contains no id"
            )

        return container_id

    def container_status(
        self,
        container_id: str,
    ) -> dict[str, Any]:
        """
        Return normalized Instagram media-container state.
        """

        value = str(
            container_id
        ).strip()

        if not value:
            raise ValueError(
                "container_id is required"
            )

        payload = self._request_json(
            method="GET",
            path=value,
            params={
                "fields":
                    "status_code,status",
            },
        )

        status_code = str(
            payload.get(
                "status_code",
                "",
            )
        ).strip().upper()

        status_text = payload.get(
            "status"
        )

        return {
            "container_id":
                value,
            "status_code":
                status_code,
            "status":
                status_text,
            "raw":
                payload,
        }

    def publish_container(
        self,
        container_id: str,
    ) -> str:
        """
        Publish a previously FINISHED Instagram
        media container.
        """

        value = str(
            container_id
        ).strip()

        if not value:
            raise ValueError(
                "container_id is required"
            )

        payload = self._request_json(
            method="POST",
            path=f"{self.user_id}/media_publish",
            params={
                "creation_id":
                    value,
            },
        )

        media_id = str(
            payload.get(
                "id",
                "",
            )
        ).strip()

        if not media_id:
            raise RuntimeError(
                "Instagram publish response "
                "contains no media id"
            )

        return media_id

