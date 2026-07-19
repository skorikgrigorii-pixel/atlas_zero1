"""Policy-aware decision evaluator for Director Supervisor Alpha 2.9.3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

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
    """Converts runtime reports into Director decisions.

    This evaluator is intentionally deterministic. A later AI evaluator may
    enrich the reasoning, but it must still obey the DirectorPolicy.
    """

    def __init__(self, policy: DirectorPolicy) -> None:
        self._policy = policy
        self._evaluator = DirectorPolicyEvaluator()

    def __call__(self, runtime_result: Any, cycle: int) -> DirectorDecision:
        report = self._coerce_report(runtime_result)
        evaluation = self._evaluator.evaluate(
            self._policy,
            report.metrics,
            report.project_facts,
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
                metadata={"score": evaluation.score, "cycle": cycle},
            )

        if evaluation.score >= profile.rework_threshold:
            targets = self._policy.validate_rework_targets(
                report.recommended_targets
            )
            if not targets:
                return DirectorDecision(
                    status=DecisionStatus.ESCALATE,
                    reason=(
                        "Project requires rework, but no valid rework targets "
                        "were provided"
                    ),
                    confidence=1.0 - evaluation.score,
                    metadata={"score": evaluation.score, "cycle": cycle},
                )

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
                        reason="Requested by policy evaluation",
                    )
                    for target in targets
                ),
                metadata={"score": evaluation.score, "cycle": cycle},
            )

        return DirectorDecision(
            status=DecisionStatus.REJECT,
            reason=(
                f"Project score {evaluation.score:.3f} is below "
                f"minimum rework threshold {profile.rework_threshold:.3f}"
            ),
            confidence=1.0 - evaluation.score,
            metadata={"score": evaluation.score, "cycle": cycle},
        )

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
