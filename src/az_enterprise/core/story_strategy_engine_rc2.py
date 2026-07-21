from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .story_strategy_contract_rc2 import (
    NarrativeTransitionRC2,
    StoryActRC2,
    StorySceneRC2,
    StoryStrategyRC2,
    StoryStrategyResultRC2,
)


EVENT_ORDER = {
    "city_context": 10,
    "preparation": 20,
    "monument": 30,
    "parade": 40,
    "flower_offering": 45,
    "music_band": 50,
    "street_festival": 60,
    "mascleta": 70,
    "crowd_reaction": 80,
    "beach_event": 85,
    "fireworks": 90,
    "firefighters": 95,
    "crema": 100,
}


EVENT_TITLES_RU = {'city_context': 'Аликанте перед праздником',
 'preparation': 'Подготовка к празднику',
 'monument': 'Город праздничных фигур',
 'parade': 'Шествия по улицам',
 'flower_offering': 'Подношение цветов',
 'music_band': 'Музыка праздника',
 'street_festival': 'Улицы Hogueras',
 'mascleta': 'Грохот масклеты',
 'crowd_reaction': 'Город смотрит и празднует',
 'beach_event': 'Праздник у моря',
 'fireworks': 'Небо над Аликанте',
 'firefighters': 'Пожарные и огненный финал',
 'crema': 'Крема — ночь огня'}

EVENT_GOALS_RU = {'city_context': 'Познакомить зрителя с городом и масштабом праздника.',
 'preparation': 'Показать, как Аликанте готовится к главным событиям.',
 'monument': 'Раскрыть художественный мир праздничных композиций.',
 'parade': 'Показать участников, костюмы и движение праздника.',
 'flower_offering': 'Передать церемониальную и традиционную сторону Hogueras.',
 'music_band': 'Создать ощущение живого уличного праздника.',
 'street_festival': 'Показать город, наполненный людьми, светом и движением.',
 'mascleta': 'Передать физическую мощь дневной пиротехники.',
 'crowd_reaction': 'Показать эмоции зрителей и атмосферу массового события.',
 'beach_event': 'Расширить пространство фильма до побережья Аликанте.',
 'fireworks': 'Подвести фильм к ночной визуальной кульминации.',
 'firefighters': 'Показать работу служб во время огненного финала.',
 'crema': 'Завершить историю главным ритуалом праздника.'}

EVENT_EMOTIONS_RU = {'city_context': 'ожидание',
 'preparation': 'предвкушение',
 'monument': 'удивление',
 'parade': 'энергия',
 'flower_offering': 'торжественность',
 'music_band': 'радость',
 'street_festival': 'праздничное движение',
 'mascleta': 'напряжение и мощь',
 'crowd_reaction': 'вовлечённость',
 'beach_event': 'свобода',
 'fireworks': 'восхищение',
 'firefighters': 'напряжение',
 'crema': 'кульминация и прощание'}



class StoryStrategyEngineRC2:
    """Build a documentary structure from Event Discovery output."""

    def __init__(
        self,
        project_id: str,
        target_duration_sec: float = 810.0,
        language: str = "ru",
        use_existing_assets_only: bool = True,
        allow_generated_visuals: bool = False,
    ) -> None:
        self.project_id = project_id
        self.target_duration_sec = float(
            target_duration_sec
        )
        self.language = language
        self.use_existing_assets_only = (
            use_existing_assets_only
        )
        self.allow_generated_visuals = (
            allow_generated_visuals
        )

    def run(
        self,
        event_discovery: dict[str, Any],
    ) -> StoryStrategyResultRC2:
        clusters = list(
            event_discovery.get(
                "event_clusters",
                [],
            )
        )

        if not clusters:
            raise ValueError(
                "Event discovery contains no clusters"
            )

        usable_clusters = [
            cluster
            for cluster in clusters
            if cluster.get("asset_ids")
            and cluster.get("event_type")
            != "unrelated_private_content"
        ]

        if not usable_clusters:
            raise ValueError(
                "No usable event clusters found"
            )

        ordered_clusters = sorted(
            usable_clusters,
            key=self._cluster_order_key,
        )

        strategy = StoryStrategyRC2(
            film_type="documentary",
            narrative_strategy="event_progression",
            language=self.language,
            target_duration_sec=self.target_duration_sec,
            target_audience="18-55",
            use_existing_assets_only=(
                self.use_existing_assets_only
            ),
            allow_generated_visuals=(
                self.allow_generated_visuals
            ),
        )

        scene_durations = self._allocate_durations(
            ordered_clusters
        )

        scenes: list[StorySceneRC2] = []

        for index, (
            cluster,
            duration,
        ) in enumerate(
            zip(
                ordered_clusters,
                scene_durations,
            ),
            start=1,
        ):
            event_type = str(
                cluster["event_type"]
            )

            scene = StorySceneRC2(
                scene_id=f"SC{index:02d}",
                act_id=self._act_id_for(
                    index,
                    len(ordered_clusters),
                ),
                title_ru=EVENT_TITLES_RU.get(
                    event_type,
                    str(
                        cluster.get(
                            "title_ru",
                            event_type,
                        )
                    ),
                ),
                narrative_goal_ru=
                    EVENT_GOALS_RU.get(
                        event_type,
                        str(
                            cluster.get(
                                "description_ru",
                                "???????? ???????.",
                            )
                        ),
                    ),
                emotional_goal_ru=
                    EVENT_EMOTIONS_RU.get(
                        event_type,
                        "???????",
                    ),
                visual_strategy_ru=(
                    "???????????? ?????? ????????? "
                    "????????? ????????; ?????????? "
                    "?????, ??????? ? ??????? ?????."
                ),
                order=index,
                duration_sec=duration,
                cluster_ids=(
                    str(cluster["cluster_id"]),
                ),
                asset_ids=tuple(
                    str(asset_id)
                    for asset_id
                    in cluster["asset_ids"]
                ),
            )

            scenes.append(scene)

        acts = self._build_acts(scenes)
        transitions = self._build_transitions(
            scenes
        )

        result = StoryStrategyResultRC2(
            project_id=self.project_id,
            strategy=strategy,
            acts=tuple(acts),
            scenes=tuple(scenes),
            transitions=tuple(transitions),
        )

        result.validate()
        return result

    @staticmethod
    def _cluster_order_key(
        cluster: dict[str, Any],
    ) -> tuple[int, int, str]:
        event_type = str(
            cluster.get(
                "event_type",
                "unknown",
            )
        )

        time_period = str(
            cluster.get(
                "time_period",
                "unknown",
            )
        )

        time_order = {
            "morning": 0,
            "day": 1,
            "evening": 2,
            "night": 3,
            "unknown": 4,
        }.get(
            time_period,
            4,
        )

        return (
            EVENT_ORDER.get(
                event_type,
                500,
            ),
            time_order,
            str(
                cluster.get(
                    "cluster_id",
                    "",
                )
            ),
        )

    def _allocate_durations(
        self,
        clusters: list[dict[str, Any]],
    ) -> list[float]:
        weights = []

        for cluster in clusters:
            story_value = float(
                cluster.get(
                    "story_value",
                    0.5,
                )
            )

            asset_count = len(
                cluster.get(
                    "asset_ids",
                    [],
                )
            )

            weight = (
                max(story_value, 0.15)
                * max(asset_count, 1) ** 0.5
            )

            weights.append(weight)

        total_weight = sum(weights)

        raw = [
            self.target_duration_sec
            * weight
            / total_weight
            for weight in weights
        ]

        durations = [
            round(value, 3)
            for value in raw
        ]

        difference = round(
            self.target_duration_sec
            - sum(durations),
            3,
        )

        durations[-1] = round(
            durations[-1] + difference,
            3,
        )

        return durations

    @staticmethod
    def _act_id_for(
        scene_index: int,
        scene_count: int,
    ) -> str:
        ratio = scene_index / max(
            scene_count,
            1,
        )

        if ratio <= 0.34:
            return "ACT01"

        if ratio <= 0.72:
            return "ACT02"

        return "ACT03"

    def _build_acts(
        self,
        scenes: list[StorySceneRC2],
    ) -> list[StoryActRC2]:
        definitions = {'ACT01': ('Город готовится',
                   'Познакомить зрителя с Аликанте, фигурами и началом праздника.'),
         'ACT02': ('Праздник захватывает улицы',
                   'Показать шествия, музыку, людей и дневную пиротехнику.'),
         'ACT03': ('Ночь огня',
                   'Привести историю к фейерверкам, креме и завершению праздника.')}

        acts: list[StoryActRC2] = []

        for order, act_id in enumerate(
            ("ACT01", "ACT02", "ACT03"),
            start=1,
        ):
            members = [
                scene
                for scene in scenes
                if scene.act_id == act_id
            ]

            if not members:
                continue

            title, goal = definitions[act_id]

            acts.append(
                StoryActRC2(
                    act_id=act_id,
                    title_ru=title,
                    narrative_goal_ru=goal,
                    order=order,
                    duration_sec=round(
                        sum(
                            scene.duration_sec
                            for scene in members
                        ),
                        3,
                    ),
                )
            )

        return acts

    @staticmethod
    def _build_transitions(
        scenes: list[StorySceneRC2],
    ) -> list[NarrativeTransitionRC2]:
        transitions = []

        for current, following in zip(
            scenes,
            scenes[1:],
        ):
            act_changed = (
                current.act_id
                != following.act_id
            )

            transitions.append(
                NarrativeTransitionRC2(
                    from_scene_id=current.scene_id,
                    to_scene_id=following.scene_id,
                    transition_type=(
                        "narrator_bridge"
                        if act_changed
                        else "visual_dissolve"
                    ),
                    rationale_ru=(
                        f"??????? ????? "
                        f"?{current.title_ru}? "
                        f"?? ?????? "
                        f"?{following.title_ru}?."
                    ),
                    narrator_bridge_required=(
                        act_changed
                    ),
                )
            )

        return transitions


def load_event_discovery(
    path: Path | str,
) -> dict[str, Any]:
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )
