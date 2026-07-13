from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StageState:
    name: str
    status: str = "PENDING"
    attempts: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ProductionStateRC2:
    schema_version: str
    project_id: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    revision: int = 0
    status: str = "PENDING"
    current_stage: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    stages: dict[str, StageState] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    release_authorized: bool = False
    error: str | None = None


class ProductionStateStoreRC2:
    """The only canonical, atomically-written state store in RC2."""

    def __init__(self, path: Path, project_id: str) -> None:
        self.path = path
        self.project_id = project_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ProductionStateRC2:
        if not self.path.exists():
            return ProductionStateRC2(schema_version="2.1", project_id=self.project_id)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload.setdefault("run_id", uuid.uuid4().hex)
        payload.setdefault("revision", 0)
        payload.setdefault("schema_version", "2.1")
        stages = {
            name: StageState(**stage)
            for name, stage in dict(payload.get("stages") or {}).items()
        }
        payload["stages"] = stages
        return ProductionStateRC2(**payload)

    def save(self, state: ProductionStateRC2) -> None:
        state.updated_at = utc_now()
        state.revision += 1
        payload = asdict(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def reset_for_run(self, state: ProductionStateRC2, *, force: bool = False) -> None:
        state.run_id = uuid.uuid4().hex
        state.status = "RUNNING"
        state.current_stage = None
        state.error = None
        state.release_authorized = False
        if force:
            state.stages = {}
            state.artifacts = {}
            state.quality = {}
        self.save(state)

    def start_stage(self, state: ProductionStateRC2, name: str) -> None:
        previous = state.stages.get(name)
        attempts = (previous.attempts if previous else 0) + 1
        state.status = "RUNNING"
        state.current_stage = name
        state.error = None
        state.stages[name] = StageState(
            name=name,
            status="RUNNING",
            attempts=attempts,
            started_at=utc_now(),
        )
        self.save(state)

    def complete_stage(
        self,
        state: ProductionStateRC2,
        name: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        stage = state.stages.setdefault(name, StageState(name=name))
        stage.status = "COMPLETED"
        stage.completed_at = utc_now()
        stage.details = details or {}
        stage.error = None
        self.save(state)

    def fail_stage(self, state: ProductionStateRC2, name: str, error: str) -> None:
        stage = state.stages.setdefault(name, StageState(name=name))
        stage.status = "FAILED"
        stage.completed_at = utc_now()
        stage.error = error
        state.status = "FAILED"
        state.current_stage = name
        state.error = error
        self.save(state)
