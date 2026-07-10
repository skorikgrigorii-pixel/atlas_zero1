from __future__ import annotations

import json
from typing import Any

from .database import Database

PROJECT_STATES = (
    "IDEA",
    "RESEARCH",
    "SCRIPT_READY",
    "VOICE_READY",
    "VISUAL_READY",
    "VIDEO_READY",
    "PACKAGED",
    "PUBLISHED",
    "ANALYTICS",
    "FAILED",
)

STEP_MAP = {
    "IDEA": ("idea", "Idea"),
    "RESEARCH": ("research", "Research"),
    "SCRIPT_READY": ("script_ready", "Production Script"),
    "VOICE_READY": ("voice_ready", "Voice Production"),
    "VISUAL_READY": ("visual_ready", "Visual Production"),
    "VIDEO_READY": ("video_ready", "Video Production"),
    "PACKAGED": ("packaged", "Packaging"),
    "PUBLISHED": ("published", "YouTube Publishing"),
    "ANALYTICS": ("analytics", "Analytics"),
    "FAILED": ("failed", "Failed"),
}


class ProjectState:
    """Minimal state tracker for the media pipeline."""

    def __init__(self, db: Database, project_id: str):
        self.db = db
        self.project_id = project_id
        self.db.init()
        self._ensure_project()

    def _ensure_project(self) -> None:
        row = self.db.one("SELECT id FROM projects WHERE id=?", (self.project_id,))
        if not row:
            self.db.execute(
                "INSERT INTO projects(id, title, status) VALUES(?,?,?)",
                (self.project_id, self.project_id, "IDEA"),
            )
        for state_name, (step_key, title) in STEP_MAP.items():
            self._ensure_step(step_key, title)

    def _ensure_step(self, step_key: str, title: str) -> None:
        row = self.db.one(
            "SELECT id FROM workflow_steps WHERE project_id=? AND step_key=?",
            (self.project_id, step_key),
        )
        if row:
            return
        self.db.execute(
            "INSERT INTO workflow_steps(project_id, step_key, title, status) VALUES(?,?,?,?)",
            (self.project_id, step_key, title, "pending"),
        )

    def current_state(self) -> str:
        row = self.db.one("SELECT status FROM projects WHERE id=?", (self.project_id,))
        return row["status"] if row else "IDEA"

    def advance(self, state_name: str, payload: dict[str, Any] | None = None) -> str:
        if state_name not in PROJECT_STATES:
            raise ValueError(f"Unsupported project state: {state_name}")
        step_key, title = STEP_MAP[state_name]
        self._ensure_step(step_key, title)
        self.db.execute(
            "UPDATE projects SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (state_name, self.project_id),
        )
        self.db.execute(
            "UPDATE workflow_steps SET status=?, result_json=?, updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND step_key=?",
            ("done" if state_name != "FAILED" else "failed", json.dumps(payload or {}, ensure_ascii=False), self.project_id, step_key),
        )
        self.db.execute(
            "INSERT INTO events(project_id, type, payload) VALUES(?,?,?)",
            (self.project_id, "PROJECT_STATE", json.dumps({"state": state_name, "payload": payload or {}}, ensure_ascii=False)),
        )
        return state_name

    def mark_step(self, step_key: str, status: str, payload: dict[str, Any] | None = None) -> None:
        self.db.execute(
            "UPDATE workflow_steps SET status=?, result_json=?, updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND step_key=?",
            (status, json.dumps(payload or {}, ensure_ascii=False), self.project_id, step_key),
        )

    def get_step_status(self, step_key: str) -> str:
        row = self.db.one(
            "SELECT status FROM workflow_steps WHERE project_id=? AND step_key=?",
            (self.project_id, step_key),
        )
        return row["status"] if row else "pending"
