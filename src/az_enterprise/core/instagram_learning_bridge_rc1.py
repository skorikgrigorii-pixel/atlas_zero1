from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InstagramLearningSignalRC1:
    project_id: str
    candidate_id: str
    media_id: str
    platform: str

    views: int
    reach: int
    likes: int
    comments: int
    shares: int
    saved: int
    total_interactions: int

    engagement_per_view: float
    like_rate: float
    comment_rate: float
    share_rate: float
    save_rate: float

    confidence: str
    learning_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InstagramLearningBridgeRC1:
    """
    ATLAS ZERO ? Instagram -> Learning Bridge RC1.

    Converts raw Instagram analytics snapshots into
    normalized promotion-performance signals.

    RC1 confidence gate:

        views < 100     -> LOW
        views < 500     -> MEDIUM
        views >= 500    -> HIGH

    LOW-confidence signals are stored but must not
    influence autonomous learning decisions.
    """

    PLATFORM = "instagram"

    def __init__(
        self,
        *,
        project_id: str,
        root: Path | str,
    ) -> None:

        self.project_id = str(
            project_id
        ).strip()

        if not self.project_id:
            raise ValueError(
                "project_id is required"
            )

        self.root = Path(root)

        self.analytics_path = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "promotion"
            / "instagram_analytics.jsonl"
        )

        self.learning_path = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "promotion"
            / "instagram_learning_signals.jsonl"
        )

    @staticmethod
    def _safe_int(
        value: Any,
    ) -> int:

        try:
            return max(
                0,
                int(
                    value or 0
                ),
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0

    @staticmethod
    def _rate(
        numerator: int,
        denominator: int,
    ) -> float:

        if denominator <= 0:
            return 0.0

        return (
            float(numerator)
            / float(denominator)
        )

    @staticmethod
    def confidence_for_views(
        views: int,
    ) -> str:

        if views >= 500:
            return "HIGH"

        if views >= 100:
            return "MEDIUM"

        return "LOW"

    def build_signal(
        self,
        snapshot: dict[str, Any],
    ) -> InstagramLearningSignalRC1:

        views = self._safe_int(
            snapshot.get(
                "views"
            )
        )

        reach = self._safe_int(
            snapshot.get(
                "reach"
            )
        )

        likes = self._safe_int(
            snapshot.get(
                "likes"
            )
        )

        comments = self._safe_int(
            snapshot.get(
                "comments"
            )
        )

        shares = self._safe_int(
            snapshot.get(
                "shares"
            )
        )

        saved = self._safe_int(
            snapshot.get(
                "saved"
            )
        )

        total = self._safe_int(
            snapshot.get(
                "total_interactions"
            )
        )

        confidence = (
            self.confidence_for_views(
                views
            )
        )

        return InstagramLearningSignalRC1(
            project_id=self.project_id,
            candidate_id=str(
                snapshot.get(
                    "candidate_id",
                    "",
                )
            ),
            media_id=str(
                snapshot.get(
                    "media_id",
                    "",
                )
            ),
            platform=self.PLATFORM,
            views=views,
            reach=reach,
            likes=likes,
            comments=comments,
            shares=shares,
            saved=saved,
            total_interactions=total,
            engagement_per_view=self._rate(
                total,
                views,
            ),
            like_rate=self._rate(
                likes,
                views,
            ),
            comment_rate=self._rate(
                comments,
                views,
            ),
            share_rate=self._rate(
                shares,
                views,
            ),
            save_rate=self._rate(
                saved,
                views,
            ),
            confidence=confidence,
            learning_enabled=(
                confidence
                != "LOW"
            ),
        )

    def read_snapshots(
        self,
    ) -> list[dict[str, Any]]:

        if not self.analytics_path.is_file():
            return []

        rows = []

        for raw in self.analytics_path.read_text(
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
                rows.append(
                    payload
                )

        return rows

    def latest_snapshots(
        self,
    ) -> list[dict[str, Any]]:
        """
        Keep only the latest snapshot per media_id.
        """

        latest: dict[
            str,
            dict[str, Any],
        ] = {}

        for row in self.read_snapshots():

            media_id = str(
                row.get(
                    "media_id",
                    "",
                )
            ).strip()

            if not media_id:
                continue

            current = latest.get(
                media_id
            )

            if current is None:
                latest[
                    media_id
                ] = row
                continue

            current_time = str(
                current.get(
                    "collected_at",
                    "",
                )
            )

            new_time = str(
                row.get(
                    "collected_at",
                    "",
                )
            )

            if new_time >= current_time:
                latest[
                    media_id
                ] = row

        return list(
            latest.values()
        )

    def write_signals(
        self,
        signals: list[
            InstagramLearningSignalRC1
        ],
    ) -> None:

        self.learning_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.learning_path.open(
            "w",
            encoding="utf-8",
        ) as handle:

            for signal in signals:

                handle.write(
                    json.dumps(
                        signal.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )

                handle.write(
                    "\n"
                )

    def build_latest_signals(
        self,
    ) -> list[
        InstagramLearningSignalRC1
    ]:

        signals = [
            self.build_signal(
                snapshot
            )
            for snapshot
            in self.latest_snapshots()
        ]

        self.write_signals(
            signals
        )

        return signals
