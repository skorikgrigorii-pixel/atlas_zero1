from pathlib import Path


def test_rc2_assignment_does_not_use_director_ai_state_authority():
    path = Path(
        "src/az_enterprise/core/assignment_engine_rc2.py"
    )

    source = path.read_text(encoding="utf-8")

    forbidden = (
        "transition_project_state(",
        "record_module_failure(",
        "_persist_state(",
    )

    for token in forbidden:
        assert token not in source


def test_director_core_rc2_owns_canonical_state_store():
    path = Path(
        "src/az_enterprise/core/director_core_rc2.py"
    )

    source = path.read_text(encoding="utf-8")

    assert "ProductionStateStoreRC2" in source
    assert "reset_for_run" in source
    assert "start_stage" in source
    assert "complete_stage" in source
    assert "fail_stage" in source
