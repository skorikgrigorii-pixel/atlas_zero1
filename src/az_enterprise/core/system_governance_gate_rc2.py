from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypeVar

from .system_registry_rc2 import (
    DependencyIntelligenceRC2,
    ProjectKnowledgeGraphRC2,
    SystemHealthRC2,
    SystemRegistryRC2,
)

T = TypeVar("T")


class GovernanceDecision(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class GovernanceError(RuntimeError):
    """Base exception for governance integration."""


class GovernanceBlockedError(GovernanceError):
    """Raised when policy blocks a protected operation."""

    def __init__(self, result: "GovernanceResult") -> None:
        self.result = result
        super().__init__(
            f"ATLAS ZERO governance blocked execution: "
            f"score={result.architecture_score}, "
            f"syntax_errors={result.syntax_errors}, "
            f"layer_violations={result.layer_violations}"
        )


@dataclass(slots=True, frozen=True)
class GovernancePolicy:
    """Thresholds controlling the governance gate."""

    minimum_architecture_score: float = 70.0
    block_architecture_score: float = 50.0
    maximum_syntax_errors: int = 0
    block_syntax_errors: int = 25
    maximum_layer_violations: int = 0
    maximum_critical_nodes: Optional[int] = None
    maximum_dead_modules: Optional[int] = None
    fail_closed: bool = True
    refresh_before_run: bool = True
    build_knowledge_graph: bool = True

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "GovernancePolicy":
        allowed = {field.name for field in __import__("dataclasses").fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in allowed})

    @classmethod
    def from_json(cls, path: Path | str) -> "GovernancePolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Governance policy must be a JSON object")
        return cls.from_mapping(payload)


@dataclass(slots=True)
class GovernanceResult:
    schema: str
    generated_at: str
    decision: GovernanceDecision
    allowed: bool
    status: str
    architecture_score: float
    syntax_errors: int
    layer_violations: int
    critical_nodes: int
    dead_modules: int
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    policy: dict[str, Any] = field(default_factory=dict)
    evidence_files: dict[str, str] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = self.decision.value
        return payload


class SystemGovernanceGateRC2:
    """
    Runtime bridge between SystemRegistryRC2 and operational modules.

    The gate refreshes architecture intelligence, evaluates policy,
    writes an immutable decision record and optionally blocks execution.
    """

    _lock = threading.RLock()

    def __init__(
        self,
        project_root: Path | str,
        output_dir: Path | str | None = None,
        *,
        policy: GovernancePolicy | None = None,
        policy_path: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.output_dir = (
            Path(output_dir).resolve()
            if output_dir is not None
            else self.project_root / "workspace" / "system"
        )
        if policy is not None and policy_path is not None:
            raise ValueError("Provide policy or policy_path, not both")
        if policy_path is not None:
            policy = GovernancePolicy.from_json(policy_path)
        self.policy = policy or GovernancePolicy()
        self.decision_dir = self.output_dir / "governance"
        self.latest_path = self.output_dir / "governance_decision.json"
        self.history_path = self.decision_dir / "governance_history.jsonl"

    def refresh(self) -> dict[str, Any]:
        """Build the complete intelligence chain in dependency order."""
        with self._lock:
            registry = SystemRegistryRC2(
                self.project_root,
                self.output_dir,
                include_untracked=True,
            ).build()
            dependency = DependencyIntelligenceRC2(
                self.project_root,
                self.output_dir,
            ).build()
            knowledge: dict[str, Any] | None = None
            if self.policy.build_knowledge_graph:
                knowledge = ProjectKnowledgeGraphRC2(
                    self.project_root,
                    self.output_dir,
                ).build()
            health = SystemHealthRC2(
                self.project_root,
                self.output_dir,
            ).build()
            return {
                "registry": registry,
                "dependency": dependency,
                "knowledge": knowledge,
                "health": health,
            }

    def evaluate(
        self,
        *,
        refresh: Optional[bool] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> GovernanceResult:
        refresh_enabled = (
            self.policy.refresh_before_run if refresh is None else bool(refresh)
        )
        try:
            if refresh_enabled:
                chain = self.refresh()
                health = chain["health"]
            else:
                health = self._load_health()
            result = self._evaluate_health(health, dict(context or {}))
        except Exception as exc:
            if not self.policy.fail_closed:
                result = GovernanceResult(
                    schema="atlas_zero.governance_result.rc2",
                    generated_at=_utc_now(),
                    decision=GovernanceDecision.WARN,
                    allowed=True,
                    status="diagnostic_error",
                    architecture_score=0.0,
                    syntax_errors=0,
                    layer_violations=0,
                    critical_nodes=0,
                    dead_modules=0,
                    reasons=[],
                    warnings=[f"{type(exc).__name__}: {exc}"],
                    policy=asdict(self.policy),
                    evidence_files={},
                    context=dict(context or {}),
                )
            else:
                result = GovernanceResult(
                    schema="atlas_zero.governance_result.rc2",
                    generated_at=_utc_now(),
                    decision=GovernanceDecision.BLOCK,
                    allowed=False,
                    status="diagnostic_error",
                    architecture_score=0.0,
                    syntax_errors=0,
                    layer_violations=0,
                    critical_nodes=0,
                    dead_modules=0,
                    reasons=[f"diagnostic_failure:{type(exc).__name__}: {exc}"],
                    warnings=[],
                    policy=asdict(self.policy),
                    evidence_files={},
                    context=dict(context or {}),
                )
        self._persist(result)
        return result

    def enforce(
        self,
        *,
        refresh: Optional[bool] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> GovernanceResult:
        result = self.evaluate(refresh=refresh, context=context)
        if not result.allowed:
            raise GovernanceBlockedError(result)
        return result

    def protect(
        self,
        operation: Callable[..., T],
        *args: Any,
        refresh: Optional[bool] = None,
        context: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> T:
        self.enforce(refresh=refresh, context=context)
        return operation(*args, **kwargs)

    def _load_health(self) -> dict[str, Any]:
        path = self.output_dir / "system_health.json"
        if not path.exists():
            raise FileNotFoundError(
                f"System health does not exist: {path}. Run with refresh enabled."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("system_health.json must contain a JSON object")
        return payload

    def _evaluate_health(
        self,
        health: Mapping[str, Any],
        context: dict[str, Any],
    ) -> GovernanceResult:
        score = float(health.get("architecture_score", 0.0))
        syntax_errors = int(health.get("syntax_errors", 0))
        layer_violations = int(health.get("layer_violations", 0))
        critical_nodes = int(health.get("critical_nodes", 0))
        dead_modules = int(health.get("dead_modules", 0))
        status = str(health.get("status", "unknown"))

        reasons: list[str] = []
        warnings: list[str] = []

        if score < self.policy.block_architecture_score:
            reasons.append(
                f"architecture_score_below_block_threshold:{score}"
            )
        elif score < self.policy.minimum_architecture_score:
            warnings.append(
                f"architecture_score_below_target:{score}"
            )

        if syntax_errors >= self.policy.block_syntax_errors:
            reasons.append(f"syntax_errors_block_threshold:{syntax_errors}")
        elif syntax_errors > self.policy.maximum_syntax_errors:
            reasons.append(f"syntax_errors_present:{syntax_errors}")

        if layer_violations > self.policy.maximum_layer_violations:
            warnings.append(f"layer_violations:{layer_violations}")

        if (
            self.policy.maximum_critical_nodes is not None
            and critical_nodes > self.policy.maximum_critical_nodes
        ):
            warnings.append(f"critical_nodes:{critical_nodes}")

        if (
            self.policy.maximum_dead_modules is not None
            and dead_modules > self.policy.maximum_dead_modules
        ):
            warnings.append(f"dead_modules:{dead_modules}")

        if reasons:
            decision = GovernanceDecision.BLOCK
            allowed = False
        elif warnings:
            decision = GovernanceDecision.WARN
            allowed = True
        else:
            decision = GovernanceDecision.ALLOW
            allowed = True

        return GovernanceResult(
            schema="atlas_zero.governance_result.rc2",
            generated_at=_utc_now(),
            decision=decision,
            allowed=allowed,
            status=status,
            architecture_score=score,
            syntax_errors=syntax_errors,
            layer_violations=layer_violations,
            critical_nodes=critical_nodes,
            dead_modules=dead_modules,
            reasons=reasons,
            warnings=warnings,
            policy=asdict(self.policy),
            evidence_files={
                "system_health": str(self.output_dir / "system_health.json"),
                "architecture_score": str(
                    self.output_dir / "architecture_score.json"
                ),
                "critical_nodes": str(self.output_dir / "critical_nodes.json"),
                "node_health": str(self.output_dir / "node_health.json"),
                "knowledge_graph": str(
                    self.output_dir / "knowledge_graph.json"
                ),
            },
            context=context,
        )

    def _persist(self, result: GovernanceResult) -> None:
        self.decision_dir.mkdir(parents=True, exist_ok=True)
        payload = result.to_dict()
        _atomic_json_dump(self.latest_path, payload)

        stamp = result.generated_at.replace(":", "").replace("-", "")
        decision_path = self.decision_dir / f"decision_{stamp}.json"
        _atomic_json_dump(decision_path, payload)

        with self.history_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def governed(
    gate: SystemGovernanceGateRC2,
    *,
    refresh: Optional[bool] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for Director, pipeline or renderer entry points."""

    def decorator(operation: Callable[..., T]) -> Callable[..., T]:
        def wrapped(*args: Any, **kwargs: Any) -> T:
            gate.enforce(refresh=refresh, context=context)
            return operation(*args, **kwargs)

        wrapped.__name__ = getattr(operation, "__name__", "governed_operation")
        wrapped.__doc__ = getattr(operation, "__doc__", None)
        wrapped.__module__ = getattr(operation, "__module__", __name__)
        return wrapped

    return decorator


def gate_from_environment(
    project_root: Path | str,
    output_dir: Path | str | None = None,
) -> SystemGovernanceGateRC2:
    policy_path = os.environ.get("ATLAS_ZERO_GOVERNANCE_POLICY")
    return SystemGovernanceGateRC2(
        project_root,
        output_dir,
        policy_path=policy_path or None,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
