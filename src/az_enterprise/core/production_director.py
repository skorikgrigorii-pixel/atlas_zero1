from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .paths import ROOT


class ProductionDirector:
    """Orchestrates production next-step decisions from existing project reports."""

    def __init__(
        self,
        project_id: str,
        deadline_days_remaining: int = 4,
        root_dir: Path | None = None,
    ) -> None:
        self.project_id = project_id
        self.deadline_days_remaining = int(deadline_days_remaining)
        self.root_dir = Path(root_dir) if root_dir is not None else ROOT
        self.export_dir = self.root_dir / "workspace" / "exports" / project_id

    def run(self) -> dict[str, Any]:
        status = self._build_status()
        self.export_dir.mkdir(parents=True, exist_ok=True)

        status_path = self.export_dir / "production_director_status.json"
        brief_path = self.export_dir / "production_director_brief.md"

        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        brief_path.write_text(self._build_brief(status), encoding="utf-8")

        return status

    def _build_status(self) -> dict[str, Any]:
        production_state = self._read_json(self.export_dir / "production_state.json") or {}
        missing_story_requirements = self._read_json(self.export_dir / "missing_story_requirements.json")
        director_tasks = self._read_csv_rows(self.export_dir / "director_tasks.csv")
        asset_inventory = self._read_json(self.export_dir / "movie_runtime_rc1" / "asset_inventory.json") or {}
        render_report = self._read_json(self.export_dir / "render_rc1" / "render_report.json")
        render_manifest = self._read_json(self.export_dir / "render_rc1" / "render_manifest.json") or {}

        script_ready = bool(production_state.get("shots", 0)) or bool(director_tasks)

        inventory_counts = asset_inventory.get("counts", {}) if isinstance(asset_inventory, dict) else {}
        audio_count = int(inventory_counts.get("audio", 0) or 0)
        images_found = int(inventory_counts.get("image", 0) or 0)
        videos_found = int(inventory_counts.get("video", 0) or 0)
        voice_ready = audio_count > 0

        if isinstance(missing_story_requirements, list):
            images_missing = len(missing_story_requirements)
        else:
            images_missing = int(production_state.get("missing", 0) or 0)

        manifest_clips = render_manifest.get("clips", []) if isinstance(render_manifest, dict) else []
        timeline_ready = bool(production_state.get("shots", 0)) or bool(manifest_clips)

        render_duration_sec = 0.0
        for clip in manifest_clips:
            try:
                render_duration_sec += float(clip.get("duration_sec", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
        render_duration_sec = round(render_duration_sec, 3)

        render_exists = isinstance(render_report, dict)
        render_state = str((render_report or {}).get("state", "")).upper()
        output_mp4_exists = bool((render_report or {}).get("output_mp4_exists", False))
        render_ready = render_exists and render_state == "RENDERED" and output_mp4_exists

        clips_total = int((render_report or {}).get("clips_total", 0) or 0)
        clips_renderable = int((render_report or {}).get("clips_renderable", 0) or 0)
        render_incomplete = render_exists and clips_total > 0 and clips_renderable < clips_total

        state_flags = [
            script_ready,
            voice_ready,
            images_missing == 0,
            timeline_ready,
            render_ready and not render_incomplete,
        ]
        release_progress_percent = round(sum(1 for flag in state_flags if flag) / len(state_flags) * 100, 1)

        main_blocker, next_action, next_module = self._decide_next_step(
            script_ready=script_ready,
            voice_ready=voice_ready,
            images_missing=images_missing,
            timeline_ready=timeline_ready,
            render_exists=render_exists,
            render_ready=render_ready,
            render_incomplete=render_incomplete,
        )

        operator_message = (
            f"Project {self.project_id}: blocker '{main_blocker}'. "
            f"Run {next_module} now: {next_action}"
        )

        return {
            "project_id": self.project_id,
            "deadline_days_remaining": self.deadline_days_remaining,
            "script_ready": script_ready,
            "voice_ready": voice_ready,
            "images_found": images_found,
            "images_missing": images_missing,
            "videos_found": videos_found,
            "timeline_ready": timeline_ready,
            "render_ready": render_ready,
            "render_duration_sec": render_duration_sec,
            "release_progress_percent": release_progress_percent,
            "main_blocker": main_blocker,
            "next_action": next_action,
            "next_module": next_module,
            "operator_message": operator_message,
        }

    def _decide_next_step(
        self,
        *,
        script_ready: bool,
        voice_ready: bool,
        images_missing: int,
        timeline_ready: bool,
        render_exists: bool,
        render_ready: bool,
        render_incomplete: bool,
    ) -> tuple[str, str, str]:
        if not script_ready:
            return (
                "script missing",
                "Generate and approve production script for all scenes.",
                "Story Engine",
            )
        if not voice_ready:
            return (
                "voice missing",
                "Produce and attach the voice-over master track.",
                "Voice Production",
            )
        if images_missing > 0:
            return (
                "visual assets missing",
                "Close top-priority missing visuals from missing_story_requirements.",
                "Visual Production",
            )
        if not timeline_ready:
            return (
                "timeline missing",
                "Build movie runtime timeline from available approved assets.",
                "MovieRuntimeRC1",
            )
        if not render_exists:
            return (
                "render missing",
                "Run RC1 render to produce MP4 and render reports.",
                "RenderEngineRC1",
            )
        if render_incomplete:
            return (
                "incomplete visual coverage",
                "Generate missing visual coverage for skipped timeline shots.",
                "Visual Production",
            )
        if not render_ready:
            return (
                "render missing",
                "Re-run render pipeline to complete final MP4 output.",
                "RenderEngineRC1",
            )
        return (
            "none",
            "Assemble final release package and hand off for delivery.",
            "Release Packaging",
        )

    def _build_brief(self, status: dict[str, Any]) -> str:
        current_stage = self._stage_name(status)
        lines = [
            "# Production Director Brief",
            "",
            f"- project: {status['project_id']}",
            f"- days remaining: {status['deadline_days_remaining']}",
            f"- readiness percentage: {status['release_progress_percent']}%",
            f"- current stage: {current_stage}",
            f"- main blocker: {status['main_blocker']}",
            f"- next action: {status['next_action']}",
            f"- module to run: {status['next_module']}",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _stage_name(status: dict[str, Any]) -> str:
        if not status.get("script_ready"):
            return "story planning"
        if not status.get("voice_ready"):
            return "voice production"
        if status.get("images_missing", 0) > 0:
            return "visual production"
        if not status.get("timeline_ready"):
            return "timeline assembly"
        if not status.get("render_ready"):
            return "rendering"
        return "release packaging"

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _read_csv_rows(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8", newline="") as fh:
                return [dict(row) for row in csv.DictReader(fh)]
        except UnicodeDecodeError:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                return [dict(row) for row in csv.DictReader(fh)]
        except Exception:
            return []