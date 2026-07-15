from az_enterprise.core.database import Database
from az_enterprise.core.generated_asset_store_rc2 import (
    GeneratedAssetStoreRC2,
)


def make_store(tmp_path):
    db = Database(tmp_path / "candidate_store.sqlite3")
    db.init()

    return (
        db,
        GeneratedAssetStoreRC2(
            db,
            project_id="franklin",
        ),
    )


def test_batch_requires_exact_shot_binding(tmp_path):
    _, store = make_store(tmp_path)

    try:
        store.create_batch(
            task_uid="task-1",
            shot_id="",
            prompt="Create historical image",
        )
    except ValueError as exc:
        assert "shot_id is required" in str(exc)
    else:
        raise AssertionError(
            "Batch without shot_id must be rejected"
        )


def test_batch_creation_is_idempotent(tmp_path):
    _, store = make_store(tmp_path)

    first = store.create_batch(
        task_uid="task-1",
        shot_id="shot_0074",
        prompt="Wooden boat runners on Arctic ice",
        candidate_count=4,
    )

    second = store.create_batch(
        task_uid="task-1",
        shot_id="shot_0074",
        prompt="Wooden boat runners on Arctic ice",
        candidate_count=4,
    )

    assert first["id"] == second["id"]


def test_candidates_remain_outside_assets_table(tmp_path):
    db, store = make_store(tmp_path)

    batch = store.create_batch(
        task_uid="task-2",
        shot_id="shot_0084",
        prompt="Victorian silver spoon",
        candidate_count=4,
    )

    for index in range(4):
        store.add_candidate(
            batch_id=batch["id"],
            candidate_index=index,
            remote_url=f"https://example.test/{index}.png",
        )

    candidates = store.list_candidates(batch["id"])

    assert len(candidates) == 4

    asset_count = db.one(
        "SELECT COUNT(*) AS count FROM assets"
    )["count"]

    assert asset_count == 0


def test_only_reviewed_candidate_can_be_winner(tmp_path):
    _, store = make_store(tmp_path)

    batch = store.create_batch(
        task_uid="task-3",
        shot_id="shot_0093",
        prompt="Forensic bone close-up",
        candidate_count=2,
    )

    first = store.add_candidate(
        batch_id=batch["id"],
        candidate_index=0,
    )

    second = store.add_candidate(
        batch_id=batch["id"],
        candidate_index=1,
    )

    store.record_review(
        first["id"],
        status="REVIEWED",
        technical_score=0.95,
        semantic_score=0.91,
        temporal_score=0.88,
        editorial_score=0.90,
        final_score=0.91,
    )

    store.record_review(
        second["id"],
        status="REVIEWED",
        technical_score=0.90,
        semantic_score=0.62,
        temporal_score=0.85,
        editorial_score=0.70,
        final_score=0.73,
    )

    winner = store.select_winner(
        batch_id=batch["id"],
        candidate_id=first["id"],
    )

    rows = store.list_candidates(batch["id"])

    assert winner["status"] == "ACCEPTED"
    assert winner["selected_as_winner"] == 1

    assert sum(
        row["selected_as_winner"]
        for row in rows
    ) == 1

    assert any(
        row["id"] == second["id"]
        and row["status"] == "REJECTED"
        for row in rows
    )


def test_unreviewed_candidate_cannot_be_selected(tmp_path):
    _, store = make_store(tmp_path)

    batch = store.create_batch(
        task_uid="task-4",
        shot_id="shot_0100",
        prompt="Wooden coffin at Arctic camp",
        candidate_count=2,
    )

    candidate = store.add_candidate(
        batch_id=batch["id"],
        candidate_index=0,
    )

    try:
        store.select_winner(
            batch_id=batch["id"],
            candidate_id=candidate["id"],
        )
    except RuntimeError as exc:
        assert "must pass review" in str(exc)
    else:
        raise AssertionError(
            "Unreviewed candidate must not be selected"
        )
