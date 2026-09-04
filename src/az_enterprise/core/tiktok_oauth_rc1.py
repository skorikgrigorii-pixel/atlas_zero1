from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


@dataclass
class TikTokTokenRC1:
    access_token: str
    refresh_token: str
    expires_at: float
    refresh_expires_at: float
    open_id: str = ""
    scope: str = ""
    token_type: str = "Bearer"

    def valid(self, *, margin_sec: int = 60) -> bool:
        return bool(
            self.access_token
            and time.time() < self.expires_at - margin_sec
        )


class TikTokOAuthRC1:
    """
    ATLAS ZERO — TikTok OAuth RC1.

    Canonical credentials:
    - TIKTOK_CLIENT_KEY
    - TIKTOK_CLIENT_SECRET
    - TIKTOK_REFRESH_TOKEN

    Bootstrap:
    - TIKTOK_REDIRECT_URI

    Access tokens are cached only in memory.
    """

    def __init__(
        self,
        *,
        client_key: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        redirect_uri: str | None = None,
        timeout_sec: int = 15,
    ) -> None:

        self.client_key = (
            client_key
            or os.getenv("TIKTOK_CLIENT_KEY", "")
        ).strip()

        self.client_secret = (
            client_secret
            or os.getenv("TIKTOK_CLIENT_SECRET", "")
        ).strip()

        self.refresh_token = (
            refresh_token
            or os.getenv("TIKTOK_REFRESH_TOKEN", "")
        ).strip()

        self.redirect_uri = (
            redirect_uri
            or os.getenv("TIKTOK_REDIRECT_URI", "")
        ).strip()

        self.timeout_sec = int(timeout_sec)
        self._cached_token: TikTokTokenRC1 | None = None

    def credential_status(self) -> dict[str, Any]:

        return {
            "service": "tiktok",
            "refresh_oauth_ready": all((
                self.client_key,
                self.client_secret,
                self.refresh_token,
            )),
            "bootstrap_ready": all((
                self.client_key,
                self.client_secret,
                self.redirect_uri,
            )),
            "canonical_credentials": {
                "client_key": bool(self.client_key),
                "client_secret": bool(self.client_secret),
                "refresh_token": bool(self.refresh_token),
                "redirect_uri": bool(self.redirect_uri),
            },
        }

    def authorization_header(self) -> str:
        return "Bearer " + self.access_token()

    def access_token(self) -> str:

        if (
            self._cached_token is not None
            and self._cached_token.valid()
        ):
            return self._cached_token.access_token

        if all((
            self.client_key,
            self.client_secret,
            self.refresh_token,
        )):
            token = self._refresh()
            self._cached_token = token
            self.refresh_token = token.refresh_token
            return token.access_token

        raise RuntimeError(
            "TikTok OAuth credentials are not configured. "
            "Set TIKTOK_CLIENT_KEY, "
            "TIKTOK_CLIENT_SECRET and "
            "TIKTOK_REFRESH_TOKEN."
        )

    def exchange_code(
        self,
        code: str,
    ) -> TikTokTokenRC1:

        if not all((
            self.client_key,
            self.client_secret,
            self.redirect_uri,
        )):
            raise RuntimeError(
                "TikTok OAuth bootstrap credentials "
                "are not configured."
            )

        payload = self._token_request({
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        })

        token = self._parse_token(payload)
        self._cached_token = token
        self.refresh_token = token.refresh_token
        return token

    def _refresh(self) -> TikTokTokenRC1:

        payload = self._token_request({
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        })

        return self._parse_token(payload)

    def _token_request(
        self,
        fields: dict[str, str],
    ) -> dict[str, Any]:

        body = urllib.parse.urlencode(
            fields
        ).encode("utf-8")

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
                    "ATLAS-ZERO-RC2/TikTokOAuth",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_sec,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        except Exception as exc:
            raise RuntimeError(
                "TikTok OAuth token request failed"
            ) from exc

    @staticmethod
    def _parse_token(
        payload: dict[str, Any],
    ) -> TikTokTokenRC1:

        access_token = str(
            payload.get("access_token", "")
        ).strip()

        refresh_token = str(
            payload.get("refresh_token", "")
        ).strip()

        if not access_token:
            raise RuntimeError(
                "TikTok OAuth response contains "
                "no access_token"
            )

        if not refresh_token:
            raise RuntimeError(
                "TikTok OAuth response contains "
                "no refresh_token"
            )

        expires_in = int(
            payload.get("expires_in", 86400)
        )

        refresh_expires_in = int(
            payload.get(
                "refresh_expires_in",
                31536000,
            )
        )

        return TikTokTokenRC1(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
            refresh_expires_at=(
                time.time() + refresh_expires_in
            ),
            open_id=str(
                payload.get("open_id", "")
            ),
            scope=str(
                payload.get("scope", "")
            ),
            token_type=str(
                payload.get(
                    "token_type",
                    "Bearer",
                )
            ),
        )
