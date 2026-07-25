"""ATLAS ZERO Alpha 2.9.3 — Director Policy & Project Strategy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class ProjectType(str, Enum):
    DOCUMENTARY = "DOCUMENTARY"
    YOUTUBE = "YOUTUBE"
    SHORT_FORM = "SHORT_FORM"
    ADVERTISEMENT = "ADVERTISEMENT"
    EDUCATIONAL = "EDUCATIONAL"
    SHORT_FILM = "SHORT_FILM"
    CUSTOM = "CUSTOM"


class ProjectObjective(str, Enum):
    RETENTION = "RETENTION"
    EMOTION = "EMOTION"
    ACCURACY = "ACCURACY"
    CONVERSION = "CONVERSION"
    CLARITY = "CLARITY"
    PRESTIGE = "PRESTIGE"
    BALANCED = "BALANCED"


@dataclass(frozen=True)
class QualityProfile:
    """Weighted evaluation profile used by Director AI."""

    weights: Mapping[str, float]
    release_threshold: float = 0.80
    rework_threshold: float = 0.55

    def __post_init__(self) -> None:
        if not self.weights:
            raise ValueError("quality profile requires at least one criterion")

        for criterion, weight in self.weights.items():
            if not criterion.strip():
                raise ValueError("quality criterion cannot be empty")
            if weight < 0:
                raise ValueError("quality weights cannot be negative")

        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("quality weights total must be greater than zero")

        if not 0.0 <= self.rework_threshold <= 1.0:
            raise ValueError("rework_threshold must be between 0.0 and 1.0")
        if not 0.0 <= self.release_threshold <= 1.0:
            raise ValueError("release_threshold must be between 0.0 and 1.0")
        if self.rework_threshold > self.release_threshold:
            raise ValueError("rework_threshold cannot exceed release_threshold")

    def normalized_weights(self) -> dict[str, float]:
        total = sum(self.weights.values())
        return {key: value / total for key, value in self.weights.items()}

    def score(self, metrics: Mapping[str, float]) -> float:
        normalized = self.normalized_weights()
        missing = [criterion for criterion in normalized if criterion not in metrics]
        if missing:
            raise ValueError(
                "missing quality metrics: " + ", ".join(sorted(missing))
            )

        score = 0.0
        for criterion, weight in normalized.items():
            value = metrics[criterion]
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"metric '{criterion}' must be between 0.0 and 1.0"
                )
            score += value * weight
        return score


@dataclass(frozen=True)
class MandatoryConstraint:
    name: str
    expected: Any
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("constraint name cannot be empty")


@dataclass(frozen=True)
class DirectorPolicy:
    """Project-level decision policy owned by Director AI."""

    project_type: ProjectType
    objective: ProjectObjective
    quality_profile: QualityProfile
    constraints: tuple[MandatoryConstraint, ...] = ()
    allowed_rework_targets: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate_constraints(
        self,
        project_facts: Mapping[str, Any],
    ) -> tuple[str, ...]:
        violations: list[str] = []
        for constraint in self.constraints:
            actual = project_facts.get(constraint.name)
            if actual != constraint.expected:
                violations.append(
                    f"{constraint.name}: expected {constraint.expected!r}, "
                    f"got {actual!r}"
                )
        return tuple(violations)

    def validate_rework_targets(
        self,
        targets: Sequence[str],
    ) -> tuple[str, ...]:
        if not self.allowed_rework_targets:
            return tuple(targets)

        allowed = set(self.allowed_rework_targets)
        invalid = [target for target in targets if target not in allowed]
        if invalid:
            raise ValueError(
                "rework targets are not allowed by policy: "
                + ", ".join(sorted(set(invalid)))
            )
        return tuple(targets)


@dataclass(frozen=True)
class ProjectEvaluation:
    score: float
    constraint_violations: tuple[str, ...]
    metrics: Mapping[str, float]

    @property
    def constraints_passed(self) -> bool:
        return not self.constraint_violations


class DirectorPolicyEvaluator:
    """Deterministic policy evaluation before AI interpretation."""

    def evaluate(
        self,
        policy: DirectorPolicy,
        metrics: Mapping[str, float],
        project_facts: Mapping[str, Any],
    ) -> ProjectEvaluation:
        return ProjectEvaluation(
            score=policy.quality_profile.score(metrics),
            constraint_violations=policy.validate_constraints(project_facts),
            metrics=dict(metrics),
        )
