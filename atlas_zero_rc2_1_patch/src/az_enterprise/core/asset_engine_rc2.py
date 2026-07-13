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
        if not self.config.project_dir.exists():
            raise FileNotFoundError(
                f"Project media directory not found: {self.config.project_dir}"
            )
        result = AssetIntelligence(
            self.db,
            project_id=self.config.project_id,
            root=self.config.project_dir,
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
            "legacy_scan": result,
        }
