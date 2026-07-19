from __future__ import annotations

import pytest

from az_enterprise.core.director_policy_alpha293 import (
    DirectorPolicy,
    DirectorPolicyEvaluator,
    MandatoryConstraint,
    ProjectObjective,
    ProjectType,
    QualityProfile,
)
from az_enterprise.core.director_policy_evaluator_alpha293 import (
    PolicyDecisionEvaluator,
    RuntimeReport,
)
from az_enterprise.core.director_supervisor_alpha292 import DecisionStatus


def make_policy():
    return DirectorPolicy(
        project_type=ProjectType.DOCUMENTARY,
        objective=ProjectObjective.ACCURACY,
        quality_profile=QualityProfile(
            weights={
                "accuracy": 0.5,
                "retention": 0.3,
                "technical": 0.2,
            },
            release_threshold=0.80,
            rework_threshold=0.55,
        ),
        constraints=(
            MandatoryConstraint("language", "en"),
            MandatoryConstraint("duration_ok", True),
        ),
        allowed_rework_targets=("research", "visual", "timeline"),
    )


def test_quality_profile_normalizes_and_scores():
    profile = QualityProfile(
        weights={"a": 2.0, "b": 1.0},
        release_threshold=0.8,
        rework_threshold=0.5,
    )

    assert profile.normalized_weights() == pytest.approx(
        {"a": 2 / 3, "b": 1 / 3}
    )
    assert profile.score({"a": 0.9, "b": 0.6}) == pytest.approx(0.8)


def test_missing_metric_is_rejected():
    profile = QualityProfile(weights={"accuracy": 1.0})

    with pytest.raises(ValueError, match="missing quality metrics"):
        profile.score({})


def test_constraint_validation_reports_violation():
    policy = make_policy()

    violations = policy.validate_constraints(
        {"language": "es", "duration_ok": True}
    )

    assert len(violations) == 1
    assert "language" in violations[0]


def test_policy_evaluator_approves_release():
    evaluator = PolicyDecisionEvaluator(make_policy())

    decision = evaluator(
        RuntimeReport(
            metrics={
                "accuracy": 0.95,
                "retention": 0.80,
                "technical": 0.85,
            },
            project_facts={"language": "en", "duration_ok": True},
        ),
        cycle=0,
    )

    assert decision.status is DecisionStatus.APPROVE


def test_policy_evaluator_requests_targeted_rework():
    evaluator = PolicyDecisionEvaluator(make_policy())

    decision = evaluator(
        RuntimeReport(
            metrics={
                "accuracy": 0.70,
                "retention": 0.65,
                "technical": 0.75,
            },
            project_facts={"language": "en", "duration_ok": True},
            recommended_targets=("research", "timeline"),
        ),
        cycle=0,
    )

    assert decision.status is DecisionStatus.REWORK
    assert tuple(action.target for action in decision.actions) == (
        "research",
        "timeline",
    )


def test_policy_evaluator_rejects_constraint_failure():
    evaluator = PolicyDecisionEvaluator(make_policy())

    decision = evaluator(
        RuntimeReport(
            metrics={
                "accuracy": 0.95,
                "retention": 0.95,
                "technical": 0.95,
            },
            project_facts={"language": "es", "duration_ok": True},
        ),
        cycle=0,
    )

    assert decision.status is DecisionStatus.REJECT
    assert "Mandatory constraints failed" in decision.reason


def test_low_score_is_rejected():
    evaluator = PolicyDecisionEvaluator(make_policy())

    decision = evaluator(
        RuntimeReport(
            metrics={
                "accuracy": 0.30,
                "retention": 0.30,
                "technical": 0.30,
            },
            project_facts={"language": "en", "duration_ok": True},
        ),
        cycle=0,
    )

    assert decision.status is DecisionStatus.REJECT


def test_rework_without_targets_escalates():
    evaluator = PolicyDecisionEvaluator(make_policy())

    decision = evaluator(
        RuntimeReport(
            metrics={
                "accuracy": 0.70,
                "retention": 0.65,
                "technical": 0.75,
            },
            project_facts={"language": "en", "duration_ok": True},
        ),
        cycle=0,
    )

    assert decision.status is DecisionStatus.ESCALATE


def test_disallowed_rework_target_is_rejected():
    evaluator = PolicyDecisionEvaluator(make_policy())

    with pytest.raises(ValueError, match="not allowed"):
        evaluator(
            RuntimeReport(
                metrics={
                    "accuracy": 0.70,
                    "retention": 0.65,
                    "technical": 0.75,
                },
                project_facts={"language": "en", "duration_ok": True},
                recommended_targets=("packaging",),
            ),
            cycle=0,
        )


def test_policy_evaluation_object():
    evaluation = DirectorPolicyEvaluator().evaluate(
        make_policy(),
        metrics={
            "accuracy": 0.8,
            "retention": 0.8,
            "technical": 0.8,
        },
        project_facts={"language": "en", "duration_ok": True},
    )

    assert evaluation.score == pytest.approx(0.8)
    assert evaluation.constraints_passed is True
