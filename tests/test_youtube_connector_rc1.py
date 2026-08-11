from az_enterprise.core.youtube_connector_rc1 import (
    YouTubeConnectorRC1,
)


class OAuthStub:

    def credential_status(self):
        return {
            "refresh_oauth_ready": True,
        }

    def authorization_header(self):
        return "Bearer TEST"


def test_youtube_connector_contract():

    connector = YouTubeConnectorRC1(
        oauth=OAuthStub(),
    )

    assert (
        connector.DATA_API_BASE
        == "https://www.googleapis.com/youtube/v3"
    )

    assert (
        connector.ANALYTICS_API_BASE
        == "https://youtubeanalytics.googleapis.com/v2"
    )

    assert (
        connector.credential_status()[
            "refresh_oauth_ready"
        ]
        is True
    )


def test_youtube_connector_validation():

    connector = YouTubeConnectorRC1(
        oauth=OAuthStub(),
    )

    try:
        connector.video("")
        assert False

    except ValueError:
        pass
