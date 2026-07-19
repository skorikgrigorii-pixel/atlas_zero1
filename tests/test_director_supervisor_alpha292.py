from __future__ import annotations

import pytest

from az_enterprise.core.director_supervisor_alpha292 import (
    DecisionLog,
    DecisionStatus,
    DirectorAction,
    DirectorDecision,
    DirectorSupervisor,
)


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = []

    def run(self, targets=None):
        normalized = None if targets is None else tuple(targets)
        self.calls.append(normalized)
        return {"targets": normalized, "call": len(self.calls)}


def test_approve_finishes_after_first_cycle():
    runtime = FakeRuntime()
    supervisor = DirectorSupervisor(
        runtime,
        lambda result, cycle: DirectorDecision(
            status=DecisionStatus.APPROVE,
            reason="Quality threshold reached",
            confidence=0.94,
        ),
    )

    result = supervisor.run_project()

    assert result.final_decision.status is DecisionStatus.APPROVE
    assert result.cycles == 1
    assert runtime.calls == [None]
    assert len(result.decisions) == 1


def test_rework_runs_only_requested_targets():
    runtime = FakeRuntime()

    def evaluator(result, cycle):
        if cycle == 0:
            return DirectorDecision(
                status=DecisionStatus.REWORK,
                reason="Visual rhythm needs correction",
                confidence=0.87,
                actions=(
                    DirectorAction("visual"),
                    DirectorAction("timeline"),
                    DirectorAction("visual"),
                ),
            )
        return DirectorDecision(
            status=DecisionStatus.APPROVE,
            reason="Corrections accepted",
            confidence=0.92,
        )

    result = DirectorSupervisor(runtime, evaluator).run_project(
        initial_targets=("research", "visual", "timeline")
    )

    assert result.cycles == 2
    assert runtime.calls == [
        ("research", "visual", "timeline"),
        ("visual", "timeline"),
    ]


def test_reject_does_not_rerun_runtime():
    runtime = FakeRuntime()
    supervisor = DirectorSupervisor(
        runtime,
        lambda result, cycle: DirectorDecision(
            status=DecisionStatus.REJECT,
            reason="Project violates mandatory constraints",
            confidence=0.99,
        ),
    )

    result = supervisor.run_project()

    assert result.final_decision.status is DecisionStatus.REJECT
    assert len(runtime.calls) == 1


def test_rework_limit_escalates():
    runtime = FakeRuntime()
    supervisor = DirectorSupervisor(
        runtime,
        lambda result, cycle: DirectorDecision(
            status=DecisionStatus.REWORK,
            reason="Still below threshold",
            confidence=0.8,
            actions=(DirectorAction("quality"),),
        ),
        max_rework_cycles=1,
    )

    result = supervisor.run_project()

    assert runtime.calls == [None, ("quality",)]
    assert result.final_decision.status is DecisionStatus.ESCALATE
    assert len(result.decisions) == 3


def test_rework_requires_actions():
    with pytest.raises(ValueError, match="requires at least one action"):
        DirectorDecision(
            status=DecisionStatus.REWORK,
            reason="Missing actions",
            confidence=0.7,
        )


def test_confidence_range_is_validated():
    with pytest.raises(ValueError, match="between"):
        DirectorDecision(
            status=DecisionStatus.APPROVE,
            reason="invalid",
            confidence=1.5,
        )


def test_decision_log_is_append_only_snapshot():
    log = DecisionLog()
    first = log.append(
        DirectorDecision(
            status=DecisionStatus.APPROVE,
            reason="done",
            confidence=1.0,
        )
    )

    snapshot = log.records()

    assert first.sequence == 1
    assert snapshot == (first,)
    assert log.latest() == first
