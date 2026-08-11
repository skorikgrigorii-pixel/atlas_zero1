from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .instagram_connector_rc1 import (
    InstagramConnectorRC1,
)

from .promotion_media_staging_rc1 import (
    PromotionMediaStagingRC1,
    StagedMediaRC1,
)


@dataclass(frozen=True)
class InstagramPublishResultRC1:
    local_path: Path
    public_url: str
    container_id: str
    media_id: str
    final_status: str
    attempts: int
    elapsed_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_path":
                str(self.local_path),
            "public_url":
                self.public_url,
            "container_id":
                self.container_id,
            "media_id":
                self.media_id,
            "final_status":
                self.final_status,
            "attempts":
                self.attempts,
            "elapsed_sec":
                self.elapsed_sec,
        }


class InstagramReelPublisherRC1:
    """
    ATLAS ZERO ? Instagram Reel Publisher RC1.

    Canonical flow:

        local master
            ->
        public staging
            ->
        Instagram media container
            ->
        wait until FINISHED
            ->
        media_publish
            ->
        cleanup staging

    The publisher does not implement storage itself.
    """

    READY_STATUS = "FINISHED"

    TERMINAL_ERROR_STATUSES = {
        "ERROR",
        "EXPIRED",
    }

    WAIT_STATUSES = {
        "",
        "IN_PROGRESS",
        "PUBLISHED",
    }

    def __init__(
        self,
        *,
        connector: InstagramConnectorRC1,
        staging: PromotionMediaStagingRC1,
        poll_interval_sec: float = 5.0,
        timeout_sec: float = 180.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:

        self.connector = connector
        self.staging = staging

        self.poll_interval_sec = float(
            poll_interval_sec
        )

        self.timeout_sec = float(
            timeout_sec
        )

        self.sleep_fn = sleep_fn
        self.monotonic_fn = monotonic_fn

        if self.poll_interval_sec < 0:
            raise ValueError(
                "poll_interval_sec cannot be negative"
            )

        if self.timeout_sec <= 0:
            raise ValueError(
                "timeout_sec must be positive"
            )

    def wait_until_ready(
        self,
        container_id: str,
    ) -> dict[str, Any]:

        started = self.monotonic_fn()

        attempts = 0

        while True:

            attempts += 1

            state = (
                self.connector
                .container_status(
                    container_id
                )
            )

            status_code = str(
                state.get(
                    "status_code",
                    "",
                )
            ).strip().upper()

            elapsed = (
                self.monotonic_fn()
                - started
            )

            if (
                status_code
                == self.READY_STATUS
            ):
                return {
                    "status_code":
                        status_code,
                    "attempts":
                        attempts,
                    "elapsed_sec":
                        elapsed,
                    "state":
                        state,
                }

            if (
                status_code
                in self.TERMINAL_ERROR_STATUSES
            ):
                raise RuntimeError(
                    "Instagram container "
                    f"{container_id} failed "
                    f"with status "
                    f"{status_code}: "
                    f"{state.get('status')}"
                )

            if elapsed >= self.timeout_sec:
                raise TimeoutError(
                    "Instagram container "
                    f"{container_id} did not "
                    "become FINISHED within "
                    f"{self.timeout_sec:.1f}s"
                )

            self.sleep_fn(
                self.poll_interval_sec
            )

    def publish(
        self,
        *,
        local_path: Path | str,
        caption: str = "",
        share_to_feed: bool = True,
        cleanup_staging: bool = True,
    ) -> InstagramPublishResultRC1:

        staged: StagedMediaRC1 | None = None

        try:

            staged = self.staging.stage(
                local_path
            )

            if not staged.public_url.startswith(
                "https://"
            ):
                raise RuntimeError(
                    "Instagram staging URL must "
                    "use HTTPS"
                )

            container_id = (
                self.connector
                .create_reel_container(
                    video_url=
                        staged.public_url,
                    caption=caption,
                    share_to_feed=
                        share_to_feed,
                )
            )

            ready = self.wait_until_ready(
                container_id
            )

            media_id = (
                self.connector
                .publish_container(
                    container_id
                )
            )

            return InstagramPublishResultRC1(
                local_path=Path(
                    local_path
                ),
                public_url=
                    staged.public_url,
                container_id=
                    container_id,
                media_id=
                    media_id,
                final_status=
                    ready["status_code"],
                attempts=int(
                    ready["attempts"]
                ),
                elapsed_sec=float(
                    ready["elapsed_sec"]
                ),
            )

        finally:

            if (
                staged is not None
                and cleanup_staging
            ):
                self.staging.cleanup(
                    staged
                )
