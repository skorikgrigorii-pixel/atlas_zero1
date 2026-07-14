from pathlib import Path

import pytest

from az_enterprise.core.database import Database
from az_enterprise.core.director_ai import DirectorAI


def test_assignment_engine_disables_legacy_state_authority():
    source = Path(
        "src/az_enterprise/core/assignment_engine_rc2.py"
    ).read_text(encoding="utf-8")

    assert "enable_legacy_state_authority=False" in source


def test_director_ai_rc2_mode_blocks_state_transitions(tmp_path):
    db_path = tmp_path / "director_ai_authority.sqlite3"
    db = Database(db_path)
    db.init()

    ai = DirectorAI(
        db,
        project_id="authority_test",
        enable_legacy_state_authority=False,
    )

    with pytest.raises(
        RuntimeError,
        match="state authority is disabled",
    ):
        ai.transition_project_state(
            "RESEARCH_READY",
            reason="must be blocked",
        )


def test_director_ai_legacy_mode_remains_available(tmp_path):
    db_path = tmp_path / "director_ai_legacy.sqlite3"
    db = Database(db_path)
    db.init()

    ai = DirectorAI(
        db,
        project_id="legacy_authority_test",
    )

    state = ai.get_project_state()

    assert state["current_stage"] == "NEW"
