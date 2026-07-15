from __future__ import annotations

from pathlib import Path
from typing import Any

from .asset_intelligence import AssetIntelligence
from .database import Database
from .project_config_rc2 import ProjectConfigRC2


class AssetEngineRC2:
    """Single public entry point for project media registration."""

    def __init__(self, db: Database, config: ProjectConfigRC2) -> None:
        self.db = db
        self.config = config

    def run(self) -> dict[str, Any]:
        source_dir = self.config.effective_media_source_dir

        if not source_dir.exists():
            raise FileNotFoundError(
                f"Project media directory not found: {source_dir}"
            )

        external_source = (
            self.config.media_source_dir is not None
        )

        result = AssetIntelligence(
            self.db,
            project_id=self.config.project_id,
            root=source_dir,
            direct_root_scan=external_source,
        ).scan()
        counts = {
            row["media_type"]: int(row["count"])
            for row in self.db.rows(
                """
                SELECT media_type, COUNT(*) AS count
                FROM assets
                WHERE project_id=?
                GROUP BY media_type
                """,
                (self.config.project_id,),
            )
        }
        return {
            "state": "ASSETS_INDEXED",
            "project_id": self.config.project_id,
            "assets_total": sum(counts.values()),
            "media_counts": counts,
            "source_dir": str(source_dir),
            "source_mode": (
                "external_read_only"
                if external_source
                else "project_directory"
            ),
            "source_files_modified": False,
            "legacy_scan": result,
        }
