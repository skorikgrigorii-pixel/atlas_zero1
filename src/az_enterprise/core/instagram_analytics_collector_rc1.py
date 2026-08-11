from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .instagram_connector_rc1 import (
    InstagramConnectorRC1,
)


@dataclass(frozen=True)
class InstagramMediaMetricsRC1:
    project_id: str
    candidate_id: str
    media_id: str
    platform: str
    collected_at: str

    views: int | None = None
    reach: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saved: int | None = None
    total_interactions: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InstagramAnalyticsCollectorRC1:
    """
    ATLAS ZERO ? Instagram Analytics Collector RC1.

    Collects only metrics confirmed available for
    the current Instagram API/account contract.

    Confirmed metrics:
        views
        reach
        likes
        comments
        shares
        saved
        total_interactions

    Explicitly NOT used:
        plays
    """

    PLATFORM = "instagram"

    METRICS = (
        "views",
        "reach",
        "likes",
        "comments",
        "shares",
        "saved",
        "total_interactions",
    )

    def __init__(
        self,
        *,
        project_id: str,
        root: Path | str,
        connector: Any | None = None,
    ) -> None:

        self.project_id = str(
            project_id
        ).strip()

        if not self.project_id:
            raise ValueError(
                "project_id is required"
            )

        self.root = Path(root)

        self.publication_registry_path = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "promotion"
            / "instagram_publications.jsonl"
        )

        self.analytics_registry_path = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "promotion"
            / "instagram_analytics.jsonl"
        )

        if connector is None:
            connector = InstagramConnectorRC1(
                env_path=self.root / ".env"
            )

        self.connector = connector

    @staticmethod
    def _extract_metric_value(
        payload: dict[str, Any],
    ) -> int | None:

        data = payload.get(
            "data",
            [],
        )

        if not data:
            return None

        row = data[0]

        raw = row.get(
            "values",
            row.get(
                "value",
            ),
        )

        if isinstance(
            raw,
            list,
        ):

            if not raw:
                return None

            last = raw[-1]

            if isinstance(
                last,
                dict,
            ):
                raw = last.get(
                    "value"
                )

        if isinstance(
            raw,
            dict,
        ):
            raw = raw.get(
                "value"
            )

        if raw is None:
            return None

        try:
            return int(
                raw
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    def collect_metric(
        self,
        *,
        media_id: str,
        metric: str,
    ) -> int | None:

        metric = str(
            metric
        ).strip()

        if metric not in self.METRICS:
            raise ValueError(
                f"Unsupported Instagram metric: {metric}"
            )

        payload = self.connector._request_json(
            method="GET",
            path=f"{media_id}/insights",
            params={
                "metric":
                    metric,
            },
        )

        return self._extract_metric_value(
            payload
        )

    def collect_media(
        self,
        *,
        candidate_id: str,
        media_id: str,
    ) -> InstagramMediaMetricsRC1:

        values: dict[str, int | None] = {}

        for metric in self.METRICS:

            values[metric] = (
                self.collect_metric(
                    media_id=media_id,
                    metric=metric,
                )
            )

        return InstagramMediaMetricsRC1(
            project_id=self.project_id,
            candidate_id=str(
                candidate_id
            ),
            media_id=str(
                media_id
            ),
            platform=self.PLATFORM,
            collected_at=(
                datetime.now(
                    timezone.utc
                )
                .isoformat()
            ),
            **values,
        )

    def publication_records(
        self,
    ) -> list[dict[str, Any]]:

        if not self.publication_registry_path.is_file():
            return []

        rows = []

        for raw in self.publication_registry_path.read_text(
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

            if (
                isinstance(
                    payload,
                    dict,
                )
                and payload.get(
                    "platform"
                ) == self.PLATFORM
                and payload.get(
                    "status"
                ) == "PUBLISHED"
            ):
                rows.append(
                    payload
                )

        return rows

    def _append_snapshot(
        self,
        record: InstagramMediaMetricsRC1,
    ) -> None:

        self.analytics_registry_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.analytics_registry_path.open(
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

            handle.write(
                "\n"
            )

    def collect_registered_media(
        self,
    ) -> list[
        InstagramMediaMetricsRC1
    ]:

        results = []

        for row in self.publication_records():

            media_id = str(
                row.get(
                    "media_id",
                    "",
                )
            ).strip()

            candidate_id = str(
                row.get(
                    "candidate_id",
                    "",
                )
            ).strip()

            if (
                not media_id
                or not candidate_id
            ):
                continue

            result = self.collect_media(
                candidate_id=
                    candidate_id,
                media_id=
                    media_id,
            )

            self._append_snapshot(
                result
            )

            results.append(
                result
            )

        return results
