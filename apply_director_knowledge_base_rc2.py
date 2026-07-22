from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ROOT / "src" / "az_enterprise" / "core"
TESTS = ROOT / "tests"

KB_PATH = CORE / "director_knowledge_base_rc2.py"
EVALUATOR_PATH = CORE / "director_policy_evaluator_alpha293.py"
TEST_PATH = TESTS / "test_director_knowledge_base_rc2.py"

KB_CONTENT = r'''"""Persistent learning memory for Director decisions in RC2.

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
'''

EVALUATOR_CONTENT = r'''"""Policy-aware decision evaluator for Director Supervisor Alpha 2.9.3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from az_enterprise.core.database import Database
from az_enterprise.core.director_knowledge_base_rc2 import DirectorKnowledgeBaseRC2
from az_enterprise.core.director_policy_alpha293 import (
    DirectorPolicy,
    DirectorPolicyEvaluator,
)
from az_enterprise.core.director_supervisor_alpha292 import (
    DecisionStatus,
    DirectorAction,
    DirectorDecision,
)


@dataclass(frozen=True)
class RuntimeReport:
    metrics: Mapping[str, float]
    project_facts: Mapping[str, Any]
    recommended_targets: tuple[str, ...] = ()
    metadata: Mapping[str, Any] | None = None


class PolicyDecisionEvaluator:
    """Convert runtime reports into policy-safe, experience-aware decisions.

    DirectorPolicy remains the hard authority. Historical experience can only
    reorder targets that the policy has already allowed.
    """

    def __init__(
        self,
        policy: DirectorPolicy,
        *,
        knowledge_base: DirectorKnowledgeBaseRC2 | None = None,
    ) -> None:
        self._policy = policy
        self._evaluator = DirectorPolicyEvaluator()
        self._knowledge = knowledge_base or DirectorKnowledgeBaseRC2(
            self._create_default_database()
        )
        self._pending_cycle_id: int | None = None
        self._pending_project_id: str | None = None

    @staticmethod
    def _create_default_database() -> Database:
        db = Database()
        db.init()
        return db

    def __call__(self, runtime_result: Any, cycle: int) -> DirectorDecision:
        report = self._coerce_report(runtime_result)
        evaluation = self._evaluator.evaluate(
            self._policy,
            report.metrics,
            report.project_facts,
        )

        project_id = str(
            report.project_facts.get("project_id") or "unknown-project"
        )
        learning_feedback = self._complete_previous_cycle(
            project_id=project_id,
            score_after=evaluation.score,
        )

        if evaluation.constraint_violations:
            return DirectorDecision(
                status=DecisionStatus.REJECT,
                reason=(
                    "Mandatory constraints failed: "
                    + "; ".join(evaluation.constraint_violations)
                ),
                confidence=1.0,
                metadata={
                    "score": evaluation.score,
                    "cycle": cycle,
                    "violations": evaluation.constraint_violations,
                    "learning_feedback": learning_feedback,
                },
            )

        profile = self._policy.quality_profile

        if evaluation.score >= profile.release_threshold:
            return DirectorDecision(
                status=DecisionStatus.APPROVE,
                reason=(
                    f"Project score {evaluation.score:.3f} reached "
                    f"release threshold {profile.release_threshold:.3f}"
                ),
                confidence=evaluation.score,
                metadata={
                    "score": evaluation.score,
                    "cycle": cycle,
                    "learning_feedback": learning_feedback,
                },
            )

        if evaluation.score >= profile.rework_threshold:
            allowed_targets = self._policy.validate_rework_targets(
                report.recommended_targets
            )
            if not allowed_targets:
                return DirectorDecision(
                    status=DecisionStatus.ESCALATE,
                    reason=(
                        "Project requires rework, but no valid rework targets "
                        "were provided"
                    ),
                    confidence=1.0 - evaluation.score,
                    metadata={
                        "score": evaluation.score,
                        "cycle": cycle,
                        "learning_feedback": learning_feedback,
                    },
                )

            ranked_targets = self._knowledge.rank_targets(
                project_id=project_id,
                targets=allowed_targets,
            )
            experience = self._knowledge.target_experience(
                project_id,
                ranked_targets,
            )
            issue_codes = self._issue_codes(report)
            self._pending_cycle_id = self._knowledge.begin_cycle(
                project_id=project_id,
                cycle=cycle,
                score_before=evaluation.score,
                targets=ranked_targets,
                issue_codes=issue_codes,
                runtime_metadata=report.metadata,
            )
            self._pending_project_id = project_id

            return DirectorDecision(
                status=DecisionStatus.REWORK,
                reason=(
                    f"Project score {evaluation.score:.3f} is below "
                    f"release threshold {profile.release_threshold:.3f}"
                ),
                confidence=max(evaluation.score, 0.5),
                actions=tuple(
                    DirectorAction(
                        target=target,
                        reason=(
                            "Policy allowed; ordered using accumulated "
                            "Director experience"
                        ),
                    )
                    for target in ranked_targets
                ),
                metadata={
                    "score": evaluation.score,
                    "cycle": cycle,
                    "learning_cycle_id": self._pending_cycle_id,
                    "learning_feedback": learning_feedback,
                    "target_experience": {
                        target: {
                            "attempts": item.attempts,
                            "successes": item.successes,
                            "average_score_delta": item.average_score_delta,
                            "effectiveness": item.effectiveness,
                        }
                        for target, item in experience.items()
                    },
                },
            )

        return DirectorDecision(
            status=DecisionStatus.REJECT,
            reason=(
                f"Project score {evaluation.score:.3f} is below "
                f"minimum rework threshold {profile.rework_threshold:.3f}"
            ),
            confidence=1.0 - evaluation.score,
            metadata={
                "score": evaluation.score,
                "cycle": cycle,
                "learning_feedback": learning_feedback,
            },
        )

    def _complete_previous_cycle(
        self,
        *,
        project_id: str,
        score_after: float,
    ) -> Mapping[str, Any] | None:
        if self._pending_cycle_id is None:
            return None
        if self._pending_project_id != project_id:
            return {
                "state": "IGNORED",
                "reason": "project_changed",
                "pending_project_id": self._pending_project_id,
                "current_project_id": project_id,
            }

        feedback = self._knowledge.complete_cycle(
            cycle_id=self._pending_cycle_id,
            score_after=score_after,
        )
        self._pending_cycle_id = None
        self._pending_project_id = None
        return feedback

    @staticmethod
    def _issue_codes(report: RuntimeReport) -> tuple[str, ...]:
        metadata = report.metadata or {}
        values = metadata.get("issue_codes", ())
        return tuple(sorted({str(item) for item in values if str(item)}))

    @staticmethod
    def _coerce_report(runtime_result: Any) -> RuntimeReport:
        if isinstance(runtime_result, RuntimeReport):
            return runtime_result

        if isinstance(runtime_result, Mapping):
            return RuntimeReport(
                metrics=runtime_result.get("metrics", {}),
                project_facts=runtime_result.get("project_facts", {}),
                recommended_targets=tuple(
                    runtime_result.get("recommended_targets", ())
                ),
                metadata=runtime_result.get("metadata"),
            )

        raise TypeError(
            "runtime result must be RuntimeReport or mapping"
        )
'''

TEST_CONTENT = r'''from pathlib import Path

from az_enterprise.core.database import Database
from az_enterprise.core.director_knowledge_base_rc2 import DirectorKnowledgeBaseRC2


def test_knowledge_base_learns_target_effectiveness(tmp_path: Path) -> None:
    db = Database(tmp_path / "director_learning.sqlite3")
    db.init()
    knowledge = DirectorKnowledgeBaseRC2(db)

    cycle_id = knowledge.begin_cycle(
        project_id="demo",
        cycle=0,
        score_before=0.5,
        targets=("timeline", "assignment"),
        issue_codes=("LOW_VISUAL_DYNAMICS",),
    )
    result = knowledge.complete_cycle(
        cycle_id=cycle_id,
        score_after=0.8,
    )

    assert result["outcome"] == "improved"
    experience = knowledge.target_experience(
        "demo",
        ("timeline", "assignment"),
    )
    assert experience["timeline"].attempts == 1
    assert experience["timeline"].successes == 1
    assert experience["timeline"].average_score_delta == 0.3


def test_knowledge_base_ranks_effective_target_first(tmp_path: Path) -> None:
    db = Database(tmp_path / "director_learning.sqlite3")
    db.init()
    knowledge = DirectorKnowledgeBaseRC2(db)

    first = knowledge.begin_cycle(
        project_id="demo",
        cycle=0,
        score_before=0.5,
        targets=("timeline",),
    )
    knowledge.complete_cycle(cycle_id=first, score_after=0.8)

    second = knowledge.begin_cycle(
        project_id="demo",
        cycle=1,
        score_before=0.8,
        targets=("assignment",),
    )
    knowledge.complete_cycle(cycle_id=second, score_after=0.7)

    assert knowledge.rank_targets(
        project_id="demo",
        targets=("assignment", "timeline"),
    ) == ("timeline", "assignment")
'''


def backup(path: Path) -> None:
    if path.exists():
        backup_path = path.with_suffix(path.suffix + ".before_knowledge_base")
        shutil.copy2(path, backup_path)
        print(f"Backup: {backup_path}")


def main() -> None:
    if not CORE.exists():
        raise SystemExit(
            "Run this script from the ATLAS ZERO repository root."
        )

    backup(EVALUATOR_PATH)
    KB_PATH.write_text(KB_CONTENT, encoding="utf-8")
    EVALUATOR_PATH.write_text(EVALUATOR_CONTENT, encoding="utf-8")
    TESTS.mkdir(parents=True, exist_ok=True)
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("Director Knowledge Base RC2 installed.")
    print(f"Created: {KB_PATH}")
    print(f"Updated: {EVALUATOR_PATH}")
    print(f"Created: {TEST_PATH}")
    print()
    print("Run:")
    print("  python -m pytest tests/test_director_knowledge_base_rc2.py -q")
    print("  python -m compileall src/az_enterprise/core")


if __name__ == "__main__":
    main()
