from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_RELEVANCE_STATUSES = {
    "RELEVANT",
    "UNCERTAIN",
    "OFF_TOPIC",
}

VALID_COVERAGE_STATUSES = {
    "PRESENT",
    "PARTIAL",
    "MISSING",
}

VALID_TIME_PERIODS = {
    "unknown",
    "morning",
    "day",
    "evening",
    "night",
}

REQUIRED_RESULT_SECTIONS = {
    "event_clusters",
    "festival_chronology",
    "off_topic_assets",
    "missing_episodes",
}


@dataclass(frozen=True)
class AssetUnderstandingRC2:
    asset_id: str
    filename: str
    media_type: str
    event_type: str
    event_confidence: float
    relevance_status: str
    relevance_score: float
    off_topic_score: float
    time_period: str
    description: str
    story_value: float
    detected_objects: tuple[str, ...] = ()
    detected_actions: tuple[str, ...] = ()
    location_hint: str | None = None
    chronology_timestamp: str | None = None
    evidence: dict[str, Any] = field(
        default_factory=dict
    )

    def validate(self) -> None:
        required_text = {
            "asset_id": self.asset_id,
            "filename": self.filename,
            "media_type": self.media_type,
            "event_type": self.event_type,
            "description": self.description,
        }

        for name, value in required_text.items():
            if not str(value).strip():
                raise ValueError(
                    f"{name} is required"
                )

        if self.relevance_status not in (
            VALID_RELEVANCE_STATUSES
        ):
            raise ValueError(
                "Unsupported relevance_status: "
                f"{self.relevance_status}"
            )

        if self.time_period not in VALID_TIME_PERIODS:
            raise ValueError(
                "Unsupported time_period: "
                f"{self.time_period}"
            )

        for name, value in {
            "event_confidence": self.event_confidence,
            "relevance_score": self.relevance_score,
            "off_topic_score": self.off_topic_score,
            "story_value": self.story_value,
        }.items():
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(
                    f"{name} must be between 0 and 1"
                )

        if (
            self.relevance_status == "OFF_TOPIC"
            and self.off_topic_score < 0.5
        ):
            raise ValueError(
                "OFF_TOPIC assets require "
                "off_topic_score >= 0.5"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class EventClusterRC2:
    cluster_id: str
    event_type: str
    title_ru: str
    description_ru: str
    asset_ids: tuple[str, ...]
    confidence: float
    time_period: str
    chronology_order: int
    total_duration_sec: float
    story_value: float

    def validate(self) -> None:
        if not self.cluster_id.strip():
            raise ValueError(
                "cluster_id is required"
            )

        if not self.event_type.strip():
            raise ValueError(
                "event_type is required"
            )

        if not self.asset_ids:
            raise ValueError(
                "Event cluster must contain assets"
            )

        if self.chronology_order < 0:
            raise ValueError(
                "chronology_order must be >= 0"
            )

        if self.total_duration_sec < 0:
            raise ValueError(
                "total_duration_sec must be >= 0"
            )

        if self.time_period not in VALID_TIME_PERIODS:
            raise ValueError(
                "Unsupported time_period"
            )

        for value in (
            self.confidence,
            self.story_value,
        ):
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(
                    "Cluster scores must be between 0 and 1"
                )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class ChronologyEntryRC2:
    order: int
    cluster_id: str
    event_type: str
    title_ru: str
    time_period: str
    rationale_ru: str
    asset_ids: tuple[str, ...]

    def validate(self) -> None:
        if self.order < 0:
            raise ValueError(
                "Chronology order must be >= 0"
            )

        if not self.cluster_id.strip():
            raise ValueError(
                "cluster_id is required"
            )

        if not self.asset_ids:
            raise ValueError(
                "Chronology entry requires assets"
            )

        if self.time_period not in VALID_TIME_PERIODS:
            raise ValueError(
                "Unsupported time_period"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class OffTopicAssetRC2:
    asset_id: str
    filename: str
    reason_ru: str
    off_topic_score: float
    detected_subject: str
    recommended_action: str = "EXCLUDE"

    def validate(self) -> None:
        if not self.asset_id.strip():
            raise ValueError(
                "asset_id is required"
            )

        if not self.reason_ru.strip():
            raise ValueError(
                "reason_ru is required"
            )

        if not 0.0 <= self.off_topic_score <= 1.0:
            raise ValueError(
                "off_topic_score must be between 0 and 1"
            )

        if self.recommended_action not in {
            "EXCLUDE",
            "REVIEW",
        }:
            raise ValueError(
                "Unsupported recommended_action"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class MissingEpisodeRC2:
    episode_id: str
    event_type: str
    title_ru: str
    description_ru: str
    coverage_status: str
    importance: float
    evidence_asset_ids: tuple[str, ...] = ()
    required_visuals: tuple[str, ...] = ()
    generation_recommended: bool = False

    def validate(self) -> None:
        if not self.episode_id.strip():
            raise ValueError(
                "episode_id is required"
            )

        if self.coverage_status not in (
            VALID_COVERAGE_STATUSES
        ):
            raise ValueError(
                "Unsupported coverage_status"
            )

        if not 0.0 <= self.importance <= 1.0:
            raise ValueError(
                "importance must be between 0 and 1"
            )

        if (
            self.coverage_status == "MISSING"
            and not self.required_visuals
        ):
            raise ValueError(
                "Missing episode requires "
                "required_visuals"
            )

        if (
            self.coverage_status == "PRESENT"
            and self.generation_recommended
        ):
            raise ValueError(
                "Present episode must not request generation"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class VisualUnderstandingResultRC2:
    project_id: str
    topic: str
    source_assets_total: int
    analyzed_assets_total: int
    event_clusters: tuple[EventClusterRC2, ...]
    festival_chronology: tuple[
        ChronologyEntryRC2,
        ...
    ]
    off_topic_assets: tuple[
        OffTopicAssetRC2,
        ...
    ]
    missing_episodes: tuple[
        MissingEpisodeRC2,
        ...
    ]
    asset_understanding: tuple[
        AssetUnderstandingRC2,
        ...
    ] = ()
    engine: str = "visual_understanding_rc2"
    state: str = "UNDERSTANDING_COMPLETE"

    def validate(self) -> None:
        if not self.project_id.strip():
            raise ValueError(
                "project_id is required"
            )

        if not self.topic.strip():
            raise ValueError(
                "topic is required"
            )

        if self.source_assets_total < 1:
            raise ValueError(
                "source_assets_total must be >= 1"
            )

        if (
            self.analyzed_assets_total
            != self.source_assets_total
        ):
            raise ValueError(
                "All source assets must be analyzed"
            )

        understood_ids = {
            row.asset_id
            for row in self.asset_understanding
        }

        if (
            self.asset_understanding
            and len(understood_ids)
            != self.source_assets_total
        ):
            raise ValueError(
                "asset_understanding must contain "
                "one unique record per source asset"
            )

        cluster_ids = set()

        for cluster in self.event_clusters:
            cluster.validate()

            if cluster.cluster_id in cluster_ids:
                raise ValueError(
                    "Duplicate cluster_id: "
                    f"{cluster.cluster_id}"
                )

            cluster_ids.add(cluster.cluster_id)

        previous_order = -1

        for entry in self.festival_chronology:
            entry.validate()

            if entry.cluster_id not in cluster_ids:
                raise ValueError(
                    "Chronology references unknown cluster: "
                    f"{entry.cluster_id}"
                )

            if entry.order <= previous_order:
                raise ValueError(
                    "Chronology order must be "
                    "strictly increasing"
                )

            previous_order = entry.order

        off_topic_ids = set()

        for item in self.off_topic_assets:
            item.validate()

            if item.asset_id in off_topic_ids:
                raise ValueError(
                    "Duplicate off-topic asset"
                )

            off_topic_ids.add(item.asset_id)

        for episode in self.missing_episodes:
            episode.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()

        result = {
            "engine": self.engine,
            "state": self.state,
            "project_id": self.project_id,
            "topic": self.topic,
            "source_assets_total":
                self.source_assets_total,
            "analyzed_assets_total":
                self.analyzed_assets_total,
            "event_clusters": [
                row.to_dict()
                for row in self.event_clusters
            ],
            "festival_chronology": [
                row.to_dict()
                for row in self.festival_chronology
            ],
            "off_topic_assets": [
                row.to_dict()
                for row in self.off_topic_assets
            ],
            "missing_episodes": [
                row.to_dict()
                for row in self.missing_episodes
            ],
            "asset_understanding": [
                row.to_dict()
                for row in self.asset_understanding
            ],
        }

        missing_sections = (
            REQUIRED_RESULT_SECTIONS
            - result.keys()
        )

        if missing_sections:
            raise RuntimeError(
                "Visual understanding result is "
                "missing required sections"
            )

        return result
