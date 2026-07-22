from pathlib import Path

from az_enterprise.core.database import Database
from az_enterprise.core.director_knowledge_base_rc2 import DirectorKnowledgeBaseRC2


def test_knowledge_base_learns_target_effectiveness(tmp_path: Path) -> None:
    db = Database(tmp_path / "director_learning.sqlite3")
    db.init()
    knowledge = DirectorKnowledgeBaseRC2(db)

    cycle_id = knowledge.begin_cycle(
        project_id="demo",
        cycle=0,
        score_before=0.5,
        targets=("timeline", "assignment"),
        issue_codes=("LOW_VISUAL_DYNAMICS",),
    )
    result = knowledge.complete_cycle(
        cycle_id=cycle_id,
        score_after=0.8,
    )

    assert result["outcome"] == "improved"
    experience = knowledge.target_experience(
        "demo",
        ("timeline", "assignment"),
    )
    assert experience["timeline"].attempts == 1
    assert experience["timeline"].successes == 1
    assert experience["timeline"].average_score_delta == 0.3


def test_knowledge_base_ranks_effective_target_first(tmp_path: Path) -> None:
    db = Database(tmp_path / "director_learning.sqlite3")
    db.init()
    knowledge = DirectorKnowledgeBaseRC2(db)

    first = knowledge.begin_cycle(
        project_id="demo",
        cycle=0,
        score_before=0.5,
        targets=("timeline",),
    )
    knowledge.complete_cycle(cycle_id=first, score_after=0.8)

    second = knowledge.begin_cycle(
        project_id="demo",
        cycle=1,
        score_before=0.8,
        targets=("assignment",),
    )
    knowledge.complete_cycle(cycle_id=second, score_after=0.7)

    assert knowledge.rank_targets(
        project_id="demo",
        targets=("assignment", "timeline"),
    ) == ("timeline", "assignment")
