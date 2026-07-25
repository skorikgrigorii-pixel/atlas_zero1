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
        normalized = tuple(
            dict.fromkeys(str(item) for item in targets if str(item))
        )
        if not normalized:
            return {}

        placeholders = ",".join("?" for _ in normalized)
        rows = self.db.rows(
            f"""
            SELECT target, attempts, successes, total_score_delta
            FROM director_target_experience
            WHERE project_id=? AND target IN ({placeholders})
            """,
            (project_id, *normalized),
        )

        result: dict[str, TargetExperience] = {}
        for row in rows:
            attempts = int(row["attempts"] or 0)
            successes = int(row["successes"] or 0)
            average_delta = (
                float(row["total_score_delta"] or 0.0) / attempts
                if attempts
                else 0.0
            )
            success_rate = successes / attempts if attempts else 0.0
            effectiveness = success_rate + max(-0.5, min(0.5, average_delta))
            result[str(row["target"])] = TargetExperience(
                target=str(row["target"]),
                attempts=attempts,
                successes=successes,
                average_score_delta=round(average_delta, 6),
                effectiveness=round(effectiveness, 6),
            )
        return result

    def rank_targets(
        self,
        *,
        project_id: str,
        targets: Iterable[str],
    ) -> tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(str(item) for item in targets if str(item))
        )
        experience = self.target_experience(project_id, normalized)
        original_order = {
            target: index for index, target in enumerate(normalized)
        }
        default = TargetExperience("", 0, 0, 0.0, 0.0)
        return tuple(
            sorted(
                normalized,
                key=lambda target: (
                    -experience.get(target, default).effectiveness,
                    original_order[target],
                ),
            )
        )
