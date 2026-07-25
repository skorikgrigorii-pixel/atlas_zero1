"""ATLAS ZERO Alpha 2.9.2 — Director Supervisor Framework.

The kernel executes work. DirectorSupervisor alone approves, rejects,
requests rework, or escalates the project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


class DecisionStatus(str, Enum):
    APPROVE = "APPROVE"
    REWORK = "REWORK"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class DirectorAction:
    target: str
    reason: str = ""


@dataclass(frozen=True)
class DirectorDecision:
    status: DecisionStatus
    reason: str
    confidence: float
    actions: tuple[DirectorAction, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.status is DecisionStatus.REWORK and not self.actions:
            raise ValueError("REWORK decision requires at least one action")


@dataclass(frozen=True)
class DecisionRecord:
    sequence: int
    created_at: str
    decision: DirectorDecision


class DecisionLog:
    """Small append-only decision history."""

    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []

    def append(self, decision: DirectorDecision) -> DecisionRecord:
        record = DecisionRecord(
            sequence=len(self._records) + 1,
            created_at=datetime.now(timezone.utc).isoformat(),
            decision=decision,
        )
        self._records.append(record)
        return record

    def records(self) -> tuple[DecisionRecord, ...]:
        return tuple(self._records)

    def latest(self) -> DecisionRecord | None:
        return self._records[-1] if self._records else None


class RuntimePort(Protocol):
    def run(self, targets: Sequence[str] | None = None) -> Any:
        ...


DecisionEvaluator = Callable[[Any, int], DirectorDecision]


@dataclass(frozen=True)
class SupervisorResult:
    final_decision: DirectorDecision
    cycles: int
    runtime_results: tuple[Any, ...]
    decisions: tuple[DecisionRecord, ...]


class DirectorSupervisor:
    """Single decision authority above the execution kernel."""

    def __init__(
        self,
        runtime: RuntimePort,
        evaluator: DecisionEvaluator,
        *,
        max_rework_cycles: int = 3,
        decision_log: DecisionLog | None = None,
    ) -> None:
        if max_rework_cycles < 0:
            raise ValueError("max_rework_cycles cannot be negative")
        self._runtime = runtime
        self._evaluator = evaluator
        self._max_rework_cycles = max_rework_cycles
        self._log = decision_log or DecisionLog()

    @property
    def decision_log(self) -> DecisionLog:
        return self._log

    def run_project(
        self,
        initial_targets: Sequence[str] | None = None,
    ) -> SupervisorResult:
        runtime_results: list[Any] = []
        targets = initial_targets
        rework_cycles = 0
        previous_signature: tuple[str, ...] | None = None

        while True:
            result = self._runtime.run(targets=targets)
            runtime_results.append(result)

            decision = self._evaluator(result, rework_cycles)
            self._log.append(decision)

            if decision.status is not DecisionStatus.REWORK:
                return SupervisorResult(
                    final_decision=decision,
                    cycles=len(runtime_results),
                    runtime_results=tuple(runtime_results),
                    decisions=self._log.records(),
                )

            if rework_cycles >= self._max_rework_cycles:
                escalation = DirectorDecision(
                    status=DecisionStatus.ESCALATE,
                    reason=(
                        "Maximum rework cycles reached. "
                        f"Last reason: {decision.reason}"
                    ),
                    confidence=1.0,
                    metadata={"last_decision": decision.status.value},
                )
                self._log.append(escalation)
                return SupervisorResult(
                    final_decision=escalation,
                    cycles=len(runtime_results),
                    runtime_results=tuple(runtime_results),
                    decisions=self._log.records(),
                )

            targets = self._targets_from_actions(decision.actions)
            signature = tuple(targets)
            if signature == previous_signature:
                escalation = DirectorDecision(
                    status=DecisionStatus.ESCALATE,
                    reason=(
                        "Rework produced no new corrective plan; "
                        f"repeated targets: {', '.join(signature)}"
                    ),
                    confidence=1.0,
                    metadata={
                        "last_decision": decision.status.value,
                        "repeated_targets": signature,
                    },
                )
                self._log.append(escalation)
                return SupervisorResult(
                    final_decision=escalation,
                    cycles=len(runtime_results),
                    runtime_results=tuple(runtime_results),
                    decisions=self._log.records(),
                )

            previous_signature = signature
            rework_cycles += 1

    @staticmethod
    def _targets_from_actions(actions: Iterable[DirectorAction]) -> tuple[str, ...]:
        targets: list[str] = []
        seen: set[str] = set()
        for action in actions:
            target = action.target.strip()
            if not target:
                raise ValueError("DirectorAction target cannot be empty")
            if target not in seen:
                seen.add(target)
                targets.append(target)
        return tuple(targets)
