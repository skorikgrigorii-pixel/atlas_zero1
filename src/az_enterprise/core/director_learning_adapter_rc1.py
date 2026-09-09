from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from .director_knowledge_base_rc2 import (
    DirectorKnowledgeBaseRC2,
)
from .learning_core_rc1 import (
    LearningCoreRC1,
)


class DirectorLearningAdapterRC1:
    """
    ATLAS ZERO — Director Learning Adapter RC1.

    Purpose:
    translate evidence accumulated by LearningCoreRC1 into
    advisory data that Director AI can safely consume.

    Important authority rules:

    - Learning Core is evidence authority.
    - DirectorKnowledgeBaseRC2 remains Director historical authority.
    - Director AI remains decision authority.
    - This adapter never rewrites Director policies.
    - This adapter never changes source code.
    - This adapter never bypasses quality gates.
    """

    EVENT = "LEARNING_UPDATED"

    def __init__(
        self,
        *,
        db: Any,
        project_id: str,
        event_bus: Any | None = None,
    ) -> None:

        self.db = db
        self.project_id = str(project_id).strip()

        if not self.project_id:
            raise ValueError(
                "project_id is required"
            )

        self.learning = LearningCoreRC1(
            db=db,
            project_id=self.project_id,
        )

        self.director_knowledge = (
            DirectorKnowledgeBaseRC2(db)
        )

        self.event_bus = event_bus

        self.ensure_schema()

        if self.event_bus is not None:
            self.event_bus.on(
                self.EVENT,
                self._on_learning_updated,
            )

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:

        self.db.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS
            director_learning_advisories(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                project_id TEXT NOT NULL,

                source_event TEXT,

                minimum_confidence REAL NOT NULL,

                profile_count INTEGER NOT NULL,

                advisory_json TEXT NOT NULL,

                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_director_learning_advisory_project
            ON director_learning_advisories(
                project_id,
                created_at
            );
            """
        )

        self.db.conn.commit()

    # ------------------------------------------------------------------
    # Build advisory
    # ------------------------------------------------------------------

    def build_advisory(
        self,
        *,
        minimum_confidence: float = 0.60,
        candidate_targets: Iterable[str] = (),
        source_event: str | None = None,
    ) -> dict[str, Any]:

        profiles = self.learning.profiles(
            minimum_confidence=
                minimum_confidence
        )

        targets = tuple(
            str(target).strip()
            for target in candidate_targets
            if str(target).strip()
        )

        ranked_targets: tuple[str, ...] = ()
        target_experience: dict[str, Any] = {}

        if targets:

            ranked_targets = (
                self.director_knowledge.rank_targets(
                    project_id=self.project_id,
                    targets=targets,
                )
            )

            experience = (
                self.director_knowledge.target_experience(
                    self.project_id,
                    targets,
                )
            )

            for target, item in experience.items():

                if hasattr(item, "__dict__"):
                    payload = dict(item.__dict__)
                else:
                    payload = {
                        "value": str(item)
                    }

                target_experience[
                    str(target)
                ] = payload

        advisory = {
            "schema":
                "atlas_zero.director_learning_advisory.rc1",

            "state":
                "DIRECTOR_LEARNING_ADVISORY_READY",

            "project_id":
                self.project_id,

            "created_at":
                self._now(),

            "source_event":
                source_event,

            "authority":
                "LearningCoreRC1",

            "decision_authority":
                "DirectorAI",

            "mode":
                "advisory_only",

            "minimum_confidence":
                float(minimum_confidence),

            "profiles":
                profiles,

            "profile_count":
                len(profiles),

            "candidate_targets":
                list(targets),

            "ranked_targets":
                list(ranked_targets),

            "director_target_experience":
                target_experience,

            "permissions": {
                "override_director":
                    False,

                "modify_source":
                    False,

                "bypass_quality_gate":
                    False,

                "rewrite_policy":
                    False,
            },
        }

        return advisory

    # ------------------------------------------------------------------
    # Learning -> bounded production target preferences
    # ------------------------------------------------------------------

    @staticmethod
    def _profile_rework_targets(
        profile: dict[str, Any],
    ) -> tuple[str, ...]:
        """
        Convert one LearningCore profile into soft Director rework
        preferences.

        Contract:
        - project agnostic;
        - negative evidence only;
        - positive/protected evidence never creates rework;
        - no policy authority;
        - no QualityGate authority;
        - minimal affected production domain only.
        """

        scope = str(
            profile.get("scope", "")
        ).strip().lower()

        key = str(
            profile.get("key", "")
        ).strip().lower()

        value = profile.get(
            "value",
            {}
        )

        if not isinstance(value, dict):
            return ()

        # Positive evidence must never manufacture work.
        if (
            bool(value.get("acceptable", False))
            or
            bool(
                value.get(
                    "protect_from_visual_failure_compensation",
                    False,
                )
            )
        ):
            return ()

        negative = bool(
            value.get("negative_example", False)
            or
            value.get("primary_failure", False)
        )

        if not negative:
            return ()

        blob = " ".join(
            (
                scope,
                key,
                str(
                    value.get(
                        "human_verdict",
                        "",
                    )
                ).lower(),
                str(
                    value.get(
                        "requirement",
                        "",
                    )
                ).lower(),
                str(
                    value.get(
                        "quality",
                        "",
                    )
                ).lower(),
            )
        )

        targets: list[str] = []

        def add(*items: str) -> None:
            for item in items:
                if item not in targets:
                    targets.append(item)

        # Visual assignment / semantic correspondence.
        if (
            "visual_assignment" in scope
            or
            "narration_visual" in blob
            or
            "semantic" in blob
            or
            "event_relevance" in blob
            or
            "irrelevant_event" in blob
        ):
            add("assignment")

        # Asset diversity / coverage / repetition.
        if (
            "asset_repetition" in blob
            or
            "excessive_asset_repetition" in blob
            or
            "visual_gap" in blob
            or
            "missing_visual" in blob
            or
            "visual_coverage" in blob
        ):
            add(
                "assignment",
                "assets",
            )

        # Assembly-level visual failure is repaired locally first.
        if (
            "assembly_quality" in scope
            and (
                "visual" in blob
                or
                "assembly" in blob
            )
        ):
            add("assignment")

        # Story is touched only by explicit story/narrative failure.
        if (
            (
                "story" in scope
                or
                "narrative" in scope
                or
                key in (
                    "story",
                    "narrative",
                    "story_structure",
                    "narrative_structure",
                )
            )
            and negative
        ):
            add("story")

        # Opening/hook-specific evidence.
        if (
            "opening" in scope
            or
            "hook" in scope
            or
            key in (
                "opening",
                "opening_hook",
                "hook",
            )
        ):
            add(
                "opening_rework",
                "story",
            )

        # Duration/pacing evidence.
        if (
            "duration" in scope
            or
            "pacing" in scope
            or
            key in (
                "duration",
                "pacing",
                "shot_duration",
            )
        ):
            add(
                "duration_rework",
                "timeline",
            )

        # Voice only when voice itself is explicitly the failure domain.
        if (
            (
                "voice" in scope
                or
                key in (
                    "voice",
                    "voice_quality",
                    "tts",
                    "pronunciation",
                )
            )
            and not (
                "visual" in scope
                or
                "narration_visual" in blob
            )
        ):
            add("voice")

        return tuple(targets)

    def learning_target_preferences(
        self,
        *,
        minimum_confidence: float = 0.60,
    ) -> dict[str, Any]:
        """
        Build auditable soft rework preferences from LearningCore profiles.

        This method does not apply DirectorPolicy. The caller must intersect
        returned preferences with the active policy before execution.
        """

        profiles = self.learning.profiles(
            minimum_confidence=minimum_confidence
        )

        ranked_targets: list[str] = []
        evidence: list[dict[str, Any]] = []
        protected_components: list[str] = []

        for profile in profiles:

            value = profile.get(
                "value",
                {}
            )

            if not isinstance(value, dict):
                value = {}

            protected = bool(
                value.get("acceptable", False)
                or
                value.get(
                    "protect_from_visual_failure_compensation",
                    False,
                )
            )

            if protected:
                protected_components.append(
                    (
                        f"{profile.get('scope', '')}"
                        f"/{profile.get('key', '')}"
                    )
                )

            targets = self._profile_rework_targets(
                profile
            )

            if not targets:
                continue

            for target in targets:
                if target not in ranked_targets:
                    ranked_targets.append(target)

            evidence.append(
                {
                    "scope":
                        profile.get("scope"),

                    "key":
                        profile.get("key"),

                    "confidence":
                        profile.get("confidence"),

                    "evidence_count":
                        profile.get("evidence_count"),

                    "targets":
                        list(targets),

                    "human_verdict":
                        value.get("human_verdict"),

                    "requirement":
                        value.get("requirement"),
                }
            )

        return {
            "schema":
                "atlas_zero.learning_target_preferences.rc1",

            "project_id":
                self.project_id,

            "mode":
                "advisory_only",

            "minimum_confidence":
                float(minimum_confidence),

            "profile_count":
                len(profiles),

            "ranked_targets":
                ranked_targets,

            "evidence":
                evidence,

            "protected_components":
                protected_components,

            "permissions": {
                "override_director":
                    False,

                "rewrite_policy":
                    False,

                "bypass_quality_gate":
                    False,

                "modify_stage_order":
                    False,
            },
        }


    # ------------------------------------------------------------------
    # PATCH 7A2 ? ProductionPolicyAdvisory BUILDER
    # ------------------------------------------------------------------

    @staticmethod
    def _bounded_pressure(
        value: Any,
    ) -> int:
        """
        Normalize one production-advisory pressure level.

        Learning is allowed to request only:
            0 = baseline
            1 = moderate preventive pressure
            2 = strong preventive pressure

        Negative values and values above the bounded contract are blocked.
        """
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = 0

        return max(
            0,
            min(
                2,
                normalized,
            ),
        )

    @classmethod
    def _production_policy_from_evidence(
        cls,
        evidence: Iterable[dict[str, Any]],
        *,
        minimum_confidence: float = 0.60,
    ) -> dict[str, Any]:
        """
        Convert normalized learning evidence into bounded production pressure.

        Important:
        - returns advisory pressure only;
        - never returns arbitrary production thresholds;
        - never changes hard safety/max-use rules;
        - never forces an asset;
        - never bypasses QualityGate;
        - never changes canonical stage order.
        """
        semantic_strictness = 0
        reuse_pressure = 0
        diversity_pressure = 0
        sequencing_pressure = 0
        coverage_pressure = 0

        confidence_values: list[float] = []
        evidence_codes: list[str] = []
        provenance: list[str] = []

        accepted_evidence: list[
            dict[str, Any]
        ] = []

        for raw_item in evidence:

            if not isinstance(
                raw_item,
                dict,
            ):
                continue

            try:
                confidence = float(
                    raw_item.get(
                        "confidence",
                        0.0,
                    )
                    or 0.0
                )
            except (TypeError, ValueError):
                confidence = 0.0

            confidence = max(
                0.0,
                min(
                    1.0,
                    confidence,
                ),
            )

            if confidence < float(
                minimum_confidence
            ):
                continue

            scope = str(
                raw_item.get(
                    "scope",
                    "",
                )
                or ""
            ).strip().lower()

            key = str(
                raw_item.get(
                    "key",
                    "",
                )
                or ""
            ).strip().lower()

            verdict = str(
                raw_item.get(
                    "human_verdict",
                    "",
                )
                or ""
            ).strip().upper()

            requirement = str(
                raw_item.get(
                    "requirement",
                    "",
                )
                or ""
            ).strip().lower()

            targets = tuple(
                str(item).strip().lower()
                for item
                in (
                    raw_item.get(
                        "targets",
                        (),
                    )
                    or ()
                )
                if str(item).strip()
            )

            #
            # Production advisory is currently limited to the assignment /
            # visual-production domain.
            #
            # Evidence explicitly attributed to another target must not
            # silently alter assignment policy.
            #
            if (
                targets
                and
                "assignment" not in targets
                and
                "assets" not in targets
            ):
                continue

            blob = " ".join(
                (
                    scope,
                    key,
                    verdict.lower(),
                    requirement,
                    " ".join(
                        targets
                    ),
                )
            )

            confidence_values.append(
                confidence
            )

            code = (
                verdict
                or key.upper()
                or scope.upper()
            )

            if (
                code
                and code not in evidence_codes
            ):
                evidence_codes.append(
                    code
                )

            provenance_item = (
                f"{scope or 'unknown'}"
                f"/"
                f"{key or 'unknown'}"
            )

            if (
                provenance_item
                not in provenance
            ):
                provenance.append(
                    provenance_item
                )

            accepted_evidence.append(
                {
                    "scope":
                        raw_item.get(
                            "scope"
                        ),

                    "key":
                        raw_item.get(
                            "key"
                        ),

                    "confidence":
                        confidence,

                    "targets":
                        list(
                            targets
                        ),

                    "human_verdict":
                        raw_item.get(
                            "human_verdict"
                        ),

                    "requirement":
                        raw_item.get(
                            "requirement"
                        ),
                }
            )

            # ---------------------------------------------------------
            # Semantic mismatch / event relevance.
            # ---------------------------------------------------------

            semantic_markers = (
                "narration_visual_mismatch",
                "narration_visual_alignment",
                "irrelevant_event_material",
                "irrelevant_event",
                "event_relevance",
                "strict_semantic_correspondence",
                "false_semantic_assignment",
                "semantic_mismatch",
            )

            if any(
                marker in blob
                for marker in semantic_markers
            ):
                semantic_strictness = max(
                    semantic_strictness,
                    1,
                )

            severe_semantic_markers = (
                "false_semantic_assignment_risk",
                "severe_semantic_mismatch",
                "systematic_semantic_mismatch",
                "repeated_semantic_mismatch",
            )

            if any(
                marker in blob
                for marker
                in severe_semantic_markers
            ):
                semantic_strictness = 2

            # ---------------------------------------------------------
            # Repetition.
            # ---------------------------------------------------------

            repetition_markers = (
                "asset_repetition",
                "excessive_asset_repetition",
                "avoid_unjustified_repetition",
                "repeated_asset",
            )

            if any(
                marker in blob
                for marker in repetition_markers
            ):
                reuse_pressure = max(
                    reuse_pressure,
                    2,
                )

                diversity_pressure = max(
                    diversity_pressure,
                    1,
                )

                sequencing_pressure = max(
                    sequencing_pressure,
                    1,
                )

            # ---------------------------------------------------------
            # Visual family / motif / source repetition.
            # ---------------------------------------------------------

            diversity_markers = (
                "visual_family_repetition",
                "motif_repetition",
                "source_repetition",
                "editorial_repetition",
                "lineage_repetition",
            )

            if any(
                marker in blob
                for marker in diversity_markers
            ):
                diversity_pressure = max(
                    diversity_pressure,
                    2,
                )

                sequencing_pressure = max(
                    sequencing_pressure,
                    2,
                )

            # ---------------------------------------------------------
            # Coverage.
            # ---------------------------------------------------------

            coverage_markers = (
                "visual_gap",
                "missing_visual",
                "visual_coverage",
                "coverage_failure",
            )

            if any(
                marker in blob
                for marker in coverage_markers
            ):
                coverage_pressure = max(
                    coverage_pressure,
                    1,
                )

            severe_coverage_markers = (
                "severe_visual_gap",
                "systematic_visual_gap",
            )

            if any(
                marker in blob
                for marker
                in severe_coverage_markers
            ):
                coverage_pressure = 2

        average_confidence = (
            sum(
                confidence_values
            )
            /
            len(
                confidence_values
            )
            if confidence_values
            else 0.0
        )

        pressures = {
            "semantic_strictness":
                cls._bounded_pressure(
                    semantic_strictness
                ),

            "reuse_pressure":
                cls._bounded_pressure(
                    reuse_pressure
                ),

            "diversity_pressure":
                cls._bounded_pressure(
                    diversity_pressure
                ),

            "sequencing_pressure":
                cls._bounded_pressure(
                    sequencing_pressure
                ),

            "coverage_pressure":
                cls._bounded_pressure(
                    coverage_pressure
                ),
        }

        active = any(
            value > 0
            for value
            in pressures.values()
        )

        return {
            "schema":
                "atlas_zero.production_policy_advisory.rc1",

            "state":
                (
                    "PRODUCTION_POLICY_ADVISORY_READY"
                    if active
                    else
                    "PRODUCTION_POLICY_BASELINE"
                ),

            "mode":
                "advisory_only",

            "minimum_confidence":
                float(
                    minimum_confidence
                ),

            "confidence":
                round(
                    average_confidence,
                    6,
                ),

            "pressures":
                pressures,

            "evidence":
                evidence_codes,

            "provenance":
                provenance,

            "accepted_evidence":
                accepted_evidence,

            "permissions": {
                "override_director":
                    False,

                "rewrite_hard_policy":
                    False,

                "modify_source":
                    False,

                "bypass_quality_gate":
                    False,

                "lower_safety_threshold":
                    False,

                "force_asset_selection":
                    False,

                "modify_stage_order":
                    False,

                "request_bounded_policy_pressure":
                    True,
            },
        }

    # ------------------------------------------------------------------
    # PATCH 7B1 ? CONTEXT-FILTERED HISTORICAL ADVISORY
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_bounded_pressures(
        pressure_items: Iterable[dict[str, Any]],
    ) -> dict[str, int]:
        """
        Conservatively merge historical bounded pressure.

        V1 rule:
        take MAX pressure per dimension after each source has already passed
        the context gate.

        Rationale:
        - pressure is already bounded to 0..2;
        - no raw production parameter is merged;
        - one proven strong historical warning should not be averaged away;
        - AssignmentPolicyRC2 still owns concrete parameter projection.
        """
        keys = (
            "semantic_strictness",
            "reuse_pressure",
            "diversity_pressure",
            "sequencing_pressure",
            "coverage_pressure",
        )

        result = {
            key:
                0
            for key
            in keys
        }

        for item in pressure_items:

            if not isinstance(
                item,
                dict,
            ):
                continue

            for key in keys:

                try:
                    value = int(
                        item.get(
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

                value = max(
                    0,
                    min(
                        2,
                        value,
                    ),
                )

                result[
                    key
                ] = max(
                    result[
                        key
                    ],
                    value,
                )

        return result

    def historical_production_policy_advisory(
        self,
        *,
        runtime_metadata: dict[str, Any] | None = None,
        issue_codes: Iterable[str] = (),
        target: str = "assignment",
        minimum_similarity: float = 0.60,
    ) -> dict[str, Any]:
        """
        Build a cross-project preventive-production advisory from VERIFIED
        historical production experience.

        PATCH 7B1 authority contract:

        - current project is excluded by DirectorKnowledgeBaseRC2;
        - only outcome='improved' records are read;
        - every record must pass PATCH 6 _context_similarity();
        - known failure-domain mismatch is hard blocked by PATCH 6B2.1;
        - only bounded pressure 0..2 can transfer;
        - no raw thresholds transfer;
        - no asset IDs transfer;
        - no production application happens here.
        """
        normalized_target = str(
            target
        ).strip()

        if not normalized_target:
            raise ValueError(
                "target is required"
            )

        current_metadata = dict(
            runtime_metadata
            or {}
        )

        current_issues = tuple(
            sorted(
                {
                    str(item).strip()
                    for item
                    in issue_codes
                    if str(item).strip()
                }
            )
        )

        current_context = {
            "project_type":
                current_metadata.get(
                    "project_type"
                ),

            "objective":
                current_metadata.get(
                    "objective"
                ),

            "failure_domain":
                current_metadata.get(
                    "failure_domain"
                ),

            "target":
                normalized_target,

            "source":
                current_metadata.get(
                    "source"
                ),

            "issue_codes":
                current_issues,
        }

        historical_records = (
            self.director_knowledge
            .production_experience(
                current_project_id=
                    self.project_id,

                target=
                    normalized_target,

                outcome=
                    "improved",
            )
        )

        accepted = []
        rejected = []

        for record in historical_records:

            historical_metadata = dict(
                record.get(
                    "runtime_metadata",
                    {},
                )
                or {}
            )

            historical_context = {
                "project_type":
                    (
                        record.get(
                            "project_type"
                        )
                        if record.get(
                            "project_type"
                        ) is not None
                        else historical_metadata.get(
                            "project_type"
                        )
                    ),

                "objective":
                    (
                        record.get(
                            "objective"
                        )
                        if record.get(
                            "objective"
                        ) is not None
                        else historical_metadata.get(
                            "objective"
                        )
                    ),

                "failure_domain":
                    (
                        record.get(
                            "failure_domain"
                        )
                        or historical_metadata.get(
                            "failure_domain"
                        )
                    ),

                "target":
                    (
                        record.get(
                            "target"
                        )
                        or normalized_target
                    ),

                "source":
                    historical_metadata.get(
                        "source"
                    ),

                "issue_codes":
                    tuple(
                        record.get(
                            "issue_codes",
                            (),
                        )
                        or ()
                    ),
            }

            similarity = (
                self.director_knowledge
                ._context_similarity(
                    current_context,
                    historical_context,
                )
            )

            transfer_eligible = bool(
                similarity.get(
                    "transfer_eligible",
                    False,
                )
            )

            adjusted_similarity = float(
                similarity.get(
                    "adjusted_similarity",
                    0.0,
                )
                or 0.0
            )

            accepted_by_threshold = (
                transfer_eligible
                and
                adjusted_similarity
                >=
                float(
                    minimum_similarity
                )
            )

            trace = {
                "experience_id":
                    record.get(
                        "experience_id"
                    ),

                "source_project_id":
                    record.get(
                        "project_id"
                    ),

                "failure_domain":
                    record.get(
                        "failure_domain"
                    ),

                "score_delta":
                    record.get(
                        "score_delta"
                    ),

                "pressures":
                    dict(
                        record.get(
                            "pressures",
                            {},
                        )
                        or {}
                    ),

                "similarity":
                    similarity,
            }

            if accepted_by_threshold:

                accepted.append(
                    trace
                )

            else:

                rejected.append(
                    trace
                )

        merged_pressures = (
            self._merge_bounded_pressures(
                item.get(
                    "pressures",
                    {},
                )
                for item
                in accepted
            )
        )

        active = any(
            value > 0
            for value
            in merged_pressures.values()
        )

        source_projects = tuple(
            dict.fromkeys(
                str(
                    item.get(
                        "source_project_id"
                    )
                )
                for item
                in accepted
                if item.get(
                    "source_project_id"
                )
            )
        )

        experience_ids = tuple(
            item.get(
                "experience_id"
            )
            for item
            in accepted
            if item.get(
                "experience_id"
            ) is not None
        )

        provenance = tuple(
            (
                "director_production_experience/"
                f"{item.get('source_project_id')}/"
                f"{item.get('experience_id')}"
            )
            for item
            in accepted
        )

        #
        # Confidence is context confidence, not permission.
        #
        # Every source already passed transfer_eligible.
        #
        accepted_similarity = [
            float(
                item.get(
                    "similarity",
                    {},
                ).get(
                    "adjusted_similarity",
                    0.0,
                )
                or 0.0
            )
            for item
            in accepted
        ]

        confidence = (
            sum(
                accepted_similarity
            )
            /
            len(
                accepted_similarity
            )
            if accepted_similarity
            else 0.0
        )

        return {
            "schema":
                "atlas_zero.historical_production_policy_advisory.rc1",

            "state":
                (
                    "HISTORICAL_PRODUCTION_POLICY_ADVISORY_READY"
                    if active
                    else
                    "NO_COMPATIBLE_HISTORICAL_PRODUCTION_EXPERIENCE"
                ),

            "mode":
                "advisory_only",

            "project_id":
                self.project_id,

            "target":
                normalized_target,

            "current_context":
                current_context,

            "minimum_similarity":
                float(
                    minimum_similarity
                ),

            "confidence":
                round(
                    confidence,
                    6,
                ),

            "pressures":
                merged_pressures,

            "accepted_experience_count":
                len(
                    accepted
                ),

            "rejected_experience_count":
                len(
                    rejected
                ),

            "source_projects":
                list(
                    source_projects
                ),

            "experience_ids":
                list(
                    experience_ids
                ),

            "provenance":
                list(
                    provenance
                ),

            "accepted":
                accepted,

            "rejected":
                rejected,

            "permissions": {
                "override_director":
                    False,

                "rewrite_hard_policy":
                    False,

                "modify_source":
                    False,

                "bypass_quality_gate":
                    False,

                "lower_safety_threshold":
                    False,

                "force_asset_selection":
                    False,

                "modify_stage_order":
                    False,

                "apply_to_production":
                    False,

                "request_bounded_policy_pressure":
                    True,
            },
        }

    # ------------------------------------------------------------------
    # PATCH 7B2 ? LOCAL + HISTORICAL ADVISORY MERGE
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_local_historical_pressures(
        *,
        local_pressures: dict[str, Any] | None,
        historical_pressures: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Merge current-project learning with compatible historical prior.

        Authority rule:

        1. A non-zero LOCAL pressure is authoritative.
        2. HISTORICAL pressure may fill a zero local dimension.
        3. Historical pressure may never overwrite or amplify an existing
           non-zero local pressure.
        4. Every pressure remains bounded to 0..2.
        """
        keys = (
            "semantic_strictness",
            "reuse_pressure",
            "diversity_pressure",
            "sequencing_pressure",
            "coverage_pressure",
        )

        local_pressures = dict(
            local_pressures
            or {}
        )

        historical_pressures = dict(
            historical_pressures
            or {}
        )

        merged = {}
        authority = {}

        for key in keys:

            try:
                local_value = int(
                    local_pressures.get(
                        key,
                        0,
                    )
                    or 0
                )
            except (
                TypeError,
                ValueError,
            ):
                local_value = 0

            try:
                historical_value = int(
                    historical_pressures.get(
                        key,
                        0,
                    )
                    or 0
                )
            except (
                TypeError,
                ValueError,
            ):
                historical_value = 0

            local_value = max(
                0,
                min(
                    2,
                    local_value,
                ),
            )

            historical_value = max(
                0,
                min(
                    2,
                    historical_value,
                ),
            )

            if local_value > 0:

                merged_value = local_value
                source = "local"

            elif historical_value > 0:

                merged_value = historical_value
                source = "historical"

            else:

                merged_value = 0
                source = "none"

            merged[key] = merged_value

            authority[key] = {
                "source":
                    source,

                "local":
                    local_value,

                "historical":
                    historical_value,

                "merged":
                    merged_value,
            }

        return {
            "pressures":
                merged,

            "authority":
                authority,
        }

    def merged_production_policy_advisory(
        self,
        *,
        runtime_metadata: dict[str, Any] | None = None,
        issue_codes: Iterable[str] = (),
        target: str = "assignment",
        minimum_confidence: float = 0.60,
        minimum_similarity: float = 0.60,
    ) -> dict[str, Any]:
        """
        Build the bounded production advisory that combines:

        - LOCAL current-project learning;
        - compatible HISTORICAL cross-project production experience.

        This method remains advisory-only.

        It does NOT apply policy to AssignmentEngineRC2.
        """
        local = self.production_policy_advisory(
            minimum_confidence=
                minimum_confidence
        )

        historical = (
            self.historical_production_policy_advisory(
                runtime_metadata=
                    runtime_metadata,

                issue_codes=
                    issue_codes,

                target=
                    target,

                minimum_similarity=
                    minimum_similarity,
            )
        )

        local_pressures = dict(
            local.get(
                "pressures",
                {},
            )
            or {}
        )

        historical_pressures = dict(
            historical.get(
                "pressures",
                {},
            )
            or {}
        )

        merge = (
            self._merge_local_historical_pressures(
                local_pressures=
                    local_pressures,

                historical_pressures=
                    historical_pressures,
            )
        )

        merged_pressures = dict(
            merge[
                "pressures"
            ]
        )

        authority = dict(
            merge[
                "authority"
            ]
        )

        active = any(
            int(value) > 0
            for value
            in merged_pressures.values()
        )

        local_active_dimensions = [
            key
            for key, item
            in authority.items()
            if item.get(
                "source"
            )
            ==
            "local"
        ]

        historical_active_dimensions = [
            key
            for key, item
            in authority.items()
            if item.get(
                "source"
            )
            ==
            "historical"
        ]

        return {
            "schema":
                "atlas_zero.merged_production_policy_advisory.rc1",

            "state":
                (
                    "MERGED_PRODUCTION_POLICY_ADVISORY_READY"
                    if active
                    else
                    "NO_PRODUCTION_POLICY_PRESSURE"
                ),

            "mode":
                "advisory_only",

            "project_id":
                self.project_id,

            "target":
                str(
                    target
                ).strip(),

            "pressures":
                merged_pressures,

            "authority":
                authority,

            "local_active_dimensions":
                local_active_dimensions,

            "historical_active_dimensions":
                historical_active_dimensions,

            "local_advisory":
                local,

            "historical_advisory":
                historical,

            "historical_source_projects":
                list(
                    historical.get(
                        "source_projects",
                        (),
                    )
                    or ()
                ),

            "historical_experience_ids":
                list(
                    historical.get(
                        "experience_ids",
                        (),
                    )
                    or ()
                ),

            "historical_provenance":
                list(
                    historical.get(
                        "provenance",
                        (),
                    )
                    or ()
                ),

            "permissions": {
                "override_director":
                    False,

                "rewrite_hard_policy":
                    False,

                "modify_source":
                    False,

                "bypass_quality_gate":
                    False,

                "lower_safety_threshold":
                    False,

                "force_asset_selection":
                    False,

                "modify_stage_order":
                    False,

                "apply_to_production":
                    False,

                "request_bounded_policy_pressure":
                    True,
            },
        }

    def production_policy_advisory(
        self,
        *,
        minimum_confidence: float = 0.60,
    ) -> dict[str, Any]:
        """
        Build a bounded production-policy advisory from current-project
        LearningCore evidence.

        PATCH 7A2 intentionally does NOT apply this advisory to production.
        AssignmentPolicyRC2 remains untouched and authoritative.

        Cross-project production-policy transfer is intentionally NOT
        implemented here yet. LearningCoreRC1.profiles() is project-scoped.
        """
        preference = (
            self.learning_target_preferences(
                minimum_confidence=
                    minimum_confidence
            )
        )

        evidence = tuple(
            item
            for item
            in (
                preference.get(
                    "evidence",
                    (),
                )
                or ()
            )
            if isinstance(
                item,
                dict,
            )
        )

        result = (
            self._production_policy_from_evidence(
                evidence,
                minimum_confidence=
                    minimum_confidence,
            )
        )

        result.update(
            {
                "project_id":
                    self.project_id,

                "source":
                    "DirectorLearningAdapterRC1",

                "source_scope":
                    "project_local_learning_profiles",

                "learning_preference_schema":
                    preference.get(
                        "schema"
                    ),

                "profile_count":
                    preference.get(
                        "profile_count",
                        0,
                    ),

                "protected_components":
                    list(
                        preference.get(
                            "protected_components",
                            (),
                        )
                        or ()
                    ),
            }
        )

        return result


    # ------------------------------------------------------------------
    # Persist advisory
    # ------------------------------------------------------------------

    def save_advisory(
        self,
        advisory: dict[str, Any],
    ) -> dict[str, Any]:

        cursor = self.db.conn.execute(
            """
            INSERT INTO director_learning_advisories(
                project_id,
                source_event,
                minimum_confidence,
                profile_count,
                advisory_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self.project_id,

                advisory.get(
                    "source_event"
                ),

                float(
                    advisory.get(
                        "minimum_confidence",
                        0.60,
                    )
                ),

                int(
                    advisory.get(
                        "profile_count",
                        0,
                    )
                ),

                json.dumps(
                    advisory,
                    ensure_ascii=False,
                    sort_keys=True,
                ),

                self._now(),
            ),
        )

        self.db.conn.commit()

        return {
            "state":
                "DIRECTOR_LEARNING_ADVISORY_SAVED",

            "project_id":
                self.project_id,

            "advisory_id":
                cursor.lastrowid,
        }

    # ------------------------------------------------------------------
    # Latest
    # ------------------------------------------------------------------

    def latest_advisory(
        self,
    ) -> dict[str, Any] | None:

        row = self.db.conn.execute(
            """
            SELECT advisory_json
            FROM director_learning_advisories
            WHERE project_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                self.project_id,
            ),
        ).fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    # ------------------------------------------------------------------
    # Event consumer
    # ------------------------------------------------------------------

    def _on_learning_updated(
        self,
        payload: dict[str, Any] | None,
    ) -> None:

        payload = payload or {}

        event_project = str(
            payload.get(
                "project_id",
                "",
            )
        ).strip()

        if (
            event_project
            and event_project
            != self.project_id
        ):
            return

        advisory = self.build_advisory(
            source_event=self.EVENT,
        )

        self.save_advisory(
            advisory
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> str:

        return datetime.now(
            timezone.utc
        ).isoformat()
