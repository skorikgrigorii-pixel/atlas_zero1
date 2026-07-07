from __future__ import annotations
import json
from .database import Database

class EventBus:
    def __init__(self, db: Database, project_id: str = "franklin"):
        self.db = db
        self.project_id = project_id

    def emit(self, event_type: str, payload: dict | None = None):
        self.db.execute(
            "INSERT INTO events(project_id,type,payload) VALUES(?,?,?)",
            (self.project_id, event_type, json.dumps(payload or {}, ensure_ascii=False))
        )
