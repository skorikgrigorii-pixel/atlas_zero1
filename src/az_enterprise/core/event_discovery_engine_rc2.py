from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .visual_understanding_contract_rc2 import (
    EventClusterRC2,
    OffTopicAssetRC2,
)


EVENT_TITLES_RU: dict[str, str] = {
    "monument": "??????????? ??????",
    "parade": "??????????? ???????",
    "flower_offering": "?????????? ??????",
    "mascleta": "????????",
    "fireworks": "?????? ?????????",
    "crema": "???????? ?????",
    "street_festival": "????? ?????????",
    "music_band": "??????????? ????????",
    "beach_event": "???????? ? ????",
    "city_context": "???????? ? ????????? ?????",
    "preparation": "?????????? ?????????",
    "firefighters": "?????? ????????",
    "crowd_reaction": "??????? ????????",
    "unrelated_private_content":
        "??????????? ?????? ????????",
}


EVENT_DESCRIPTIONS_RU: dict[str, str] = {
    "monument":
        "??????? ?????????????? ?????????? ? ?????? Hogueras.",
    "parade":
        "??????? ??????????, ???????, ??????? ? ???????? ?? ??????.",
    "flower_offering":
        "?????????????? ??????? ? ???????.",
    "mascleta":
        "??????? ??????????????? ????????????? ? ????? ? ????????.",
    "fireworks":
        "?????? ????????? ? ??????? ????????.",
    "crema":
        "????????? ???????? ??????????? ?????.",
    "street_festival":
        "??????????? ????? ?? ?????? ????????.",
    "music_band":
        "???????? ? ??????????? ???????????.",
    "beach_event":
        "??????? ????????? ?? ?????????.",
    "city_context":
        "????????? ????? ? ???????? ????????.",
    "preparation":
        "????????, ????????? ? ?????????? ??????????? ????????.",
    "firefighters":
        "?????? ???????? ?? ????? ????????? ???????.",
    "crowd_reaction":
        "??????, ???????? ? ??????? ????????.",
}


EVENT_STORY_IMPORTANCE: dict[str, float] = {
    "preparation": 0.82,
    "city_context": 0.62,
    "monument": 0.90,
    "parade": 0.84,
    "flower_offering": 0.82,
    "music_band": 0.72,
    "street_festival": 0.70,
    "mascleta": 0.94,
    "crowd_reaction": 0.66,
    "beach_event": 0.60,
    "fireworks": 0.94,
    "firefighters": 0.82,
    "crema": 1.00,
}


TIME_ORDER: dict[str, int] = {
    "morning": 0,
    "day": 1,
    "evening": 2,
    "night": 3,
    "unknown": 4,
}


@dataclass(frozen=True)
class ReviewAssetRC2:
    asset_id: str
    filename: str
    event_type: str
    event_confidence: float
    relevance_status: str
    off_topic_score: float
    reason_ru: str
    recommended_action: str = "REVIEW"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventDiscoveryEngineRC2:
    """Create event clusters and exclusion decisions.

    Input is the completed VisualSemanticAnalyzerRC2 report.
    The engine never reopens or reclassifies source media.
    """

    def __init__(
        self,
        *,
        off_topic_exclude_threshold: float = 0.72,
        off_topic_review_threshold: float = 0.50,
        low_confidence_threshold: float = 0.40,
    ) -> None:
        self.off_topic_exclude_threshold = (
            off_topic_exclude_threshold
        )
        self.off_topic_review_threshold = (
            off_topic_review_threshold
        )
        self.low_confidence_threshold = (
            low_confidence_threshold
        )

    def run(
        self,
        semantic_report: dict[str, Any],
    ) -> dict[str, Any]:
        rows = list(
            semantic_report.get("results", [])
        )

        if not rows:
            raise ValueError(
                "Semantic report contains no results"
            )

        included: list[dict[str, Any]] = []
        off_topic: list[OffTopicAssetRC2] = []
        review: list[ReviewAssetRC2] = []

        for row in rows:
            decision = self._decision(row)

            if decision == "EXCLUDE":
                off_topic.append(
                    self._build_off_topic(row)
                )
                continue

            if decision == "REVIEW":
                review.append(
                    self._build_review(row)
                )

            included.append(row)

        clusters = self._build_clusters(included)

        return {
            "engine": "event_discovery_engine_rc2",
            "project_id": semantic_report.get(
                "project_id"
            ),
            "source_assets_total": len(rows),
            "included_assets_total":
                len(included),
            "excluded_assets_total":
                len(off_topic),
            "review_assets_total":
                len(review),
            "event_clusters": [
                cluster.to_dict()
                for cluster in clusters
            ],
            "off_topic_assets": [
                item.to_dict()
                for item in off_topic
            ],
            "review_assets": [
                item.to_dict()
                for item in review
            ],
            "cluster_statistics":
                self._cluster_statistics(
                    clusters
                ),
        }

    def _decision(
        self,
        row: dict[str, Any],
    ) -> str:
        event_type = str(
            row.get("event_type", "")
        )
        status = str(
            row.get("relevance_status", "")
        )
        off_topic = float(
            row.get("off_topic_score", 0.0)
        )
        confidence = float(
            row.get("event_confidence", 0.0)
        )

        clearly_private = (
            event_type
            == "unrelated_private_content"
            and off_topic
            >= self.off_topic_exclude_threshold
        )

        status_and_score = (
            status == "OFF_TOPIC"
            and off_topic
            >= self.off_topic_exclude_threshold
        )

        if clearly_private or status_and_score:
            return "EXCLUDE"

        conflicting_off_topic = (
            off_topic
            >= self.off_topic_review_threshold
        )

        uncertain = (
            status == "UNCERTAIN"
        )

        low_confidence = (
            confidence
            < self.low_confidence_threshold
        )

        unusual_status = (
            status == "OFF_TOPIC"
            and off_topic
            < self.off_topic_exclude_threshold
        )

        if (
            conflicting_off_topic
            or uncertain
            or low_confidence
            or unusual_status
        ):
            return "REVIEW"

        return "INCLUDE"

    def _build_off_topic(
        self,
        row: dict[str, Any],
    ) -> OffTopicAssetRC2:
        event_type = str(
            row.get("event_type", "unknown")
        )

        if (
            event_type
            == "unrelated_private_content"
        ):
            reason = (
                "???????? ? ??????? ???????????? "
                "???????? ?????? ??? ??????? ? ?? "
                "????????? ? ????????? Hogueras."
            )
        else:
            reason = (
                "????????????? ?????? ????????? "
                "??????? ??????????? ?????????????? "
                "???? ??????."
            )

        item = OffTopicAssetRC2(
            asset_id=str(row["asset_id"]),
            filename=str(row["filename"]),
            reason_ru=reason,
            off_topic_score=float(
                row["off_topic_score"]
            ),
            detected_subject=event_type,
            recommended_action="EXCLUDE",
        )

        item.validate()
        return item

    def _build_review(
        self,
        row: dict[str, Any],
    ) -> ReviewAssetRC2:
        confidence = float(
            row.get("event_confidence", 0.0)
        )
        off_topic = float(
            row.get("off_topic_score", 0.0)
        )
        status = str(
            row.get(
                "relevance_status",
                "UNCERTAIN",
            )
        )

        reasons: list[str] = []

        if (
            confidence
            < self.low_confidence_threshold
        ):
            reasons.append(
                "?????? ??????????? ??????????? ???????"
            )

        if (
            off_topic
            >= self.off_topic_review_threshold
        ):
            reasons.append(
                "?????????? ??????????? ???????????? ?????????"
            )

        if status == "UNCERTAIN":
            reasons.append(
                "?????????????? ???????????? ?????????????"
            )

        if (
            status == "OFF_TOPIC"
            and off_topic
            < self.off_topic_exclude_threshold
        ):
            reasons.append(
                "?????? OFF_TOPIC ??? ??????????? "
                "??????????? ??? ??????????????? ??????????"
            )

        reason_ru = "; ".join(reasons)

        if not reason_ru:
            reason_ru = (
                "???????? ??????? ?????????????? "
                "????????????? ????????."
            )

        return ReviewAssetRC2(
            asset_id=str(row["asset_id"]),
            filename=str(row["filename"]),
            event_type=str(
                row.get("event_type", "unknown")
            ),
            event_confidence=confidence,
            relevance_status=status,
            off_topic_score=off_topic,
            reason_ru=reason_ru,
        )

    def _build_clusters(
        self,
        rows: Iterable[dict[str, Any]],
    ) -> list[EventClusterRC2]:
        grouped: dict[
            tuple[str, str],
            list[dict[str, Any]],
        ] = defaultdict(list)

        for row in rows:
            event_type = str(
                row.get(
                    "event_type",
                    "unknown",
                )
            )

            if (
                event_type
                == "unrelated_private_content"
            ):
                continue

            time_period = str(
                row.get(
                    "time_period",
                    "unknown",
                )
            )

            grouped[
                (event_type, time_period)
            ].append(row)

        preliminary: list[
            tuple[
                tuple[str, str],
                list[dict[str, Any]],
            ]
        ] = sorted(
            grouped.items(),
            key=lambda item: (
                TIME_ORDER.get(
                    item[0][1],
                    99,
                ),
                -mean(
                    float(
                        row.get(
                            "story_value",
                            0.0,
                        )
                    )
                    for row in item[1]
                ),
                item[0][0],
            ),
        )

        clusters: list[EventClusterRC2] = []

        for order, (
            (event_type, time_period),
            members,
        ) in enumerate(
            preliminary,
            start=1,
        ):
            confidence = mean(
                float(
                    row.get(
                        "event_confidence",
                        0.0,
                    )
                )
                for row in members
            )

            story_value = mean(
                float(
                    row.get(
                        "story_value",
                        EVENT_STORY_IMPORTANCE.get(
                            event_type,
                            0.5,
                        ),
                    )
                )
                for row in members
            )

            duration = sum(
                self._duration_for(row)
                for row in members
            )

            cluster_id = (
                f"cluster-{event_type}-"
                f"{time_period}"
            )

            cluster = EventClusterRC2(
                cluster_id=cluster_id,
                event_type=event_type,
                title_ru=EVENT_TITLES_RU.get(
                    event_type,
                    event_type,
                ),
                description_ru=
                    EVENT_DESCRIPTIONS_RU.get(
                        event_type,
                        "?????? ??????????? ????????? ??????????.",
                    ),
                asset_ids=tuple(
                    str(row["asset_id"])
                    for row in members
                ),
                confidence=round(
                    confidence,
                    6,
                ),
                time_period=time_period,
                chronology_order=order,
                total_duration_sec=round(
                    duration,
                    3,
                ),
                story_value=round(
                    story_value,
                    6,
                ),
            )

            cluster.validate()
            clusters.append(cluster)

        return clusters

    @staticmethod
    def _duration_for(
        row: dict[str, Any],
    ) -> float:
        evidence = row.get("evidence") or {}

        for value in (
            evidence.get("duration_sec"),
            evidence.get("cv_duration_sec"),
        ):
            try:
                duration = float(value)

                if duration > 0:
                    return duration
            except (TypeError, ValueError):
                pass

        if row.get("media_type") == "image":
            return 5.0

        return 0.0

    @staticmethod
    def _cluster_statistics(
        clusters: Iterable[EventClusterRC2],
    ) -> dict[str, Any]:
        rows = list(clusters)

        return {
            "clusters_total": len(rows),
            "assets_clustered": sum(
                len(cluster.asset_ids)
                for cluster in rows
            ),
            "duration_sec": round(
                sum(
                    cluster.total_duration_sec
                    for cluster in rows
                ),
                3,
            ),
            "event_types": sorted({
                cluster.event_type
                for cluster in rows
            }),
            "time_periods": sorted({
                cluster.time_period
                for cluster in rows
            }),
        }


def load_semantic_report(
    path: Path | str,
) -> dict[str, Any]:
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )
