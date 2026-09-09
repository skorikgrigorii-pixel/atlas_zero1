from __future__ import annotations

from typing import Any

from .database import Database
from .assignment_policy_rc2 import AssignmentPolicyRC2
from .director_ai import DirectorAI
from .project_config_rc2 import ProjectConfigRC2


class AssignmentEngineRC2:
    """One assignment API. Legacy scoring remains behind this adapter during migration."""

    def __init__(
        self,
        db: Database,
        config: ProjectConfigRC2,
        *,
        production_policy_advisory: dict[str, Any] | None = None,
    ) -> None:
        self.db = db
        self.config = config

        # PATCH 7A3 ? DIAGNOSTIC ProductionPolicyAdvisory BRIDGE
        #
        # This value is diagnostic only.
        #
        # It is deliberately NOT passed into AssignmentPolicyRC2.
        # Therefore PATCH 7A3 cannot change scoring, selection, reuse,
        # semantic acceptance, assignment writes or any other production
        # decision.
        self.production_policy_advisory = (
            dict(production_policy_advisory)
            if isinstance(
                production_policy_advisory,
                dict,
            )
            else None
        )

    def _production_policy_diagnostics(
        self,
    ) -> dict[str, Any]:
        """
        Return a safe diagnostic representation of the learning advisory.

        PATCH 7A3 contract:
        - diagnostics only;
        - no policy parameter conversion;
        - no assignment authority;
        - no QualityGate authority;
        - no stage-order authority.
        """
        advisory = (
            self.production_policy_advisory
        )

        if not isinstance(
            advisory,
            dict,
        ):
            return {
                "schema":
                    "atlas_zero.assignment_engine_policy_advisory.rc1",

                "state":
                    "NO_PRODUCTION_POLICY_ADVISORY",

                "mode":
                    "diagnostic_only",

                "active":
                    False,

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

                "confidence":
                    0.0,

                "evidence":
                    [],

                "provenance":
                    [],

                "applied_to_assignment":
                    False,
            }

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

        active = (
            advisory.get(
                "state"
            )
            ==
            "PRODUCTION_POLICY_ADVISORY_READY"
            and
            any(
                value > 0
                for value
                in pressures.values()
            )
        )

        return {
            "schema":
                "atlas_zero.assignment_engine_policy_advisory.rc1",

            "source_schema":
                advisory.get(
                    "schema"
                ),

            "state":
                (
                    "PRODUCTION_POLICY_ADVISORY_RECEIVED"
                    if active
                    else
                    "PRODUCTION_POLICY_BASELINE"
                ),

            "mode":
                "diagnostic_only",

            "active":
                bool(
                    active
                ),

            "pressures":
                pressures,

            "confidence":
                confidence,

            "evidence":
                evidence,

            "provenance":
                provenance,

            "permissions":
                dict(
                    advisory.get(
                        "permissions",
                        {},
                    )
                    or {}
                ),

            # Critical PATCH 7A3 invariant.
            "applied_to_assignment":
                False,
        }

    def run(self) -> dict[str, Any]:
        production_policy_diagnostics = (
            self._production_policy_diagnostics()
        )

        # PATCH 7A4 ? APPLY BOUNDED ADVISORY
        #
        # AssignmentPolicyRC2 remains the concrete parameter authority.
        # Engine forwards advisory evidence only; policy owns normalization,
        # bounds and all effective production values.
        result = AssignmentPolicyRC2(
            self.db,
            project_id=self.config.project_id,
            production_policy_advisory=
                self.production_policy_advisory,
        ).run()

        effective_profile = dict(
            result.get(
                "production_policy_profile",
                {},
            )
            or {}
        )

        production_policy_diagnostics[
            "applied_to_assignment"
        ] = bool(
            effective_profile.get(
                "active",
                False,
            )
        )

        production_policy_diagnostics[
            "effective_profile"
        ] = effective_profile

        # DirectorAI remains an analysis/task service only.
        analysis = DirectorAI(
            self.db,
            project_id=self.config.project_id,
            enable_legacy_state_authority=False,
        )._analyze_completeness()

        assigned = self.db.one(
            """
            SELECT COUNT(*) AS count
            FROM shots
            WHERE project_id=? AND status='assigned'
            """,
            (self.config.project_id,),
        )
        missing = self.db.one(
            """
            SELECT COUNT(*) AS count
            FROM shots
            WHERE project_id=? AND status!='assigned'
            """,
            (self.config.project_id,),
        )
        return {
            "state": "ASSIGNED",
            "project_id": self.config.project_id,
            "assigned": int(assigned["count"] if assigned else 0),
            "missing": int(missing["count"] if missing else 0),
            "assignment_result": result,
            "analysis": analysis,

            # PATCH 7A3 diagnostic surface.
            #
            # This reports what learning requested, not what assignment
            # applied. applied_to_assignment must remain False until PATCH
            # 7A4 explicitly delegates bounded parameter projection to
            # AssignmentPolicyRC2.
            "production_policy_advisory":
                production_policy_diagnostics,
        }
