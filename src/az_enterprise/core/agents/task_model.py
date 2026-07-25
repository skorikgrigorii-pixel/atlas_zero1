from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid

TASK_STATUSES = (
    "QUEUED",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "SKIPPED",
)


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    agent_role: str = ""
    title: str = ""
    status: str = "QUEUED"
    priority: int = 3
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "agent_role": self.agent_role,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def mark_running(self) -> None:
        self.status = "RUNNING"
        self.updated_at = _utc_now_iso()

    def mark_completed(self, output_data: dict[str, Any] | None = None) -> None:
        self.status = "COMPLETED"
        self.output_data = output_data or {}
        self.updated_at = _utc_now_iso()

    def mark_failed(self, error: str) -> None:
        self.status = "FAILED"
        self.error = error
        self.updated_at = _utc_now_iso()
