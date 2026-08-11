from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cloudflare_r2_staging_rc1 import (
    CloudflareR2StagingRC1,
)

from .instagram_connector_rc1 import (
    InstagramConnectorRC1,
)

from .instagram_reel_publisher_rc1 import (
    InstagramReelPublisherRC1,
)


@dataclass(frozen=True)
class InstagramPublicationRecordRC1:
    project_id: str
    candidate_id: str
    platform: str
    media_id: str
    container_id: str
    source_path: str
    caption: str
    status: str
    published_at: str
    attempts: int
    elapsed_sec: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InstagramPublicationRuntimeRC1:
    """
    ATLAS ZERO ? Instagram Publication Runtime RC1.

    Canonical chain:

        promotion master
            ->
        Cloudflare R2 temporary staging
            ->
        Instagram media container
            ->
        FINISHED
            ->
        media_publish
            ->
        publication registry

    Rules:

    1. Maximum 3 promotional publications per
       project/platform batch.

    2. candidate_id is idempotent by default.

    3. A successful publication MUST contain
       Instagram media_id.

    4. Secrets remain in local .env.

    5. Temporary R2 media is cleaned by
       InstagramReelPublisherRC1.

    6. This runtime never rebuilds or modifies
       the canonical documentary master.
    """

    PLATFORM = "instagram"
    MAX_PUBLICATIONS = 3

    def __init__(
        self,
        *,
        project_id: str,
        root: Path | str,
        connector: Any | None = None,
        staging: Any | None = None,
        publisher: Any | None = None,
    ) -> None:

        self.project_id = str(
            project_id
        ).strip()

        if not self.project_id:
            raise ValueError(
                "project_id is required"
            )

        self.root = Path(root)

        self.registry_path = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "promotion"
            / "instagram_publications.jsonl"
        )

        if connector is None:
            connector = InstagramConnectorRC1(
                env_path=self.root / ".env"
            )

        if staging is None:
            staging = (
                CloudflareR2StagingRC1
                .from_env_file(
                    self.root / ".env"
                )
            )

        if publisher is None:
            publisher = InstagramReelPublisherRC1(
                connector=connector,
                staging=staging,
            )

        self.connector = connector
        self.staging = staging
        self.publisher = publisher

    def existing_records(
        self,
    ) -> list[dict[str, Any]]:

        if not self.registry_path.is_file():
            return []

        records = []

        for raw in self.registry_path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        ).splitlines():

            line = raw.strip()

            if not line:
                continue

            try:
                payload = json.loads(
                    line
                )
            except json.JSONDecodeError:
                continue

            if isinstance(
                payload,
                dict,
            ):
                records.append(
                    payload
                )

        return records

    def published_candidate_ids(
        self,
    ) -> set[str]:

        return {
            str(
                row.get(
                    "candidate_id",
                    "",
                )
            )
            for row
            in self.existing_records()
            if (
                row.get("platform")
                == self.PLATFORM
                and row.get("status")
                == "PUBLISHED"
            )
        }

    def is_already_published(
        self,
        candidate_id: str,
    ) -> bool:

        return (
            str(candidate_id)
            in self.published_candidate_ids()
        )

    def _append_record(
        self,
        record: InstagramPublicationRecordRC1,
    ) -> None:

        self.registry_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.registry_path.open(
            "a",
            encoding="utf-8",
        ) as handle:

            handle.write(
                json.dumps(
                    record.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

            handle.write("\n")

    def publish_one(
        self,
        *,
        candidate_id: str,
        local_path: Path | str,
        caption: str,
        share_to_feed: bool = True,
        allow_republish: bool = False,
    ) -> InstagramPublicationRecordRC1:

        candidate_id = str(
            candidate_id
        ).strip()

        if not candidate_id:
            raise ValueError(
                "candidate_id is required"
            )

        source = Path(
            local_path
        )

        if not source.is_file():
            raise FileNotFoundError(
                f"Promotion master not found: {source}"
            )

        if source.stat().st_size <= 0:
            raise RuntimeError(
                "Promotion master is empty"
            )

        if (
            not allow_republish
            and self.is_already_published(
                candidate_id
            )
        ):
            raise RuntimeError(
                "Instagram candidate already "
                f"published: {candidate_id}"
            )

        result = self.publisher.publish(
            local_path=source,
            caption=str(caption),
            share_to_feed=share_to_feed,
            cleanup_staging=True,
        )

        media_id = str(
            result.media_id
        ).strip()

        if not media_id:
            raise RuntimeError(
                "Instagram publication returned "
                "empty media_id"
            )

        record = InstagramPublicationRecordRC1(
            project_id=self.project_id,
            candidate_id=candidate_id,
            platform=self.PLATFORM,
            media_id=media_id,
            container_id=str(
                result.container_id
            ),
            source_path=str(
                source
            ),
            caption=str(
                caption
            ),
            status="PUBLISHED",
            published_at=(
                datetime.now(
                    timezone.utc
                )
                .isoformat()
            ),
            attempts=int(
                result.attempts
            ),
            elapsed_sec=float(
                result.elapsed_sec
            ),
        )

        self._append_record(
            record
        )

        return record

    def publish_batch(
        self,
        items: list[dict[str, Any]],
        *,
        limit: int = MAX_PUBLICATIONS,
    ) -> list[
        InstagramPublicationRecordRC1
    ]:

        effective_limit = min(
            max(
                int(limit),
                0,
            ),
            self.MAX_PUBLICATIONS,
        )

        if effective_limit == 0:
            return []

        results = []

        for item in items[
            :effective_limit
        ]:

            result = self.publish_one(
                candidate_id=item[
                    "candidate_id"
                ],
                local_path=item[
                    "local_path"
                ],
                caption=item.get(
                    "caption",
                    "",
                ),
                share_to_feed=bool(
                    item.get(
                        "share_to_feed",
                        True,
                    )
                ),
                allow_republish=bool(
                    item.get(
                        "allow_republish",
                        False,
                    )
                ),
            )

            results.append(
                result
            )

        return results
