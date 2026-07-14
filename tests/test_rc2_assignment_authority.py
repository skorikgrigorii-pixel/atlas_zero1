from pathlib import Path

from az_enterprise.core.assignment_policy_rc2 import (
    AssignmentPolicyRC2,
)


def test_assignment_engine_uses_canonical_policy():
    source = Path(
        "src/az_enterprise/core/assignment_engine_rc2.py"
    ).read_text(encoding="utf-8")

    assert "AssignmentPolicyRC2" in source
    assert ").assign_assets()" not in source


def test_director_ai_delegates_assignment_to_policy():
    source = Path(
        "src/az_enterprise/core/director_ai.py"
    ).read_text(encoding="utf-8")

    assert "AssignmentPolicyRC2" in source
    assert "policy_result = AssignmentPolicyRC2" in source


def test_policy_is_assignment_write_owner():
    source = Path(
        "src/az_enterprise/core/assignment_policy_rc2.py"
    ).read_text(encoding="utf-8")

    assert "UPDATE shots" in source
    assert "assigned_asset_id" in source
    assert "director_decisions" in source
    assert AssignmentPolicyRC2.ACCEPTANCE_THRESHOLD == 0.62
