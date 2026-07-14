from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from .database import Database
from .director_ai import DirectorAI
from .director_ai_runtime import DirectorAIRuntime
from .final_assembly_pack import FinalAssemblyPack
from .events import EventBus
from .paths import EXPORTS, MEDIA_DIRS, PROJECTS
from .story_engine import StoryEngine
from .story_engine_runtime import StoryEngineRuntime
from .timeline_studio import TimelineStudio
from .timeline_engine_rc2 import TimelineEngineRC2


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


class MovieRuntimeRC1:
    """Minimal local movie runtime for RC1.

    This runtime intentionally avoids external APIs and networking.
    It transforms an existing production script and existing voice assets
    into a local movie package that is ready for manual upload.
    """

    def __init__(self, db: Database, project_id: str):
        self.db = db
        self.project_id = project_id
        self.db.init()
        self.bus = EventBus(db, project_id)
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir = self.export_dir / "movie_runtime_rc1"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.project_dir = PROJECTS / project_id
        self._ensure_project()

    def _ensure_project(self) -> None:
        row = self.db.one("SELECT id FROM projects WHERE id=?", (self.project_id,))
        if not row:
            self.db.execute(
                "INSERT INTO projects(id, title, status) VALUES(?,?,?)",
                (self.project_id, self.project_id, "NEW"),
            )

    def _job(self, stage: str, status: str, details: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO workflow_jobs(project_id,stage,status,details) VALUES(?,?,?,?)",
            (self.project_id, stage, status, json.dumps(details, ensure_ascii=False)),
        )

    @staticmethod
    def _media_kind(path: Path) -> str | None:
        suffix = path.suffix.lower()
        if suffix in AUDIO_EXTENSIONS:
            return "audio"
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        if suffix in VIDEO_EXTENSIONS:
            return "video"
        return None

    def _scan_project_assets(self) -> dict[str, list[dict[str, Any]]]:
        assets: dict[str, list[dict[str, Any]]] = {"audio": [], "image": [], "video": []}
        for media_kind, folder_name in MEDIA_DIRS.items():
            if media_kind not in assets:
                continue
            folder = self.project_dir / folder_name
            if not folder.exists():
                continue
            for path in sorted(folder.rglob("*")):
                if not path.is_file():
                    continue
                detected_kind = self._media_kind(path)
                if detected_kind != media_kind:
                    continue
                rel_path = path.relative_to(self.project_dir).as_posix()
                assets[media_kind].append(
                    {
                        "path": str(path),
                        "relative_path": rel_path,
                        "filename": path.name,
                        "media_type": media_kind,
                        "size_bytes": path.stat().st_size,
                    }
                )
        return assets

    def _sync_project_assets(self, assets: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        synced = {"audio": 0, "image": 0, "video": 0}
        existing_paths = {
            row["path"]
            for row in self.db.rows(
                "SELECT path FROM assets WHERE project_id=?",
                (self.project_id,),
            )
        }
        for media_kind, rows in assets.items():
            for asset in rows:
                if asset["path"] in existing_paths:
                    continue
                asset_id = f"{self.project_id}:{media_kind}:{asset['relative_path'].replace('/', '__')}"
                self.db.execute(
                    "INSERT OR IGNORE INTO assets(id, project_id, path, filename, media_type, category, quality, duration_sec) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        asset_id,
                        self.project_id,
                        asset["path"],
                        asset["filename"],
                        media_kind,
                        media_kind,
                        1.0,
                        None,
                    ),
                )
                synced[media_kind] += 1
        return synced

    def _discover_script_path(self) -> Path | None:
        step = self.db.one(
            "SELECT result_json FROM workflow_steps WHERE project_id=? AND step_key='script_ready' ORDER BY id DESC LIMIT 1",
            (self.project_id,),
        )
        if step and step["result_json"]:
            try:
                payload = json.loads(step["result_json"])
                artifact = payload.get("artifact")
                if artifact:
                    p = Path(str(artifact))
                    if p.exists() and p.is_file():
                        return p
            except Exception:
                pass
        candidates = [
            PROJECTS / self.project_id / "script" / "final.txt",
            PROJECTS / self.project_id / "script" / "production_script.txt",
            PROJECTS / self.project_id / "production_script.txt",
            self.export_dir / "production_script.txt",
            self.project_dir / "production_script.txt",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _load_production_script(self) -> dict[str, Any]:
        path = self._discover_script_path()
        if not path:
            raise ValueError("Production Script not found. Add script artifact before running movie runtime.")
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise ValueError("Production Script is empty.")
        return {
            "path": str(path),
            "line_count": len(lines),
            "char_count": len(text),
            "estimated_duration_sec": max(120.0, len(lines) * 5.5),
        }

    def _load_voice_assets(self) -> dict[str, Any]:
        scanned_assets = self._scan_project_assets()
        self._sync_project_assets(scanned_assets)
        rows = self.db.rows(
            "SELECT id,path,filename,duration_sec FROM assets WHERE project_id=? AND media_type='audio' ORDER BY created_at",
            (self.project_id,),
        )
        voices = [dict(r) for r in rows]
        if not voices:
            raise ValueError("Voice assets not found. Add at least one audio asset.")
        total_duration = round(sum(float(v.get("duration_sec") or 0.0) for v in voices), 3)
        return {
            "count": len(voices),
            "total_duration_sec": total_duration,
            "assets": voices,
        }

    def _build_scene_and_shots(self, script: dict[str, Any]) -> dict[str, Any]:
        # RC1 shot-generation mode.
        # The approved production script defines the narrative structure,
        # while the number of montage shots is calculated from film duration.
        shot_mode = "production_script"

        duration_sec = max(
            180.0,
            float(script["estimated_duration_sec"]),
        )

        if shot_mode == "production_script":
            # Documentary pacing: approximately one montage shot
            # every 6.5 seconds.
            average_shot_duration_sec = 6.5

            target_shots = round(
                duration_sec / average_shot_duration_sec
            )

            # Safety limits for an RC1 documentary film.
            target_shots = min(
                180,
                max(120, target_shots),
            )

        elif shot_mode == "auto_storyboard":
            target_shots = min(
                220,
                max(24, int(script["line_count"] * 1.6)),
            )

        else:
            raise ValueError(
                f"Unknown shot mode: {shot_mode}. "
                "Expected production_script or auto_storyboard."
            )
        result = StoryEngine(self.db, self.project_id).build_shots(
            target_count=target_shots,
            duration_sec=duration_sec,
        )
        scene_count = self.db.one(
            "SELECT COUNT(*) c FROM story_scenes WHERE project_id=?",
            (self.project_id,),
        )["c"]
        shot_count = self.db.one(
            "SELECT COUNT(*) c FROM shots WHERE project_id=?",
            (self.project_id,),
        )["c"]
        return {
            "story_engine": result,
            "scenes": int(scene_count),
            "shots": int(shot_count),
        }

    def _generate_visual_task_list(self) -> dict[str, Any]:
        rows = self.db.rows(
            "SELECT id,idx,block,visual_need,emotion,story_goal FROM shots WHERE project_id=? ORDER BY idx",
            (self.project_id,),
        )
        tasks = [
            {
                "shot_id": r["id"],
                "shot_index": r["idx"],
                "block": r["block"],
                "visual_need": r["visual_need"],
                "emotion": r["emotion"],
                "story_goal": r["story_goal"],
            }
            for r in rows
        ]
        out = self.export_dir / "visual_task_list.json"
        out.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"tasks": len(tasks), "artifact": str(out)}

    def _execute_visual_generator(self) -> dict[str, Any]:
        result = DirectorAI(self.db, self.project_id).assign_assets()
        return result if isinstance(result, dict) else {"result": result}

    def _execute_review_agent(self) -> dict[str, Any]:
        try:
            story_report = StoryEngineRuntime(self.db, self.project_id).build()
        except Exception as exc:
            story_report = {"readiness": 0, "fallback": str(exc)}
        try:
            review_report = DirectorAIRuntime(self.db, self.project_id).analyze()
        except Exception as exc:
            review_report = {"quality": {"overall": 0}, "summary": {"issues": 1, "tasks": 0}, "fallback": str(exc)}
        return {
            "story_readiness": story_report.get("readiness", 0),
            "quality_score": review_report.get("quality", {}).get("overall", 0),
            "issues": review_report.get("summary", {}).get("issues", 0),
            "tasks": review_report.get("summary", {}).get("tasks", 0),
        }

    def _build_timeline(self) -> dict[str, Any]:
        """Legacy compatibility wrapper.

        TimelineEngineRC2 owns canonical timeline creation.
        """
        from .project_config_rc2 import ProjectConfigRC2

        config = ProjectConfigRC2(
            project_id=self.project_id,
        )

        return TimelineEngineRC2(
            self.db,
            config,
        ).run()

    def _synchronize_audio(self, voice: dict[str, Any]) -> dict[str, Any]:
        shots = self.db.rows(
            "SELECT idx,start_sec,end_sec,story_goal FROM shots WHERE project_id=? ORDER BY idx",
            (self.project_id,),
        )
        total_timeline = max((float(r["end_sec"]) for r in shots), default=0.0)
        sync = {
            "project_id": self.project_id,
            "timeline_duration_sec": round(total_timeline, 3),
            "voice_duration_sec": float(voice.get("total_duration_sec") or 0.0),
            "tracks": [
                {
                    "track": "narration",
                    "assets": voice.get("assets", []),
                    "start_sec": 0.0,
                    "end_sec": round(total_timeline, 3),
                }
            ],
            "shot_cues": [
                {
                    "shot_index": r["idx"],
                    "start_sec": r["start_sec"],
                    "end_sec": r["end_sec"],
                    "cue": (r["story_goal"] or "")[:180],
                }
                for r in shots
            ],
        }
        sync_json = self.export_dir / "audio_sync_map.json"
        sync_json.write_text(json.dumps(sync, ensure_ascii=False, indent=2), encoding="utf-8")

        sync_csv = self.export_dir / "audio_sync_map.csv"
        with sync_csv.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["shot_index", "start_sec", "end_sec", "cue"])
            for cue in sync["shot_cues"]:
                writer.writerow([cue["shot_index"], cue["start_sec"], cue["end_sec"], cue["cue"]])
        return {
            "artifact_json": str(sync_json),
            "artifact_csv": str(sync_csv),
            "timeline_duration_sec": sync["timeline_duration_sec"],
            "voice_duration_sec": sync["voice_duration_sec"],
        }

    def _render_movie(self) -> dict[str, Any]:
        out_movie = self.runtime_dir / "movie_render_stub.mp4"
        out_movie.write_bytes(b"")
        manifest = {
            "project_id": self.project_id,
            "mode": "local_stub_render",
            "output": str(out_movie),
            "note": "RC1 local runtime does not call external render services.",
        }
        manifest_path = self.runtime_dir / "render_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"output": str(out_movie), "manifest": str(manifest_path)}

    def _package_output(self, stage_results: dict[str, Any]) -> dict[str, Any]:
        package_dir = self.runtime_dir
        package_dir.mkdir(parents=True, exist_ok=True)

        package_manifest = {
            "project_id": self.project_id,
            "final_state": "READY_FOR_MANUAL_EDIT",
            "stages": stage_results,
            "files": [],
            "networking": "disabled",
            "youtube_upload": "not_executed",
        }
        assets = self._scan_project_assets()
        asset_inventory = {
            "project_id": self.project_id,
            "audio": assets["audio"],
            "image": assets["image"],
            "video": assets["video"],
            "counts": {key: len(value) for key, value in assets.items()},
        }
        asset_inventory_path = package_dir / "asset_inventory.json"
        asset_inventory_path.write_text(json.dumps(asset_inventory, ensure_ascii=False, indent=2), encoding="utf-8")

        timeline_json = package_dir / "timeline.json"
        timeline_csv = package_dir / "timeline.csv"
        manual_edit_md = package_dir / "manual_edit_package.md"
        missing_assets_md = package_dir / "missing_assets.md"

        missing_lines = ["# Missing Assets", ""]
        for media_kind in ("audio", "image", "video"):
            if not assets[media_kind]:
                missing_lines.append(f"- {media_kind}: none detected")
        if len(missing_lines) == 2:
            missing_lines.append("- none")
        missing_assets_md.write_text("\n".join(missing_lines), encoding="utf-8")

        timeline_rows = json.loads(timeline_json.read_text(encoding="utf-8")) if timeline_json.exists() else []
        manual_edit_md.write_text(
            "\n".join(
                [
                    "# Movie Runtime RC1 Manual Edit Package",
                    "",
                    f"Project: {self.project_id}",
                    "",
                    "## Ready State",
                    "- READY_FOR_MANUAL_EDIT",
                    "- No YouTube upload",
                    "- No networking",
                    "",
                    "## Outputs",
                    f"- timeline.json: {timeline_json.name}",
                    f"- timeline.csv: {timeline_csv.name}",
                    f"- asset_inventory.json: {asset_inventory_path.name}",
                    f"- missing_assets.md: {missing_assets_md.name}",
                    "",
                    f"Detected assets: audio={len(assets['audio'])}, image={len(assets['image'])}, video={len(assets['video'])}",
                    f"Timeline items: {len(timeline_rows)}",
                    "",
                    "## Next Step",
                    "Open this folder in an editor and make the manual cut using the detected media and timeline.",
                ]
            ),
            encoding="utf-8",
        )

        package_manifest["files"] = [
            str(timeline_json),
            str(timeline_csv),
            str(manual_edit_md),
            str(asset_inventory_path),
            str(missing_assets_md),
        ]
        manifest_path = package_dir / "movie_package_manifest.json"
        manifest_path.write_text(json.dumps(package_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        package_manifest["files"].append(str(manifest_path))

        archive_base = self.export_dir / f"{self.project_id}_READY_FOR_MANUAL_EDIT"
        archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=package_dir)
        return {
            "package_dir": str(package_dir),
            "package_zip": archive_path,
            "files": package_manifest["files"],
        }

    def run(self) -> dict[str, Any]:
        stages: dict[str, dict[str, Any]] = {}

        script = self._load_production_script()
        stages["1_load_production_script"] = script
        self._job("movie_runtime_stage_1", "done", script)

        voice = self._load_voice_assets()
        stages["2_load_voice_assets"] = voice
        self._job("movie_runtime_stage_2", "done", voice)

        structure = self._build_scene_and_shots(script)
        stages["3_build_scene_objects"] = {"scenes": structure["scenes"]}
        self._job("movie_runtime_stage_3", "done", stages["3_build_scene_objects"])
        stages["4_build_shot_objects"] = {"shots": structure["shots"]}
        self._job("movie_runtime_stage_4", "done", stages["4_build_shot_objects"])

        visual_tasks = self._generate_visual_task_list()
        stages["5_generate_visual_task_list"] = visual_tasks
        self._job("movie_runtime_stage_5", "done", visual_tasks)

        visual_result = self._execute_visual_generator()
        stages["6_execute_visual_generator"] = visual_result
        self._job("movie_runtime_stage_6", "done", visual_result)

        review = self._execute_review_agent()
        stages["7_execute_review_agent"] = review
        self._job("movie_runtime_stage_7", "done", review)

        timeline = self._build_timeline()
        stages["8_build_timeline"] = timeline
        self._job("movie_runtime_stage_8", "done", timeline)

        audio_sync = self._synchronize_audio(voice)
        stages["9_synchronize_audio"] = audio_sync
        self._job("movie_runtime_stage_9", "done", audio_sync)

        render = self._render_movie()
        stages["10_render_movie"] = render
        self._job("movie_runtime_stage_10", "done", render)

        package = self._package_output(stages)
        stages["11_package_output"] = package
        self._job("movie_runtime_stage_11", "done", package)

        final_state = "READY_FOR_MANUAL_EDIT"
        self.db.execute(
            "UPDATE projects SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (final_state, self.project_id),
        )
        self.bus.emit("MOVIE_RUNTIME_RC1_COMPLETED", {"final_state": final_state, "package": package})

        return {
            "project_id": self.project_id,
            "final_state": final_state,
            "stages": stages,
            "package_dir": package["package_dir"],
            "package_zip": package["package_zip"],
            "networking": False,
        }


def run_movie(project_id: str, db: Database | None = None) -> dict[str, Any]:
    if db is None:
        db = Database()
    return MovieRuntimeRC1(db, project_id).run()
