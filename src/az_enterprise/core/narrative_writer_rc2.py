from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .openai_adapter_rc2 import OpenAIAdapterRC2


RUSSIAN_WORDS_PER_MINUTE = 132.0


@dataclass(frozen=True)
class SceneNarrationRC2:
    scene_id: str
    scene_title: str
    start_sec: float
    end_sec: float
    duration_sec: float
    target_words: int
    narration_ru: str
    opening_line_ru: str
    closing_line_ru: str
    narrator_bridge_ru: str
    source_cluster_ids: tuple[str, ...]
    source_asset_ids: tuple[str, ...]

    def validate(self) -> None:
        if not self.scene_id.strip():
            raise ValueError("scene_id is required")

        if not self.scene_title.strip():
            raise ValueError(
                "scene_title is required"
            )

        if self.start_sec < 0:
            raise ValueError(
                "start_sec must be >= 0"
            )

        if self.end_sec <= self.start_sec:
            raise ValueError(
                "end_sec must be greater than start_sec"
            )

        if self.duration_sec <= 0:
            raise ValueError(
                "duration_sec must be > 0"
            )

        if self.target_words < 1:
            raise ValueError(
                "target_words must be >= 1"
            )

        if not self.narration_ru.strip():
            raise ValueError(
                "narration_ru is required"
            )

        if not self.source_cluster_ids:
            raise ValueError(
                "source_cluster_ids are required"
            )

        if not self.source_asset_ids:
            raise ValueError(
                "source_asset_ids are required"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class NarrativeResultRC2:
    project_id: str
    language: str
    target_duration_sec: float
    total_target_words: int
    scenes: tuple[SceneNarrationRC2, ...]
    full_narration_ru: str
    engine: str = "narrative_writer_rc2"
    state: str = "NARRATIVE_READY"

    def validate(self) -> None:
        if not self.project_id.strip():
            raise ValueError(
                "project_id is required"
            )

        if self.language != "ru":
            raise ValueError(
                "NarrativeWriterRC2 currently supports ru"
            )

        if self.target_duration_sec <= 0:
            raise ValueError(
                "target_duration_sec must be > 0"
            )

        if not self.scenes:
            raise ValueError(
                "At least one narrated scene is required"
            )

        previous_end = 0.0

        for scene in self.scenes:
            scene.validate()

            if scene.start_sec < previous_end - 0.001:
                raise ValueError(
                    "Scene narration timing overlaps"
                )

            previous_end = scene.end_sec

        if not self.full_narration_ru.strip():
            raise ValueError(
                "full_narration_ru is required"
            )

        calculated_words = sum(
            scene.target_words
            for scene in self.scenes
        )

        if calculated_words != self.total_target_words:
            raise ValueError(
                "total_target_words mismatch"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()

        return {
            "engine": self.engine,
            "state": self.state,
            "project_id": self.project_id,
            "language": self.language,
            "target_duration_sec":
                self.target_duration_sec,
            "total_target_words":
                self.total_target_words,
            "scenes": [
                scene.to_dict()
                for scene in self.scenes
            ],
            "full_narration_ru":
                self.full_narration_ru,
        }


class NarrativeWriterRC2:
    """Create deterministic Russian narration scaffolding.

    This stage produces a grounded first narrative draft from the
    semantic story strategy. It does not call an external language
    model and does not generate audio.
    """

    def __init__(
        self,
        *,
        project_id: str,
        words_per_minute: float =
            RUSSIAN_WORDS_PER_MINUTE,
        mode: str = "local_fallback",
        openai_adapter: OpenAIAdapterRC2 | None = None,
        allow_paid: bool = False,
    ) -> None:
        self.project_id = project_id
        self.words_per_minute = max(
            80.0,
            float(words_per_minute),
        )

        if mode not in {
            "local_fallback",
            "openai_editorial",
        }:
            raise ValueError(
                f"Unsupported narrative mode: {mode}"
            )

        self.mode = mode
        self.openai_adapter = (
            openai_adapter
            if openai_adapter is not None
            else OpenAIAdapterRC2()
        )
        self.allow_paid = bool(allow_paid)
        self.last_editorial_status = (
            "not_requested"
        )

    def run(
        self,
        strategy_payload: dict[str, Any],
    ) -> NarrativeResultRC2:
        strategy = dict(
            strategy_payload.get(
                "strategy",
                {},
            )
        )

        scenes = list(
            strategy_payload.get(
                "scenes",
                [],
            )
        )

        transitions = {
            str(item["to_scene_id"]): item
            for item in strategy_payload.get(
                "transitions",
                [],
            )
        }

        if not scenes:
            raise ValueError(
                "Strategy payload contains no scenes"
            )

        target_duration = float(
            strategy.get(
                "target_duration_sec",
                0.0,
            )
        )

        if target_duration <= 0:
            target_duration = sum(
                float(
                    scene.get(
                        "duration_sec",
                        0.0,
                    )
                )
                for scene in scenes
            )

        current_time = 0.0
        narrated_scenes: list[
            SceneNarrationRC2
        ] = []

        for index, scene in enumerate(
            scenes,
            start=1,
        ):
            duration = float(
                scene["duration_sec"]
            )

            start_sec = round(
                current_time,
                3,
            )

            end_sec = round(
                current_time + duration,
                3,
            )

            target_words = max(
                30,
                round(
                    duration
                    / 60.0
                    * self.words_per_minute
                ),
            )

            title = str(
                scene.get(
                    "title_ru",
                    f"Сцена {index}",
                )
            )

            goal = str(
                scene.get(
                    "narrative_goal_ru",
                    "",
                )
            )

            emotion = str(
                scene.get(
                    "emotional_goal_ru",
                    "интерес",
                )
            )

            opening = self._opening_line(
                index=index,
                title=title,
            )

            body = self._scene_body(
                title=title,
                goal=goal,
                emotion=emotion,
            )

            closing = self._closing_line(
                index=index,
                total=len(scenes),
                title=title,
            )

            transition = transitions.get(
                str(
                    scene.get(
                        "scene_id",
                        "",
                    )
                )
            )

            bridge = ""

            if transition:
                bridge = str(
                    transition.get(
                        "rationale_ru",
                        "",
                    )
                )

            narration = " ".join(
                part.strip()
                for part in (
                    opening,
                    body,
                    closing,
                    bridge,
                )
                if part.strip()
            )

            narration = self._expand_to_target(
                narration,
                target_words,
                title=title,
                goal=goal,
            )

            narrated_scenes.append(
                SceneNarrationRC2(
                    scene_id=str(
                        scene["scene_id"]
                    ),
                    scene_title=title,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    duration_sec=duration,
                    target_words=target_words,
                    narration_ru=narration,
                    opening_line_ru=opening,
                    closing_line_ru=closing,
                    narrator_bridge_ru=bridge,
                    source_cluster_ids=tuple(
                        str(value)
                        for value in (
                            scene.get(
                                "cluster_ids",
                                [],
                            )
                        )
                    ),
                    source_asset_ids=tuple(
                        str(value)
                        for value in (
                            scene.get(
                                "asset_ids",
                                [],
                            )
                        )
                    ),
                )
            )

            current_time = end_sec

        full_narration = "\n\n".join(
            (
                f"{scene.scene_id}. "
                f"{scene.scene_title}\n"
                f"{scene.narration_ru}"
            )
            for scene in narrated_scenes
        )

        result = NarrativeResultRC2(
            project_id=self.project_id,
            language=str(
                strategy.get(
                    "language",
                    "ru",
                )
            ),
            target_duration_sec=round(
                target_duration,
                3,
            ),
            total_target_words=sum(
                scene.target_words
                for scene in narrated_scenes
            ),
            scenes=tuple(
                narrated_scenes
            ),
            full_narration_ru=
                full_narration,
        )

        result.validate()

        if self.mode == "openai_editorial":
            return self._apply_openai_editorial(
                result
            )

        self.last_editorial_status = (
            "local_fallback"
        )
        return result

    def _apply_openai_editorial(
        self,
        result: NarrativeResultRC2,
    ) -> NarrativeResultRC2:
        instructions = (
            "You are the senior documentary editor "
            "for ATLAS ZERO. Rewrite the supplied "
            "Russian narration into a coherent, "
            "fact-conscious documentary voice-over. "
            "Write only in Russian. Remove repetition, "
            "technical production language and generic "
            "phrases. Preserve all scene headings in "
            "the exact format SC01., SC02. and so on. "
            "Do not invent interviews, events, people "
            "or visuals that are not present. Keep the "
            "overall length close to the source."
        )

        response = (
            self.openai_adapter.generate_text(
                instructions=instructions,
                input_text=result.full_narration_ru,
                allow_paid=self.allow_paid,
                reasoning_effort="low",
            )
        )

        self.last_editorial_status = (
            response.status
        )

        if response.status != "completed":
            return result

        edited_text = response.text.strip()

        if not edited_text:
            self.last_editorial_status = (
                "fallback_empty_editorial"
            )
            return result

        edited_result = NarrativeResultRC2(
            project_id=result.project_id,
            language=result.language,
            target_duration_sec=(
                result.target_duration_sec
            ),
            total_target_words=(
                result.total_target_words
            ),
            scenes=result.scenes,
            full_narration_ru=edited_text,
        )

        edited_result.validate()
        return edited_result

    @staticmethod
    def _opening_line(
        *,
        index: int,
        title: str,
    ) -> str:
        if index == 1:
            return (
                "Аликанте меняется задолго до того, "
                "как над городом вспыхивает первый огонь."
            )

        return (
            f"Следующая часть этой истории — "
            f"{title.lower()}."
        )

    @staticmethod
    def _scene_body(
        *,
        title: str,
        goal: str,
        emotion: str,
    ) -> str:
        return (
            f"{title} становится самостоятельной "
            f"главой праздника. {goal} "
            f"Визуальный ритм сцены должен передать "
            f"состояние: {emotion}."
        )

    @staticmethod
    def _closing_line(
        *,
        index: int,
        total: int,
        title: str,
    ) -> str:
        if index == total:
            return (
                "Праздник заканчивается, но город "
                "уже хранит ожидание следующего лета."
            )

        return (
            f"Но история {title.lower()} "
            f"ещё не завершает праздник."
        )

    @staticmethod
    def _expand_to_target(
        text: str,
        target_words: int,
        *,
        title: str,
        goal: str,
    ) -> str:
        words = text.split()

        additions = (
            f"Кадры сцены «{title}» раскрывают событие "
            f"через реальные детали, движение людей, "
            f"звук улиц и изменение городской среды. "
            f"{goal} "
            "Материал используется без вымышленных "
            "визуальных эпизодов и без подмены "
            "документального наблюдения реконструкцией."
        )

        addition_words = additions.split()

        while len(words) < target_words:
            remaining = (
                target_words - len(words)
            )

            words.extend(
                addition_words[:remaining]
            )

        return " ".join(
            words[:target_words]
        )
