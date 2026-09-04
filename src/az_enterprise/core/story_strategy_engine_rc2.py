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
        target_duration_sec: float | None = None,
        language: str = "ru",
        use_existing_assets_only: bool = True,
        allow_generated_visuals: bool = False,
    ) -> None:
        self.project_id = project_id

        if (
            target_duration_sec is not None
            and float(target_duration_sec) <= 0.0
        ):
            raise ValueError(
                "target_duration_sec must be greater than zero"
            )

        # CHANGE-006A:
        # An explicitly supplied duration remains authoritative.
        # When omitted, run() derives it from the usable event clusters.
        self.target_duration_sec = (
            float(target_duration_sec)
            if target_duration_sec is not None
            else None
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

        resolved_target_duration_sec = (
            self._resolve_target_duration(
                ordered_clusters
            )
        )

        strategy = StoryStrategyRC2(
            film_type="documentary",
            narrative_strategy="event_progression",
            language=self.language,
            target_duration_sec=resolved_target_duration_sec,
            target_audience="18-55",
            use_existing_assets_only=(
                self.use_existing_assets_only
            ),
            allow_generated_visuals=(
                self.allow_generated_visuals
            ),
        )

        scene_durations = self._allocate_durations(
            ordered_clusters,
            resolved_target_duration_sec,
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

    def run_from_external_script(
        self,
        external_scenes,
        *,
        title: str = "",
        asset_ids=(),
        narration_words_per_minute: float = 120.0,
    ) -> StoryStrategyResultRC2:
        """Build canonical Story Strategy from an approved script.

        Approved external narration is the story authority in this mode.
        Visual-semantic analysis remains evidence/asset intelligence and
        must not redefine the screenplay structure.

        This path is project-independent.
        """

        rows = list(external_scenes)

        if not rows:
            raise ValueError(
                "Approved external script contains no scenes"
            )

        words_per_minute = float(
            narration_words_per_minute
        )

        if words_per_minute <= 0.0:
            raise ValueError(
                "narration_words_per_minute must be > 0"
            )

        normalized_assets = tuple(
            str(asset_id)
            for asset_id in asset_ids
            if str(asset_id).strip()
        )

        scene_rows = []

        for index, row in enumerate(
            rows,
            start=1,
        ):

            if isinstance(row, dict):
                scene_id = str(
                    row.get("scene_id")
                    or ""
                ).strip()

                scene_title = str(
                    row.get("title")
                    or row.get("scene_title")
                    or ""
                ).strip()

                narration = str(
                    row.get("narration_ru")
                    or row.get("narration")
                    or row.get("voiceover")
                    or row.get("text")
                    or ""
                ).strip()

                raw_duration = row.get(
                    "duration_sec"
                )

                explicit_duration = (
                    float(raw_duration)
                    if raw_duration not in (None, "")
                    else None
                )

            else:
                scene_id = str(
                    getattr(
                        row,
                        "scene_id",
                        "",
                    )
                ).strip()

                scene_title = str(
                    getattr(
                        row,
                        "title",
                        "",
                    )
                ).strip()

                narration = str(
                    getattr(
                        row,
                        "narration_ru",
                        "",
                    )
                    or getattr(
                        row,
                        "narration",
                        "",
                    )
                ).strip()

                raw_duration = getattr(
                    row,
                    "duration_sec",
                    None,
                )

                explicit_duration = (
                    float(raw_duration)
                    if raw_duration not in (None, "")
                    else None
                )

            if isinstance(row, dict):
                storytelling_mode = str(
                    row.get("storytelling_mode")
                    or "NARRATION"
                ).strip().upper()

                visual_direction = str(
                    row.get("visual_direction")
                    or ""
                ).strip()
            else:
                storytelling_mode = str(
                    getattr(
                        row,
                        "storytelling_mode",
                        "NARRATION",
                    )
                    or "NARRATION"
                ).strip().upper()

                visual_direction = str(
                    getattr(
                        row,
                        "visual_direction",
                        "",
                    )
                    or ""
                ).strip()

            if not scene_id:
                scene_id = (
                    f"scene_{index:03d}"
                )

            valid_modes = {
                "NARRATION",
                "VISUAL_MUSIC",
                "VISUAL_SFX",
                "MUSIC_ONLY",
            }

            if storytelling_mode not in valid_modes:
                raise ValueError(
                    f"Approved external script scene "
                    f"{scene_id!r} has unsupported "
                    f"storytelling_mode={storytelling_mode!r}"
                )

            if (
                storytelling_mode == "NARRATION"
                and not narration
            ):
                raise ValueError(
                    f"Approved external script scene "
                    f"{scene_id!r} has no narration"
                )

            if (
                storytelling_mode != "NARRATION"
                and explicit_duration is None
            ):
                raise ValueError(
                    f"Approved external non-narration "
                    f"scene {scene_id!r} requires "
                    f"explicit duration_sec"
                )

            if not scene_title:
                scene_title = (
                    f"????? {index}"
                )

            word_count = (
                len(narration.split())
                if narration
                else 0
            )

            if explicit_duration is not None:

                if explicit_duration <= 0.0:
                    raise ValueError(
                        f"Approved external script scene "
                        f"{scene_id!r} has invalid "
                        f"duration_sec={explicit_duration!r}"
                    )

                duration_sec = float(
                    explicit_duration
                )

                duration_authority = (
                    "approved_external_script"
                )

            else:

                duration_sec = max(
                    8.0,
                    word_count
                    * 60.0
                    / words_per_minute,
                )

                duration_authority = (
                    "narration_estimate"
                )

            scene_rows.append({
                "scene_id":
                    scene_id,

                "title":
                    scene_title,

                "narration":
                    narration,

                "word_count":
                    word_count,

                "duration_sec":
                    duration_sec,

                "duration_authority":
                    duration_authority,

                # Directorial metadata must survive
                # the normalization pass and remain
                # bound to this exact scene.
                "storytelling_mode":
                    storytelling_mode,

                "visual_direction":
                    visual_direction,
            })


        # -------------------------------------------------------------
        # Optional explicit target duration remains authoritative.
        # Otherwise narration itself determines documentary duration.
        # -------------------------------------------------------------

        natural_total = sum(
            row["duration_sec"]
            for row in scene_rows
        )

        if self.target_duration_sec is not None:

            target_total = float(
                self.target_duration_sec
            )

            scale = (
                target_total
                / natural_total
            )

            for row in scene_rows:
                row["duration_sec"] *= scale

        else:
            target_total = natural_total


        # -------------------------------------------------------------
        # Build scenes preserving EXACT external-script scene IDs/order.
        # -------------------------------------------------------------

        scenes: list[StorySceneRC2] = []

        scene_count = len(
            scene_rows
        )

        for index, row in enumerate(
            scene_rows,
            start=1,
        ):

            if normalized_assets:

                assigned_asset = (
                    normalized_assets[
                        (index - 1)
                        % len(normalized_assets)
                    ],
                )

            else:

                assigned_asset = ()


            scene = StorySceneRC2(
                scene_id=row[
                    "scene_id"
                ],

                act_id=self._act_id_for(
                    index,
                    scene_count,
                ),

                title_ru=row[
                    "title"
                ],

                narrative_goal_ru=(
                    "???????? ???????????? ?????? "
                    "?????????? ????????."
                ),

                emotional_goal_ru=(
                    "????????????????? ???????"
                ),

                visual_strategy_ru=(
                    str(
                        row.get(
                            "visual_direction",
                            "",
                        )
                    ).strip()
                    or (
                        "Follow the approved external "
                        "script visual direction while "
                        "preserving documentary integrity."
                    )
                ),

                order=index,

                duration_sec=round(
                    float(
                        row["duration_sec"]
                    ),
                    3,
                ),

                cluster_ids=(
                    "approved_external_script:"
                    + row["scene_id"],
                ),

                asset_ids=assigned_asset,
            )

            scenes.append(
                scene
            )


        # -------------------------------------------------------------
        # Generic acts.
        # Do NOT use the legacy Hogueras act titles.
        # -------------------------------------------------------------

        act_definitions = {
            "ACT01": (
                "?????? ?????????????",
                "????????? ??????????? ?????? ?????? "
                "? ??????????? ???????? ??????????????.",
            ),

            "ACT02": (
                "???????? ?????????????",
                "???????? ???????? ??????????????, "
                "????? ? ????????????.",
            ),

            "ACT03": (
                "??????",
                "??????? ?????????????? ? ???????? "
                "??????? ? ????????? ??????.",
            ),
        }

        acts: list[StoryActRC2] = []

        for order, act_id in enumerate(
            (
                "ACT01",
                "ACT02",
                "ACT03",
            ),
            start=1,
        ):

            members = [
                scene
                for scene in scenes
                if scene.act_id
                == act_id
            ]

            if not members:
                continue

            act_title, act_goal = (
                act_definitions[
                    act_id
                ]
            )

            acts.append(
                StoryActRC2(
                    act_id=act_id,
                    title_ru=act_title,
                    narrative_goal_ru=(
                        act_goal
                    ),
                    order=order,
                    duration_sec=round(
                        sum(
                            scene.duration_sec
                            for scene
                            in members
                        ),
                        3,
                    ),
                )
            )


        # -------------------------------------------------------------
        # Generic transitions preserving script order.
        # -------------------------------------------------------------

        transitions: list[
            NarrativeTransitionRC2
        ] = []

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
                    from_scene_id=(
                        current.scene_id
                    ),

                    to_scene_id=(
                        following.scene_id
                    ),

                    transition_type=(
                        "narrator_bridge"
                        if act_changed
                        else "visual_dissolve"
                    ),

                    rationale_ru=(
                        "??????? ????? ????????? "
                        "??????? ????????????? "
                        "????????."
                    ),

                    narrator_bridge_required=(
                        act_changed
                    ),
                )
            )


        strategy = StoryStrategyRC2(
            film_type="documentary",

            narrative_strategy=(
                "event_progression"
            ),

            language=self.language,

            target_duration_sec=round(
                sum(
                    scene.duration_sec
                    for scene
                    in scenes
                ),
                3,
            ),

            target_audience="18-55",

            use_existing_assets_only=(
                self.use_existing_assets_only
            ),

            allow_generated_visuals=(
                self.allow_generated_visuals
            ),
        )


        result = StoryStrategyResultRC2(
            project_id=self.project_id,
            strategy=strategy,
            acts=tuple(acts),
            scenes=tuple(scenes),
            transitions=tuple(
                transitions
            ),
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

    def _resolve_target_duration(
        self,
        clusters: list[dict[str, Any]],
    ) -> float:
        """Resolve one authoritative film duration for the strategy."""

        if self.target_duration_sec is not None:
            return self.target_duration_sec

        cluster_count = len(clusters)

        unique_asset_ids = {
            str(asset_id)
            for cluster in clusters
            for asset_id in cluster.get(
                "asset_ids",
                [],
            )
        }
        asset_count = len(unique_asset_ids)

        story_values = [
            max(
                0.0,
                min(
                    float(
                        cluster.get(
                            "story_value",
                            0.5,
                        )
                    ),
                    1.5,
                ),
            )
            for cluster in clusters
        ]
        average_story_value = (
            sum(story_values)
            / max(len(story_values), 1)
        )

        # Documentary duration model:
        # - editorial setup and conclusion;
        # - structural cost of every distinct event;
        # - additional room for available visual evidence;
        # - a modest complexity allowance for high-value material.
        estimated_duration = (
            180.0
            + cluster_count * 30.0
            + min(asset_count, 180) * 2.0
            + average_story_value * 60.0
        )

        minimum_duration = max(
            300.0,
            cluster_count * 20.0,
        )
        maximum_duration = 1500.0

        resolved_duration = min(
            max(
                estimated_duration,
                minimum_duration,
            ),
            maximum_duration,
        )

        # Five-second precision keeps downstream scene allocation stable
        # while avoiding an artificial frame-perfect strategy target.
        return round(
            resolved_duration / 5.0
        ) * 5.0

    def _allocate_durations(
        self,
        clusters: list[dict[str, Any]],
        target_duration_sec: float,
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
            target_duration_sec
            * weight
            / total_weight
            for weight in weights
        ]

        durations = [
            round(value, 3)
            for value in raw
        ]

        difference = round(
            target_duration_sec
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
