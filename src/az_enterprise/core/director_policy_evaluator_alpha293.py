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
        preferred_targets: tuple[str, ...] = (),
    ) -> None:
        self._policy = policy
        self._evaluator = DirectorPolicyEvaluator()
        self._knowledge = knowledge_base or DirectorKnowledgeBaseRC2(
            self._create_default_database()
        )
        self._pending_cycle_id: int | None = None
        self._pending_project_id: str | None = None

        # PATCH 4B:
        # Advisory preference only. This does not grant authority to a
        # target and does not alter DirectorPolicy or QualityGate.
        self._preferred_targets = tuple(
            dict.fromkeys(
                str(target).strip()
                for target in preferred_targets
                if str(target).strip()
            )
        )

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

            # PATCH 4B:
            # Learning is a soft preference only.
            #
            # DirectorPolicy validation has already constrained the target
            # set. Learning only establishes an advisory input order.
            # DirectorKnowledgeBaseRC2 then remains responsible for the
            # final historical effectiveness ranking.
            preferred_index = {
                target: index
                for index, target in enumerate(
                    self._preferred_targets
                )
            }

            original_index = {
                target: index
                for index, target in enumerate(
                    allowed_targets
                )
            }

            learning_ordered_targets = tuple(
                sorted(
                    allowed_targets,
                    key=lambda target: (
                        0 if target in preferred_index else 1,
                        preferred_index.get(
                            target,
                            len(preferred_index),
                        ),
                        original_index[target],
                    ),
                )
            )

            # PATCH 6B3 ? CANONICAL RUNTIME CONTEXT PROPAGATION
            #
            # PATCH 6B2 made DirectorKnowledgeBaseRC2 capable of
            # context-aware cross-project ranking. The canonical evaluator
            # must therefore provide the context BEFORE historical ranking.
            #
            # Policy remains authoritative:
            #   - allowed_targets are already policy-validated;
            #   - learning may only reorder that allowed set;
            #   - QualityGate thresholds remain unchanged;
            #   - context cannot create new rework targets.
            #
            # Runtime metadata contributes failure-domain/source context.
            # Canonical policy contributes stable project_type/objective.
            # Issue codes are resolved before ranking and are reused when
            # opening the learning cycle so ranking and persistence observe
            # exactly the same context.

            issue_codes = self._issue_codes(
                report
            )

            learning_runtime_metadata = dict(
                report.metadata
                or {}
            )

            policy_project_type = getattr(
                self._policy.project_type,
                "value",
                self._policy.project_type,
            )

            policy_objective = getattr(
                self._policy.objective,
                "value",
                self._policy.objective,
            )

            if policy_project_type is not None:
                learning_runtime_metadata.setdefault(
                    "project_type",
                    str(
                        policy_project_type
                    ),
                )

            if policy_objective is not None:
                learning_runtime_metadata.setdefault(
                    "objective",
                    str(
                        policy_objective
                    ),
                )

            ranked_targets = self._knowledge.rank_targets(
                project_id=project_id,
                targets=learning_ordered_targets,
                runtime_metadata=learning_runtime_metadata,
                issue_codes=issue_codes,
            )

            experience = self._knowledge.target_experience(
                project_id,
                ranked_targets,
            )

            self._pending_cycle_id = self._knowledge.begin_cycle(
                project_id=project_id,
                cycle=cycle,
                score_before=evaluation.score,
                targets=ranked_targets,
                issue_codes=issue_codes,
                runtime_metadata=learning_runtime_metadata,
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

                    "learning_preference": {
                        "mode":
                            "soft_tiebreak_before_historical_rank",

                        "preferred_targets":
                            list(self._preferred_targets),

                        "policy_allowed_targets":
                            list(allowed_targets),

                        "learning_ordered_targets":
                            list(learning_ordered_targets),

                        "final_ranked_targets":
                            list(ranked_targets),
                    },

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
