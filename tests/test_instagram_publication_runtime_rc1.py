from pathlib import Path
from types import SimpleNamespace

import pytest

from az_enterprise.core.instagram_publication_runtime_rc1 import (
    InstagramPublicationRuntimeRC1,
)


class FakePublisher:

    def __init__(self):
        self.calls = []

    def publish(
        self,
        *,
        local_path,
        caption,
        share_to_feed,
        cleanup_staging,
    ):

        self.calls.append({
            "local_path":
                str(local_path),
            "caption":
                caption,
            "share_to_feed":
                share_to_feed,
            "cleanup_staging":
                cleanup_staging,
        })

        index = len(
            self.calls
        )

        return SimpleNamespace(
            media_id=
                f"media_{index}",
            container_id=
                f"container_{index}",
            attempts=2,
            elapsed_sec=1.5,
        )


def make_video(
    tmp_path: Path,
    name: str,
) -> Path:

    path = (
        tmp_path
        / name
    )

    path.write_bytes(
        b"fake-video"
    )

    return path


def make_runtime(
    tmp_path: Path,
):

    publisher = FakePublisher()

    runtime = InstagramPublicationRuntimeRC1(
        project_id="franklin",
        root=tmp_path,
        connector=object(),
        staging=object(),
        publisher=publisher,
    )

    return runtime, publisher


def test_publish_one_records_media_id(
    tmp_path: Path,
):

    runtime, publisher = (
        make_runtime(
            tmp_path
        )
    )

    video = make_video(
        tmp_path,
        "promo.mp4",
    )

    result = runtime.publish_one(
        candidate_id="promo_001",
        local_path=video,
        caption="ATLAS ZERO",
    )

    assert (
        result.status
        == "PUBLISHED"
    )

    assert (
        result.media_id
        == "media_1"
    )

    assert (
        result.platform
        == "instagram"
    )

    assert (
        runtime.registry_path
        .is_file()
    )

    assert (
        runtime.is_already_published(
            "promo_001"
        )
        is True
    )


def test_duplicate_blocked(
    tmp_path: Path,
):

    runtime, _ = make_runtime(
        tmp_path
    )

    video = make_video(
        tmp_path,
        "promo.mp4",
    )

    runtime.publish_one(
        candidate_id="promo_001",
        local_path=video,
        caption="one",
    )

    with pytest.raises(
        RuntimeError,
        match="already published",
    ):
        runtime.publish_one(
            candidate_id="promo_001",
            local_path=video,
            caption="two",
        )


def test_explicit_republish_allowed(
    tmp_path: Path,
):

    runtime, publisher = (
        make_runtime(
            tmp_path
        )
    )

    video = make_video(
        tmp_path,
        "promo.mp4",
    )

    runtime.publish_one(
        candidate_id="promo_001",
        local_path=video,
        caption="one",
    )

    runtime.publish_one(
        candidate_id="promo_001",
        local_path=video,
        caption="two",
        allow_republish=True,
    )

    assert len(
        publisher.calls
    ) == 2


def test_batch_hard_limit_three(
    tmp_path: Path,
):

    runtime, publisher = (
        make_runtime(
            tmp_path
        )
    )

    items = []

    for index in range(5):

        video = make_video(
            tmp_path,
            f"promo_{index}.mp4",
        )

        items.append({
            "candidate_id":
                f"promo_{index}",
            "local_path":
                video,
            "caption":
                f"caption {index}",
        })

    results = runtime.publish_batch(
        items,
        limit=5,
    )

    assert len(
        results
    ) == 3

    assert len(
        publisher.calls
    ) == 3


def test_zero_limit_publishes_nothing(
    tmp_path: Path,
):

    runtime, publisher = (
        make_runtime(
            tmp_path
        )
    )

    results = runtime.publish_batch(
        [],
        limit=0,
    )

    assert results == []
    assert publisher.calls == []


def test_missing_master_rejected(
    tmp_path: Path,
):

    runtime, _ = make_runtime(
        tmp_path
    )

    with pytest.raises(
        FileNotFoundError,
    ):
        runtime.publish_one(
            candidate_id="promo_001",
            local_path=(
                tmp_path
                / "missing.mp4"
            ),
            caption="",
        )
