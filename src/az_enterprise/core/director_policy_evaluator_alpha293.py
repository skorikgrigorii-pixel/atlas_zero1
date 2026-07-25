"""Policy-aware decision evaluator for Director Supervisor Alpha 2.9.3."""

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
