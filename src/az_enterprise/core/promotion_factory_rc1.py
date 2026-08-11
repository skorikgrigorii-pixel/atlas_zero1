from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CONTENT_CLASS_FILM = "FILM_PROMOTION"
CONTENT_CLASS_CHANNEL = "CHANNEL_PROMOTION"

PLATFORM_PROFILES = {
    "youtube_shorts": {
        "width": 1080,
        "height": 1920,
        "aspect_ratio": "9:16",
        "max_duration_sec": 60.0,
    },
    "instagram_reels": {
        "width": 1080,
        "height": 1920,
        "aspect_ratio": "9:16",
        "max_duration_sec": 90.0,
    },
    "tiktok": {
        "width": 1080,
        "height": 1920,
        "aspect_ratio": "9:16",
        "max_duration_sec": 60.0,
    },
}


@dataclass(frozen=True)
class PromotionDestinationRC1:
    youtube_video_url: str = ""
    youtube_channel_url: str = ""

    @property
    def valid(self) -> bool:
        return bool(
            self.youtube_video_url.strip()
            or self.youtube_channel_url.strip()
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionCandidateRC1:
    candidate_id: str
    source_start_sec: float
    source_end_sec: float
    reason: str = ""

    @property
    def duration_sec(self) -> float:
        return max(
            0.0,
            self.source_end_sec
            - self.source_start_sec,
        )


@dataclass(frozen=True)
class PromotionJobRC1:
    job_id: str
    project_id: str
    platform: str
    source_video: str
    source_start_sec: float
    source_end_sec: float
    output_width: int
    output_height: int
    destination: dict[str, Any]
    state: str
    reason: str
    content_class: str = CONTENT_CLASS_FILM

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PromotionFactoryRC1:
    """
    ATLAS ZERO ? Promotion Factory RC1.

    Builds promotion render jobs from an already completed film.

    This class does NOT introduce a second render authority.
    Rendering remains delegated to the existing RC2/FFmpeg stack.

    Mandatory funnel invariant:
        every promotion asset must lead to either
        the full YouTube film or the ATLAS ZERO YouTube channel.
    """

    def __init__(
        self,
        *,
        project_id: str,
        root: str | Path,
    ) -> None:

        self.project_id = str(project_id).strip()

        if not self.project_id:
            raise ValueError(
                "project_id is required"
            )

        self.root = Path(root)

        self.output_dir = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "promotion"
        )

    @staticmethod
    def platform_profile(
        platform: str,
    ) -> dict[str, Any]:

        key = str(platform).strip().lower()

        if key not in PLATFORM_PROFILES:
            raise ValueError(
                f"Unsupported promotion platform: {platform}"
            )

        return dict(
            PLATFORM_PROFILES[key]
        )

    @staticmethod
    def validate_destination(
        destination: PromotionDestinationRC1,
    ) -> None:

        if not destination.valid:
            raise RuntimeError(
                "PROMOTION_INCOMPLETE: "
                "youtube_video_url or "
                "youtube_channel_url is required"
            )

    def build_jobs(
        self,
        *,
        source_video: str | Path,
        candidates: list[PromotionCandidateRC1],
        destination: PromotionDestinationRC1,
        platforms: tuple[str, ...] = (
            "youtube_shorts",
            "instagram_reels",
            "tiktok",
        ),
        content_class: str = CONTENT_CLASS_FILM,
    ) -> list[PromotionJobRC1]:

        self.validate_destination(
            destination
        )

        content_class = str(
            content_class
        ).strip().upper()

        if content_class not in {
            CONTENT_CLASS_FILM,
            CONTENT_CLASS_CHANNEL,
        }:
            raise ValueError(
                f"Unsupported content_class: "
                f"{content_class}"
            )

        source = Path(source_video)

        if not source.exists():
            raise FileNotFoundError(
                source
            )

        jobs: list[PromotionJobRC1] = []

        for candidate in candidates:

            if candidate.duration_sec <= 0:
                raise ValueError(
                    "Promotion candidate duration "
                    "must be greater than zero"
                )

            for platform in platforms:

                profile = self.platform_profile(
                    platform
                )

                duration = min(
                    candidate.duration_sec,
                    float(
                        profile[
                            "max_duration_sec"
                        ]
                    ),
                )

                end_sec = (
                    candidate.source_start_sec
                    + duration
                )

                job_id = (
                    f"{candidate.candidate_id}"
                    f"__{platform}"
                )

                jobs.append(
                    PromotionJobRC1(
                        job_id=job_id,
                        project_id=self.project_id,
                        platform=platform,
                        source_video=str(
                            source.resolve()
                        ),
                        source_start_sec=float(
                            candidate.source_start_sec
                        ),
                        source_end_sec=float(
                            end_sec
                        ),
                        output_width=int(
                            profile["width"]
                        ),
                        output_height=int(
                            profile["height"]
                        ),
                        destination=(
                            destination.to_dict()
                        ),
                        state="PROMOTION_READY",
                        reason=candidate.reason,
                        content_class=content_class,
                    )
                )

        return jobs

    def write_manifest(
        self,
        jobs: list[PromotionJobRC1],
    ) -> Path:

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            self.output_dir
            / "promotion_manifest.json"
        )

        payload = {
            "schema":
                "atlas_zero.promotion.rc1",

            "project_id":
                self.project_id,

            "promotion_assets":
                [
                    job.to_dict()
                    for job in jobs
                ],
        }

        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return path
