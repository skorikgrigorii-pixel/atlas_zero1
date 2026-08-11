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
