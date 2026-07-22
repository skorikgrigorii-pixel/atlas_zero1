from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .database import Database
from .project_config_rc2 import ProjectConfigRC2
from .timeline_engine_rc2 import TimelineEngineRC2
from .render_engine_rc2 import RenderEngineRC2


class RC2ReadinessPlanner:
    def __init__(self, db: Database, project_id: str = "franklin") -> None:
        self.db = db
        self.project_id = project_id
        self.config = ProjectConfigRC2(project_id=project_id)

    def evaluate(self) -> dict[str, Any]:
        checks = {
            "canonical_timeline_exists": self.config.timeline_path.exists(),
            "canonical_render_exists": self.config.canonical_render_path.exists(),
            "project_directory_exists": self.config.project_dir.exists(),
            "export_directory_exists": self.config.export_dir.exists(),
        }
        score = round(sum(checks.values()) / len(checks) * 100, 1)
        blockers = [name for name, passed in checks.items() if not passed]
        payload = {
            "schema": "atlas_zero.rc2_readiness.v1",
            "project_id": self.project_id,
            "authority": "RC2ControlLayer",
            "score": score,
            "ready": not blockers,
            "checks": checks,
            "blockers": blockers,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_reports(payload)
        return payload

    def plan(self) -> dict[str, Any]:
        readiness = self.evaluate()
        actions = []
        if not readiness["checks"]["canonical_timeline_exists"]:
            actions.append("Build canonical RC2 timeline.")
        if not readiness["checks"]["canonical_render_exists"]:
            actions.append("Run canonical RC2 render.")
        if not actions:
            actions.append("Proceed to production benchmark.")
        return {
            **readiness,
            "tasks": len(actions),
            "actions": actions,
            "missing": len(readiness["blockers"]),
            "qc": readiness["score"],
            "json": str(self.config.rc2_dir / "control" / "readiness_rc2.json"),
            "html": str(self.config.rc2_dir / "control" / "readiness_rc2.md"),
            "csv": None,
        }

    def _write_reports(self, payload: dict[str, Any]) -> None:
        output_dir = self.config.rc2_dir / "control"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "readiness_rc2.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        lines = [
            "# ATLAS ZERO RC2 Readiness",
            "",
            f"- Project: `{self.project_id}`",
            f"- Score: **{payload['score']}%**",
            f"- Ready: **{payload['ready']}**",
            f"- Authority: **{payload['authority']}**",
            "",
            "## Checks",
            "",
        ]
        for name, passed in payload["checks"].items():
            lines.append(f"- {'✅' if passed else '❌'} `{name}`")
        (output_dir / "readiness_rc2.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )


class RC2ControlLayer:
    def __init__(self, *, project_id: str, db: Database | None = None) -> None:
        self.project_id = project_id
        self.db = db or Database()
        self.db.init()
        self.config = ProjectConfigRC2(project_id=project_id)

    def build_timeline(self) -> dict[str, Any]:
        return TimelineEngineRC2(self.db, self.config).run()

    def render(self, *, rebuild_timeline: bool = True) -> dict[str, Any]:
        timeline_report = None
        if rebuild_timeline or not self.config.timeline_path.exists():
            timeline_report = self.build_timeline()
        render_report = RenderEngineRC2(self.config).run()
        return {
            "schema": "atlas_zero.control_layer.rc2.v1",
            "project_id": self.project_id,
            "authority": "RC2ControlLayer",
            "timeline_report": timeline_report,
            "render_report": render_report,
            "output": render_report.get("output"),
            "state": render_report.get("state"),
        }
