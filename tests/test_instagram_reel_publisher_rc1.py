from pathlib import Path

import pytest

from az_enterprise.core.instagram_connector_rc1 import (
    InstagramConnectorRC1,
)

from az_enterprise.core.instagram_reel_publisher_rc1 import (
    InstagramReelPublisherRC1,
)

from az_enterprise.core.promotion_media_staging_rc1 import (
    PromotionMediaStagingRC1,
    StagedMediaRC1,
)


class FakeStaging(
    PromotionMediaStagingRC1,
):

    def __init__(
        self,
        *,
        public_url=(
            "https://media.example/"
            "promo.mp4"
        ),
    ):
        self.public_url = public_url
        self.cleaned = []
        self.staged = []

    def stage(
        self,
        local_path,
    ):

        path = self.validate_local_media(
            local_path
        )

        result = StagedMediaRC1(
            local_path=path,
            public_url=self.public_url,
            provider="fake",
            cleanup_token="fake-token",
        )

        self.staged.append(
            result
        )

        return result

    def cleanup(
        self,
        staged,
    ):
        self.cleaned.append(
            staged
        )


class FakeConnector:

    def __init__(
        self,
        statuses,
    ):
        self.statuses = list(
            statuses
        )

        self.container_calls = []
        self.publish_calls = []

    def create_reel_container(
        self,
        *,
        video_url,
        caption="",
        share_to_feed=True,
    ):

        self.container_calls.append({
            "video_url":
                video_url,
            "caption":
                caption,
            "share_to_feed":
                share_to_feed,
        })

        return "container_001"

    def container_status(
        self,
        container_id,
    ):

        if not self.statuses:
            raise RuntimeError(
                "No fake statuses left"
            )

        value = self.statuses.pop(
            0
        )

        return {
            "container_id":
                container_id,
            "status_code":
                value,
            "status":
                value,
        }

    def publish_container(
        self,
        container_id,
    ):

        self.publish_calls.append(
            container_id
        )

        return "media_001"


def make_video(
    tmp_path: Path,
):

    path = (
        tmp_path
        / "promo.mp4"
    )

    path.write_bytes(
        b"fake-video"
    )

    return path


def test_env_file_fallback(
    tmp_path: Path,
    monkeypatch,
):

    monkeypatch.delenv(
        "INSTAGRAM_ACCESS_TOKEN",
        raising=False,
    )

    monkeypatch.delenv(
        "INSTAGRAM_USER_ID",
        raising=False,
    )

    env = tmp_path / ".env"

    env.write_text(
        "INSTAGRAM_ACCESS_TOKEN=abc123\n"
        "INSTAGRAM_USER_ID=777\n",
        encoding="utf-8",
    )

    connector = InstagramConnectorRC1(
        env_path=env,
    )

    status = connector.credential_status()

    assert (
        status["access_token_present"]
        is True
    )

    assert (
        status["user_id_present"]
        is True
    )

    assert status["ready"] is True


def test_publish_success(
    tmp_path: Path,
):

    video = make_video(
        tmp_path
    )

    staging = FakeStaging()

    connector = FakeConnector([
        "IN_PROGRESS",
        "IN_PROGRESS",
        "FINISHED",
    ])

    clock = iter([
        0.0,
        0.0,
        1.0,
        2.0,
        3.0,
    ])

    publisher = InstagramReelPublisherRC1(
        connector=connector,
        staging=staging,
        poll_interval_sec=0,
        timeout_sec=30,
        sleep_fn=lambda _: None,
        monotonic_fn=lambda: next(
            clock
        ),
    )

    result = publisher.publish(
        local_path=video,
        caption="ATLAS ZERO",
    )

    assert (
        result.container_id
        == "container_001"
    )

    assert (
        result.media_id
        == "media_001"
    )

    assert (
        result.final_status
        == "FINISHED"
    )

    assert result.attempts == 3

    assert len(
        connector.publish_calls
    ) == 1

    assert len(
        staging.cleaned
    ) == 1


@pytest.mark.parametrize(
    "status",
    [
        "ERROR",
        "EXPIRED",
    ],
)
def test_terminal_failure(
    tmp_path: Path,
    status,
):

    video = make_video(
        tmp_path
    )

    staging = FakeStaging()

    connector = FakeConnector([
        status
    ])

    publisher = InstagramReelPublisherRC1(
        connector=connector,
        staging=staging,
        poll_interval_sec=0,
        timeout_sec=30,
        sleep_fn=lambda _: None,
    )

    with pytest.raises(
        RuntimeError,
        match=status,
    ):
        publisher.publish(
            local_path=video,
        )

    assert (
        connector.publish_calls
        == []
    )

    assert len(
        staging.cleaned
    ) == 1


def test_timeout(
    tmp_path: Path,
):

    video = make_video(
        tmp_path
    )

    staging = FakeStaging()

    connector = FakeConnector([
        "IN_PROGRESS",
        "IN_PROGRESS",
        "IN_PROGRESS",
    ])

    times = iter([
        0.0,
        0.0,
        2.0,
        4.0,
    ])

    publisher = InstagramReelPublisherRC1(
        connector=connector,
        staging=staging,
        poll_interval_sec=0,
        timeout_sec=3,
        sleep_fn=lambda _: None,
        monotonic_fn=lambda: next(
            times
        ),
    )

    with pytest.raises(
        TimeoutError,
    ):
        publisher.publish(
            local_path=video,
        )

    assert (
        connector.publish_calls
        == []
    )

    assert len(
        staging.cleaned
    ) == 1


def test_http_staging_rejected(
    tmp_path: Path,
):

    video = make_video(
        tmp_path
    )

    staging = FakeStaging(
        public_url=(
            "http://example.com/"
            "promo.mp4"
        )
    )

    connector = FakeConnector([
        "FINISHED"
    ])

    publisher = InstagramReelPublisherRC1(
        connector=connector,
        staging=staging,
    )

    with pytest.raises(
        RuntimeError,
        match="HTTPS",
    ):
        publisher.publish(
            local_path=video,
        )

    assert len(
        staging.cleaned
    ) == 1
