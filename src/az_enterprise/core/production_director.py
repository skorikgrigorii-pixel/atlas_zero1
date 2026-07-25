from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .paths import ROOT
from .project_config_rc2 import ProjectConfigRC2


class ProductionDirector:
    """RC2 production-status orchestrator.

    Reads only canonical RC2 artifacts and determines the next production step.
    The public constructor and ``run()`` contract remain compatible with the
    previous ProductionDirector implementation.
    """

    def __init__(
        self,
        project_id: str,
        deadline_days_remaining: int = 4,
        root_dir: Path | None = None,
    ) -> None:
        self.project_id = project_id
        self.deadline_days_remaining = int(deadline_days_remaining)
        self.root_dir = Path(root_dir) if root_dir is not None else ROOT
        self.config = ProjectConfigRC2(
            project_id=project_id,
            root_dir=self.root_dir,
        )
        self.export_dir = self.config.export_dir
        self.rc2_dir = self.config.rc2_dir

    def run(self) -> dict[str, Any]:
        status = self._build_status()

        self.rc2_dir.mkdir(parents=True, exist_ok=True)
        status_path = self.rc2_dir / "production_director_status.json"
        brief_path = self.rc2_dir / "production_director_brief.md"

        self._write_json(status_path, status)
        brief_path.write_text(
            self._build_brief(status),
            encoding="utf-8",
        )

        return status

    def _build_status(self) -> dict[str, Any]:
        production_state = self._read_json(self.config.state_path) or {}
        timeline_payload = self._read_json(self.config.timeline_path)
        timeline_rows = self._extract_timeline_rows(timeline_payload)

        missing_story_requirements = self._read_json(
            self.export_dir / "missing_story_requirements.json"
        )
        director_tasks = self._read_csv_rows(
            self.export_dir / "director_tasks.csv"
        )

        render_dir = self.config.canonical_render_path.parent
        render_report = self._read_json(
            render_dir / "render_report_rc2.json"
        )
        render_model = self._read_json(
            render_dir / "render_model_rc2.json"
        ) or {}
        render_validation = self._read_json(
            render_dir / "render_validation_rc2.json"
        ) or {}

        script_ready = self._script_ready(
            production_state=production_state,
            timeline_rows=timeline_rows,
            director_tasks=director_tasks,
        )

        media_counts = self._count_timeline_media(timeline_rows)
        images_found = media_counts["image"]
        videos_found = media_counts["video"]
        assigned_assets = media_counts["assigned"]
        missing_assets = media_counts["missing"]

        voice_path = self._discover_voice_path()
        voice_ready = voice_path is not None

        if isinstance(missing_story_requirements, list):
            images_missing = max(
                len(missing_story_requirements),
                missing_assets,
            )
        else:
            images_missing = max(
                int(production_state.get("missing", 0) or 0),
                missing_assets,
            )

        timeline_ready = bool(timeline_rows)
        timeline_duration_sec = self._timeline_duration(timeline_rows)

        render_exists = isinstance(render_report, dict)
        render_state = str(
            (render_report or {}).get("state", "")
        ).upper()

        render_output = Path(
            str(
                (render_report or {}).get("output")
                or self.config.canonical_render_path
            )
        )
        render_output_exists = (
            render_output.exists()
            and render_output.is_file()
        )

        render_ready = (
            render_exists
            and render_state == "RENDERED_VERIFIED"
            and render_output_exists
        )

        clips_total = int(
            (render_report or {}).get(
                "clips_total",
                len(timeline_rows),
            )
            or 0
        )
        clips_renderable = int(
            (render_report or {}).get(
                "clips_renderable",
                len((render_model or {}).get("clips", [])),
            )
            or 0
        )
        clips_skipped = int(
            (render_report or {}).get(
                "clips_skipped",
                len((render_model or {}).get("skipped", [])),
            )
            or 0
        )

        blocking_errors = list(
            render_validation.get("blocking_errors", [])
        ) if isinstance(render_validation, dict) else []

        render_incomplete = (
            bool(blocking_errors)
            or clips_skipped > 0
            or (
                clips_total > 0
                and clips_renderable < clips_total
            )
        )

        render_duration_sec = self._render_duration(
            render_report=render_report,
            fallback=timeline_duration_sec,
        )

        state_flags = [
            script_ready,
            voice_ready,
            images_missing == 0,
            timeline_ready,
            render_ready and not render_incomplete,
        ]
        release_progress_percent = round(
            sum(1 for flag in state_flags if flag)
            / len(state_flags)
            * 100,
            1,
        )

        main_blocker, next_action, next_module = (
            self._decide_next_step(
                script_ready=script_ready,
                voice_ready=voice_ready,
                images_missing=images_missing,
                timeline_ready=timeline_ready,
                render_exists=render_exists,
                render_ready=render_ready,
                render_incomplete=render_incomplete,
            )
        )

        operator_message = (
            f"Project {self.project_id}: blocker "
            f"'{main_blocker}'. Run {next_module} now: "
            f"{next_action}"
        )

        return {
            "schema": "atlas_zero.production_director.rc2.v1",
            "authority": "ProductionDirectorRC2",
            "project_id": self.project_id,
            "deadline_days_remaining": self.deadline_days_remaining,
            "script_ready": script_ready,
            "voice_ready": voice_ready,
            "voice_path": str(voice_path) if voice_path else None,
            "assigned_assets": assigned_assets,
            "images_found": images_found,
            "images_missing": images_missing,
            "videos_found": videos_found,
            "timeline_ready": timeline_ready,
            "timeline_path": str(self.config.timeline_path),
            "timeline_items": len(timeline_rows),
            "timeline_duration_sec": timeline_duration_sec,
            "render_exists": render_exists,
            "render_ready": render_ready,
            "render_incomplete": render_incomplete,
            "render_state": render_state or None,
            "render_path": str(self.config.canonical_render_path),
            "render_duration_sec": render_duration_sec,
            "clips_total": clips_total,
            "clips_renderable": clips_renderable,
            "clips_skipped": clips_skipped,
            "render_blocking_errors": blocking_errors,
            "release_progress_percent": release_progress_percent,
            "main_blocker": main_blocker,
            "next_action": next_action,
            "next_module": next_module,
            "operator_message": operator_message,
        }

    @staticmethod
    def _script_ready(
        *,
        production_state: dict[str, Any],
        timeline_rows: list[dict[str, Any]],
        director_tasks: list[dict[str, str]],
    ) -> bool:
        if timeline_rows:
            return True
        if int(production_state.get("shots", 0) or 0) > 0:
            return True
        return bool(director_tasks)

    @staticmethod
    def _extract_timeline_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [
                dict(row)
                for row in payload
                if isinstance(row, dict)
            ]

        if not isinstance(payload, dict):
            return []

        if isinstance(payload.get("timeline"), list):
            return [
                dict(row)
                for row in payload["timeline"]
                if isinstance(row, dict)
            ]

        rows: list[dict[str, Any]] = []
        for track in payload.get("tracks", []):
            if not isinstance(track, dict):
                continue
            if str(track.get("type", "")).lower() != "video":
                continue
            for clip in track.get("clips", []):
                if isinstance(clip, dict):
                    rows.append(dict(clip))
        return rows

    @staticmethod
    def _count_timeline_media(
        rows: list[dict[str, Any]],
    ) -> dict[str, int]:
        counts = {
            "image": 0,
            "video": 0,
            "assigned": 0,
            "missing": 0,
        }

        missing_statuses = {
            "missing",
            "rejected",
            "excluded",
            "disabled",
        }

        for row in rows:
            media_type = str(
                row.get("media_type") or ""
            ).strip().lower()
            status = str(
                row.get("status") or "assigned"
            ).strip().lower()
            asset_path = str(
                row.get("asset_path") or ""
            ).strip()

            if media_type == "image":
                counts["image"] += 1
            elif media_type == "video":
                counts["video"] += 1

            if (
                status in missing_statuses
                or not asset_path
            ):
                counts["missing"] += 1
            else:
                counts["assigned"] += 1

        return counts

    def _discover_voice_path(self) -> Path | None:
        audio_dir = self.config.project_dir / "01_Audio"
        candidates = (
            self.config.master_audio_path,
            audio_dir / "voice_master.wav",
            audio_dir / "voice_master.m4a",
            audio_dir / "voice_master.mp3",
        )

        seen: set[Path] = set()
        for candidate in candidates:
            path = Path(candidate)
            if path in seen:
                continue
            seen.add(path)
            if path.exists() and path.is_file():
                return path
        return None

    @staticmethod
    def _timeline_duration(
        rows: list[dict[str, Any]],
    ) -> float:
        maximum = 0.0
        for row in rows:
            try:
                end_sec = float(
                    row.get(
                        "end_sec",
                        row.get("end", 0.0),
                    )
                    or 0.0
                )
            except (TypeError, ValueError):
                continue
            maximum = max(maximum, end_sec)
        return round(maximum, 3)

    @staticmethod
    def _render_duration(
        *,
        render_report: Any,
        fallback: float,
    ) -> float:
        if not isinstance(render_report, dict):
            return fallback

        candidates = (
            render_report.get("expected_duration_sec"),
            (render_report.get("media_probe") or {})
            .get("format", {})
            .get("duration")
            if isinstance(render_report.get("media_probe"), dict)
            else None,
        )

        for value in candidates:
            try:
                duration = float(value)
            except (TypeError, ValueError):
                continue
            if duration >= 0:
                return round(duration, 3)

        return fallback

    @staticmethod
    def _decide_next_step(
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
                "Generate and approve the production script.",
                "Story Engine RC2",
            )

        if not voice_ready:
            return (
                "voice missing",
                "Produce the canonical voice_master audio track.",
                "Voice Production RC2",
            )

        if images_missing > 0:
            return (
                "visual assets missing",
                "Resolve missing or unassigned timeline visuals.",
                "Visual Production RC2",
            )

        if not timeline_ready:
            return (
                "timeline missing",
                "Build the canonical RC2 timeline.",
                "TimelineEngineRC2",
            )

        if not render_exists:
            return (
                "render missing",
                "Run the canonical RC2 render pipeline.",
                "RenderEngineRC2",
            )

        if render_incomplete:
            return (
                "render validation failed",
                "Resolve skipped clips and blocking render-validation errors.",
                "Visual Production RC2",
            )

        if not render_ready:
            return (
                "render incomplete",
                "Re-run RenderEngineRC2 and verify the canonical output.",
                "RenderEngineRC2",
            )

        return (
            "none",
            "Assemble the final release package.",
            "Release Packaging",
        )

    def _build_brief(self, status: dict[str, Any]) -> str:
        lines = [
            "# Production Director RC2 Brief",
            "",
            f"- project: {status['project_id']}",
            f"- days remaining: {status['deadline_days_remaining']}",
            (
                "- readiness percentage: "
                f"{status['release_progress_percent']}%"
            ),
            f"- current stage: {self._stage_name(status)}",
            f"- main blocker: {status['main_blocker']}",
            f"- next action: {status['next_action']}",
            f"- module to run: {status['next_module']}",
            f"- timeline: {status['timeline_path']}",
            f"- render: {status['render_path']}",
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
            if not path.exists() or not path.is_file():
                return None
            return json.loads(
                path.read_text(encoding="utf-8-sig")
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _read_csv_rows(
        path: Path,
    ) -> list[dict[str, str]]:
        if not path.exists() or not path.is_file():
            return []

        for encoding in ("utf-8", "utf-8-sig"):
            try:
                with path.open(
                    "r",
                    encoding=encoding,
                    newline="",
                ) as handle:
                    return [
                        dict(row)
                        for row in csv.DictReader(handle)
                    ]
            except UnicodeDecodeError:
                continue
            except OSError:
                return []

        return []

    @staticmethod
    def _write_json(
        path: Path,
        payload: dict[str, Any],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(
            path.suffix + ".partial"
        )
        temporary.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
