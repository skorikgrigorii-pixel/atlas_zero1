from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VALID_STRATEGIES = {
    "chronological",
    "thematic",
    "investigative",
    "journey",
    "event_progression",
    "biographical",
    "causal",
}


@dataclass(frozen=True)
class StoryStrategyRC2:
    film_type: str
    narrative_strategy: str
    language: str
    target_duration_sec: float
    target_audience: str
    use_existing_assets_only: bool
    allow_generated_visuals: bool

    def validate(self) -> None:
        if not self.film_type.strip():
            raise ValueError("film_type is required")

        if self.narrative_strategy not in VALID_STRATEGIES:
            raise ValueError(
                f"Unsupported narrative_strategy: "
                f"{self.narrative_strategy}"
            )

        if not self.language.strip():
            raise ValueError("language is required")

        if self.target_duration_sec <= 0:
            raise ValueError(
                "target_duration_sec must be > 0"
            )

        if not self.target_audience.strip():
            raise ValueError(
                "target_audience is required"
            )

        if (
            self.use_existing_assets_only
            and self.allow_generated_visuals
        ):
            raise ValueError(
                "Existing-assets-only mode cannot allow "
                "generated visuals"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class StoryActRC2:
    act_id: str
    title_ru: str
    narrative_goal_ru: str
    order: int
    duration_sec: float

    def validate(self) -> None:
        if not self.act_id.strip():
            raise ValueError("act_id is required")

        if not self.title_ru.strip():
            raise ValueError("title_ru is required")

        if not self.narrative_goal_ru.strip():
            raise ValueError(
                "narrative_goal_ru is required"
            )

        if self.order < 1:
            raise ValueError("order must be >= 1")

        if self.duration_sec <= 0:
            raise ValueError(
                "duration_sec must be > 0"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class StorySceneRC2:
    scene_id: str
    act_id: str
    title_ru: str
    narrative_goal_ru: str
    emotional_goal_ru: str
    visual_strategy_ru: str
    order: int
    duration_sec: float
    cluster_ids: tuple[str, ...]
    asset_ids: tuple[str, ...]

    def validate(self) -> None:
        if not self.scene_id.strip():
            raise ValueError("scene_id is required")

        if not self.act_id.strip():
            raise ValueError("act_id is required")

        if not self.title_ru.strip():
            raise ValueError("title_ru is required")

        if not self.narrative_goal_ru.strip():
            raise ValueError(
                "narrative_goal_ru is required"
            )

        if not self.emotional_goal_ru.strip():
            raise ValueError(
                "emotional_goal_ru is required"
            )

        if not self.visual_strategy_ru.strip():
            raise ValueError(
                "visual_strategy_ru is required"
            )

        if self.order < 1:
            raise ValueError("order must be >= 1")

        if self.duration_sec <= 0:
            raise ValueError(
                "duration_sec must be > 0"
            )

        if not self.cluster_ids:
            raise ValueError(
                "Story scene must reference clusters"
            )

        if not self.asset_ids:
            raise ValueError(
                "Story scene must reference assets"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class NarrativeTransitionRC2:
    from_scene_id: str
    to_scene_id: str
    transition_type: str
    rationale_ru: str
    narrator_bridge_required: bool

    def validate(self) -> None:
        if not self.from_scene_id.strip():
            raise ValueError(
                "from_scene_id is required"
            )

        if not self.to_scene_id.strip():
            raise ValueError(
                "to_scene_id is required"
            )

        if (
            self.from_scene_id
            == self.to_scene_id
        ):
            raise ValueError(
                "Transition cannot reference "
                "the same scene"
            )

        if not self.transition_type.strip():
            raise ValueError(
                "transition_type is required"
            )

        if not self.rationale_ru.strip():
            raise ValueError(
                "rationale_ru is required"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class StoryStrategyResultRC2:
    project_id: str
    strategy: StoryStrategyRC2
    acts: tuple[StoryActRC2, ...]
    scenes: tuple[StorySceneRC2, ...]
    transitions: tuple[
        NarrativeTransitionRC2,
        ...
    ]
    engine: str = "story_strategy_engine_rc2"
    state: str = "STORY_STRATEGY_READY"

    def validate(self) -> None:
        if not self.project_id.strip():
            raise ValueError(
                "project_id is required"
            )

        self.strategy.validate()

        if not self.acts:
            raise ValueError(
                "At least one act is required"
            )

        if not self.scenes:
            raise ValueError(
                "At least one scene is required"
            )

        act_ids: set[str] = set()

        for act in self.acts:
            act.validate()

            if act.act_id in act_ids:
                raise ValueError(
                    f"Duplicate act_id: {act.act_id}"
                )

            act_ids.add(act.act_id)

        scene_ids: set[str] = set()

        previous_order = 0

        for scene in self.scenes:
            scene.validate()

            if scene.scene_id in scene_ids:
                raise ValueError(
                    f"Duplicate scene_id: "
                    f"{scene.scene_id}"
                )

            if scene.act_id not in act_ids:
                raise ValueError(
                    f"Scene references unknown act: "
                    f"{scene.act_id}"
                )

            if scene.order <= previous_order:
                raise ValueError(
                    "Scene order must be "
                    "strictly increasing"
                )

            previous_order = scene.order
            scene_ids.add(scene.scene_id)

        expected_transitions = max(
            len(self.scenes) - 1,
            0,
        )

        if len(self.transitions) != expected_transitions:
            raise ValueError(
                "Transitions must connect every "
                "adjacent scene"
            )

        for index, transition in enumerate(
            self.transitions
        ):
            transition.validate()

            expected_from = (
                self.scenes[index].scene_id
            )
            expected_to = (
                self.scenes[index + 1].scene_id
            )

            if (
                transition.from_scene_id
                != expected_from
                or transition.to_scene_id
                != expected_to
            ):
                raise ValueError(
                    "Transitions must follow scene order"
                )

        scene_duration = sum(
            scene.duration_sec
            for scene in self.scenes
        )

        if abs(
            scene_duration
            - self.strategy.target_duration_sec
        ) > 1.0:
            raise ValueError(
                "Scene duration must match "
                "target duration"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()

        return {
            "engine": self.engine,
            "state": self.state,
            "project_id": self.project_id,
            "strategy": self.strategy.to_dict(),
            "acts": [
                act.to_dict()
                for act in self.acts
            ],
            "scenes": [
                scene.to_dict()
                for scene in self.scenes
            ],
            "transitions": [
                transition.to_dict()
                for transition in self.transitions
            ],
        }
