from __future__ import annotations

from typing import Any

from .database import Database
from .director_ai import DirectorAI
from .project_config_rc2 import ProjectConfigRC2


class AssignmentEngineRC2:
    """One assignment API. Legacy scoring remains behind this adapter during migration."""

    def __init__(self, db: Database, config: ProjectConfigRC2) -> None:
        self.db = db
        self.config = config

    def run(self) -> dict[str, Any]:
        result = DirectorAI(
            self.db,
            project_id=self.config.project_id,
        ).assign_assets()

        assigned = self.db.one(
            """
            SELECT COUNT(*) AS count
            FROM shots
            WHERE project_id=? AND status='assigned'
            """,
            (self.config.project_id,),
        )
        missing = self.db.one(
            """
            SELECT COUNT(*) AS count
            FROM shots
            WHERE project_id=? AND status!='assigned'
            """,
            (self.config.project_id,),
        )
        return {
            "state": "ASSIGNED",
            "project_id": self.config.project_id,
            "assigned": int(assigned["count"] if assigned else 0),
            "missing": int(missing["count"] if missing else 0),
            "legacy_result": result,
        }
