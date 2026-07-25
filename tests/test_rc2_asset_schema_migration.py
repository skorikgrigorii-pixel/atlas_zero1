from __future__ import annotations

import sqlite3

from az_enterprise.core.database import Database


def unique_index_columns(db):
    result = []

    for index in db.rows(
        "PRAGMA index_list(assets)"
    ):
        if not index["unique"]:
            continue

        columns = db.rows(
            f"PRAGMA index_info('{index['name']}')"
        )

        result.append(
            [
                column["name"]
                for column in columns
            ]
        )

    return result


def test_migration_supports_minimal_legacy_schema(
    tmp_path,
):
    db_path = tmp_path / "minimal.sqlite3"

    connection = sqlite3.connect(db_path)

    connection.execute(
        """
        CREATE TABLE assets(
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            sha256 TEXT,
            category TEXT,
            tags TEXT,
            emotion TEXT,
            quality REAL DEFAULT 0,
            width INTEGER,
            height INTEGER,
            duration_sec REAL,
            duplicate_of TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.execute(
        """
        INSERT INTO assets(
            id,
            project_id,
            path,
            filename,
            media_type
        )
        VALUES(?,?,?,?,?)
        """,
        (
            "asset-1",
            "project-a",
            "C:/shared/file.jpg",
            "file.jpg",
            "image",
        ),
    )

    connection.commit()
    connection.close()

    db = Database(db_path)
    db.init()

    indexes = unique_index_columns(db)

    assert ["path"] not in indexes
    assert ["project_id", "path"] in indexes

    row = db.one(
        """
        SELECT
            id,
            semantic_class,
            semantic_confidence,
            max_use
        FROM assets
        WHERE id='asset-1'
        """
    )

    assert row is not None
    assert row["semantic_class"] is None
    assert row["semantic_confidence"] == 0
    assert row["max_use"] == 3


def test_migration_preserves_extended_columns(
    tmp_path,
):
    db_path = tmp_path / "extended.sqlite3"

    connection = sqlite3.connect(db_path)

    connection.execute(
        """
        CREATE TABLE assets(
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            semantic_class TEXT,
            semantic_description TEXT,
            semantic_confidence REAL DEFAULT 0,
            max_use INTEGER DEFAULT 3
        )
        """
    )

    connection.execute(
        """
        INSERT INTO assets(
            id,
            project_id,
            path,
            filename,
            media_type,
            semantic_class,
            semantic_description,
            semantic_confidence,
            max_use
        )
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            "asset-2",
            "project-b",
            "C:/shared/file.mp4",
            "file.mp4",
            "video",
            "parade",
            "Festival parade",
            0.91,
            2,
        ),
    )

    connection.commit()
    connection.close()

    db = Database(db_path)
    db.init()

    row = db.one(
        """
        SELECT
            semantic_class,
            semantic_description,
            semantic_confidence,
            max_use
        FROM assets
        WHERE id='asset-2'
        """
    )

    assert row["semantic_class"] == "parade"
    assert (
        row["semantic_description"]
        == "Festival parade"
    )
    assert row["semantic_confidence"] == 0.91
    assert row["max_use"] == 2


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "idempotent.sqlite3"

    db = Database(db_path)
    db.init()
    db.init()
    db.init()

    indexes = unique_index_columns(db)

    assert ["path"] not in indexes
    assert ["project_id", "path"] in indexes


def test_same_path_can_exist_in_two_projects(
    tmp_path,
):
    db_path = tmp_path / "projects.sqlite3"

    db = Database(db_path)
    db.init()

    common_path = "C:/shared/archive.jpg"

    db.execute(
        """
        INSERT INTO assets(
            id,
            project_id,
            path,
            filename,
            media_type
        )
        VALUES(?,?,?,?,?)
        """,
        (
            "asset-a",
            "project-a",
            common_path,
            "archive.jpg",
            "image",
        ),
    )

    db.execute(
        """
        INSERT INTO assets(
            id,
            project_id,
            path,
            filename,
            media_type
        )
        VALUES(?,?,?,?,?)
        """,
        (
            "asset-b",
            "project-b",
            common_path,
            "archive.jpg",
            "image",
        ),
    )

    row = db.one(
        """
        SELECT COUNT(*) AS count
        FROM assets
        WHERE path=?
        """,
        (common_path,),
    )

    assert row["count"] == 2
