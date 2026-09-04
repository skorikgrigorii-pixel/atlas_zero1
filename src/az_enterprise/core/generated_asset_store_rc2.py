from __future__ import annotations

import json
import uuid
from typing import Any

from .database import Database


BATCH_STATUSES = {
    "CREATED",
    "SUBMITTED",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}

CANDIDATE_STATUSES = {
    "DISCOVERED",
    "DOWNLOADED",
    "TECHNICALLY_VALID",
    "REVIEWED",
    "PROVISIONAL",
    "ACCEPTED",
    "REJECTED",
    "REGISTERED",
}


class GeneratedAssetStoreRC2:
    """Canonical persistence for generated visual candidates.

    Generated candidates remain isolated from the main assets table
    until one candidate has passed acceptance and is registered.
    """

    def __init__(
        self,
        db: Database,
        project_id: str,
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS generation_batches(
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                task_uid TEXT NOT NULL,
                shot_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                generation_id TEXT,
                attempt INTEGER NOT NULL DEFAULT 1,
                prompt TEXT NOT NULL,
                negative_prompt TEXT,
                candidate_count INTEGER NOT NULL DEFAULT 4,
                status TEXT NOT NULL DEFAULT 'CREATED',
                request_json TEXT,
                response_json TEXT,
                error TEXT,
                submitted_at TEXT,
                completed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    project_id,
                    task_uid,
                    provider,
                    attempt
                )
            )
            """
        )

        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS generated_asset_candidates(
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                task_uid TEXT NOT NULL,
                shot_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                generation_id TEXT,
                candidate_index INTEGER NOT NULL,
                remote_id TEXT,
                remote_url TEXT,
                local_path TEXT,
                status TEXT NOT NULL DEFAULT 'DISCOVERED',
                width INTEGER,
                height INTEGER,
                technical_score REAL,
                semantic_score REAL,
                temporal_score REAL,
                editorial_score REAL,
                final_score REAL,
                review_json TEXT,
                rejection_reason TEXT,
                selected_as_winner INTEGER NOT NULL DEFAULT 0,
                asset_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(batch_id)
                    REFERENCES generation_batches(id),
                UNIQUE(
                    batch_id,
                    candidate_index
                )
            )
            """
        )

        self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_generation_batches_task
            ON generation_batches(
                project_id,
                task_uid,
                status
            )
            """
        )

        self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_generated_candidates_shot
            ON generated_asset_candidates(
                project_id,
                shot_id,
                status
            )
            """
        )

    def create_batch(
        self,
        *,
        task_uid: str,
        shot_id: str,
        prompt: str,
        provider: str = "leonardo",
        attempt: int = 1,
        candidate_count: int = 4,
        negative_prompt: str | None = None,
    ) -> dict[str, Any]:
        if not task_uid.strip():
            raise ValueError("task_uid is required")

        if not shot_id.strip():
            raise ValueError(
                "shot_id is required for autonomous generation"
            )

        if not prompt.strip():
            raise ValueError("prompt is required")

        if attempt < 1:
            raise ValueError("attempt must be >= 1")

        if candidate_count < 2:
            raise ValueError(
                "candidate_count must be >= 2 "
                "to allow candidate comparison"
            )

        existing = self.db.one(
            """
            SELECT *
            FROM generation_batches
            WHERE project_id=?
              AND task_uid=?
              AND provider=?
              AND attempt=?
            """,
            (
                self.project_id,
                task_uid,
                provider,
                attempt,
            ),
        )

        if existing is not None:
            return dict(existing)

        batch_id = uuid.uuid4().hex

        self.db.execute(
            """
            INSERT INTO generation_batches(
                id,
                project_id,
                task_uid,
                shot_id,
                provider,
                attempt,
                prompt,
                negative_prompt,
                candidate_count,
                status
            )
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                batch_id,
                self.project_id,
                task_uid,
                shot_id,
                provider,
                attempt,
                prompt,
                negative_prompt,
                candidate_count,
                "CREATED",
            ),
        )

        return dict(
            self.db.one(
                """
                SELECT *
                FROM generation_batches
                WHERE id=?
                """,
                (batch_id,),
            )
        )

    def update_batch(
        self,
        batch_id: str,
        *,
        status: str,
        generation_id: str | None = None,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if status not in BATCH_STATUSES:
            raise ValueError(
                f"Unsupported batch status: {status}"
            )

        self.db.execute(
            """
            UPDATE generation_batches
            SET status=?,
                generation_id=COALESCE(?, generation_id),
                request_json=COALESCE(?, request_json),
                response_json=COALESCE(?, response_json),
                error=?,
                submitted_at=CASE
                    WHEN ?='SUBMITTED'
                    THEN CURRENT_TIMESTAMP
                    ELSE submitted_at
                END,
                completed_at=CASE
                    WHEN ? IN (
                        'COMPLETED',
                        'FAILED',
                        'CANCELLED'
                    )
                    THEN CURRENT_TIMESTAMP
                    ELSE completed_at
                END,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
              AND project_id=?
            """,
            (
                status,
                generation_id,
                (
                    json.dumps(
                        request,
                        ensure_ascii=False,
                    )
                    if request is not None
                    else None
                ),
                (
                    json.dumps(
                        response,
                        ensure_ascii=False,
                    )
                    if response is not None
                    else None
                ),
                error,
                status,
                status,
                batch_id,
                self.project_id,
            ),
        )

        row = self.db.one(
            """
            SELECT *
            FROM generation_batches
            WHERE id=?
              AND project_id=?
            """,
            (batch_id, self.project_id),
        )

        if row is None:
            raise KeyError(
                f"Generation batch not found: {batch_id}"
            )

        return dict(row)

    def add_candidate(
        self,
        *,
        batch_id: str,
        candidate_index: int,
        remote_url: str | None = None,
        remote_id: str | None = None,
        local_path: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        batch = self.db.one(
            """
            SELECT *
            FROM generation_batches
            WHERE id=?
              AND project_id=?
            """,
            (batch_id, self.project_id),
        )

        if batch is None:
            raise KeyError(
                f"Generation batch not found: {batch_id}"
            )

        if candidate_index < 0:
            raise ValueError(
                "candidate_index must be >= 0"
            )

        existing = self.db.one(
            """
            SELECT *
            FROM generated_asset_candidates
            WHERE batch_id=?
              AND candidate_index=?
            """,
            (batch_id, candidate_index),
        )

        if existing is not None:
            return dict(existing)

        candidate_id = uuid.uuid4().hex

        status = (
            "DOWNLOADED"
            if local_path
            else "DISCOVERED"
        )

        self.db.execute(
            """
            INSERT INTO generated_asset_candidates(
                id,
                project_id,
                batch_id,
                task_uid,
                shot_id,
                provider,
                generation_id,
                candidate_index,
                remote_id,
                remote_url,
                local_path,
                status,
                width,
                height
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                candidate_id,
                self.project_id,
                batch_id,
                batch["task_uid"],
                batch["shot_id"],
                batch["provider"],
                batch["generation_id"],
                candidate_index,
                remote_id,
                remote_url,
                local_path,
                status,
                width,
                height,
            ),
        )

        return dict(
            self.db.one(
                """
                SELECT *
                FROM generated_asset_candidates
                WHERE id=?
                """,
                (candidate_id,),
            )
        )

    def record_review(
        self,
        candidate_id: str,
        *,
        status: str,
        technical_score: float | None = None,
        semantic_score: float | None = None,
        temporal_score: float | None = None,
        editorial_score: float | None = None,
        final_score: float | None = None,
        review: dict[str, Any] | None = None,
        rejection_reason: str | None = None,
    ) -> dict[str, Any]:
        if status not in CANDIDATE_STATUSES:
            raise ValueError(
                f"Unsupported candidate status: {status}"
            )

        self.db.execute(
            """
            UPDATE generated_asset_candidates
            SET status=?,
                technical_score=?,
                semantic_score=?,
                temporal_score=?,
                editorial_score=?,
                final_score=?,
                review_json=?,
                rejection_reason=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
              AND project_id=?
            """,
            (
                status,
                technical_score,
                semantic_score,
                temporal_score,
                editorial_score,
                final_score,
                (
                    json.dumps(
                        review,
                        ensure_ascii=False,
                    )
                    if review is not None
                    else None
                ),
                rejection_reason,
                candidate_id,
                self.project_id,
            ),
        )

        row = self.db.one(
            """
            SELECT *
            FROM generated_asset_candidates
            WHERE id=?
              AND project_id=?
            """,
            (candidate_id, self.project_id),
        )

        if row is None:
            raise KeyError(
                f"Candidate not found: {candidate_id}"
            )

        return dict(row)

    # ========================================================================
    # ATLAS_ZERO_CONTINUITY_WINNER_GATE_RC2
    # ========================================================================
    #
    # Final generated-asset continuity safety gate.
    #
    # temporal_score is produced by the canonical continuity layer and must
    # be present before a generated visual candidate can become a winner.
    #
    # Explicit continuity BLOCK violations always prevent acceptance.
    # ========================================================================

    @staticmethod
    def _continuity_score_is_valid(
        temporal_score: object,
    ) -> bool:

        if temporal_score is None:
            return False

        try:
            score = float(
                temporal_score
            )

        except (
            TypeError,
            ValueError,
        ):
            return False

        return (
            0.0
            <= score
            <= 1.0
        )


    @staticmethod
    def _continuity_review_is_compatible(
        review_json: object,
    ) -> bool:

        if review_json is None:
            return True


        if isinstance(
            review_json,
            str,
        ):

            if not review_json.strip():
                return True

            try:

                payload = json.loads(
                    review_json
                )

            except Exception:
                return True


        elif isinstance(
            review_json,
            dict,
        ):

            payload = review_json

        else:

            return True


        if not isinstance(
            payload,
            dict,
        ):

            return True


        possible_sections = [
            payload
        ]


        for key in (
            "continuity",
            "continuity_evaluation",
            "visual_continuity",
        ):

            section = payload.get(
                key
            )

            if isinstance(
                section,
                dict,
            ):

                possible_sections.append(
                    section
                )


        for section in (
            possible_sections
        ):

            if (
                "compatible"
                in section
                and
                section.get(
                    "compatible"
                )
                is False
            ):

                return False


            violations = section.get(
                "violations",
                [],
            )


            if isinstance(
                violations,
                list,
            ):

                for violation in (
                    violations
                ):

                    if not isinstance(
                        violation,
                        dict,
                    ):

                        continue


                    severity = str(
                        violation.get(
                            "severity",
                            "",
                        )
                    ).strip().upper()


                    if severity == "BLOCK":

                        return False


        return True


    def _require_candidate_continuity(
        self,
        candidate: object,
    ) -> None:

        temporal_score = (
            candidate[
                "temporal_score"
            ]
        )


        if not self._continuity_score_is_valid(
            temporal_score
        ):

            raise RuntimeError(
                "VISUAL_CONTINUITY_BLOCKED: "
                "generated candidate has no valid "
                "temporal_score"
            )


        review_json = (
            candidate[
                "review_json"
            ]
        )


        if not self._continuity_review_is_compatible(
            review_json
        ):

            raise RuntimeError(
                "VISUAL_CONTINUITY_BLOCKED: "
                "generated candidate contains "
                "continuity incompatibility"
            )


    def select_winner(
        self,
        *,
        batch_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        candidate = self.db.one(
            """
            SELECT *
            FROM generated_asset_candidates
            WHERE id=?
              AND batch_id=?
              AND project_id=?
            """,
            (
                candidate_id,
                batch_id,
                self.project_id,
            ),
        )

        if candidate is None:
            raise KeyError(
                "Candidate does not belong to this batch"
            )

        if candidate["status"] not in {
            "REVIEWED",
            "PROVISIONAL",
            "ACCEPTED",
        }:
            raise RuntimeError(
                "Candidate must pass review "
                "before winner selection"
            )


        # ------------------------------------------------------------
        # Canonical continuity winner gate.
        #
        # Must execute before selected_as_winner / ACCEPTED mutation.
        # ------------------------------------------------------------

        self._require_candidate_continuity(
            candidate
        )

        self.db.execute(
            """
            UPDATE generated_asset_candidates
            SET selected_as_winner=0,
                updated_at=CURRENT_TIMESTAMP
            WHERE batch_id=?
              AND project_id=?
            """,
            (batch_id, self.project_id),
        )

        self.db.execute(
            """
            UPDATE generated_asset_candidates
            SET selected_as_winner=1,
                status='ACCEPTED',
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
              AND batch_id=?
              AND project_id=?
            """,
            (
                candidate_id,
                batch_id,
                self.project_id,
            ),
        )

        self.db.execute(
            """
            UPDATE generated_asset_candidates
            SET status='REJECTED',
                rejection_reason=COALESCE(
                    rejection_reason,
                    'Lower ranked than selected winner'
                ),
                updated_at=CURRENT_TIMESTAMP
            WHERE batch_id=?
              AND project_id=?
              AND id<>?
              AND status NOT IN (
                  'REGISTERED',
                  'REJECTED'
              )
            """,
            (
                batch_id,
                self.project_id,
                candidate_id,
            ),
        )

        return dict(
            self.db.one(
                """
                SELECT *
                FROM generated_asset_candidates
                WHERE id=?
                """,
                (candidate_id,),
            )
        )

    def list_candidates(
        self,
        batch_id: str,
    ) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.db.rows(
                """
                SELECT *
                FROM generated_asset_candidates
                WHERE batch_id=?
                  AND project_id=?
                ORDER BY candidate_index
                """,
                (batch_id, self.project_id),
            )
        ]

    def batch_summary(
        self,
        batch_id: str,
    ) -> dict[str, Any]:
        batch = self.db.one(
            """
            SELECT *
            FROM generation_batches
            WHERE id=?
              AND project_id=?
            """,
            (batch_id, self.project_id),
        )

        if batch is None:
            raise KeyError(
                f"Generation batch not found: {batch_id}"
            )

        candidates = self.list_candidates(batch_id)

        return {
            "batch": dict(batch),
            "candidate_count": len(candidates),
            "accepted": sum(
                1
                for row in candidates
                if row["selected_as_winner"] == 1
            ),
            "rejected": sum(
                1
                for row in candidates
                if row["status"] == "REJECTED"
            ),
            "candidates": candidates,
        }
