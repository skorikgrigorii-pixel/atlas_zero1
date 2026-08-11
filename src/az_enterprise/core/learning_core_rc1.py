from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


class LearningCoreRC1:
    """
    ATLAS ZERO — Learning Core RC1.

    Learning is evidence-driven and non-destructive.

    The module:
    - records observations;
    - builds reusable learning profiles;
    - updates confidence from repeated evidence;
    - derives performance lessons from analytics.

    It NEVER:
    - rewrites source code;
    - changes Director AI policy directly;
    - bypasses quality gates;
    - overwrites production artifacts.
    """

    def __init__(
        self,
        db: Any,
        project_id: str,
    ) -> None:
        self.db = db
        self.project_id = str(project_id).strip()

        if not self.project_id:
            raise ValueError("project_id is required")

        self.ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        self.db.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS learning_observations(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS learning_profiles(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,

                UNIQUE(project_id, scope, key)
            );

            CREATE INDEX IF NOT EXISTS
                idx_learning_observations_project
            ON learning_observations(
                project_id,
                scope,
                key
            );
            """
        )

        self.db.conn.commit()

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def record_observation(
        self,
        *,
        scope: str,
        key: str,
        value: Any,
        confidence: float,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        scope = str(scope).strip()
        key = str(key).strip()

        if not scope:
            raise ValueError("scope is required")

        if not key:
            raise ValueError("key is required")

        confidence = self._confidence(confidence)
        now = self._now()

        cursor = self.db.conn.execute(
            """
            INSERT INTO learning_observations(
                project_id,
                scope,
                key,
                value_json,
                confidence,
                evidence_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.project_id,
                scope,
                key,
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                confidence,
                (
                    json.dumps(
                        evidence,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    if evidence is not None
                    else None
                ),
                now,
            ),
        )

        self.db.conn.commit()

        self._update_profile(
            scope=scope,
            key=key,
            value=value,
            confidence=confidence,
        )

        return {
            "state": "LEARNING_OBSERVATION_RECORDED",
            "observation_id": cursor.lastrowid,
            "project_id": self.project_id,
            "scope": scope,
            "key": key,
            "confidence": confidence,
        }

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def profile(
        self,
        *,
        scope: str,
        key: str,
    ) -> dict[str, Any] | None:

        row = self.db.conn.execute(
            """
            SELECT
                value_json,
                confidence,
                evidence_count,
                updated_at
            FROM learning_profiles
            WHERE project_id=?
              AND scope=?
              AND key=?
            """,
            (
                self.project_id,
                str(scope).strip(),
                str(key).strip(),
            ),
        ).fetchone()

        if row is None:
            return None

        return {
            "project_id": self.project_id,
            "scope": str(scope).strip(),
            "key": str(key).strip(),
            "value": json.loads(row[0]),
            "confidence": float(row[1]),
            "evidence_count": int(row[2]),
            "updated_at": row[3],
        }

    def profiles(
        self,
        *,
        minimum_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:

        rows = self.db.conn.execute(
            """
            SELECT
                scope,
                key,
                value_json,
                confidence,
                evidence_count,
                updated_at
            FROM learning_profiles
            WHERE project_id=?
              AND confidence >= ?
            ORDER BY confidence DESC,
                     evidence_count DESC,
                     scope,
                     key
            """,
            (
                self.project_id,
                float(minimum_confidence),
            ),
        ).fetchall()

        return [
            {
                "project_id": self.project_id,
                "scope": row[0],
                "key": row[1],
                "value": json.loads(row[2]),
                "confidence": float(row[3]),
                "evidence_count": int(row[4]),
                "updated_at": row[5],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Analytics learning
    # ------------------------------------------------------------------

    def learn_from_performance(
        self,
        performance: dict[str, Any],
    ) -> dict[str, Any]:

        if (
            performance.get("state")
            != "PERFORMANCE_SUMMARY_READY"
        ):
            return {
                "state": "LEARNING_SKIPPED",
                "reason": "performance summary unavailable",
            }

        platform = str(
            performance.get("platform", "unknown")
        )

        latest = performance.get("latest") or {}
        deltas = performance.get("deltas") or {}

        created = []

        engagement_rate = float(
            performance.get("engagement_rate") or 0.0
        )

        created.append(
            self.record_observation(
                scope=f"platform:{platform}",
                key="engagement_rate",
                value=engagement_rate,
                confidence=0.65,
                evidence={
                    "source":
                        "marketing_performance_summary",
                    "snapshot_id":
                        latest.get("id"),
                },
            )
        )

        if latest.get("ctr") is not None:
            created.append(
                self.record_observation(
                    scope=f"platform:{platform}",
                    key="ctr",
                    value=float(latest["ctr"]),
                    confidence=0.70,
                    evidence={
                        "source":
                            "marketing_performance_summary",
                        "snapshot_id":
                            latest.get("id"),
                    },
                )
            )

        if "views" in deltas:
            created.append(
                self.record_observation(
                    scope=f"platform:{platform}",
                    key="view_growth",
                    value=float(
                        deltas.get("views") or 0.0
                    ),
                    confidence=0.60,
                    evidence={
                        "source":
                            "marketing_performance_summary",
                        "snapshot_id":
                            latest.get("id"),
                    },
                )
            )

        return {
            "state": "LEARNING_UPDATED",
            "project_id": self.project_id,
            "platform": platform,
            "observations": len(created),
        }

    # ------------------------------------------------------------------
    # Internal profile update
    # ------------------------------------------------------------------

    def _update_profile(
        self,
        *,
        scope: str,
        key: str,
        value: Any,
        confidence: float,
    ) -> None:

        existing = self.profile(
            scope=scope,
            key=key,
        )

        now = self._now()

        if existing is None:
            self.db.conn.execute(
                """
                INSERT INTO learning_profiles(
                    project_id,
                    scope,
                    key,
                    value_json,
                    confidence,
                    evidence_count,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    self.project_id,
                    scope,
                    key,
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    confidence,
                    now,
                ),
            )

        else:
            old_count = int(
                existing["evidence_count"]
            )

            old_confidence = float(
                existing["confidence"]
            )

            new_count = old_count + 1

            combined_confidence = min(
                1.0,
                (
                    old_confidence * old_count
                    + confidence
                )
                / new_count,
            )

            self.db.conn.execute(
                """
                UPDATE learning_profiles
                SET
                    value_json=?,
                    confidence=?,
                    evidence_count=?,
                    updated_at=?
                WHERE project_id=?
                  AND scope=?
                  AND key=?
                """,
                (
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    combined_confidence,
                    new_count,
                    now,
                    self.project_id,
                    scope,
                    key,
                ),
            )

        self.db.conn.commit()

    @staticmethod
    def _confidence(value: float) -> float:
        value = float(value)

        if value < 0 or value > 1:
            raise ValueError(
                "confidence must be between 0 and 1"
            )

        return value

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()
