from az_enterprise.core.asset_engine_rc2 import AssetEngineRC2
from az_enterprise.core.database import Database
from az_enterprise.core.project_config_rc2 import ProjectConfigRC2


def test_assets_path_is_unique_per_project(tmp_path):
    db = Database(tmp_path / "assets.sqlite3")
    db.init()

    indexes = db.rows("PRAGMA index_list(assets)")

    unique_columns = []

    for index in indexes:
        if not index["unique"]:
            continue

        columns = db.rows(
            f"PRAGMA index_info('{index['name']}')"
        )

        unique_columns.append(
            [column["name"] for column in columns]
        )

    assert ["path"] not in unique_columns
    assert ["project_id", "path"] in unique_columns


def test_same_physical_file_can_belong_to_two_projects(
    tmp_path,
):
    source_dir = tmp_path / "external"
    source_dir.mkdir()

    media = source_dir / "shared.jpg"
    media.write_bytes(b"shared-media-content")

    db = Database(tmp_path / "assets.sqlite3")
    db.init()

    for project_id in ("film_a", "film_b"):
        config = ProjectConfigRC2(
            project_id=project_id,
            root_dir=tmp_path,
            media_source_dir=source_dir,
        )

        AssetEngineRC2(db, config).run()

    rows = db.rows(
        """
        SELECT id, project_id, path
        FROM assets
        ORDER BY project_id
        """
    )

    assert len(rows) == 2
    assert rows[0]["project_id"] == "film_a"
    assert rows[1]["project_id"] == "film_b"
    assert rows[0]["id"] != rows[1]["id"]
    assert rows[0]["path"] == rows[1]["path"]


def test_rescan_does_not_duplicate_project_asset(
    tmp_path,
):
    source_dir = tmp_path / "external"
    source_dir.mkdir()

    media = source_dir / "single.jpg"
    media.write_bytes(b"single-media-content")

    db = Database(tmp_path / "assets.sqlite3")
    db.init()

    config = ProjectConfigRC2(
        project_id="film",
        root_dir=tmp_path,
        media_source_dir=source_dir,
    )

    AssetEngineRC2(db, config).run()
    AssetEngineRC2(db, config).run()

    row = db.one(
        """
        SELECT COUNT(*) AS count
        FROM assets
        WHERE project_id='film'
        """
    )

    assert row["count"] == 1
