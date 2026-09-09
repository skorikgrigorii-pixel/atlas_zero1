from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from .database import Database
from .events import EventBus


class AssignmentPolicyRC2:
    """Canonical assignment decision policy.

    Assignment priority:
    1. Use explicit Story Engine decisions from story_scenes.required_assets.
    2. Fall back to legacy semantic scoring only when Story Engine did not
       provide a usable asset for the shot.

    This class is the only owner of assignment writes.
    """

    ACCEPTANCE_THRESHOLD = 0.62

    # Universal semantic classes that must never enter a production timeline.
    # These classes describe private, unrelated, or otherwise non-editorial
    # material rather than project-specific story content.
    EXCLUDED_SEMANTIC_CLASSES = {
        "unrelated_private_content",
        "off_topic",
        "private_content",
        "medical_private_content",
    }

    # Semantic confidence below this value is treated as too weak to influence
    # assignment ranking. It does not reject the asset by itself.
    MIN_SEMANTIC_CONFIDENCE = 0.30


    def __init__(
        self,
        db: Database,
        project_id: str,
        *,
        production_policy_advisory: dict[str, Any] | None = None,
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)

        # PATCH 7A4 ? BOUNDED ProductionPolicyAdvisory PROJECTION
        #
        # AssignmentPolicyRC2 remains the sole owner of concrete production
        # parameters.
        #
        # Learning supplies bounded pressure only.
        #
        # Hard semantic exclusions, rights/safety gates, per-asset max_use,
        # visual-family max-use and source-lineage max-use remain immutable.
        self.production_policy_advisory = (
            dict(production_policy_advisory)
            if isinstance(
                production_policy_advisory,
                dict,
            )
            else None
        )

        self.production_policy_profile = (
            self._project_production_policy_advisory(
                self.production_policy_advisory
            )
        )

        self.acceptance_threshold = float(
            self.production_policy_profile[
                "acceptance_threshold"
            ]
        )

        self.minimum_semantic_confidence = float(
            self.production_policy_profile[
                "minimum_semantic_confidence"
            ]
        )

        self.recent_asset_window = int(
            self.production_policy_profile[
                "recent_asset_window"
            ]
        )

        # Per-project assignment usage.
        self.usage: defaultdict[str, int] = defaultdict(int)

        # Editorial diversity memory.
        #
        # AssignmentPolicyRC2 remains the canonical owner of
        # chronological assignment state.
        self.recent_asset_ids: list[str] = []
        self.recent_family_ids: list[str] = []

        # Visual-family diversity policy V3.
        #
        # One physical asset may be used only once by the existing
        # asset policy. A visual family may contain multiple physical
        # assets, therefore family usage requires its own hard limit.
        self.visual_family_max_use: int = 2
        self.visual_family_recent_window: int = int(
            self.production_policy_profile[
                "visual_family_recent_window"
            ]
        )
        self.family_usage: defaultdict[str, int] = defaultdict(int)

        # RC2 Source Lineage Gate V2.
        #
        # Different physical files may be editorial fragments derived
        # from one original source video. Asset identity, visual family
        # and provider/source identity cannot detect that case reliably.
        #
        # Example:
        #   02__HOOK_01__00006.0s.mp4
        #   03__HOOK_01__00108.0s.mp4
        #
        # They are different files but belong to one source lineage.
        self.source_lineage_max_use: int = 1
        self.source_lineage_usage: defaultdict[str, int] = defaultdict(int)
        self.recent_source_lineages: list[str] = []

        # RC2 Editorial Sequencing V4.
        #
        # Visual-family diversity prevents physical repetition.
        # Editorial sequencing prevents different assets from creating
        # the same repetitive viewing experience.
        self.motif_recent_window: int = int(
            self.production_policy_profile[
                "motif_recent_window"
            ]
        )
        self.same_motif_max_in_recent_window: int = int(
            self.production_policy_profile[
                "same_motif_max_in_recent_window"
            ]
        )
        self.same_source_max_consecutive: int = int(
            self.production_policy_profile[
                "same_source_max_consecutive"
            ]
        )
        self.same_media_type_max_consecutive: int = int(
            self.production_policy_profile[
                "same_media_type_max_consecutive"
            ]
        )

        self.recent_motifs: list[str] = []
        self.recent_sources: list[str] = []
        self.recent_media_types: list[str] = []

    @staticmethod
    def _tokens(value: Any) -> list[str]:
        """Normalize text into comparable semantic tokens."""
        return [
            token
            for token in re.findall(r"[\w]+", str(value or "").lower())
            if len(token) >= 3
        ]

    @staticmethod
    def _parse_required_assets(value: Any) -> dict[str, Any]:
        """Safely parse story_scenes.required_assets."""
        if isinstance(value, dict):
            data = value
        else:
            try:
                data = json.loads(value or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                return {
                    "asset_ids": [],
                    "cluster_ids": [],
                    "use_existing_assets_only": False,
                }

        if not isinstance(data, dict):
            return {
                "asset_ids": [],
                "cluster_ids": [],
                "use_existing_assets_only": False,
            }

        asset_ids = data.get("asset_ids") or []
        cluster_ids = data.get("cluster_ids") or []

        if not isinstance(asset_ids, list):
            asset_ids = [asset_ids]
        if not isinstance(cluster_ids, list):
            cluster_ids = [cluster_ids]

        return {
            "asset_ids": [
                str(asset_id)
                for asset_id in asset_ids
                if asset_id not in (None, "")
            ],
            "cluster_ids": [
                str(cluster_id)
                for cluster_id in cluster_ids
                if cluster_id not in (None, "")
            ],
            "use_existing_assets_only": bool(
                data.get("use_existing_assets_only", False)
            ),
        }

    @staticmethod
    def _shot_belongs_to_scene(shot: Any, scene: Any) -> bool:
        """Return True when a shot falls inside a story scene.

        Time range is the primary mapping because shots do not currently
        contain scene_id. Block matching is used as an additional guard when
        both records contain a block value.
        """
        shot_start = float(shot["start_sec"] or 0.0)
        shot_end = float(shot["end_sec"] or shot_start)
        scene_start = float(scene["start_sec"] or 0.0)
        scene_end = float(scene["end_sec"] or scene_start)

        overlaps = (
            shot_start < scene_end
            and shot_end > scene_start
        )

        if not overlaps:
            return False

        shot_block = str(shot["block"] or "").strip()
        scene_block = str(scene["block"] or "").strip()

        if shot_block and scene_block and shot_block != scene_block:
            return False

        return True

    def _preferred_assets_for_shot(
        self,
        shot: Any,
        scenes: list[Any],
        assets_by_id: dict[str, Any],
    ) -> tuple[list[Any], str | None]:
        """Resolve explicit Story Engine assets for a shot."""
        matching_scenes = [
            scene
            for scene in scenes
            if self._shot_belongs_to_scene(shot, scene)
        ]

        if not matching_scenes:
            return [], None

        # Prefer the narrowest overlapping scene if malformed ranges overlap.
        matching_scenes.sort(
            key=lambda scene: (
                float(scene["end_sec"] or 0.0)
                - float(scene["start_sec"] or 0.0),
                int(scene["idx"] or 0),
            )
        )
        scene = matching_scenes[0]
        required = self._parse_required_assets(scene["required_assets"])

        preferred = [
            assets_by_id[asset_id]
            for asset_id in required["asset_ids"]
            if asset_id in assets_by_id
        ]

        return preferred, str(scene["id"])

    @classmethod
    def _project_production_policy_advisory(
        cls,
        advisory: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Convert bounded learning pressure into concrete assignment parameters.

        PATCH 7A4 contract:
        - baseline is unchanged when advisory is absent/inactive;
        - pressures are clamped to 0..2;
        - semantic thresholds may move upward only;
        - temporal diversity windows may become stricter only;
        - hard semantic/safety/max-use gates are NOT projected here;
        - coverage pressure requests acquisition only and cannot force an asset.
        """

        baseline = {
            "acceptance_threshold":
                float(
                    cls.ACCEPTANCE_THRESHOLD
                ),

            "minimum_semantic_confidence":
                float(
                    cls.MIN_SEMANTIC_CONFIDENCE
                ),

            "recent_asset_window":
                8,

            "visual_family_recent_window":
                18,

            "motif_recent_window":
                6,

            "same_motif_max_in_recent_window":
                2,

            "same_source_max_consecutive":
                2,

            "same_media_type_max_consecutive":
                5,

            "coverage_action":
                "KEEP_MISSING_IF_NO_VALID_ASSET",

            "active":
                False,

            "mode":
                "baseline",

            "confidence":
                0.0,

            "pressures": {
                "semantic_strictness":
                    0,

                "reuse_pressure":
                    0,

                "diversity_pressure":
                    0,

                "sequencing_pressure":
                    0,

                "coverage_pressure":
                    0,
            },

            "evidence":
                [],

            "provenance":
                [],

            "source_schema":
                None,
        }

        if not isinstance(
            advisory,
            dict,
        ):
            return baseline

        if (
            advisory.get(
                "state"
            )
            !=
            "PRODUCTION_POLICY_ADVISORY_READY"
        ):
            return baseline

        raw_pressures = advisory.get(
            "pressures",
            {},
        )

        if not isinstance(
            raw_pressures,
            dict,
        ):
            raw_pressures = {}

        def bounded(
            key: str,
        ) -> int:
            try:
                value = int(
                    raw_pressures.get(
                        key,
                        0,
                    )
                    or 0
                )
            except (
                TypeError,
                ValueError,
            ):
                value = 0

            return max(
                0,
                min(
                    2,
                    value,
                ),
            )

        pressures = {
            "semantic_strictness":
                bounded(
                    "semantic_strictness"
                ),

            "reuse_pressure":
                bounded(
                    "reuse_pressure"
                ),

            "diversity_pressure":
                bounded(
                    "diversity_pressure"
                ),

            "sequencing_pressure":
                bounded(
                    "sequencing_pressure"
                ),

            "coverage_pressure":
                bounded(
                    "coverage_pressure"
                ),
        }

        try:
            confidence = float(
                advisory.get(
                    "confidence",
                    0.0,
                )
                or 0.0
            )
        except (
            TypeError,
            ValueError,
        ):
            confidence = 0.0

        confidence = max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        )

        #
        # Defense in depth:
        #
        # Even if a malformed caller labels an advisory READY, production
        # effect requires the same minimum confidence used by the learning
        # builder.
        #
        if confidence < 0.60:
            return baseline

        active = any(
            value > 0
            for value
            in pressures.values()
        )

        if not active:
            return baseline

        semantic_level = (
            pressures[
                "semantic_strictness"
            ]
        )

        reuse_level = (
            pressures[
                "reuse_pressure"
            ]
        )

        diversity_level = (
            pressures[
                "diversity_pressure"
            ]
        )

        sequencing_level = (
            pressures[
                "sequencing_pressure"
            ]
        )

        coverage_level = (
            pressures[
                "coverage_pressure"
            ]
        )

        acceptance_threshold = min(
            0.70,
            float(
                cls.ACCEPTANCE_THRESHOLD
            )
            +
            semantic_level
            * 0.04,
        )

        minimum_semantic_confidence = min(
            0.42,
            float(
                cls.MIN_SEMANTIC_CONFIDENCE
            )
            +
            semantic_level
            * 0.06,
        )

        recent_asset_window = (
            8
            +
            reuse_level
            * 4
        )

        visual_family_recent_window = (
            18
            +
            diversity_level
            * 6
        )

        motif_recent_window = (
            6
            +
            sequencing_level
            * 2
        )

        same_motif_max = (
            1
            if sequencing_level >= 2
            else 2
        )

        same_source_max = (
            1
            if sequencing_level >= 1
            else 2
        )

        same_media_max = max(
            3,
            5
            -
            sequencing_level,
        )

        if coverage_level >= 2:
            coverage_action = (
                "REQUEST_NEW_VISUAL_ASSET_HIGH_PRIORITY"
            )

        elif coverage_level == 1:
            coverage_action = (
                "REQUEST_NEW_VISUAL_ASSET"
            )

        else:
            coverage_action = (
                "KEEP_MISSING_IF_NO_VALID_ASSET"
            )

        evidence = [
            str(item)
            for item
            in (
                advisory.get(
                    "evidence",
                    (),
                )
                or ()
            )
            if str(item)
        ]

        provenance = [
            str(item)
            for item
            in (
                advisory.get(
                    "provenance",
                    (),
                )
                or ()
            )
            if str(item)
        ]

        return {
            "acceptance_threshold":
                round(
                    acceptance_threshold,
                    4,
                ),

            "minimum_semantic_confidence":
                round(
                    minimum_semantic_confidence,
                    4,
                ),

            "recent_asset_window":
                int(
                    recent_asset_window
                ),

            "visual_family_recent_window":
                int(
                    visual_family_recent_window
                ),

            "motif_recent_window":
                int(
                    motif_recent_window
                ),

            "same_motif_max_in_recent_window":
                int(
                    same_motif_max
                ),

            "same_source_max_consecutive":
                int(
                    same_source_max
                ),

            "same_media_type_max_consecutive":
                int(
                    same_media_max
                ),

            "coverage_action":
                coverage_action,

            "active":
                True,

            "mode":
                "bounded_advisory",

            "confidence":
                round(
                    confidence,
                    6,
                ),

            "pressures":
                pressures,

            "evidence":
                evidence,

            "provenance":
                provenance,

            "source_schema":
                advisory.get(
                    "schema"
                ),
        }

    @staticmethod
    def _row_value(
        row: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        """Read a value from sqlite rows, dicts, or row-like objects."""
        try:
            value = row[key]
        except (KeyError, IndexError, TypeError):
            return default
        return default if value is None else value

    def _semantic_profile(
        self,
        asset: Any,
    ) -> tuple[str, str, float]:
        """Return normalized semantic class, description, and confidence."""
        semantic_class = str(
            self._row_value(asset, "semantic_class", "")
        ).strip().lower()
        semantic_description = str(
            self._row_value(asset, "semantic_description", "")
        ).strip().lower()

        try:
            semantic_confidence = float(
                self._row_value(asset, "semantic_confidence", 0.0)
            )
        except (TypeError, ValueError):
            semantic_confidence = 0.0

        semantic_confidence = max(
            0.0,
            min(semantic_confidence, 1.0),
        )

        return (
            semantic_class,
            semantic_description,
            semantic_confidence,
        )

    def _asset_is_semantically_allowed(
        self,
        asset: Any,
    ) -> bool:
        """Reject universally unrelated or private material.

        This rule is intentionally project-independent. Project relevance is
        determined by score; explicit unrelated/private classes are hard
        exclusions for both Story Engine and fallback candidates.
        """
        semantic_class, semantic_description, _ = self._semantic_profile(
            asset
        )

        if semantic_class in self.EXCLUDED_SEMANTIC_CLASSES:
            return False

        if semantic_class.startswith("unrelated_"):
            return False

        exclusion_markers = (
            "off_topic",
            "off topic",
            "unrelated private",
        )
        return not any(
            marker in semantic_description
            for marker in exclusion_markers
        )


    def _asset_family(
        self,
        asset: Any,
    ) -> str:
        """Return the strongest available visual-family identity."""

        asset_id = str(
            self._row_value(
                asset,
                "id",
                "",
            )
            or ""
        )

        # Prefer explicit content/visual identity fields when present.
        for key in (
            "visual_family",
            "visual_family_id",
            "perceptual_hash",
            "phash",
            "content_hash",
            "sha256",
            "cluster_id",
        ):
            value = str(
                self._row_value(
                    asset,
                    key,
                    "",
                )
                or ""
            ).strip()

            if value:
                return (
                    f"{key}:{value}"
                )

        # duplicate_of points at the canonical visual.
        duplicate_of = str(
            self._row_value(
                asset,
                "duplicate_of",
                "",
            )
            or ""
        ).strip()

        if duplicate_of:
            return (
                f"duplicate_root:{duplicate_of}"
            )

        return (
            f"asset:{asset_id}"
        )


    def _source_profile(
        self,
        asset: Any,
    ) -> str:
        """Infer broad editorial provenance from existing asset metadata."""

        haystack = " ".join(
            str(
                self._row_value(
                    asset,
                    key,
                    "",
                )
                or ""
            )
            for key in (
                "path",
                "filename",
                "category",
                "semantic_class",
                "semantic_description",
                "tags",
                "source",
                "source_type",
                "provenance",
            )
        ).lower()

        user_markers = (
            "user_original",
            "user original",
            "user_upload",
            "user upload",
            "from_phone",
            "phone",
            "mobile",
            "iphone",
            "android",
            "personal_video",
            "camera upload",
        )

        if any(
            marker in haystack
            for marker in user_markers
        ):
            return "USER_ORIGINAL"

        real_markers = (
            "real_footage",
            "real footage",
            "clean_real",
            "news",
            "archive",
            "rtve",
            "euronews",
            "efe",
            "ap ",
            "reuters",
            "guardian",
            "elpais",
            "el pais",
            "dw news",
        )

        if any(
            marker in haystack
            for marker in real_markers
        ):
            return "REAL"

        generated_markers = (
            "leonardo",
            "generated",
            "generation",
            "ai_generated",
            "gen_job",
        )

        if any(
            marker in haystack
            for marker in generated_markers
        ):
            return "GENERATED"

        graphics_markers = (
            "graphic",
            "infographic",
            "motion_graphic",
            "map_",
        )

        if any(
            marker in haystack
            for marker in graphics_markers
        ):
            return "GRAPHICS"

        return "UNKNOWN"


    def _director_visual_source(
        self,
        shot: Any,
    ) -> str:
        """Return canonical shot-level Director source intent."""

        return str(
            self._row_value(
                shot,
                "visual_source",
                "",
            )
            or ""
        ).strip().upper()


    def _director_asset_haystack(
        self,
        asset: Any,
    ) -> str:
        """Normalized metadata used only for Director source resolution."""

        return " ".join(
            str(
                self._row_value(
                    asset,
                    key,
                    "",
                )
                or ""
            )
            for key in (
                "id",
                "filename",
                "path",
                "category",
                "semantic_class",
                "semantic_description",
                "tags",
                "source",
                "source_type",
                "provenance",
            )
        ).lower()


    def _director_source_allowed(
        self,
        shot: Any,
        asset: Any,
    ) -> bool:
        """Return hard Director provenance eligibility.

        RC2 editorial contract:

        USER_OWNED is a hard provenance requirement because substituting
        generated or third-party material would change source authority.

        SAFE_REAL, GENERATED and GRAPHICS are Director preferences rather
        than hard eligibility exclusions. Their preference is handled by
        scoring/ranking; safety, rights and semantic admissibility remain
        independent hard gates.
        """
        requested = self._director_visual_source(
            shot
        )

        if not requested:
            return True

        profile = self._source_profile(
            asset
        )

        if requested == "USER_OWNED":
            return (
                profile
                ==
                "USER_ORIGINAL"
            )

        if requested in {
            "SAFE_REAL",
            "GENERATED",
            "GRAPHICS",
        }:
            return True

        # Unknown Director source classes must not silently become
        # permissive. Preserve fail-closed behavior.
        return False

    def _director_planned_asset_match(
        self,
        shot: Any,
        asset: Any,
    ) -> bool:
        """Best-effort match against canonical storyboard asset_id.

        Registry asset IDs may be canonical hashes, therefore logical
        Director IDs are also searched in filename/path/metadata.
        """

        planned = str(
            self._row_value(
                shot,
                "planned_asset_id",
                "",
            )
            or ""
        ).strip().lower()

        if not planned:
            return False


        asset_id = str(
            self._row_value(
                asset,
                "id",
                "",
            )
            or ""
        ).strip().lower()


        if planned == asset_id:
            return True


        haystack = self._director_asset_haystack(
            asset
        )


        return (
            planned in haystack
        )

    def _source_priority(
        self,
        shot: Any,
        asset: Any,
    ) -> float:
        """Editorial provenance/media bonus, never a semantic substitute."""

        source = self._source_profile(
            asset
        )

        media_type = str(
            self._row_value(
                asset,
                "media_type",
                "",
            )
            or ""
        ).strip().lower()

        bonus = 0.0

        if source == "USER_ORIGINAL":
            bonus += 0.35

        elif source == "REAL":
            bonus += 0.25

        elif source == "GENERATED":
            bonus += (
                0.12
                if media_type == "video"
                else 0.02
            )

        elif source == "GRAPHICS":
            bonus += 0.05

        # Motion scenes should strongly prefer motion material.
        visual_need = str(
            self._row_value(
                shot,
                "visual_need",
                "",
            )
            or ""
        ).lower()

        motion_markers = (
            "run",
            "running",
            "move",
            "moving",
            "movement",
            "crowd",
            "cross",
            "crossing",
            "swim",
            "swimming",
            "clash",
            "protest",
            "vehicle",
            "police",
            "military",
            "boat",
            "rescue",
            "walk",
            "walking",
        )

        motion_required = any(
            marker in visual_need
            for marker in motion_markers
        )

        if motion_required:

            if media_type == "video":
                bonus += 0.15

            elif media_type == "image":
                bonus -= 0.18

        return bonus


    def _asset_motif(
        self,
        asset: Any,
    ) -> str:
        """Return a broad visual editorial motif.

        High-confidence visual evidence has priority over generic
        registry classes such as REAL_FOOTAGE / GENERATED / GENERAL.

        The purpose is visual sequencing, not source classification.
        """

        def value(
            key: str,
        ) -> str:
            return str(
                self._row_value(
                    asset,
                    key,
                    "",
                )
                or ""
            )


        filename = value(
            "filename"
        ).lower()

        path_value = value(
            "path"
        ).lower()

        semantic_description = value(
            "semantic_description"
        ).lower()

        tags = value(
            "tags"
        ).lower()

        category = value(
            "category"
        ).lower()

        semantic_class_raw = value(
            "semantic_class"
        ).strip()


        haystack = " ".join(
            (
                filename,
                path_value,
                semantic_description,
                tags,
                category,
            )
        )


        # ------------------------------------------------------------------
        # PHONE / SOCIAL / MISINFORMATION
        # ------------------------------------------------------------------

        if any(
            marker in haystack
            for marker in (
                "whatsapp",
                "telegram",
                "social_media",
                "social media",
                "smartphone",
                "mobile_phone",
                "mobile phone",
                "phone_screen",
                "phone screen",
                "viral_message",
                "viral message",
                "misinformation",
                "facebook",
                "instagram",
                "tiktok",
            )
        ):
            return "PHONE_SOCIAL_MEDIA"


        # ------------------------------------------------------------------
        # PEOPLE IN WATER
        # ------------------------------------------------------------------

        if any(
            marker in haystack
            for marker in (
                "mass_water",
                "people_in_water",
                "people in water",
                "migrants_in_water",
                "migrants in water",
                "swimmer",
                "swimmers",
                "swimming",
                "water_crossing",
                "water crossing",
                "sea_crossing",
                "sea crossing",
                "sea_route",
                "sea route",
                "water_rescue",
                "water rescue",
                "beach_arrival",
                "beach arrival",
                "beach_landing",
                "beach landing",
                "shoreline_swim",
            )
        ):
            return "PEOPLE_IN_WATER"


        # ------------------------------------------------------------------
        # SECURITY / POLICE / MILITARY
        # ------------------------------------------------------------------

        if any(
            marker in haystack
            for marker in (
                "guardia_civil",
                "guardia civil",
                "riot_police",
                "riot police",
                "army_deployment",
                "army deployment",
                "security_boats",
                "security boats",
                "security_forces",
                "security forces",
                "military",
                "soldier",
                "police",
            )
        ):
            return "POLICE_SECURITY"


        # ------------------------------------------------------------------
        # BORDER / FENCE / CROWD MOVEMENT
        # ------------------------------------------------------------------

        if any(
            marker in haystack
            for marker in (
                "border_movement",
                "border movement",
                "mass_entry",
                "mass entry",
                "mass_crossing",
                "mass crossing",
                "border_fence",
                "border fence",
                "border_crossing",
                "border crossing",
                "crowd_border",
                "crowd border",
                "checkpoint",
                "frontier",
                "breakwater",
                "tarajal",
            )
        ):
            return "CROWD_BORDER_FENCE"


        # ------------------------------------------------------------------
        # CITY / GEOGRAPHY
        # ------------------------------------------------------------------

        if any(
            marker in haystack
            for marker in (
                "city_geography",
                "city geography",
                "city_aerial",
                "city aerial",
                "ceuta_aerial",
                "ceuta aerial",
                "skyline",
                "city_view",
                "city view",
                "urban_panorama",
                "urban panorama",
                "city_shutdown",
                "city shutdown",
                "harbour_view",
                "harbor_view",
                "street_view",
                "street view",
                "map_ceuta",
            )
        ):
            return "CITY_GEOGRAPHY"


        # ------------------------------------------------------------------
        # EXISTING NON-GENERIC SEMANTIC CLASS
        # ------------------------------------------------------------------

        semantic_class = (
            semantic_class_raw
            .strip()
            .upper()
        )


        generic_semantic_classes = {
            "",
            "UNKNOWN",
            "OTHER",
            "UNCLASSIFIED",
            "NONE",
            "REAL_FOOTAGE",
            "GENERATED",
            "GENERAL",
            "USER_ORIGINAL",
            "USER_ORIGINAL_VIDEO",
            "USER_ORIGINAL_IMAGE",
        }


        if (
            semantic_class
            not in generic_semantic_classes
        ):
            return (
                "SEMANTIC:"
                +
                semantic_class[:64]
            )


        # Generic registry class is not itself a visual motif.
        return "UNCLASSIFIED"


    def _source_lineage(
        self,
        asset: Any,
    ) -> str:
        """Return the underlying physical/editorial source lineage.

        This identity is deliberately narrower than _source_identity().
        _source_identity() answers "which provider/source class?".
        _source_lineage() answers "which original piece of visual media
        did this derivative clip come from?".

        The method prefers explicit provenance metadata. When that is
        unavailable it recognizes common RC2 derivative clip naming,
        including TOP_CANDIDATES slices such as:

            02__HOOK_01__00006.0s.mp4
            03__HOOK_01__00108.0s.mp4

        Both resolve to DERIVED_HOOK:01.
        """

        def value(key: str) -> str:
            return str(
                self._row_value(
                    asset,
                    key,
                    "",
                )
                or ""
            ).strip()

        # Strong explicit lineage/provenance fields have priority.
        for key in (
            "source_lineage",
            "source_lineage_id",
            "origin_asset_id",
            "parent_asset_id",
            "source_media_id",
            "source_video_id",
            "original_asset_id",
            "source_url",
            "original_url",
            "download_url",
        ):
            explicit = value(key)

            if explicit:
                normalized = re.sub(
                    r"\s+",
                    " ",
                    explicit,
                ).strip().casefold()

                return (
                    f"EXPLICIT:{key}:{normalized}"
                )

        path_value = value("path")
        filename = value("filename")

        raw_name = (
            filename
            or re.split(
                r"[\\/]+",
                path_value,
            )[-1]
        )

        raw_name = raw_name.strip().casefold()

        # Remove ordinary extension only.
        stem = re.sub(
            r"\.(?:mp4|mov|mkv|avi|webm|m4v|jpg|jpeg|png|webp)$",
            "",
            raw_name,
            flags=re.IGNORECASE,
        )

        # RC2 semantic/QC fragments cut from HOOK source masters.
        #
        # Examples:
        # 02__HOOK_01__00006.0s
        # 48__HOOK_01__00228.0s
        match = re.search(
            r"(?:^|__)hook[_\-]?(\d+)(?:__|[_\-])",
            stem,
            flags=re.IGNORECASE,
        )

        if match:
            return (
                "DERIVED_HOOK:"
                + match.group(1).zfill(2)
            )

        # Generic time-sliced derivative names.
        #
        # Preserve the source portion and remove only an obvious
        # terminal editorial timestamp.
        generic = re.sub(
            r"(?:__|[_\-])"
            r"\d{2,6}(?:\.\d+)?s$",
            "",
            stem,
            flags=re.IGNORECASE,
        )

        generic = re.sub(
            r"(?:__|[_\-])"
            r"(?:clip|segment|slice|cut)"
            r"[_\-]?\d+$",
            "",
            generic,
            flags=re.IGNORECASE,
        )

        generic = generic.strip("_- ")

        if generic:
            return (
                "DERIVED_NAME:"
                + generic[:160]
            )

        # Final fallback is intentionally physical-asset-specific.
        # Never collapse all EURONEWS, USER_ORIGINAL, REAL, etc.
        asset_id = value("id")

        return (
            "ASSET:"
            + (
                asset_id.casefold()
                if asset_id
                else raw_name
            )
        )


    def _source_identity(
        self,
        asset: Any,
    ) -> str:
        """Return a stable editorial source identity."""

        profile = self._source_profile(
            asset
        )

        haystack = " ".join(
            str(
                self._row_value(
                    asset,
                    key,
                    "",
                )
                or ""
            )
            for key in (
                "filename",
                "path",
                "category",
                "semantic_description",
                "tags",
                "source",
                "source_type",
                "provenance",
            )
        ).lower()

        providers = (
            ("euronews", "EURONEWS"),
            ("reuters", "REUTERS"),
            ("efe", "EFE"),
            ("rtve", "RTVE"),
            ("human rights watch", "HRW"),
            ("hrw", "HRW"),
            ("associated press", "AP"),
            ("ap news", "AP"),
            ("deutsche welle", "DW"),
            ("dw news", "DW"),
            ("guardian", "GUARDIAN"),
            ("el pais", "EL_PAIS"),
            ("elpais", "EL_PAIS"),
        )

        for marker, identity in providers:
            if marker in haystack:
                return identity

        if profile == "USER_ORIGINAL":
            return "USER_ORIGINAL"

        path_value = str(
            self._row_value(
                asset,
                "path",
                "",
            )
            or ""
        ).strip()

        if path_value:
            parts = [
                part
                for part in re.split(
                    r"[\\/]+",
                    path_value,
                )
                if part
            ]

            if len(parts) >= 2:
                parent = re.sub(
                    r"[^a-zA-Z0-9_\-]+",
                    "_",
                    parts[-2],
                ).strip("_")

                if parent:
                    return (
                        f"{profile}:{parent[:48]}"
                    )

        filename = str(
            self._row_value(
                asset,
                "filename",
                "",
            )
            or ""
        ).strip()

        prefix = re.split(
            r"[_\-]{2,}|[_\-]\d",
            filename,
            maxsplit=1,
        )[0].strip()

        if prefix:
            return (
                f"{profile}:{prefix[:48]}"
            )

        return profile


    def _media_identity(
        self,
        asset: Any,
    ) -> str:
        """Canonical media rhythm identity."""

        media_type = str(
            self._row_value(
                asset,
                "media_type",
                "",
            )
            or ""
        ).strip().lower()

        if media_type in {
            "video",
            "image",
        }:
            return media_type

        return "unknown"


    def _asset_safety_blocked(
        self,
        asset: Any,
    ) -> bool:
        """Hard final-production safety gate.

        Reference assets, rights-pending assets and overlay-review
        assets are production inputs only and can never be selected
        into the final documentary timeline.
        """

        def value(
            key: str,
        ) -> str:
            return str(
                self._row_value(
                    asset,
                    key,
                    "",
                )
                or ""
            ).strip()


        filename = value(
            "filename"
        ).lower()

        path_value = value(
            "path"
        ).lower()


        structured_values = [
            value("category"),
            value("semantic_class"),
            value("source_type"),
            value("provenance"),
            value("rights"),
            value("rights_status"),
            value("tags"),
        ]


        for raw in structured_values:

            normalized = (
                raw
                .upper()
                .replace("-", "_")
                .replace(" ", "_")
            )


            if normalized in {
                "REFERENCE",
                "REFERENCE_ONLY",
                "REFERENCE_ONLY_PENDING_RIGHTS",
                "REFERENCE_PENDING_RIGHTS",
                "V2V_REFERENCE",
                "V2V_REFERENCE_ONLY",
                "RIGHTS_PENDING",
                "PENDING_RIGHTS",
                "OVERLAY_REVIEW",
                "NEWS_OVERLAY_REVIEW",
            }:
                return True


            if (
                "REFERENCE_ONLY"
                in normalized
            ):
                return True


            if (
                "V2V_REFERENCE"
                in normalized
            ):
                return True


            if (
                "RIGHTS_PENDING"
                in normalized
                or
                "PENDING_RIGHTS"
                in normalized
            ):
                return True


            if (
                "OVERLAY_REVIEW"
                in normalized
            ):
                return True


        # ------------------------------------------------------------------
        # KNOWN CEUTA PRODUCTION REFERENCE FAMILIES
        #
        # These are not final-film assets. They were downloaded / retained
        # as factual production references for Leonardo and research.
        # ------------------------------------------------------------------

        reference_prefixes = (
            "z06_efe_",
            "z06_rtve_",
            "z06_europapress_",
            "z08_ceutaact_",
            "z09_efe_",
            "z10_efe_",
            "z10_hrw_",
            "z10_faro_",
            "z10_ceutaact_",
            "ceuta_hook_ref_",
        )


        if filename.startswith(
            reference_prefixes
        ):
            return True


        forbidden_path_markers = (
            "raw_reference_only",
            "reference_only_pending_rights",
            "reference_pending_rights",
            "v2v_reference",
            "v2v_reference_candidates",
            "overlay_review",
            "rights_pending",
            "pending_rights",
        )


        if any(
            marker in path_value
            for marker in forbidden_path_markers
        ):
            return True


        if (
            "hook_ref_" in filename
            or
            "hook_ref_" in path_value
        ):
            return True


        return False


    def _sequencing_violation(
        self,
        asset: Any,
    ) -> str | None:
        """Return a hard editorial sequencing violation, if present."""

        motif = self._asset_motif(
            asset
        )

        source = self._source_identity(
            asset
        )

        media = self._media_identity(
            asset
        )

        motif_window = (
            self.recent_motifs[
                -self.motif_recent_window:
            ]
        )

        if (
            motif_window.count(
                motif
            )
            >=
            self.same_motif_max_in_recent_window
        ):
            return "MOTIF"

        if (
            len(self.recent_sources)
            >=
            self.same_source_max_consecutive
            and
            all(
                previous == source
                for previous in self.recent_sources[
                    -self.same_source_max_consecutive:
                ]
            )
        ):
            return "SOURCE"

        if (
            len(self.recent_media_types)
            >=
            self.same_media_type_max_consecutive
            and
            all(
                previous == media
                for previous in self.recent_media_types[
                    -self.same_media_type_max_consecutive:
                ]
            )
        ):
            return "MEDIA"

        return None
    def _director_ranking_v6(
        self,
        asset: Any,
    ) -> tuple[int, int, int, int, int, int]:
        """RC2 Director Ranking V6.

        Evaluate the complete current editorial sequence for an
        already hard-eligible candidate.

        Hard constraints are outside this method and remain
        non-relaxable:
        safety, semantic eligibility, duplicate control,
        asset max-use, visual-family limits and duration fit.
        """

        motif = self._asset_motif(
            asset
        )

        source = self._source_identity(
            asset
        )

        media = self._media_identity(
            asset
        )

        motif_window = (
            self.recent_motifs[
                -self.motif_recent_window:
            ]
        )

        motif_count = (
            motif_window.count(
                motif
            )
        )

        source_run = 0

        for previous in reversed(
            self.recent_sources
        ):

            if previous != source:
                break

            source_run += 1


        media_run = 0

        for previous in reversed(
            self.recent_media_types
        ):

            if previous != media:
                break

            media_run += 1


        motif_violation = int(
            motif_count
            >=
            self.same_motif_max_in_recent_window
        )

        source_violation = int(
            source_run
            >=
            self.same_source_max_consecutive
        )

        media_violation = int(
            media_run
            >=
            self.same_media_type_max_consecutive
        )


        total_violations = (
            motif_violation
            +
            source_violation
            +
            media_violation
        )


        # reverse=True ranking:
        #
        # 1. fewer hard editorial sequence violations;
        # 2. avoid motif violation first;
        # 3. then avoid source repetition;
        # 4. then avoid media repetition;
        # 5. within non-violating candidates prefer a motif
        #    occurring less often in the current window;
        # 6. prefer shorter current source run.
        return (
            -total_violations,
            -motif_violation,
            -source_violation,
            -media_violation,
            -motif_count,
            -source_run,
        )

    def _sequencing_relaxation_tier(
        self,
        asset: Any,
    ) -> int:
        """Return V5 editorial relaxation level.

        0 = strict
        1 = media rhythm relaxed
        2 = source sequencing relaxed
        3 = motif sequencing relaxed

        Hard safety, duplicate, asset max-use and visual-family
        constraints are never represented here and therefore can
        never be relaxed by V5.
        """

        violation = self._sequencing_violation(
            asset
        )

        return {
            None: 0,
            "MEDIA": 1,
            "SOURCE": 2,
            "MOTIF": 3,
        }.get(
            violation,
            3,
        )
    def _recently_used(
        self,
        asset: Any,
    ) -> bool:
        """Prevent adjacent and near-adjacent visual repetition."""

        asset_id = str(
            self._row_value(
                asset,
                "id",
                "",
            )
            or ""
        )

        family = self._asset_family(
            asset
        )

        recent_asset_window = (
            self.recent_asset_ids[
                -self.recent_asset_window:
            ]
        )

        recent_family_window = (
            self.recent_family_ids[
                -self.visual_family_recent_window:
            ]
        )

        return (
            asset_id in recent_asset_window
            or
            family in recent_family_window
        )


    def _editorially_eligible(
        self,
        shot: Any,
        asset: Any,
    ) -> bool:
        """Hard eligibility gate before either Story or fallback ranking."""
        if not self._director_source_allowed(
            shot,
            asset,
        ):
            return False


        if self._asset_safety_blocked(
            asset
        ):
            return False

        if not self._asset_is_semantically_allowed(
            asset
        ):
            return False

        if not self._asset_fits_shot(
            shot,
            asset
        ):
            return False

        asset_id = str(
            self._row_value(
                asset,
                "id",
                "",
            )
            or ""
        )

        if (
            self.usage.get(asset_id, 0)
            >=
            self._max_use(asset)
        ):
            return False

        duplicate_of = str(
            self._row_value(
                asset,
                "duplicate_of",
                "",
            )
            or ""
        ).strip()

        if duplicate_of:
            return False

        family = self._asset_family(
            asset
        )

        if (
            self.family_usage.get(family, 0)
            >=
            self.visual_family_max_use
        ):
            return False

        lineage = self._source_lineage(
            asset
        )

        if (
            lineage
            and
            self.source_lineage_usage.get(lineage, 0)
            >=
            self.source_lineage_max_use
        ):
            return False

        if self._recently_used(
            asset
        ):
            return False

        return True


    def _effective_score(
        self,
        shot: Any,
        asset: Any,
        *,
        story_preferred: bool = False,
    ) -> float:
        """Semantic score plus bounded editorial priorities."""

        score = float(
            self.score(
                shot,
                asset
            )
        )

        score += self._source_priority(
            shot,
            asset
        )

        if self._director_planned_asset_match(
            shot,
            asset,
        ):
            score += 0.75

        if story_preferred:
            # Story Engine is a strong hint, not an unconditional override.
            score += 0.12

        return round(
            max(
                0.0,
                score,
            ),
            4,
        )


    def _max_use(self, asset: Any) -> int:
        """Return strict per-asset usage limit.

        RC2 editorial invariant:
        missing or invalid max_use means ONE use, not unlimited use.
        Any deliberate reuse must therefore be explicitly declared.
        """

        try:
            value = int(
                self._row_value(
                    asset,
                    "max_use",
                    1,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            return 1

        return (
            value
            if value > 0
            else 1
        )


    def _asset_fits_shot(
        self,
        shot: Any,
        asset: Any,
    ) -> bool:
        """Return True when the asset is renderable for visual coverage.

        RC2 editorial contract:

        A video does not need to be as long as the complete shot interval.
        Duration is a render-planning/ranking concern, not a semantic
        eligibility condition. Images can cover arbitrary shot duration.

        Videos must still have a positive known duration.
        """
        media_type = str(
            self._row_value(
                asset,
                "media_type",
                "",
            )
            or ""
        ).strip().lower()

        if media_type == "image":
            return True

        if media_type != "video":
            return False

        try:
            asset_duration = float(
                self._row_value(
                    asset,
                    "duration_sec",
                    0.0,
                )
                or 0.0
            )
        except (TypeError, ValueError):
            return False

        return asset_duration > 0.10

    def _select_story_asset(
        self,
        shot: Any,
        candidates: list[Any],
    ) -> Any | None:
        """Select the best EDITORIALLY ELIGIBLE Story candidate.

        Story Engine candidates receive preference, but diversity,
        semantic relevance, duration and reuse rules remain mandatory.
        """

        ranked = [
            (
                self._effective_score(
                    shot,
                    asset,
                    story_preferred=True,
                ),
                asset,
            )
            for asset in candidates
            if self._editorially_eligible(
                shot,
                asset,
            )
        ]

        ranked.sort(
            key=lambda item: (
                item[0],
                float(
                    self._row_value(
                        item[1],
                        "quality",
                        0.0,
                    )
                    or 0.0
                ),
                str(
                    self._row_value(
                        item[1],
                        "id",
                        "",
                    )
                ),
            ),
            reverse=True,
        )

        if not ranked:
            return None

        if (
            ranked[0][0]
            <
            self.acceptance_threshold
        ):
            return None

        return ranked[0][1]

    def score(self, shot: Any, asset: Any) -> float:
        """Fallback score with universal semantic understanding."""
        if not self._asset_is_semantically_allowed(asset):
            return 0.0

        need_tokens = self._tokens(shot["visual_need"])
        raw_tags = asset["tags"] or "[]"

        try:
            tags = json.loads(raw_tags)
        except (TypeError, ValueError, json.JSONDecodeError):
            tags = [
                item.strip("'\"")
                for item in str(raw_tags).strip("[]").split(",")
                if item.strip()
            ]

        if not isinstance(tags, list):
            tags = [str(tags)]

        (
            semantic_class,
            semantic_description,
            semantic_confidence,
        ) = self._semantic_profile(asset)

        searchable_values = [
            asset["filename"],
            asset["category"],
            asset["emotion"],
            semantic_class,
            semantic_description,
            *tags,
        ]

        haystack_tokens: set[str] = set()
        haystack_text_parts: list[str] = []

        for value in searchable_values:
            normalized = str(value or "").lower()
            haystack_text_parts.append(normalized)
            haystack_tokens.update(self._tokens(normalized))

        haystack_text = " ".join(haystack_text_parts)

        exact_matches = sum(
            1
            for token in need_tokens
            if token in haystack_tokens
        )

        partial_matches = sum(
            1
            for token in need_tokens
            if token not in haystack_tokens
            and any(
                token in candidate or candidate in token
                for candidate in haystack_tokens
                if len(candidate) >= 4
            )
        )

        phrase_bonus = 0.0
        visual_need = str(shot["visual_need"] or "").lower().strip()
        if visual_need and visual_need in haystack_text:
            phrase_bonus = 0.15

        score = float(asset["quality"] or 0)
        score += exact_matches * 0.18
        score += partial_matches * 0.08
        score += phrase_bonus

        if semantic_confidence >= self.minimum_semantic_confidence:
            semantic_tokens = set(
                self._tokens(
                    f"{semantic_class} {semantic_description}"
                )
            )
            semantic_exact_matches = sum(
                1
                for token in need_tokens
                if token in semantic_tokens
            )
            semantic_partial_matches = sum(
                1
                for token in need_tokens
                if token not in semantic_tokens
                and any(
                    token in candidate or candidate in token
                    for candidate in semantic_tokens
                    if len(candidate) >= 4
                )
            )

            class_tokens = set(
                self._tokens(
                    semantic_class.replace("_", " ")
                )
            )
            class_overlap = bool(
                class_tokens.intersection(need_tokens)
            )

            if class_overlap:
                score += 0.45 * semantic_confidence

            score += (
                semantic_exact_matches
                * 0.12
                * semantic_confidence
            )
            score += (
                semantic_partial_matches
                * 0.05
                * semantic_confidence
            )

            if (
                visual_need
                and visual_need in semantic_description
            ):
                score += 0.20 * semantic_confidence

        shot_emotion = str(shot["emotion"] or "").strip().lower()
        asset_emotion = str(asset["emotion"] or "").strip().lower()
        if shot_emotion and shot_emotion == asset_emotion:
            score += 0.12

        if self.usage[str(asset["id"])] >= self._max_use(asset):
            score -= 1.0

        if asset["duplicate_of"]:
            score -= 0.25

        return round(max(score, 0.0), 4)


    def _alternative_payload(
        self,
        asset: Any,
        *,
        score: float,
        provenance: str,
    ) -> dict[str, Any]:
        """Serialize a verified alternative for downstream RC2 stages."""
        try:
            duration_sec = float(asset["duration_sec"] or 0.0)
        except (TypeError, ValueError, KeyError):
            duration_sec = 0.0

        try:
            quality = float(asset["quality"] or 0.0)
        except (TypeError, ValueError, KeyError):
            quality = 0.0

        return {
            "asset_id": str(asset["id"]),
            "asset_name": str(asset["filename"] or ""),
            "asset_path": str(asset["path"] or ""),
            "media_type": str(asset["media_type"] or "").strip().lower(),
            "duration_sec": round(max(0.0, duration_sec), 3),
            "quality": round(max(0.0, quality), 4),
            "assignment_score": round(max(0.0, float(score)), 4),
            "provenance": provenance,
            "verified": True,
        }


    def _write_assignment(
        self,
        shot: Any,
        asset: Any,
        score: float,
        reason: str,
        alternatives: list[Any],
    ) -> None:
        asset_id = str(
            asset["id"]
        )

        self.usage[
            asset_id
        ] += 1

        family = self._asset_family(
            asset
        )

        # Persistent usage count for the physical visual family.
        self.family_usage[
            family
        ] += 1

        lineage = self._source_lineage(
            asset
        )

        if lineage:
            self.source_lineage_usage[
                lineage
            ] += 1

            self.recent_source_lineages.append(
                lineage
            )

            if len(
                self.recent_source_lineages
            ) > 64:
                self.recent_source_lineages = (
                    self.recent_source_lineages[-64:]
                )

        # Chronological editorial memory.
        self.recent_asset_ids.append(
            asset_id
        )

        self.recent_family_ids.append(
            family
        )

        # Bound memory growth while retaining enough history for diagnostics.
        if len(
            self.recent_asset_ids
        ) > 64:
            self.recent_asset_ids = (
                self.recent_asset_ids[-64:]
            )

        if len(
            self.recent_family_ids
        ) > 64:
            self.recent_family_ids = (
                self.recent_family_ids[-64:]
            )

        self.recent_motifs.append(
            self._asset_motif(
                asset
            )
        )

        self.recent_sources.append(
            self._source_identity(
                asset
            )
        )

        self.recent_media_types.append(
            self._media_identity(
                asset
            )
        )

        if len(
            self.recent_motifs
        ) > 64:
            self.recent_motifs = (
                self.recent_motifs[-64:]
            )

        if len(
            self.recent_sources
        ) > 64:
            self.recent_sources = (
                self.recent_sources[-64:]
            )

        if len(
            self.recent_media_types
        ) > 64:
            self.recent_media_types = (
                self.recent_media_types[-64:]
            )
        self.db.execute(
            """
            UPDATE shots
            SET assigned_asset_id=?, status='assigned'
            WHERE id=? AND project_id=?
            """,
            (
                asset_id,
                shot["id"],
                self.project_id,
            ),
        )

        self.db.execute(
            """
            INSERT INTO director_decisions(
                project_id,
                shot_id,
                asset_id,
                score,
                reason,
                alternatives
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                self.project_id,
                shot["id"],
                asset_id,
                score,
                reason,
                json.dumps(
                    alternatives,
                    ensure_ascii=False,
                ),
            ),
        )

    def _write_missing(
        self,
        shot: Any,
        best_score: float,
        reason: str,
    ) -> None:
        # V5 invariant:
        # a missing shot must never retain a stale previous assignment.
        self.db.execute(
            """
            UPDATE shots
            SET assigned_asset_id=NULL
            WHERE id=? AND project_id=?
            """,
            (
                shot["id"],
                self.project_id,
            ),
        )
        prompt = (
            f"Required visual: {shot['visual_need']}. "
            f"Story goal: {shot['story_goal']}. "
            f"Emotion: {shot['emotion']}."
        )

        self.db.execute(
            """
            UPDATE shots
            SET assigned_asset_id=NULL,
                status='missing'
            WHERE id=? AND project_id=?
            """,
            (
                shot["id"],
                self.project_id,
            ),
        )

        self.db.execute(
            """
            INSERT INTO director_decisions(
                project_id,
                shot_id,
                asset_id,
                score,
                reason,
                alternatives
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                self.project_id,
                shot["id"],
                None,
                best_score,
                reason,
                prompt,
            ),
        )


    def run(self) -> dict[str, Any]:
        """Run diversity-aware canonical assignment.

        Editorial invariants:
        - Story Engine is preference, not unconditional authority.
        - exact duplicate records cannot compete;
        - default asset reuse is one;
        - recent asset/family repetition is forbidden;
        - real/user footage outranks generated stills when semantic
          relevance is sufficient;
        - bad semantic matches remain missing.
        """

        self.db.execute(
            "DELETE FROM director_decisions WHERE project_id=?",
            (
                self.project_id,
            ),
        )

        shots = self.db.rows(
            """
            SELECT *
            FROM shots
            WHERE project_id=?
            ORDER BY start_sec, id
            """,
            (
                self.project_id,
            ),
        )

        assets = self.db.rows(
            """
            SELECT *
            FROM assets
            WHERE project_id=?
              AND media_type IN ('image','video')
            """,
            (
                self.project_id,
            ),
        )

        scenes = self.db.rows(
            """
            SELECT *
            FROM story_scenes
            WHERE project_id=?
            ORDER BY start_sec, id
            """,
            (
                self.project_id,
            ),
        )

        if not scenes:
            raise RuntimeError(
                "ASSIGNMENT_CONTRACT_VIOLATION: story_scenes "
                f"are empty for project {self.project_id!r}. "
                "Canonical assignment requires materialized Story."
            )

        if not shots:
            raise RuntimeError(
                "ASSIGNMENT_CONTRACT_VIOLATION: shots "
                f"are empty for project {self.project_id!r}. "
                "Canonical assignment requires materialized shots."
            )

        assets_by_id = {
            str(
                asset["id"]
            ): asset
            for asset in assets
        }

        assigned = 0
        assigned_from_story = 0
        assigned_from_fallback = 0
        missing = 0
        # RC2 V5 constraint-relaxation telemetry.
        strict_assigned = 0
        media_relaxed = 0
        source_relaxed = 0
        motif_relaxed = 0

        rejected_duplicates = 0
        rejected_recent_reuse = 0
        rejected_max_use = 0
        rejected_family_max_use = 0
        rejected_source_lineage_max_use = 0

        self.usage.clear()
        self.family_usage.clear()
        self.source_lineage_usage.clear()
        self.recent_source_lineages.clear()
        self.recent_asset_ids.clear()
        self.recent_family_ids.clear()
        self.recent_motifs.clear()
        self.recent_sources.clear()
        self.recent_media_types.clear()

        for shot in shots:

            (
                preferred_assets,
                scene_id,
            ) = self._preferred_assets_for_shot(
                shot,
                scenes,
                assets_by_id,
            )

            preferred_ids = {
                str(
                    asset["id"]
                )
                for asset in preferred_assets
            }

            ranked = []
            relaxation_tiers: dict[str, int] = {}

            for asset in assets:

                asset_id = str(
                    asset["id"]
                )

                duplicate_of = str(
                    self._row_value(
                        asset,
                        "duplicate_of",
                        "",
                    )
                    or ""
                ).strip()

                if duplicate_of:
                    rejected_duplicates += 1
                    continue

                if (
                    self.usage.get(asset_id, 0)
                    >=
                    self._max_use(asset)
                ):
                    rejected_max_use += 1
                    continue

                family = self._asset_family(
                    asset
                )

                if (
                    self.family_usage.get(family, 0)
                    >=
                    self.visual_family_max_use
                ):
                    rejected_family_max_use += 1
                    continue

                lineage = self._source_lineage(
                    asset
                )

                if (
                    lineage
                    and
                    self.source_lineage_usage.get(lineage, 0)
                    >=
                    self.source_lineage_max_use
                ):
                    rejected_source_lineage_max_use += 1
                    continue

                if self._recently_used(
                    asset
                ):
                    rejected_recent_reuse += 1
                    continue

                if not self._editorially_eligible(
                    shot,
                    asset,
                ):
                    continue

                story_preferred = (
                    asset_id
                    in preferred_ids
                )

                effective = self._effective_score(
                    shot,
                    asset,
                    story_preferred=story_preferred,
                )
                relaxation_tiers[
                    asset_id
                ] = self._sequencing_relaxation_tier(
                    asset
                )

                ranked.append(
                    (
                        effective,
                        asset,
                        story_preferred,
                    )
                )

            ranked.sort(
                key=lambda item: (
                    item[0]
                    >=
                    self.acceptance_threshold,

                    self._director_ranking_v6(
                        item[1]
                    ),

                    item[0],

                    float(
                        self._row_value(
                            item[1],
                            "quality",
                            0.0,
                        )
                        or 0.0
                    ),

                    str(
                        self._row_value(
                            item[1],
                            "id",
                            "",
                        )
                    ),
                ),
                reverse=True,
            )

            if (
                ranked
                and
                ranked[0][0]
                >=
                self.acceptance_threshold
            ):

                (
                    score,
                    asset,
                    story_preferred,
                ) = ranked[0]

                asset_id = str(
                    asset["id"]
                )
                selected_relaxation_tier = (
                    relaxation_tiers.get(
                        asset_id,
                        3,
                    )
                )

                if selected_relaxation_tier == 0:
                    strict_assigned += 1

                elif selected_relaxation_tier == 1:
                    media_relaxed += 1

                elif selected_relaxation_tier == 2:
                    source_relaxed += 1

                else:
                    motif_relaxed += 1

                provenance = (
                    "story_engine_preferred"
                    if story_preferred
                    else "global_semantic"
                )

                source_profile = (
                    self._source_profile(
                        asset
                    )
                )

                alternatives = [
                    self._alternative_payload(
                        candidate_asset,
                        score=candidate_score,
                        provenance=(
                            "story_engine_preferred"
                            if candidate_story
                            else "global_semantic"
                        ),
                    )
                    for (
                        candidate_score,
                        candidate_asset,
                        candidate_story,
                    )
                    in ranked[1:]
                    if (
                        candidate_score
                        >=
                        self.acceptance_threshold
                    )
                    and
                    str(
                        candidate_asset["id"]
                    )
                    != asset_id
                ][:3]

                reason = (
                    f"Editorial diversity assignment selected "
                    f"'{asset['filename']}' for visual need "
                    f"'{shot['visual_need']}'. "
                    f"Score={score}. "
                    f"Source={source_profile}. "
                    f"Provenance={provenance}. "
                    f"Family={self._asset_family(asset)}. "
                    f"Lineage={self._source_lineage(asset)}. "
                    f"Usage={self.usage.get(asset_id, 0) + 1}/"
                    f"{self._max_use(asset)}."
                )
                reason += (
                    " RelaxationTier="
                    + {
                        0: "STRICT",
                        1: "MEDIA_RELAXED",
                        2: "SOURCE_RELAXED",
                        3: "MOTIF_RELAXED",
                    }.get(
                        selected_relaxation_tier,
                        "MOTIF_RELAXED",
                    )
                    + "."
                )

                self._write_assignment(
                    shot=shot,
                    asset=asset,
                    score=score,
                    reason=reason,
                    alternatives=alternatives,
                )

                assigned += 1

                if story_preferred:
                    assigned_from_story += 1
                else:
                    assigned_from_fallback += 1

            else:

                best_score = (
                    float(
                        ranked[0][0]
                    )
                    if ranked
                    else 0.0
                )

                if preferred_assets:
                    reason = (
                        "Story Engine candidates were considered, "
                        "but no editorially eligible candidate reached "
                        "the semantic/diversity threshold."
                    )

                elif scene_id:
                    reason = (
                        f"Scene '{scene_id}' has no editorially acceptable "
                        f"asset above threshold."
                    )

                else:
                    reason = (
                        "No global asset reached the editorial acceptance "
                        "threshold; shot intentionally remains open."
                    )

                self._write_missing(
                    shot=shot,
                    best_score=best_score,
                    reason=reason,
                )

                missing += 1

        unique_assets_used = len(
            self.usage
        )

        max_asset_usage = max(
            self.usage.values(),
            default=0,
        )

        reused_assets = sum(
            1
            for count in self.usage.values()
            if count > 1
        )

        unique_visual_families_used = len(
            self.family_usage
        )

        reused_visual_families = sum(
            1
            for count in self.family_usage.values()
            if count > 1
        )

        max_visual_family_usage = max(
            self.family_usage.values(),
            default=0,
        )

        unique_source_lineages_used = len(
            self.source_lineage_usage
        )

        reused_source_lineages = sum(
            1
            for count in self.source_lineage_usage.values()
            if count > 1
        )

        max_source_lineage_usage = max(
            self.source_lineage_usage.values(),
            default=0,
        )

        result = {
            "state":
                "ASSIGNMENT_COMPLETED",

            "project_id":
                self.project_id,

            "assigned":
                assigned,

            "assigned_from_story":
                assigned_from_story,

            "assigned_from_fallback":
                assigned_from_fallback,

            "missing":
                missing,

            "threshold":
                self.acceptance_threshold,

            "policy":
                "AssignmentPolicyRC2_EDITORIAL_DIVERSITY",

            "production_policy_profile": {
                "schema":
                    "atlas_zero.assignment_policy_profile.rc1",

                "active":
                    bool(
                        self.production_policy_profile.get(
                            "active",
                            False,
                        )
                    ),

                "mode":
                    self.production_policy_profile.get(
                        "mode",
                        "baseline",
                    ),

                "acceptance_threshold":
                    self.acceptance_threshold,

                "minimum_semantic_confidence":
                    self.minimum_semantic_confidence,

                "recent_asset_window":
                    self.recent_asset_window,

                "visual_family_recent_window":
                    self.visual_family_recent_window,

                "motif_recent_window":
                    self.motif_recent_window,

                "same_motif_max_in_recent_window":
                    self.same_motif_max_in_recent_window,

                "same_source_max_consecutive":
                    self.same_source_max_consecutive,

                "same_media_type_max_consecutive":
                    self.same_media_type_max_consecutive,

                # HARD invariants exposed for regression visibility.
                "visual_family_max_use":
                    self.visual_family_max_use,

                "source_lineage_max_use":
                    self.source_lineage_max_use,

                "coverage_action":
                    self.production_policy_profile.get(
                        "coverage_action",
                        "KEEP_MISSING_IF_NO_VALID_ASSET",
                    ),

                "confidence":
                    self.production_policy_profile.get(
                        "confidence",
                        0.0,
                    ),

                "pressures":
                    dict(
                        self.production_policy_profile.get(
                            "pressures",
                            {},
                        )
                        or {}
                    ),

                "evidence":
                    list(
                        self.production_policy_profile.get(
                            "evidence",
                            (),
                        )
                        or ()
                    ),

                "provenance":
                    list(
                        self.production_policy_profile.get(
                            "provenance",
                            (),
                        )
                        or ()
                    ),

                "source_schema":
                    self.production_policy_profile.get(
                        "source_schema"
                    ),
            },

            "editorial_diversity": {
                "default_max_use":
                    1,

                "recent_asset_window":
                    self.recent_asset_window,

                "recent_family_window":
                    self.visual_family_recent_window,

                "visual_family_max_use":
                    self.visual_family_max_use,

                "visual_family_recent_window":
                    self.visual_family_recent_window,

                "unique_assets_used":
                    unique_assets_used,

                "reused_assets":
                    reused_assets,

                "max_asset_usage":
                    max_asset_usage,

                "unique_visual_families_used":
                    unique_visual_families_used,

                "reused_visual_families":
                    reused_visual_families,

                "max_visual_family_usage":
                    max_visual_family_usage,

                "duplicate_records_rejected":
                    rejected_duplicates,

                "recent_reuse_rejected":
                    rejected_recent_reuse,

                "max_use_rejected":
                    rejected_max_use,

                "family_max_use_rejected":
                    rejected_family_max_use,

                "source_lineage_max_use":
                    self.source_lineage_max_use,

                "unique_source_lineages_used":
                    unique_source_lineages_used,

                "reused_source_lineages":
                    reused_source_lineages,

                "max_source_lineage_usage":
                    max_source_lineage_usage,

                "source_lineage_max_use_rejected":
                    rejected_source_lineage_max_use,

                "story_engine_authoritative":
                    False,

                "bad_match_remains_open":
                    True,
            },
        }
        result[
            "editorial_diversity"
        ][
            "constraint_relaxation_v5"
        ] = {
            "strict_assigned":
                strict_assigned,

            "media_relaxed":
                media_relaxed,

            "source_relaxed":
                source_relaxed,

            "motif_relaxed":
                motif_relaxed,

            "total_relaxed":
                (
                    media_relaxed
                    +
                    source_relaxed
                    +
                    motif_relaxed
                ),

            "still_missing":
                missing,

            "hard_constraints": [
                "semantic_safety",
                "reference_overlay_rights_safety",
                "physical_duplicate",
                "asset_max_use",
                "visual_family_max_use",
                "visual_family_recent_window",
                "source_lineage_max_use",
                "duration_fit",
            ],

            "relaxation_order": [
                "STRICT",
                "MEDIA_RELAXED",
                "SOURCE_RELAXED",
                "MOTIF_RELAXED",
            ],
        }

        self.bus.emit(
            "ASSIGNMENT_POLICY_COMPLETED",
            result,
        )

        return result
