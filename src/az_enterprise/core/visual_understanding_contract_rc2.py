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


# ATLAS_ZERO_VISUAL_CONTINUITY_CONTRACT_RC2
# ============================================================================
# Canonical cross-shot world-state contract.
#
# Purpose:
#   Preserve physical, temporal and causal continuity between adjacent shots.
#
# Example blocked by this contract:
#   shot N   : character jumps from aircraft stairs
#   shot N+1 : same character is again descending those stairs
#              without FLASHBACK / REPLAY / other non-linear mode.
# ============================================================================

VALID_CONTINUITY_MODES = {
    "LINEAR",
    "FLASHBACK",
    "FLASHFORWARD",
    "REPLAY",
    "MONTAGE",
    "ABSTRACT",
    "UNKNOWN",
}


VALID_CONTINUITY_SEVERITIES = {
    "INFO",
    "WARNING",
    "BLOCK",
}


@dataclass(frozen=True)
class ContinuityStateRC2:
    """
    Observable world state immediately before or after a shot.

    This contract deliberately stores semantic state rather than
    provider-specific visual-generation metadata.
    """

    character_ids: tuple[str, ...] = ()

    location: str | None = None
    position: str | None = None
    action: str | None = None
    movement_direction: str | None = None

    object_states: tuple[str, ...] = ()
    wardrobe_state: tuple[str, ...] = ()

    lighting: str | None = None
    time_period: str = "unknown"
    emotional_state: str | None = None

    completed_events: tuple[str, ...] = ()


    def validate(self) -> None:

        if self.time_period not in VALID_TIME_PERIODS:

            raise ValueError(
                "Unsupported continuity time_period: "
                f"{self.time_period}"
            )


        if len(
            set(
                self.character_ids
            )
        ) != len(
            self.character_ids
        ):

            raise ValueError(
                "Continuity character_ids must be unique"
            )


        if len(
            set(
                self.completed_events
            )
        ) != len(
            self.completed_events
        ):

            raise ValueError(
                "Continuity completed_events must be unique"
            )


    def to_dict(self) -> dict[str, Any]:

        self.validate()

        return asdict(
            self
        )


@dataclass(frozen=True)
class ShotContinuityRC2:
    """
    Canonical continuity envelope for one shot.
    """

    shot_id: str
    scene_id: str

    before: ContinuityStateRC2
    after: ContinuityStateRC2

    narrative_order: int

    continuity_mode: str = "LINEAR"


    def validate(self) -> None:

        if not self.shot_id.strip():

            raise ValueError(
                "shot_id is required"
            )


        if not self.scene_id.strip():

            raise ValueError(
                "scene_id is required"
            )


        if self.narrative_order < 0:

            raise ValueError(
                "narrative_order must be >= 0"
            )


        if (
            self.continuity_mode
            not in VALID_CONTINUITY_MODES
        ):

            raise ValueError(
                "Unsupported continuity_mode: "
                f"{self.continuity_mode}"
            )


        self.before.validate()
        self.after.validate()


    def to_dict(self) -> dict[str, Any]:

        self.validate()

        return {
            "shot_id":
                self.shot_id,

            "scene_id":
                self.scene_id,

            "before":
                self.before.to_dict(),

            "after":
                self.after.to_dict(),

            "narrative_order":
                self.narrative_order,

            "continuity_mode":
                self.continuity_mode,
        }


@dataclass(frozen=True)
class ContinuityViolationRC2:
    """
    Structured continuity failure emitted by a continuity gate.
    """

    code: str
    severity: str

    previous_shot_id: str
    current_shot_id: str

    reason: str

    evidence: dict[str, Any] = field(
        default_factory=dict
    )


    def validate(self) -> None:

        if not self.code.strip():

            raise ValueError(
                "continuity violation code is required"
            )


        if (
            self.severity
            not in VALID_CONTINUITY_SEVERITIES
        ):

            raise ValueError(
                "Unsupported continuity severity: "
                f"{self.severity}"
            )


        if not self.previous_shot_id.strip():

            raise ValueError(
                "previous_shot_id is required"
            )


        if not self.current_shot_id.strip():

            raise ValueError(
                "current_shot_id is required"
            )


        if not self.reason.strip():

            raise ValueError(
                "continuity violation reason is required"
            )


    def to_dict(self) -> dict[str, Any]:

        self.validate()

        return asdict(
            self
        )


@dataclass(frozen=True)
class ContinuityEvaluationRC2:
    """
    Result of comparing previous-shot AFTER state
    with current-shot BEFORE state.
    """

    previous_shot_id: str
    current_shot_id: str

    compatible: bool

    temporal_score: float

    violations: tuple[
        ContinuityViolationRC2,
        ...
    ] = ()


    def validate(self) -> None:

        if not self.previous_shot_id.strip():

            raise ValueError(
                "previous_shot_id is required"
            )


        if not self.current_shot_id.strip():

            raise ValueError(
                "current_shot_id is required"
            )


        if not 0.0 <= float(
            self.temporal_score
        ) <= 1.0:

            raise ValueError(
                "temporal_score must be between 0 and 1"
            )


        for violation in self.violations:

            violation.validate()


        has_block = any(
            row.severity == "BLOCK"
            for row in self.violations
        )


        if self.compatible and has_block:

            raise ValueError(
                "Compatible continuity evaluation "
                "cannot contain BLOCK violations"
            )


    def to_dict(self) -> dict[str, Any]:

        self.validate()

        return {
            "previous_shot_id":
                self.previous_shot_id,

            "current_shot_id":
                self.current_shot_id,

            "compatible":
                self.compatible,

            "temporal_score":
                float(
                    self.temporal_score
                ),

            "violations": [
                row.to_dict()
                for row
                in self.violations
            ],
        }





# ATLAS_ZERO_VISUAL_CONTINUITY_EVALUATOR_RC2
# ============================================================================
# Canonical automatic cross-shot continuity evaluator.
#
# Compares:
#   previous_shot.after
#       ->
#   current_shot.before
#
# Produces ContinuityEvaluationRC2 including temporal_score.
# ============================================================================


class VisualContinuityEvaluatorRC2:
    """
    Conservative semantic continuity gate.

    Missing / unknown state does not create a violation.
    Explicit contradictions do.

    Non-linear continuity modes bypass ordinary linear-state
    contradiction checks by design.
    """

    NON_LINEAR_MODES = {
        "FLASHBACK",
        "FLASHFORWARD",
        "REPLAY",
        "MONTAGE",
        "ABSTRACT",
    }

    OPPOSITE_DIRECTIONS = {
        ("left", "right"),
        ("right", "left"),
        ("up", "down"),
        ("down", "up"),
        ("forward", "backward"),
        ("backward", "forward"),
        ("toward_aircraft", "away_from_aircraft"),
        ("away_from_aircraft", "toward_aircraft"),
    }

    # Common causal reversals.
    ACTION_REGRESSION_RULES = {
        "jumped": {
            "descending",
            "standing_on_stairs",
            "preparing_to_jump",
            "inside_aircraft",
        },

        "exited": {
            "inside",
            "entering",
        },

        "left": {
            "inside",
            "entering",
        },

        "landed": {
            "airborne",
            "falling",
        },

        "sat_down": {
            "standing",
        },

        "stood_up": {
            "sitting",
        },

        "closed": {
            "opening",
            "open",
        },

        "opened": {
            "closed",
            "closing",
        },
    }


    @staticmethod
    def _norm(value: str | None) -> str:

        return str(
            value or ""
        ).strip().casefold()


    @classmethod
    def _same_or_unknown(
        cls,
        previous: str | None,
        current: str | None,
    ) -> bool:

        left = cls._norm(
            previous
        )

        right = cls._norm(
            current
        )

        if not left or not right:
            return True

        return left == right


    @classmethod
    def evaluate(
        cls,
        previous: ShotContinuityRC2,
        current: ShotContinuityRC2,
    ) -> ContinuityEvaluationRC2:

        previous.validate()
        current.validate()

        violations: list[
            ContinuityViolationRC2
        ] = []


        # --------------------------------------------------------
        # Ordering
        # --------------------------------------------------------

        if (
            current.narrative_order
            <= previous.narrative_order
        ):

            violations.append(
                ContinuityViolationRC2(
                    code=
                        "NARRATIVE_ORDER_REGRESSION",

                    severity=
                        "BLOCK",

                    previous_shot_id=
                        previous.shot_id,

                    current_shot_id=
                        current.shot_id,

                    reason=(
                        "Current shot narrative_order must be "
                        "greater than previous shot in linear evaluation."
                    ),

                    evidence={
                        "previous_order":
                            previous.narrative_order,

                        "current_order":
                            current.narrative_order,
                    },
                )
            )


        # --------------------------------------------------------
        # Non-linear modes
        # --------------------------------------------------------

        if (
            previous.continuity_mode
            in cls.NON_LINEAR_MODES
            or
            current.continuity_mode
            in cls.NON_LINEAR_MODES
        ):

            compatible = not any(
                row.severity == "BLOCK"
                for row in violations
            )

            score = (
                1.0
                if compatible
                else 0.0
            )

            return ContinuityEvaluationRC2(
                previous_shot_id=
                    previous.shot_id,

                current_shot_id=
                    current.shot_id,

                compatible=
                    compatible,

                temporal_score=
                    score,

                violations=
                    tuple(
                        violations
                    ),
            )


        previous_after = (
            previous.after
        )

        current_before = (
            current.before
        )


        # --------------------------------------------------------
        # Character identity
        # --------------------------------------------------------

        if (
            previous_after.character_ids
            and
            current_before.character_ids
        ):

            previous_chars = set(
                previous_after.character_ids
            )

            current_chars = set(
                current_before.character_ids
            )

            if previous_chars != current_chars:

                violations.append(
                    ContinuityViolationRC2(
                        code=
                            "IDENTITY_DRIFT",

                        severity=
                            "BLOCK",

                        previous_shot_id=
                            previous.shot_id,

                        current_shot_id=
                            current.shot_id,

                        reason=(
                            "Character identity changed between "
                            "adjacent linear shots."
                        ),

                        evidence={
                            "previous_characters":
                                sorted(
                                    previous_chars
                                ),

                            "current_characters":
                                sorted(
                                    current_chars
                                ),
                        },
                    )
                )


        # --------------------------------------------------------
        # Location
        # --------------------------------------------------------

        if not cls._same_or_unknown(
            previous_after.location,
            current_before.location,
        ):

            violations.append(
                ContinuityViolationRC2(
                    code=
                        "LOCATION_DRIFT",

                    severity=
                        "BLOCK",

                    previous_shot_id=
                        previous.shot_id,

                    current_shot_id=
                        current.shot_id,

                    reason=(
                        "Location changed between adjacent linear "
                        "shots without an explicit non-linear mode."
                    ),

                    evidence={
                        "previous_location":
                            previous_after.location,

                        "current_location":
                            current_before.location,
                    },
                )
            )


        # --------------------------------------------------------
        # Time period
        # --------------------------------------------------------

        previous_time = (
            previous_after.time_period
        )

        current_time = (
            current_before.time_period
        )

        if (
            previous_time != "unknown"
            and
            current_time != "unknown"
            and
            previous_time != current_time
        ):

            violations.append(
                ContinuityViolationRC2(
                    code=
                        "TIME_PERIOD_DRIFT",

                    severity=
                        "BLOCK",

                    previous_shot_id=
                        previous.shot_id,

                    current_shot_id=
                        current.shot_id,

                    reason=(
                        "Time period changed inside a linear "
                        "continuous sequence."
                    ),

                    evidence={
                        "previous_time_period":
                            previous_time,

                        "current_time_period":
                            current_time,
                    },
                )
            )


        # --------------------------------------------------------
        # Wardrobe
        # --------------------------------------------------------

        if (
            previous_after.wardrobe_state
            and
            current_before.wardrobe_state
        ):

            if (
                tuple(
                    previous_after.wardrobe_state
                )
                !=
                tuple(
                    current_before.wardrobe_state
                )
            ):

                violations.append(
                    ContinuityViolationRC2(
                        code=
                            "WARDROBE_DRIFT",

                        severity=
                            "BLOCK",

                        previous_shot_id=
                            previous.shot_id,

                        current_shot_id=
                            current.shot_id,

                        reason=(
                            "Wardrobe changed between adjacent "
                            "linear shots."
                        ),

                        evidence={
                            "previous_wardrobe":
                                list(
                                    previous_after.wardrobe_state
                                ),

                            "current_wardrobe":
                                list(
                                    current_before.wardrobe_state
                                ),
                        },
                    )
                )


        # --------------------------------------------------------
        # Movement direction
        # --------------------------------------------------------

        prev_dir = cls._norm(
            previous_after.movement_direction
        )

        curr_dir = cls._norm(
            current_before.movement_direction
        )

        if (
            prev_dir
            and
            curr_dir
            and
            (prev_dir, curr_dir)
            in cls.OPPOSITE_DIRECTIONS
        ):

            violations.append(
                ContinuityViolationRC2(
                    code=
                        "MOVEMENT_DIRECTION_CONFLICT",

                    severity=
                        "BLOCK",

                    previous_shot_id=
                        previous.shot_id,

                    current_shot_id=
                        current.shot_id,

                    reason=(
                        "Movement direction reversed inside the "
                        "same linear sequence."
                    ),

                    evidence={
                        "previous_direction":
                            previous_after.movement_direction,

                        "current_direction":
                            current_before.movement_direction,
                    },
                )
            )


        # --------------------------------------------------------
        # Completed events must never disappear.
        # --------------------------------------------------------

        previous_events = set(
            previous_after.completed_events
        )

        current_events = set(
            current_before.completed_events
        )


        if (
            previous_events
            and
            current_events
            and
            not previous_events.issubset(
                current_events
            )
        ):

            missing_events = sorted(
                previous_events
                - current_events
            )

            violations.append(
                ContinuityViolationRC2(
                    code=
                        "COMPLETED_EVENT_LOST",

                    severity=
                        "BLOCK",

                    previous_shot_id=
                        previous.shot_id,

                    current_shot_id=
                        current.shot_id,

                    reason=(
                        "Previously completed events disappeared "
                        "from current linear state."
                    ),

                    evidence={
                        "missing_completed_events":
                            missing_events,
                    },
                )
            )


        # --------------------------------------------------------
        # Explicit completed action reversal.
        # --------------------------------------------------------

        current_action = cls._norm(
            current_before.action
        )


        for completed in (
            previous_after.completed_events
        ):

            completed_norm = cls._norm(
                completed
            )

            # Match rule by semantic tail.
            for finished_action, forbidden_actions in (
                cls.ACTION_REGRESSION_RULES.items()
            ):

                if (
                    finished_action
                    not in completed_norm
                ):
                    continue

                if (
                    current_action
                    in forbidden_actions
                ):

                    violations.append(
                        ContinuityViolationRC2(
                            code=
                                "COMPLETED_ACTION_REVERSAL",

                            severity=
                                "BLOCK",

                            previous_shot_id=
                                previous.shot_id,

                            current_shot_id=
                                current.shot_id,

                            reason=(
                                f"Completed action '{completed}' "
                                f"cannot regress to "
                                f"'{current_before.action}' "
                                "in LINEAR continuity."
                            ),

                            evidence={
                                "completed_event":
                                    completed,

                                "previous_action":
                                    previous_after.action,

                                "current_action":
                                    current_before.action,

                                "previous_position":
                                    previous_after.position,

                                "current_position":
                                    current_before.position,
                            },
                        )
                    )


        # --------------------------------------------------------
        # Position inconsistency.
        #
        # Only treat explicit different values as warning because
        # many legitimate shots move through space.
        # --------------------------------------------------------

        if not cls._same_or_unknown(
            previous_after.position,
            current_before.position,
        ):

            violations.append(
                ContinuityViolationRC2(
                    code=
                        "POSITION_DISCONTINUITY",

                    severity=
                        "WARNING",

                    previous_shot_id=
                        previous.shot_id,

                    current_shot_id=
                        current.shot_id,

                    reason=(
                        "Character/object position changed between "
                        "adjacent shots. Review whether movement "
                        "between states is visually justified."
                    ),

                    evidence={
                        "previous_position":
                            previous_after.position,

                        "current_position":
                            current_before.position,
                    },
                )
            )


        # --------------------------------------------------------
        # Object state
        # --------------------------------------------------------

        if (
            previous_after.object_states
            and
            current_before.object_states
        ):

            previous_objects = set(
                previous_after.object_states
            )

            current_objects = set(
                current_before.object_states
            )

            if (
                previous_objects
                != current_objects
            ):

                violations.append(
                    ContinuityViolationRC2(
                        code=
                            "OBJECT_STATE_DRIFT",

                        severity=
                            "WARNING",

                        previous_shot_id=
                            previous.shot_id,

                        current_shot_id=
                            current.shot_id,

                        reason=(
                            "Tracked object state differs across "
                            "adjacent shots."
                        ),

                        evidence={
                            "previous_objects":
                                sorted(
                                    previous_objects
                                ),

                            "current_objects":
                                sorted(
                                    current_objects
                                ),
                        },
                    )
                )


        # --------------------------------------------------------
        # Score
        # --------------------------------------------------------

        block_count = sum(
            1
            for row in violations
            if row.severity == "BLOCK"
        )

        warning_count = sum(
            1
            for row in violations
            if row.severity == "WARNING"
        )


        if block_count:

            score = 0.0

        else:

            score = max(
                0.0,
                1.0
                - warning_count * 0.15
            )


        compatible = (
            block_count == 0
        )


        return ContinuityEvaluationRC2(
            previous_shot_id=
                previous.shot_id,

            current_shot_id=
                current.shot_id,

            compatible=
                compatible,

            temporal_score=
                score,

            violations=
                tuple(
                    violations
                ),
        )


    @classmethod
    def require_compatible(
        cls,
        previous: ShotContinuityRC2,
        current: ShotContinuityRC2,
    ) -> ContinuityEvaluationRC2:

        result = cls.evaluate(
            previous,
            current,
        )


        if not result.compatible:

            codes = [
                row.code
                for row in result.violations
                if row.severity == "BLOCK"
            ]

            raise RuntimeError(
                "VISUAL_CONTINUITY_BLOCKED: "
                f"{previous.shot_id} -> "
                f"{current.shot_id}: "
                + ", ".join(
                    codes
                )
            )


        return result




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
