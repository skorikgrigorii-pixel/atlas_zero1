from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass
class YouTubeTokenRC1:
    access_token: str
    expires_at: float
    token_type: str = "Bearer"

    def valid(self, *, margin_sec: int = 60) -> bool:
        return bool(
            self.access_token
            and time.time() < self.expires_at - margin_sec
        )


class YouTubeOAuthRC1:
    """
    ATLAS ZERO — YouTube OAuth RC1.

    Canonical credentials:
    - YOUTUBE_CLIENT_ID
    - YOUTUBE_CLIENT_SECRET
    - YOUTUBE_REFRESH_TOKEN

    Legacy fallback:
    - YOUTUBE_OAUTH_TOKEN

    Access tokens are cached only in memory.
    """

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        legacy_access_token: str | None = None,
        timeout_sec: int = 15,
    ) -> None:

        self.client_id = (
            client_id
            or os.getenv("YOUTUBE_CLIENT_ID", "")
        ).strip()

        self.client_secret = (
            client_secret
            or os.getenv("YOUTUBE_CLIENT_SECRET", "")
        ).strip()

        self.refresh_token = (
            refresh_token
            or os.getenv("YOUTUBE_REFRESH_TOKEN", "")
        ).strip()

        self.legacy_access_token = (
            legacy_access_token
            or os.getenv("YOUTUBE_OAUTH_TOKEN", "")
        ).strip()

        self.timeout_sec = int(timeout_sec)

        self._cached_token: YouTubeTokenRC1 | None = None

    def credential_status(self) -> dict[str, Any]:

        refresh_ready = all((
            self.client_id,
            self.client_secret,
            self.refresh_token,
        ))

        legacy_ready = bool(
            self.legacy_access_token
        )

        return {
            "service": "youtube",
            "refresh_oauth_ready": refresh_ready,
            "legacy_access_token_ready": legacy_ready,
            "canonical_credentials": {
                "client_id": bool(self.client_id),
                "client_secret": bool(self.client_secret),
                "refresh_token": bool(self.refresh_token),
            },
        }

    def access_token(self) -> str:

        if (
            self._cached_token is not None
            and self._cached_token.valid()
        ):
            return self._cached_token.access_token

        if all((
            self.client_id,
            self.client_secret,
            self.refresh_token,
        )):
            token = self._refresh()
            self._cached_token = token
            return token.access_token

        if self.legacy_access_token:
            return self.legacy_access_token

        raise RuntimeError(
            "YouTube OAuth credentials are not configured. "
            "Set YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET and "
            "YOUTUBE_REFRESH_TOKEN."
        )

    def authorization_header(self) -> str:
        return "Bearer " + self.access_token()

    def _refresh(self) -> YouTubeTokenRC1:

        body = urllib.parse.urlencode({
            "client_id":
                self.client_id,

            "client_secret":
                self.client_secret,

            "refresh_token":
                self.refresh_token,

            "grant_type":
                "refresh_token",
        }).encode("utf-8")

        request = urllib.request.Request(
            TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded",
                "Accept":
                    "application/json",
                "User-Agent":
                    "ATLAS-ZERO-RC2/YouTubeOAuth",
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

        except Exception as exc:
            raise RuntimeError(
                "YouTube OAuth token refresh failed"
            ) from exc

        access_token = str(
            payload.get(
                "access_token",
                "",
            )
        ).strip()

        if not access_token:
            raise RuntimeError(
                "YouTube OAuth response "
                "contains no access_token"
            )

        expires_in = int(
            payload.get(
                "expires_in",
                3600,
            )
        )

        token_type = str(
            payload.get(
                "token_type",
                "Bearer",
            )
        )

        return YouTubeTokenRC1(
            access_token=access_token,
            expires_at=time.time() + expires_in,
            token_type=token_type,
        )
