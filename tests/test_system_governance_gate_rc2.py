from __future__ import annotations

import json
from pathlib import Path

import pytest

from az_enterprise.core.system_governance_gate_rc2 import (
    GovernanceBlockedError,
    GovernanceDecision,
    GovernancePolicy,
    SystemGovernanceGateRC2,
)


def write_health(root: Path, **overrides):
    output = root / "workspace" / "system"
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "healthy",
        "architecture_score": 90.0,
        "syntax_errors": 0,
        "layer_violations": 0,
        "critical_nodes": 0,
        "dead_modules": 0,
    }
    payload.update(overrides)
    (output / "system_health.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return output


def test_allows_healthy_system(tmp_path: Path):
    output = write_health(tmp_path)
    gate = SystemGovernanceGateRC2(
        tmp_path,
        output,
        policy=GovernancePolicy(refresh_before_run=False),
    )
    result = gate.evaluate(refresh=False)
    assert result.allowed is True
    assert result.decision is GovernanceDecision.ALLOW
    assert gate.latest_path.exists()


def test_blocks_syntax_errors(tmp_path: Path):
    output = write_health(tmp_path, syntax_errors=1)
    gate = SystemGovernanceGateRC2(
        tmp_path,
        output,
        policy=GovernancePolicy(refresh_before_run=False),
    )
    result = gate.evaluate(refresh=False)
    assert result.allowed is False
    assert result.decision is GovernanceDecision.BLOCK
    with pytest.raises(GovernanceBlockedError):
        gate.enforce(refresh=False)


def test_warns_on_layer_violations(tmp_path: Path):
    output = write_health(tmp_path, layer_violations=2)
    gate = SystemGovernanceGateRC2(
        tmp_path,
        output,
        policy=GovernancePolicy(refresh_before_run=False),
    )
    result = gate.evaluate(refresh=False)
    assert result.allowed is True
    assert result.decision is GovernanceDecision.WARN


def test_fail_closed_when_health_missing(tmp_path: Path):
    gate = SystemGovernanceGateRC2(
        tmp_path,
        tmp_path / "workspace" / "system",
        policy=GovernancePolicy(refresh_before_run=False, fail_closed=True),
    )
    result = gate.evaluate(refresh=False)
    assert result.allowed is False
    assert result.status == "diagnostic_error"
