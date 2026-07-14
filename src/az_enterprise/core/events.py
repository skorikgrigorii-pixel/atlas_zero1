from __future__ import annotations

import json
from typing import Any, Callable

from .database import Database


EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    """Canonical event bus for the entire ATLAS ZERO runtime."""

    def __init__(
        self,
        db: Database | None = None,
        project_id: str = "franklin",
    ):
        self.db = db
        self.project_id = project_id
        self.handlers: dict[str, list[EventHandler]] = {}
        self.memory_events: list[dict[str, Any]] = []

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        payload = payload or {}

        event = {
            "project_id": self.project_id,
            "type": event_type,
            "payload": payload,
        }

        if self.db is not None:
            self.db.execute(
                """
                INSERT INTO events(project_id, type, payload)
                VALUES(?,?,?)
                """,
                (
                    self.project_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        else:
            self.memory_events.append(event)

        for handler in tuple(self.handlers.get(event_type, [])):
            handler(event)

    def on(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """Register an in-process event handler."""
        self.handlers.setdefault(event_type, []).append(handler)
