from pathlib import Path

import pytest

from az_enterprise.core.promotion_factory_rc1 import (
    PromotionCandidateRC1,
    PromotionDestinationRC1,
    PromotionFactoryRC1,
)


def test_promotion_factory_builds_cross_platform_jobs(
    tmp_path: Path,
):

    source = tmp_path / "movie.mp4"
    source.write_bytes(b"movie")

    factory = PromotionFactoryRC1(
        project_id="movie",
        root=tmp_path,
    )

    destination = PromotionDestinationRC1(
        youtube_video_url=(
            "https://www.youtube.com/watch?v=test"
        ),
        youtube_channel_url=(
            "https://www.youtube.com/@atlaszero"
        ),
    )

    candidate = PromotionCandidateRC1(
        candidate_id="hook_001",
        source_start_sec=100.0,
        source_end_sec=145.0,
        reason="strong narrative hook",
    )

    jobs = factory.build_jobs(
        source_video=source,
        candidates=[candidate],
        destination=destination,
    )

    assert len(jobs) == 3

    assert {
        job.platform
        for job in jobs
    } == {
        "youtube_shorts",
        "instagram_reels",
        "tiktok",
    }

    for job in jobs:
        assert job.output_width == 1080
        assert job.output_height == 1920
        assert job.state == "PROMOTION_READY"
        assert (
            job.destination[
                "youtube_video_url"
            ]
        )

    manifest = factory.write_manifest(
        jobs
    )

    assert manifest.exists()


def test_promotion_factory_blocks_missing_youtube_destination(
    tmp_path: Path,
):

    source = tmp_path / "movie.mp4"
    source.write_bytes(b"movie")

    factory = PromotionFactoryRC1(
        project_id="movie",
        root=tmp_path,
    )

    candidate = PromotionCandidateRC1(
        candidate_id="hook_001",
        source_start_sec=0,
        source_end_sec=30,
    )

    with pytest.raises(
        RuntimeError,
        match="PROMOTION_INCOMPLETE",
    ):
        factory.build_jobs(
            source_video=source,
            candidates=[candidate],
            destination=(
                PromotionDestinationRC1()
            ),
        )


def test_platform_duration_policy(
    tmp_path: Path,
):

    source = tmp_path / "movie.mp4"
    source.write_bytes(b"movie")

    factory = PromotionFactoryRC1(
        project_id="movie",
        root=tmp_path,
    )

    jobs = factory.build_jobs(
        source_video=source,
        candidates=[
            PromotionCandidateRC1(
                candidate_id="long",
                source_start_sec=10,
                source_end_sec=110,
            )
        ],
        destination=PromotionDestinationRC1(
            youtube_channel_url=(
                "https://www.youtube.com/@atlaszero"
            )
        ),
    )

    durations = {
        job.platform:
            job.source_end_sec
            - job.source_start_sec
        for job in jobs
    }

    assert durations["youtube_shorts"] == 60
    assert durations["instagram_reels"] == 90
    assert durations["tiktok"] == 60
