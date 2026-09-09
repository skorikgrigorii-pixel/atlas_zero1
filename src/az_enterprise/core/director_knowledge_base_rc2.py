"""Persistent learning memory for Director decisions in RC2.

The knowledge base does not replace DirectorPolicy. It records what the
supervisor tried, measures whether the next cycle improved the policy score,
and uses that history only to rank already-allowed rework targets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .database import Database


@dataclass(frozen=True)
class TargetExperience:
    target: str
    attempts: int
    successes: int
    average_score_delta: float
    effectiveness: float


class DirectorKnowledgeBaseRC2:
    """SQLite-backed experience store for supervised rework decisions."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._init_schema()

    def _init_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS director_learning_cycles(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                cycle INTEGER NOT NULL,
                score_before REAL NOT NULL,
                score_after REAL,
                score_delta REAL,
                targets_json TEXT NOT NULL,
                issue_codes_json TEXT NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'pending',
                runtime_metadata_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
            """
        )
        self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_director_learning_project_cycle
            ON director_learning_cycles(project_id, cycle)
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS director_target_experience(
                project_id TEXT NOT NULL,
                target TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                total_score_delta REAL NOT NULL DEFAULT 0.0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(project_id, target)
            )
            """
        )


        # PATCH 7B0 ? PRODUCTION EXPERIENCE MEMORY
        #
        # This table stores VERIFIED experience about bounded production
        # policy effects.
        #
        # It is intentionally separate from director_learning_cycles:
        #
        # - learning_cycles measure supervised rework target effectiveness;
        # - production_experience measures preventive production-policy
        #   effectiveness.
        #
        # This is memory only. It has no production authority.
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS director_production_experience(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                project_id TEXT NOT NULL,

                target TEXT NOT NULL DEFAULT 'assignment',

                failure_domain TEXT NOT NULL,

                project_type TEXT,
                objective TEXT,

                issue_codes_json TEXT NOT NULL,

                runtime_metadata_json TEXT NOT NULL,

                pressures_json TEXT NOT NULL,

                evidence_json TEXT NOT NULL,

                provenance_json TEXT NOT NULL,

                score_before REAL NOT NULL,
                score_after REAL NOT NULL,
                score_delta REAL NOT NULL,

                outcome TEXT NOT NULL,

                verification_source TEXT NOT NULL,

                advisory_schema TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_director_production_experience_project
            ON director_production_experience(
                project_id,
                target,
                outcome
            )
            """
        )

        self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_director_production_experience_context
            ON director_production_experience(
                failure_domain,
                target,
                outcome
            )
            """
        )

    @staticmethod
    def _bounded_production_pressures(
        pressures: Mapping[str, Any] | None,
    ) -> dict[str, int]:
        """
        Normalize production pressure memory to the canonical 0..2 contract.

        Historical memory never stores or transfers raw production thresholds.
        """
        source = dict(
            pressures
            or {}
        )

        keys = (
            "semantic_strictness",
            "reuse_pressure",
            "diversity_pressure",
            "sequencing_pressure",
            "coverage_pressure",
        )

        result: dict[str, int] = {}

        for key in keys:

            try:
                value = int(
                    source.get(
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

            result[
                key
            ] = max(
                0,
                min(
                    2,
                    value,
                ),
            )

        return result

    def record_production_experience(
        self,
        *,
        project_id: str,
        failure_domain: str,
        pressures: Mapping[str, Any],
        score_before: float,
        score_after: float,
        issue_codes: Iterable[str] = (),
        runtime_metadata: Mapping[str, Any] | None = None,
        evidence: Iterable[Any] = (),
        provenance: Iterable[Any] = (),
        verification_source: str,
        target: str = "assignment",
        advisory_schema: str | None = None,
        success_epsilon: float = 0.001,
    ) -> dict[str, Any]:
        """
        Persist one VERIFIED preventive-production experience record.

        PATCH 7B0 authority contract:

        - bounded pressure only;
        - no raw production thresholds;
        - no asset IDs;
        - no policy rewrite;
        - no QualityGate bypass;
        - no automatic cross-project transfer.

        A record is useful as positive global experience only when its
        measured outcome is 'improved'.
        """
        normalized_project = str(
            project_id
        ).strip()

        normalized_domain = str(
            failure_domain
        ).strip()

        normalized_target = str(
            target
        ).strip()

        normalized_verification = str(
            verification_source
        ).strip()

        if not normalized_project:
            raise ValueError(
                "project_id is required"
            )

        if not normalized_domain:
            raise ValueError(
                "failure_domain is required"
            )

        if not normalized_target:
            raise ValueError(
                "target is required"
            )

        if not normalized_verification:
            raise ValueError(
                "verification_source is required"
            )

        before = float(
            score_before
        )

        after = float(
            score_after
        )

        delta = (
            after
            -
            before
        )

        epsilon = max(
            0.0,
            float(
                success_epsilon
            ),
        )

        if delta > epsilon:
            outcome = (
                "improved"
            )

        elif delta < -epsilon:
            outcome = (
                "regressed"
            )

        else:
            outcome = (
                "neutral"
            )

        normalized_pressures = (
            self._bounded_production_pressures(
                pressures
            )
        )

        normalized_issues = tuple(
            sorted(
                {
                    str(item).strip()
                    for item
                    in issue_codes
                    if str(item).strip()
                }
            )
        )

        normalized_evidence = tuple(
            dict.fromkeys(
                str(item).strip()
                for item
                in evidence
                if str(item).strip()
            )
        )

        normalized_provenance = tuple(
            dict.fromkeys(
                str(item).strip()
                for item
                in provenance
                if str(item).strip()
            )
        )

        metadata = dict(
            runtime_metadata
            or {}
        )

        metadata[
            "failure_domain"
        ] = normalized_domain

        metadata[
            "target"
        ] = normalized_target

        self.db.execute(
            """
            INSERT INTO director_production_experience(
                project_id,
                target,
                failure_domain,
                project_type,
                objective,
                issue_codes_json,
                runtime_metadata_json,
                pressures_json,
                evidence_json,
                provenance_json,
                score_before,
                score_after,
                score_delta,
                outcome,
                verification_source,
                advisory_schema
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                normalized_project,
                normalized_target,
                normalized_domain,

                (
                    str(
                        metadata.get(
                            "project_type"
                        )
                    )
                    if metadata.get(
                        "project_type"
                    ) is not None
                    else None
                ),

                (
                    str(
                        metadata.get(
                            "objective"
                        )
                    )
                    if metadata.get(
                        "objective"
                    ) is not None
                    else None
                ),

                self._json(
                    normalized_issues
                ),

                self._json(
                    metadata
                ),

                self._json(
                    normalized_pressures
                ),

                self._json(
                    normalized_evidence
                ),

                self._json(
                    normalized_provenance
                ),

                before,
                after,
                delta,
                outcome,
                normalized_verification,

                (
                    str(
                        advisory_schema
                    )
                    if advisory_schema
                    else None
                ),
            ),
        )

        row = self.db.one(
            """
            SELECT last_insert_rowid() AS id
            """
        )

        record_id = int(
            row[
                "id"
            ]
        )

        return {
            "state":
                "PRODUCTION_EXPERIENCE_RECORDED",

            "experience_id":
                record_id,

            "project_id":
                normalized_project,

            "target":
                normalized_target,

            "failure_domain":
                normalized_domain,

            "pressures":
                normalized_pressures,

            "score_before":
                before,

            "score_after":
                after,

            "score_delta":
                delta,

            "outcome":
                outcome,

            "verification_source":
                normalized_verification,

            "transfer_authority":
                False,
        }

    def production_experience(
        self,
        *,
        current_project_id: str,
        target: str = "assignment",
        outcome: str = "improved",
    ) -> list[dict[str, Any]]:
        """
        Read verified historical preventive-production experience.

        Current project is always excluded.

        PATCH 7B0 deliberately performs NO context transfer decision here.
        PATCH 7B1 will apply the existing PATCH 6 context gate before any
        historical pressure can influence another project.
        """
        normalized_project = str(
            current_project_id
        ).strip()

        normalized_target = str(
            target
        ).strip()

        normalized_outcome = str(
            outcome
        ).strip()

        rows = self.db.rows(
            """
            SELECT
                id,
                project_id,
                target,
                failure_domain,
                project_type,
                objective,
                issue_codes_json,
                runtime_metadata_json,
                pressures_json,
                evidence_json,
                provenance_json,
                score_before,
                score_after,
                score_delta,
                outcome,
                verification_source,
                advisory_schema,
                created_at
            FROM director_production_experience
            WHERE
                project_id<>?
                AND target=?
                AND outcome=?
            ORDER BY
                score_delta DESC,
                id ASC
            """,
            (
                normalized_project,
                normalized_target,
                normalized_outcome,
            ),
        )

        result: list[
            dict[str, Any]
        ] = []

        for row in rows:

            result.append(
                {
                    "experience_id":
                        int(
                            row[
                                "id"
                            ]
                        ),

                    "project_id":
                        str(
                            row[
                                "project_id"
                            ]
                        ),

                    "target":
                        str(
                            row[
                                "target"
                            ]
                        ),

                    "failure_domain":
                        str(
                            row[
                                "failure_domain"
                            ]
                        ),

                    "project_type":
                        row[
                            "project_type"
                        ],

                    "objective":
                        row[
                            "objective"
                        ],

                    "issue_codes":
                        tuple(
                            json.loads(
                                row[
                                    "issue_codes_json"
                                ]
                                or "[]"
                            )
                        ),

                    "runtime_metadata":
                        dict(
                            json.loads(
                                row[
                                    "runtime_metadata_json"
                                ]
                                or "{}"
                            )
                        ),

                    "pressures":
                        self._bounded_production_pressures(
                            json.loads(
                                row[
                                    "pressures_json"
                                ]
                                or "{}"
                            )
                        ),

                    "evidence":
                        tuple(
                            json.loads(
                                row[
                                    "evidence_json"
                                ]
                                or "[]"
                            )
                        ),

                    "provenance":
                        tuple(
                            json.loads(
                                row[
                                    "provenance_json"
                                ]
                                or "[]"
                            )
                        ),

                    "score_before":
                        float(
                            row[
                                "score_before"
                            ]
                        ),

                    "score_after":
                        float(
                            row[
                                "score_after"
                            ]
                        ),

                    "score_delta":
                        float(
                            row[
                                "score_delta"
                            ]
                        ),

                    "outcome":
                        str(
                            row[
                                "outcome"
                            ]
                        ),

                    "verification_source":
                        str(
                            row[
                                "verification_source"
                            ]
                        ),

                    "advisory_schema":
                        row[
                            "advisory_schema"
                        ],

                    "created_at":
                        row[
                            "created_at"
                        ],
                }
            )

        return result

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def begin_cycle(
        self,
        *,
        project_id: str,
        cycle: int,
        score_before: float,
        targets: Iterable[str],
        issue_codes: Iterable[str] = (),
        runtime_metadata: Mapping[str, Any] | None = None,
    ) -> int:
        normalized_targets = tuple(
            dict.fromkeys(str(item) for item in targets if str(item))
        )
        self.db.execute(
            """
            INSERT INTO director_learning_cycles(
                project_id,
                cycle,
                score_before,
                targets_json,
                issue_codes_json,
                runtime_metadata_json
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                project_id,
                int(cycle),
                float(score_before),
                self._json(normalized_targets),
                self._json(tuple(sorted(set(issue_codes)))),
                self._json(dict(runtime_metadata or {})),
            ),
        )
        row = self.db.one("SELECT last_insert_rowid() AS id")
        return int(row["id"])

    def complete_cycle(
        self,
        *,
        cycle_id: int,
        score_after: float,
        success_epsilon: float = 0.001,
    ) -> dict[str, Any]:
        row = self.db.one(
            """
            SELECT project_id, score_before, targets_json
            FROM director_learning_cycles
            WHERE id=? AND outcome='pending'
            """,
            (cycle_id,),
        )
        if row is None:
            return {"state": "IGNORED", "reason": "cycle_not_pending"}

        before = float(row["score_before"])
        after = float(score_after)
        delta = after - before
        outcome = "improved" if delta > success_epsilon else "not_improved"
        targets = tuple(json.loads(row["targets_json"] or "[]"))
        project_id = str(row["project_id"])

        self.db.execute(
            """
            UPDATE director_learning_cycles
            SET score_after=?, score_delta=?, outcome=?, completed_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (after, delta, outcome, cycle_id),
        )

        for target in targets:
            self.db.execute(
                """
                INSERT INTO director_target_experience(
                    project_id,
                    target,
                    attempts,
                    successes,
                    total_score_delta,
                    updated_at
                )
                VALUES(?,?,1,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(project_id, target) DO UPDATE SET
                    attempts=attempts + 1,
                    successes=successes + excluded.successes,
                    total_score_delta=total_score_delta + excluded.total_score_delta,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    project_id,
                    str(target),
                    1 if outcome == "improved" else 0,
                    delta,
                ),
            )

        return {
            "state": "RECORDED",
            "cycle_id": cycle_id,
            "score_before": before,
            "score_after": after,
            "score_delta": delta,
            "outcome": outcome,
            "targets": targets,
        }

    def target_experience(
        self,
        project_id: str,
        targets: Iterable[str],
    ) -> dict[str, TargetExperience]:
        """
        Return project-local Director experience.

        This method intentionally preserves the original project-scoped
        storage contract. It is the authoritative local evidence source.
        """
        normalized = tuple(
            dict.fromkeys(
                str(item)
                for item in targets
                if str(item)
            )
        )

        if not normalized:
            return {}

        placeholders = ",".join(
            "?"
            for _ in normalized
        )

        rows = self.db.rows(
            f"""
            SELECT
                target,
                attempts,
                successes,
                total_score_delta
            FROM director_target_experience
            WHERE
                project_id=?
                AND target IN ({placeholders})
            """,
            (
                project_id,
                *normalized,
            ),
        )

        result: dict[str, TargetExperience] = {}

        for row in rows:
            attempts = int(
                row["attempts"] or 0
            )

            successes = int(
                row["successes"] or 0
            )

            average_delta = (
                float(
                    row["total_score_delta"]
                    or 0.0
                )
                / attempts
                if attempts
                else 0.0
            )

            success_rate = (
                successes / attempts
                if attempts
                else 0.0
            )

            effectiveness = (
                success_rate
                + max(
                    -0.5,
                    min(
                        0.5,
                        average_delta,
                    ),
                )
            )

            result[
                str(row["target"])
            ] = TargetExperience(
                target=str(
                    row["target"]
                ),
                attempts=attempts,
                successes=successes,
                average_score_delta=round(
                    average_delta,
                    6,
                ),
                effectiveness=round(
                    effectiveness,
                    6,
                ),
            )

        return result

    # PATCH 6B2 ? CONTEXT-WEIGHTED GLOBAL EXPERIENCE
    #
    # Cross-project learning is transferable only when historical evidence
    # has enough contextual information and is sufficiently similar to the
    # current rework context.
    #
    # This layer is advisory only:
    #   - it cannot add policy targets;
    #   - it cannot bypass QualityGate;
    #   - it cannot change stage order;
    #   - it cannot rewrite DirectorPolicy;
    #   - it does not write synthetic GLOBAL experience rows.
    #
    # Context sufficiency contract:
    #   primary dimensions:
    #       failure_domain
    #       target
    #       issue_codes
    #
    #   minimum context:
    #       >= 2 observable primary dimensions
    #       AND evidence coverage >= 0.50
    #
    #   transfer eligibility:
    #       sufficient context
    #       AND adjusted similarity >= 0.60
    #
    # Missing context reduces confidence and never increases similarity.

    @staticmethod
    def _normalize_context_value(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()

        if not normalized:
            return None

        return normalized.lower()

    @staticmethod
    def _normalize_issue_codes(
        value: Any,
    ) -> tuple[str, ...]:
        if value is None:
            return ()

        if isinstance(value, str):
            raw_items = (value,)

        else:
            try:
                raw_items = tuple(value)
            except TypeError:
                raw_items = (value,)

        normalized = tuple(
            sorted(
                {
                    str(item).strip().lower()
                    for item in raw_items
                    if str(item).strip()
                }
            )
        )

        return normalized

    @classmethod
    def _learning_context(
        cls,
        *,
        target: str | None = None,
        issue_codes: Any = (),
        runtime_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = dict(
            runtime_metadata
            or {}
        )

        nested_context = metadata.get(
            "learning_context"
        )

        if isinstance(
            nested_context,
            Mapping,
        ):
            context_source = dict(
                nested_context
            )
        else:
            context_source = {}

        def pick(
            key: str,
        ) -> Any:
            if key in context_source:
                return context_source.get(
                    key
                )

            return metadata.get(
                key
            )

        resolved_issue_codes = (
            cls._normalize_issue_codes(
                issue_codes
            )
        )

        if not resolved_issue_codes:
            resolved_issue_codes = (
                cls._normalize_issue_codes(
                    pick(
                        "issue_codes"
                    )
                )
            )

        return {
            "project_type":
                cls._normalize_context_value(
                    pick(
                        "project_type"
                    )
                ),

            "objective":
                cls._normalize_context_value(
                    pick(
                        "objective"
                    )
                ),

            "failure_domain":
                cls._normalize_context_value(
                    pick(
                        "failure_domain"
                    )
                ),

            "target":
                cls._normalize_context_value(
                    target
                    or pick(
                        "target"
                    )
                ),

            "source":
                cls._normalize_context_value(
                    pick(
                        "source"
                    )
                ),

            "issue_codes":
                resolved_issue_codes,
        }

    @classmethod
    def _context_similarity(
        cls,
        current_context: Mapping[str, Any],
        historical_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        weights = {
            "project_type": 1.0,
            "objective": 0.5,
            "failure_domain": 3.0,
            "target": 3.0,
            "source": 0.5,
            "issue_codes": 2.0,
        }

        total_possible_weight = sum(
            weights.values()
        )

        earned_weight = 0.0
        observed_weight = 0.0

        details: dict[str, Any] = {}

        for key in (
            "project_type",
            "objective",
            "failure_domain",
            "target",
            "source",
        ):
            current_value = (
                current_context.get(
                    key
                )
            )

            historical_value = (
                historical_context.get(
                    key
                )
            )

            weight = weights[key]

            if (
                current_value is None
                or historical_value is None
            ):
                details[key] = {
                    "state": "UNKNOWN",
                    "earned": 0.0,
                    "observed": 0.0,
                }

                continue

            observed_weight += weight

            if (
                current_value
                == historical_value
            ):
                earned_weight += weight

                details[key] = {
                    "state": "MATCH",
                    "earned": weight,
                    "observed": weight,
                }

            else:
                details[key] = {
                    "state": "MISMATCH",
                    "earned": 0.0,
                    "observed": weight,
                }

        current_issues = set(
            cls._normalize_issue_codes(
                current_context.get(
                    "issue_codes"
                )
            )
        )

        historical_issues = set(
            cls._normalize_issue_codes(
                historical_context.get(
                    "issue_codes"
                )
            )
        )

        issue_weight = weights[
            "issue_codes"
        ]

        if (
            current_issues
            and historical_issues
        ):
            observed_weight += (
                issue_weight
            )

            union = (
                current_issues
                | historical_issues
            )

            intersection = (
                current_issues
                & historical_issues
            )

            jaccard = (
                len(intersection)
                / len(union)
                if union
                else 0.0
            )

            issue_earned = (
                issue_weight
                * jaccard
            )

            earned_weight += (
                issue_earned
            )

            details[
                "issue_codes"
            ] = {
                "state": "COMPARED",
                "earned": round(
                    issue_earned,
                    6,
                ),
                "observed": issue_weight,
                "jaccard": round(
                    jaccard,
                    6,
                ),
            }

        else:
            details[
                "issue_codes"
            ] = {
                "state": "UNKNOWN",
                "earned": 0.0,
                "observed": 0.0,
                "jaccard": None,
            }

        raw_similarity = (
            earned_weight
            / observed_weight
            if observed_weight
            else 0.0
        )

        evidence_coverage = (
            observed_weight
            / total_possible_weight
            if total_possible_weight
            else 0.0
        )

        adjusted_similarity = (
            raw_similarity
            * evidence_coverage
        )

        primary_available = {
            "failure_domain":
                (
                    current_context.get(
                        "failure_domain"
                    )
                    is not None
                    and historical_context.get(
                        "failure_domain"
                    )
                    is not None
                ),

            "target":
                (
                    current_context.get(
                        "target"
                    )
                    is not None
                    and historical_context.get(
                        "target"
                    )
                    is not None
                ),

            "issue_codes":
                bool(
                    current_issues
                    and historical_issues
                ),
        }

        primary_count = sum(
            1
            for state
            in primary_available.values()
            if state
        )

        sufficient_context = (
            primary_count >= 2
            and evidence_coverage >= 0.50
        )

        # PATCH 6B2.1 ? HARD FAILURE-DOMAIN COMPATIBILITY GATE
        #
        # failure_domain is a semantic applicability boundary, not merely
        # another weighted feature.
        #
        # If both the current and historical learning records explicitly
        # identify a failure domain and those domains differ, the historical
        # evidence is NOT transferable ? even when project type, objective,
        # target, source or issue codes happen to match.
        #
        # Missing failure-domain information still degrades through the
        # existing evidence-coverage contract; it does not hard-block
        # transfer. Only an explicit known mismatch is blocked.

        current_failure_domain = (
            current_context.get(
                "failure_domain"
            )
        )

        historical_failure_domain = (
            historical_context.get(
                "failure_domain"
            )
        )

        failure_domain_compatible = not (
            current_failure_domain is not None
            and historical_failure_domain is not None
            and current_failure_domain
                != historical_failure_domain
        )

        transfer_eligible = (
            sufficient_context
            and failure_domain_compatible
            and adjusted_similarity >= 0.60
        )

        return {
            "raw_similarity":
                round(
                    raw_similarity,
                    6,
                ),

            "evidence_coverage":
                round(
                    evidence_coverage,
                    6,
                ),

            "adjusted_similarity":
                round(
                    adjusted_similarity,
                    6,
                ),

            "earned_weight":
                round(
                    earned_weight,
                    6,
                ),

            "observed_weight":
                round(
                    observed_weight,
                    6,
                ),

            "total_possible_weight":
                round(
                    total_possible_weight,
                    6,
                ),

            "primary_available":
                primary_available,

            "primary_count":
                primary_count,

            "sufficient_context":
                sufficient_context,

            "failure_domain_compatible":
                failure_domain_compatible,

            "transfer_eligible":
                transfer_eligible,

            "details":
                details,
        }

    def _historical_learning_cycles(
        self,
        *,
        project_id: str,
    ) -> list[dict[str, Any]]:
        rows = self.db.rows(
            """
            SELECT
                id,
                project_id,
                cycle,
                score_before,
                score_after,
                score_delta,
                targets_json,
                issue_codes_json,
                outcome,
                runtime_metadata_json
            FROM director_learning_cycles
            WHERE
                project_id<>?
                AND outcome<>'pending'
                AND score_after IS NOT NULL
                AND score_delta IS NOT NULL
            ORDER BY id ASC
            """,
            (
                project_id,
            ),
        )

        result: list[
            dict[str, Any]
        ] = []

        for row in rows:
            try:
                targets = tuple(
                    json.loads(
                        row[
                            "targets_json"
                        ]
                        or "[]"
                    )
                )
            except Exception:
                targets = ()

            try:
                issue_codes = tuple(
                    json.loads(
                        row[
                            "issue_codes_json"
                        ]
                        or "[]"
                    )
                )
            except Exception:
                issue_codes = ()

            try:
                metadata = dict(
                    json.loads(
                        row[
                            "runtime_metadata_json"
                        ]
                        or "{}"
                    )
                )
            except Exception:
                metadata = {}

            result.append(
                {
                    "id":
                        int(
                            row["id"]
                        ),

                    "project_id":
                        str(
                            row[
                                "project_id"
                            ]
                        ),

                    "cycle":
                        int(
                            row[
                                "cycle"
                            ]
                        ),

                    "score_before":
                        float(
                            row[
                                "score_before"
                            ]
                        ),

                    "score_after":
                        float(
                            row[
                                "score_after"
                            ]
                        ),

                    "score_delta":
                        float(
                            row[
                                "score_delta"
                            ]
                        ),

                    "targets":
                        tuple(
                            str(target)
                            for target
                            in targets
                            if str(target)
                        ),

                    "issue_codes":
                        tuple(
                            str(code)
                            for code
                            in issue_codes
                            if str(code)
                        ),

                    "outcome":
                        str(
                            row[
                                "outcome"
                            ]
                        ),

                    "runtime_metadata":
                        metadata,
                }
            )

        return result

    def global_target_experience(
        self,
        *,
        project_id: str,
        targets: Iterable[str],
        runtime_metadata: Mapping[str, Any] | None = None,
        issue_codes: Iterable[str] = (),
    ) -> dict[str, TargetExperience]:
        """
        Return context-weighted transferable experience from OTHER projects.

        Historical cycles are eligible only when the current context and
        historical context satisfy the PATCH 6B1.1 sufficiency contract.

        Similarity is used as evidence weight. Wrong-domain or context-poor
        evidence therefore cannot create a transferable global prior.
        """
        normalized = tuple(
            dict.fromkeys(
                str(item)
                for item in targets
                if str(item)
            )
        )

        if not normalized:
            return {}

        historical_cycles = (
            self._historical_learning_cycles(
                project_id=project_id,
            )
        )

        result: dict[
            str,
            TargetExperience,
        ] = {}

        for target in normalized:
            current_context = (
                self._learning_context(
                    target=target,
                    issue_codes=issue_codes,
                    runtime_metadata=(
                        runtime_metadata
                    ),
                )
            )

            weighted_attempts = 0.0
            weighted_successes = 0.0
            weighted_delta = 0.0

            for cycle in historical_cycles:
                if target not in cycle[
                    "targets"
                ]:
                    continue

                historical_context = (
                    self._learning_context(
                        target=target,
                        issue_codes=cycle[
                            "issue_codes"
                        ],
                        runtime_metadata=cycle[
                            "runtime_metadata"
                        ],
                    )
                )

                similarity = (
                    self._context_similarity(
                        current_context,
                        historical_context,
                    )
                )

                if not similarity[
                    "transfer_eligible"
                ]:
                    continue

                evidence_weight = float(
                    similarity[
                        "adjusted_similarity"
                    ]
                )

                if evidence_weight <= 0.0:
                    continue

                weighted_attempts += (
                    evidence_weight
                )

                if (
                    cycle["outcome"]
                    == "improved"
                ):
                    weighted_successes += (
                        evidence_weight
                    )

                weighted_delta += (
                    float(
                        cycle[
                            "score_delta"
                        ]
                    )
                    * evidence_weight
                )

            if weighted_attempts <= 0.0:
                continue

            success_rate = (
                weighted_successes
                / weighted_attempts
            )

            average_delta = (
                weighted_delta
                / weighted_attempts
            )

            effectiveness = (
                success_rate
                + max(
                    -0.5,
                    min(
                        0.5,
                        average_delta,
                    ),
                )
            )

            result[target] = (
                TargetExperience(
                    target=target,

                    attempts=int(
                        round(
                            weighted_attempts
                        )
                    ),

                    successes=int(
                        round(
                            weighted_successes
                        )
                    ),

                    average_score_delta=round(
                        average_delta,
                        6,
                    ),

                    effectiveness=round(
                        effectiveness,
                        6,
                    ),
                )
            )

        return result

    def blended_target_experience(
        self,
        *,
        project_id: str,
        targets: Iterable[str],
        global_prior_strength: float = 2.0,
        runtime_metadata: Mapping[str, Any] | None = None,
        issue_codes: Iterable[str] = (),
    ) -> dict[str, TargetExperience]:
        """
        Blend context-compatible cross-project prior with project-local
        experience.

        Local experience remains authoritative as project evidence grows.
        """
        normalized = tuple(
            dict.fromkeys(
                str(item)
                for item in targets
                if str(item)
            )
        )

        if not normalized:
            return {}

        local = self.target_experience(
            project_id,
            normalized,
        )

        global_experience = (
            self.global_target_experience(
                project_id=project_id,
                targets=normalized,
                runtime_metadata=(
                    runtime_metadata
                ),
                issue_codes=issue_codes,
            )
        )

        result: dict[
            str,
            TargetExperience,
        ] = {}

        prior_strength = max(
            0.0,
            float(
                global_prior_strength
            ),
        )

        for target in normalized:
            local_item = local.get(
                target
            )

            global_item = (
                global_experience.get(
                    target
                )
            )

            local_attempts = (
                local_item.attempts
                if local_item
                else 0
            )

            global_attempts = (
                global_item.attempts
                if global_item
                else 0
            )

            if (
                local_item is None
                and global_item is None
            ):
                continue

            if global_item is None:
                result[target] = (
                    local_item
                )
                continue

            if local_item is None:
                result[target] = (
                    TargetExperience(
                        target=target,
                        attempts=0,
                        successes=0,
                        average_score_delta=(
                            global_item
                            .average_score_delta
                        ),
                        effectiveness=(
                            global_item
                            .effectiveness
                        ),
                    )
                )
                continue

            effective_prior = min(
                prior_strength,
                float(
                    global_attempts
                ),
            )

            denominator = (
                float(
                    local_attempts
                )
                + effective_prior
            )

            if denominator <= 0.0:
                blended_effectiveness = (
                    local_item
                    .effectiveness
                )

                blended_delta = (
                    local_item
                    .average_score_delta
                )

            else:
                blended_effectiveness = (
                    (
                        local_item
                        .effectiveness
                        * float(
                            local_attempts
                        )
                    )
                    +
                    (
                        global_item
                        .effectiveness
                        * effective_prior
                    )
                ) / denominator

                blended_delta = (
                    (
                        local_item
                        .average_score_delta
                        * float(
                            local_attempts
                        )
                    )
                    +
                    (
                        global_item
                        .average_score_delta
                        * effective_prior
                    )
                ) / denominator

            result[target] = (
                TargetExperience(
                    target=target,
                    attempts=local_attempts,
                    successes=(
                        local_item
                        .successes
                    ),
                    average_score_delta=round(
                        blended_delta,
                        6,
                    ),
                    effectiveness=round(
                        blended_effectiveness,
                        6,
                    ),
                )
            )

        return result

    def rank_targets(
        self,
        *,
        project_id: str,
        targets: Iterable[str],
        runtime_metadata: Mapping[str, Any] | None = None,
        issue_codes: Iterable[str] = (),
    ) -> tuple[str, ...]:
        """
        Rank policy-approved targets using transferable experience plus
        project-local evidence.

        This method changes ordering only. It cannot add targets that were
        not supplied by the caller.
        """
        normalized = tuple(
            dict.fromkeys(
                str(item)
                for item in targets
                if str(item)
            )
        )

        experience = (
            self.blended_target_experience(
                project_id=project_id,
                targets=normalized,
                runtime_metadata=runtime_metadata,
                issue_codes=issue_codes,
            )
        )

        original_order = {
            target: index
            for index, target
            in enumerate(normalized)
        }

        default = TargetExperience(
            "",
            0,
            0,
            0.0,
            0.0,
        )

        return tuple(
            sorted(
                normalized,
                key=lambda target: (
                    -experience.get(
                        target,
                        default,
                    ).effectiveness,
                    original_order[target],
                ),
            )
        )
