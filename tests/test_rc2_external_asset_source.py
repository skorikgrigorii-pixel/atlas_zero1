from pathlib import Path

from az_enterprise.core.asset_engine_rc2 import AssetEngineRC2
from az_enterprise.core.database import Database
from az_enterprise.core.project_config_rc2 import ProjectConfigRC2


def test_external_source_is_indexed_without_copying(tmp_path):
    source_dir = tmp_path / "external"
    source_dir.mkdir()

    image = source_dir / "photo.jpg"
    video = source_dir / "video.mp4"

    image.write_bytes(b"fake-jpeg")
    video.write_bytes(b"fake-video")

    db = Database(tmp_path / "assets.sqlite3")
    db.init()

    config = ProjectConfigRC2(
        project_id="hogueras_test",
        root_dir=tmp_path,
        media_source_dir=source_dir,
    )

    result = AssetEngineRC2(db, config).run()

    assert result["assets_total"] == 2
    assert result["media_counts"]["image"] == 1
    assert result["media_counts"]["video"] == 1
    assert result["source_mode"] == "external_read_only"
    assert result["source_files_modified"] is False

    rows = db.rows(
        """
        SELECT path
        FROM assets
        WHERE project_id=?
        """,
        ("hogueras_test",),
    )

    assert len(rows) == 2
    assert all(
        Path(row["path"]).parent == source_dir
        for row in rows
    )

    assert image.read_bytes() == b"fake-jpeg"
    assert video.read_bytes() == b"fake-video"


def test_asset_ids_are_project_scoped(tmp_path):
    source_dir = tmp_path / "external"
    source_dir.mkdir()

    media = source_dir / "same.jpg"
    media.write_bytes(b"same-content")

    db = Database(tmp_path / "assets.sqlite3")
    db.init()

    for project_id in ("project_a", "project_b"):
        config = ProjectConfigRC2(
            project_id=project_id,
            root_dir=tmp_path,
            media_source_dir=source_dir,
        )
        AssetEngineRC2(db, config).run()

    rows = db.rows(
        """
        SELECT id, project_id
        FROM assets
        ORDER BY project_id
        """
    )

    assert len(rows) == 2
    assert rows[0]["id"] != rows[1]["id"]


def test_internal_project_mode_remains_available(tmp_path):
    config = ProjectConfigRC2(
        project_id="internal",
        root_dir=tmp_path,
    )

    assert (
        config.effective_media_source_dir
        == tmp_path / "workspace/projects/internal"
    )
