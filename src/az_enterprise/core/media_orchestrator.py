from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import Database
from .events import EventBus
from .paths import PROJECTS
from .production_state import ProductionState
from .project_state import ProjectState, PROJECT_STATES
from .job_queue import JobQueue
from .movie_runtime_rc1 import run_movie as run_movie

PIPELINE_STAGES = [
    ("research", "Research", "RESEARCH"),
    ("script_ready", "Production Script", "SCRIPT_READY"),
    ("voice_ready", "Voice Production", "VOICE_READY"),
    ("visual_ready", "Visual Production", "VISUAL_READY"),
    ("video_ready", "Video Production", "VIDEO_READY"),
    ("packaged", "Packaging", "PACKAGED"),
    ("published", "YouTube Publishing", "PUBLISHED"),
    ("analytics", "Analytics", "ANALYTICS"),
]


def run_project(project_id: str, db: Database | None = None) -> dict[str, Any]:
    """Execute the minimal sequential media production pipeline for a project."""

    if db is None:
        db = Database()

    db.init()
    state = ProjectState(db, project_id)
    event_bus = EventBus(db, project_id)
    queue = JobQueue()

    project_dir = PROJECTS / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    log_dir = project_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "orchestrator.log"

    def log(message: str, payload: dict[str, Any] | None = None) -> None:
        entry = {"project_id": project_id, "message": message, "payload": payload or {}}
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        db.execute(
            "INSERT INTO events(project_id, type, payload) VALUES(?,?,?)",
            (project_id, "MEDIA_ORCHESTRATOR_LOG", json.dumps(entry, ensure_ascii=False)),
        )

    def ensure_job(step_key: str, title: str, state_name: str) -> dict[str, Any]:
        job = {"project_id": project_id, "step_key": step_key, "title": title, "state_name": state_name}
        queue.enqueue(job)
        db.execute(
            "INSERT INTO workflow_jobs(project_id, stage, status, details) VALUES(?,?,?,?)",
            (project_id, step_key, "queued", json.dumps(job, ensure_ascii=False)),
        )
        return job

    def execute_stage(job: dict[str, Any]) -> dict[str, Any]:
        step_key = job["step_key"]
        title = job["title"]
        state_name = job["state_name"]
        log(f"Starting {title}", {"step_key": step_key})
        try:
            result = _run_stage_adapter(step_key, project_id, db)
            state.mark_step(step_key, "done", result)
            state.advance(state_name, result)
            event_bus.emit(f"{step_key.upper()}_DONE", result)
            db.execute(
                "UPDATE workflow_jobs SET status=?, details=? WHERE project_id=? AND stage=?",
                ("done", json.dumps(result, ensure_ascii=False), project_id, step_key),
            )
            log(f"Completed {title}", result)
            return {"step_key": step_key, "status": "done", "result": result}
        except Exception as exc:  # pragma: no cover - exercised through failure path
            state.mark_step(step_key, "failed", {"error": str(exc)})
            state.advance("FAILED", {"error": str(exc), "step_key": step_key})
            db.execute(
                "UPDATE workflow_jobs SET status=?, details=? WHERE project_id=? AND stage=?",
                ("failed", json.dumps({"error": str(exc)}, ensure_ascii=False), project_id, step_key),
            )
            log(f"Failed {title}", {"error": str(exc)})
            raise

    state.advance("IDEA", {"started": True})
    for step_key, title, state_name in PIPELINE_STAGES:
        if state.get_step_status(step_key) == "done":
            continue
        job = ensure_job(step_key, title, state_name)
        execute_stage(job)

    analytics_result = ProductionState(db, project_id).summarize()
    state.mark_step("analytics", "done", analytics_result)
    state.advance("ANALYTICS", analytics_result)
    log("Pipeline completed", analytics_result)

    return {
        "project_id": project_id,
        "status": state.current_state(),
        "completed": True,
        "steps": [row["step_key"] for row in db.rows("SELECT step_key FROM workflow_steps WHERE project_id=? ORDER BY id", (project_id,))],
    }


def _run_stage_adapter(step_key: str, project_id: str, db: Database) -> dict[str, Any]:
    if step_key == "research":
        return {"module": "research", "artifact": f"{project_id}/research/brief.md", "status": "ready"}
    if step_key == "script_ready":
        return {"module": "script", "artifact": f"{project_id}/script/final.txt", "status": "ready"}
    if step_key == "voice_ready":
        return {"module": "voice", "artifact": f"{project_id}/voice/narration.wav", "status": "ready"}
    if step_key == "visual_ready":
        return {"module": "visual", "artifact": f"{project_id}/visual/scene_pack", "status": "ready"}
    if step_key == "video_ready":
        return {"module": "video", "artifact": f"{project_id}/video/final.mp4", "status": "ready"}
    if step_key == "packaged":
        return {"module": "packaging", "artifact": f"{project_id}/packaging/package.zip", "status": "ready"}
    if step_key == "published":
        return {"module": "youtube", "artifact": f"{project_id}/publish/status.json", "status": "ready"}
    if step_key == "analytics":
        return ProductionState(db, project_id).summarize()
    raise ValueError(f"Unsupported stage: {step_key}")
