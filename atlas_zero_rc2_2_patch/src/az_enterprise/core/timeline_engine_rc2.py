from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import Database
from .movie_runtime_rc1 import MovieRuntimeRC1
from .project_config_rc2 import ProjectConfigRC2


class TimelineEngineRC2:
    """Canonical timeline builder for RC2."""

    def __init__(self, db: Database, config: ProjectConfigRC2) -> None:
        self.db = db
        self.config = config

    def run(self) -> dict[str, Any]:
        result = MovieRuntimeRC1(
            self.db,
            self.config.project_id,
        )._build_timeline()

        path = self.config.timeline_path
        if not path.exists():
            raise FileNotFoundError(f"Timeline was not created: {path}")

        rows = json.loads(path.read_text(encoding="utf-8"))
        incomplete = [
            row for row in rows
            if row.get("status") != "assigned" or not row.get("asset_path")
        ]
        return {
            "state": "TIMELINE_READY",
            "items": len(rows),
            "incomplete": len(incomplete),
            "artifact": str(path),
            "legacy_result": result,
        }
