from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .visual_production_semantics_rc2 import (
    ProductionSemanticOverlayIndexRC2,
    ProductionSemanticsRC2,
    VisualProductionSemanticsRC2,
)


SCHEMA = "ATLAS_ZERO_VISUAL_PRODUCTION_PLAN_RC2_2"


@dataclass
class ProductionUnitRC22:
    production_asset_id: str
    scene_id: str

    source_shot_ids: list[str]
    source_visual_types: list[str]

    screen_action: str
    location: str
    time_state: str
    characters: list[str]

    acquisition_mode: str
    motion_class: str

    editorial_duration_sec: float

    unique_generation_required: bool

    editorial_variations: list[str]

    semantic_sources: list[str]
    semantic_confidence: float

    estimated_manual_minutes: float
    estimated_generation_attempts: float

    warnings: list[str] = field(default_factory=list)

    # RC2 visual diversity policy.
    # One generated source must not be recycled to cover a long unit.
    required_unique_generated_assets: int = 0
    generated_target_shot_sec: float = 0.0
    generation_slot_ids: list[str] = field(default_factory=list)


class VisualProductionPlannerRC2:
    def __init__(
        self,
        *,
        overlay_index: ProductionSemanticOverlayIndexRC2 | None = None,
        generated_master_target_sec: float = 24.0,
        generated_master_max_sec: float = 34.0,
        generated_video_clip_target_sec: float = 6.0,
        generated_still_target_sec: float = 4.0,
        manual_image_minutes: float = 5.0,
        manual_video_minutes: float = 8.0,
        manual_research_minutes: float = 2.0,
    ) -> None:

        self.overlay_index = (
            overlay_index
            or ProductionSemanticOverlayIndexRC2()
        )

        self.semantic_engine = (
            VisualProductionSemanticsRC2(
                self.overlay_index
            )
        )

        self.generated_master_target_sec = (
            generated_master_target_sec
        )

        self.generated_master_max_sec = (
            generated_master_max_sec
        )

        self.generated_video_clip_target_sec = max(
            1.0,
            float(generated_video_clip_target_sec),
        )

        self.generated_still_target_sec = max(
            1.0,
            float(generated_still_target_sec),
        )

        self.manual_image_minutes = (
            manual_image_minutes
        )

        self.manual_video_minutes = (
            manual_video_minutes
        )

        self.manual_research_minutes = (
            manual_research_minutes
        )

    @staticmethod
    def _scene_id(
        scene: dict[str, Any],
        index: int,
    ) -> str:

        for key in (
            "scene_id",
            "id",
            "scene",
        ):
            value = scene.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

        return f"SC{index:02d}"

    @staticmethod
    def _extract_shots(
        scene: dict[str, Any],
    ) -> list[dict[str, Any]]:

        for key in (
            "shots",
            "planned_shots",
            "visual_shots",
        ):
            value = scene.get(key)

            if isinstance(value, list):
                return [
                    x
                    for x in value
                    if isinstance(x, dict)
                ]

        return []

    @staticmethod
    def _duration(
        shot: dict[str, Any],
    ) -> float:

        for key in (
            "duration_sec",
            "planned_duration_sec",
            "shot_duration_sec",
            "duration",
        ):
            value = shot.get(key)

            if isinstance(value, (int, float)):
                return max(
                    0.0,
                    float(value),
                )

        for parent_key in (
            "timing",
            "timeline",
            "time",
        ):
            parent = shot.get(
                parent_key
            )

            if isinstance(parent, dict):
                start = parent.get("start_sec")
                end = parent.get("end_sec")

                if (
                    isinstance(start, (int, float))
                    and isinstance(end, (int, float))
                ):
                    return max(
                        0.0,
                        float(end) - float(start),
                    )

        start = shot.get("start_sec")
        end = shot.get("end_sec")

        if (
            isinstance(start, (int, float))
            and isinstance(end, (int, float))
        ):
            return max(
                0.0,
                float(end) - float(start),
            )

        return 0.0

    @staticmethod
    def _mode(
        semantic: ProductionSemanticsRC2,
    ) -> str:

        if semantic.evidence_required:
            return "REAL_EVIDENCE_ACQUISITION"

        if semantic.ui_required:
            return "UI_CAPTURE_OR_RECONSTRUCTION"

        if semantic.upstream_visual_type == "REAL_FOOTAGE":
            return "REAL_FOOTAGE_ACQUISITION"

        if semantic.upstream_visual_type in {
            "CINEMATIC_RECONSTRUCTION",
            "GENERATED_VIDEO",
        }:
            return "GENERATED_MASTER_ASSET"

        # A stale RESEARCH_EVIDENCE label may already have been
        # overridden by production semantics.
        if (
            semantic.upstream_visual_type
            == "RESEARCH_EVIDENCE"
            and not semantic.evidence_required
        ):
            return "GENERATED_MASTER_ASSET"

        return "EDITORIAL_EXISTING_OR_REAL"

    @staticmethod
    def _semantic_compatible(
        anchor: ProductionSemanticsRC2,
        candidate: ProductionSemanticsRC2,
    ) -> bool:

        if (
            anchor.location != "UNKNOWN_LOCATION"
            and candidate.location != "UNKNOWN_LOCATION"
            and anchor.location != candidate.location
        ):
            return False

        if (
            anchor.time_state != "UNKNOWN_TIME"
            and candidate.time_state != "UNKNOWN_TIME"
            and anchor.time_state != candidate.time_state
        ):
            return False

        a = set(anchor.characters)
        b = set(candidate.characters)

        if a and b:
            if not (
                a & b
                or a.issubset(b)
                or b.issubset(a)
            ):
                return False

        if (
            anchor.motion_class == "VIDEO_REQUIRED"
            or candidate.motion_class == "VIDEO_REQUIRED"
        ):
            return False

        return True

    @staticmethod
    def _variation(
        index: int,
    ) -> str:

        variants = (
            "MASTER_FRAME",
            "EDITORIAL_CROP",
            "DETAIL_CROP",
            "SLOW_DIGITAL_PUSH",
            "REACTION_REFRAME",
            "RETURN_TO_MASTER",
        )

        return variants[
            index % len(variants)
        ]

    def _make_unit(
        self,
        *,
        scene_id: str,
        unit_index: int,
        group: list[
            tuple[
                dict[str, Any],
                ProductionSemanticsRC2,
            ]
        ],
        mode: str,
    ) -> ProductionUnitRC22:

        semantics = [
            s
            for _, s in group
        ]

        duration = round(
            sum(
                self._duration(shot)
                for shot, _ in group
            ),
            3,
        )

        motion_classes = {
            s.motion_class
            for s in semantics
        }

        if "VIDEO_REQUIRED" in motion_classes:
            motion_class = "VIDEO_REQUIRED"

        elif "VIDEO_OPTIONAL" in motion_classes:
            motion_class = "VIDEO_OPTIONAL"

        elif "SOURCE_NATIVE" in motion_classes:
            motion_class = "SOURCE_NATIVE"

        else:
            motion_class = "STILL_PREFERRED"

        if mode == "GENERATED_MASTER_ASSET":
            unique_generation = True

            if motion_class == "VIDEO_REQUIRED":
                manual_minutes = (
                    self.manual_video_minutes
                )
                attempts = 1.5

            else:
                manual_minutes = (
                    self.manual_image_minutes
                )
                attempts = 1.35

        elif mode in {
            "REAL_EVIDENCE_ACQUISITION",
            "UI_CAPTURE_OR_RECONSTRUCTION",
            "REAL_FOOTAGE_ACQUISITION",
        }:
            unique_generation = False
            manual_minutes = (
                self.manual_research_minutes
            )
            attempts = 0.0

        else:
            unique_generation = False
            manual_minutes = 0.5
            attempts = 0.0

        locations = [
            s.location
            for s in semantics
            if s.location != "UNKNOWN_LOCATION"
        ]

        times = [
            s.time_state
            for s in semantics
            if s.time_state != "UNKNOWN_TIME"
        ]

        characters = sorted(
            {
                char
                for s in semantics
                for char in s.characters
            }
        )

        source_types = sorted(
            {
                s.upstream_visual_type
                for s in semantics
            }
        )

        warnings = []

        for semantic in semantics:
            for warning in semantic.warnings:
                if warning not in warnings:
                    warnings.append(warning)

        semantic_sources = sorted(
            {
                s.semantic_source
                for s in semantics
            }
        )

        confidence = round(
            sum(
                s.semantic_confidence
                for s in semantics
            )
            / max(
                1,
                len(semantics),
            ),
            3,
        )

        actions = []

        for semantic in semantics:
            action = semantic.screen_action.strip()

            if action and action not in actions:
                actions.append(action)

        combined_action = " | ".join(
            actions[:3]
        )

        return ProductionUnitRC22(
            production_asset_id=(
                f"{scene_id}_PA_{unit_index:03d}"
            ),
            scene_id=scene_id,
            source_shot_ids=[
                s.shot_id
                for s in semantics
            ],
            source_visual_types=source_types,
            screen_action=combined_action,
            location=(
                locations[0]
                if locations
                else "UNKNOWN_LOCATION"
            ),
            time_state=(
                times[0]
                if times
                else "UNKNOWN_TIME"
            ),
            characters=characters,
            acquisition_mode=mode,
            motion_class=motion_class,
            editorial_duration_sec=duration,
            unique_generation_required=unique_generation,
            editorial_variations=[
                self._variation(i)
                for i in range(
                    len(group)
                )
            ],
            semantic_sources=semantic_sources,
            semantic_confidence=confidence,
            estimated_manual_minutes=manual_minutes,
            estimated_generation_attempts=attempts,
            warnings=warnings,
        )

    def _apply_generated_duration_policy(
        self,
        units: list[ProductionUnitRC22],
    ) -> None:
        """
        RC2 generated visual diversity policy.

        Generated screen duration must be covered by enough distinct
        generated assets. A single generated image/video may not be
        silently looped or recycled to fill a long editorial unit.

        VIDEO_REQUIRED:
            target ~= generated_video_clip_target_sec

        Other generated visual units:
            target ~= generated_still_target_sec
        """

        for unit in units:

            if (
                unit.acquisition_mode
                != "GENERATED_MASTER_ASSET"
            ):
                continue

            duration = max(
                0.0,
                float(unit.editorial_duration_sec),
            )

            if (
                unit.motion_class
                == "VIDEO_REQUIRED"
            ):
                target = (
                    self.generated_video_clip_target_sec
                )
            else:
                target = (
                    self.generated_still_target_sec
                )

            if duration <= 0:
                required = 1
            else:
                quotient = duration / target

                required = int(quotient)

                if (
                    quotient
                    - float(required)
                    > 1e-9
                ):
                    required += 1

                required = max(
                    1,
                    required,
                )

            unit.generated_target_shot_sec = round(
                target,
                3,
            )

            unit.required_unique_generated_assets = (
                required
            )

            unit.generation_slot_ids = [
                (
                    f"{unit.production_asset_id}"
                    f"_GEN_{index:03d}"
                )
                for index in range(
                    1,
                    required + 1,
                )
            ]

            if required > 1:
                unit.unique_generation_required = True

                warning = (
                    "GENERATED_DURATION_REQUIRES_"
                    f"{required}_UNIQUE_ASSETS"
                )

                if warning not in unit.warnings:
                    unit.warnings.append(
                        warning
                    )

    def plan_scene(
        self,
        scene: dict[str, Any],
        scene_index: int,
    ) -> dict[str, Any]:

        scene_id = self._scene_id(
            scene,
            scene_index,
        )

        raw_shots = self._extract_shots(
            scene
        )

        enriched: list[
            tuple[
                dict[str, Any],
                ProductionSemanticsRC2,
            ]
        ] = []

        for i, shot in enumerate(
            raw_shots,
            1,
        ):
            semantic = (
                self.semantic_engine.analyze(
                    shot,
                    fallback_shot_id=(
                        f"{scene_id}_SHOT_{i:03d}"
                    ),
                )
            )

            enriched.append(
                (
                    shot,
                    semantic,
                )
            )

        units: list[
            ProductionUnitRC22
        ] = []

        i = 0

        while i < len(enriched):
            shot, semantic = enriched[i]

            mode = self._mode(
                semantic
            )

            # Evidence and UI stay discrete:
            # each may carry different readable information.
            if mode in {
                "REAL_EVIDENCE_ACQUISITION",
                "UI_CAPTURE_OR_RECONSTRUCTION",
            }:
                units.append(
                    self._make_unit(
                        scene_id=scene_id,
                        unit_index=len(units) + 1,
                        group=[
                            (
                                shot,
                                semantic,
                            )
                        ],
                        mode=mode,
                    )
                )

                i += 1
                continue

            # Required temporal motion remains its own production unit.
            if (
                semantic.motion_class
                == "VIDEO_REQUIRED"
            ):
                units.append(
                    self._make_unit(
                        scene_id=scene_id,
                        unit_index=len(units) + 1,
                        group=[
                            (
                                shot,
                                semantic,
                            )
                        ],
                        mode=mode,
                    )
                )

                i += 1
                continue

            group = [
                (
                    shot,
                    semantic,
                )
            ]

            accumulated = (
                self._duration(
                    shot
                )
            )

            anchor = semantic

            i += 1

            while i < len(enriched):
                candidate_shot, candidate_semantic = (
                    enriched[i]
                )

                candidate_mode = self._mode(
                    candidate_semantic
                )

                if candidate_mode != mode:
                    break

                if (
                    candidate_semantic.motion_class
                    == "VIDEO_REQUIRED"
                ):
                    break

                if not self._semantic_compatible(
                    anchor,
                    candidate_semantic,
                ):
                    break

                candidate_duration = (
                    self._duration(
                        candidate_shot
                    )
                )

                if (
                    accumulated
                    + candidate_duration
                    > self.generated_master_max_sec
                    and mode
                    == "GENERATED_MASTER_ASSET"
                ):
                    break

                group.append(
                    (
                        candidate_shot,
                        candidate_semantic,
                    )
                )

                accumulated += (
                    candidate_duration
                )

                i += 1

                if (
                    mode == "GENERATED_MASTER_ASSET"
                    and accumulated
                    >= self.generated_master_target_sec
                    and len(group) >= 3
                ):
                    break

            units.append(
                self._make_unit(
                    scene_id=scene_id,
                    unit_index=len(units) + 1,
                    group=group,
                    mode=mode,
                )
            )

        # Apply RC2 duration-aware generation diversity policy.
        self._apply_generated_duration_policy(units)

        return {
            "scene_id": scene_id,

            "editorial_shot_count":
                len(enriched),

            "production_asset_count":
                len(units),

            "new_generation_count":
                sum(
                    1
                    for u in units
                    if u.unique_generation_required
                ),

            "video_required_count":
                sum(
                    1
                    for u in units
                    if u.motion_class
                    == "VIDEO_REQUIRED"
                ),

            "video_optional_count":
                sum(
                    1
                    for u in units
                    if u.motion_class
                    == "VIDEO_OPTIONAL"
                ),

            "still_preferred_count":
                sum(
                    1
                    for u in units
                    if u.motion_class
                    == "STILL_PREFERRED"
                ),

            "real_or_evidence_count":
                sum(
                    1
                    for u in units
                    if u.acquisition_mode
                    in {
                        "REAL_EVIDENCE_ACQUISITION",
                        "REAL_FOOTAGE_ACQUISITION",
                        "UI_CAPTURE_OR_RECONSTRUCTION",
                    }
                ),

            "rich_semantic_shot_count":
                sum(
                    1
                    for _, s in enriched
                    if s.semantic_source
                    == "RICH_PRODUCTION_OVERLAY"
                ),

            "estimated_manual_minutes":
                round(
                    sum(
                        u.estimated_manual_minutes
                        for u in units
                    ),
                    1,
                ),

            "semantics": [
                asdict(s)
                for _, s in enriched
            ],

            "units": [
                asdict(u)
                for u in units
            ],
        }

    def plan(
        self,
        visual_map: dict[str, Any],
    ) -> dict[str, Any]:

        scenes = visual_map.get(
            "scenes"
        )

        if not isinstance(
            scenes,
            list,
        ):
            raise ValueError(
                "Visual map does not contain scenes list."
            )

        plans = [
            self.plan_scene(
                scene,
                index,
            )
            for index, scene in enumerate(
                scenes,
                1,
            )
            if isinstance(
                scene,
                dict,
            )
        ]

        editorial = sum(
            x["editorial_shot_count"]
            for x in plans
        )

        assets = sum(
            x["production_asset_count"]
            for x in plans
        )

        manual = round(
            sum(
                x["estimated_manual_minutes"]
                for x in plans
            ),
            1,
        )

        return {
            "schema": SCHEMA,

            "project_id":
                visual_map.get(
                    "project_id"
                ),

            "source_schema":
                visual_map.get(
                    "schema"
                ),

            "production_policy": {
                "fundamental_rule":
                    "NARRATION_BEAT != EDITORIAL_SHOT != PRODUCTION_ASSET",

                "semantic_enrichment_required":
                    True,

                "rich_production_overlay_priority":
                    True,

                "semantic_grouping":
                    True,

                "continuity_compatibility_required":
                    True,

                "video_only_when_temporal_motion_has_screen_value":
                    True,

                "stale_upstream_visual_type_may_be_overridden":
                    True,

                "fixed_generation_quota":
                    False,

                "rights_gate_required":
                    True,

                "generated_duration_requires_unique_assets":
                    True,

                "generated_video_clip_target_sec":
                    self.generated_video_clip_target_sec,

                "generated_still_target_sec":
                    self.generated_still_target_sec,

                "generated_asset_repetition_allowed":
                    False,

                "reference_only_must_generate_original":
                    True,
            },

            "summary": {
                "scene_count":
                    len(plans),

                "editorial_shot_count":
                    editorial,

                "production_asset_count":
                    assets,

                "production_asset_compression_ratio":
                    round(
                        0.0
                        if editorial == 0
                        else 1.0
                        - assets / editorial,
                        4,
                    ),

                "new_generation_count":
                    sum(
                        x["new_generation_count"]
                        for x in plans
                    ),

                "video_required_count":
                    sum(
                        x["video_required_count"]
                        for x in plans
                    ),

                "video_optional_count":
                    sum(
                        x["video_optional_count"]
                        for x in plans
                    ),

                "still_preferred_count":
                    sum(
                        x["still_preferred_count"]
                        for x in plans
                    ),

                "real_or_evidence_count":
                    sum(
                        x["real_or_evidence_count"]
                        for x in plans
                    ),

                "rich_semantic_shot_count":
                    sum(
                        x["rich_semantic_shot_count"]
                        for x in plans
                    ),

                "estimated_manual_minutes":
                    manual,

                "estimated_manual_hours":
                    round(
                        manual / 60.0,
                        2,
                    ),
            },

            "scenes":
                plans,

            "status":
                "PLANNED_RC2_2",
        }


def load_json(
    path: str | Path,
) -> dict[str, Any]:

    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(
    path: str | Path,
    payload: dict[str, Any],
) -> Path:

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )

        f.write("\n")

    tmp.replace(
        path
    )

    return path
