import io
import json
import urllib.request

import pytest

from az_enterprise.core.instagram_connector_rc1 import (
    InstagramConnectorRC1,
)


class FakeResponse:
    def __init__(
        self,
        payload,
    ):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False

    def read(self):
        return json.dumps(
            self.payload
        ).encode("utf-8")


def test_credential_status():

    connector = InstagramConnectorRC1(
        access_token="secret",
        user_id="123",
    )

    status = (
        connector.credential_status()
    )

    assert status["ready"] is True
    assert (
        status["login_mode"]
        == "instagram_login"
    )


def test_profile_and_identity(
    monkeypatch,
):

    def fake_urlopen(
        request,
        timeout,
    ):
        return FakeResponse({
            "user_id": "123",
            "username":
                "atlaszero_channel",
            "account_type":
                "MEDIA_CREATOR",
            "media_count": 0,
        })

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        fake_urlopen,
    )

    connector = InstagramConnectorRC1(
        access_token="secret",
        user_id="123",
    )

    result = (
        connector.verify_identity()
    )

    assert result[
        "connected"
    ] is True

    assert result[
        "identity_match"
    ] is True

    assert (
        result["profile"]["username"]
        == "atlaszero_channel"
    )


def test_identity_mismatch_rejected(
    monkeypatch,
):

    def fake_urlopen(
        request,
        timeout,
    ):
        return FakeResponse({
            "user_id": "999",
            "username": "wrong",
        })

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        fake_urlopen,
    )

    connector = InstagramConnectorRC1(
        access_token="secret",
        user_id="123",
    )

    with pytest.raises(
        RuntimeError,
        match="identity mismatch",
    ):
        connector.verify_identity()


def test_reel_container_contract(
    monkeypatch,
):

    captured = {}

    def fake_urlopen(
        request,
        timeout,
    ):

        captured["method"] = (
            request.get_method()
        )

        captured["url"] = (
            request.full_url
        )

        captured["body"] = (
            request.data.decode(
                "utf-8"
            )
        )

        return FakeResponse({
            "id": "container_001"
        })

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        fake_urlopen,
    )

    connector = InstagramConnectorRC1(
        access_token="secret",
        user_id="123",
    )

    result = (
        connector.create_reel_container(
            video_url=(
                "https://example.com/"
                "promo.mp4"
            ),
            caption="ATLAS ZERO",
        )
    )

    assert result == "container_001"
    assert captured[
        "method"
    ] == "POST"

    assert (
        "/123/media"
        in captured["url"]
    )

    assert (
        "media_type=REELS"
        in captured["body"]
    )


def test_local_video_path_rejected():

    connector = InstagramConnectorRC1(
        access_token="secret",
        user_id="123",
    )

    with pytest.raises(
        ValueError,
    ):
        connector.create_reel_container(
            video_url=(
                "C:/video/promo.mp4"
            )
        )
