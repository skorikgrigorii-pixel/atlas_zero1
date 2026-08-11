from az_enterprise.core.youtube_oauth_rc1 import (
    YouTubeOAuthRC1,
)


def test_youtube_oauth_status():

    oauth = YouTubeOAuthRC1(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
    )

    status = oauth.credential_status()

    assert (
        status["refresh_oauth_ready"]
        is True
    )

    assert (
        status["canonical_credentials"][
            "refresh_token"
        ]
        is True
    )


def test_youtube_oauth_legacy():

    oauth = YouTubeOAuthRC1(
        legacy_access_token="legacy-token",
    )

    assert (
        oauth.access_token()
        == "legacy-token"
    )
