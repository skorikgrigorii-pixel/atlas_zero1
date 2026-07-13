from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import ROOT


IMAGE_MEDIA_TYPE = "image"
VIDEO_MEDIA_TYPE = "video"
SKIP_ASSET_MARKER = "НУЖНО СОЗДАТЬ"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


@dataclass
class ClipSpec:
    shot_id: str
    shot_index: int
    media_type: str
    asset: str
    asset_path: str
    duration_sec: float


class RenderEngineRC1:
    """Local-first renderer for Franklin RC1 timeline export."""

    def __init__(self, project_id: str = "franklin", root_dir: Path | None = None) -> None:
        self.project_id = project_id
        self.root_dir = Path(root_dir) if root_dir is not None else ROOT
        self.workspace_dir = self.root_dir / "workspace"
        self.export_dir = self.workspace_dir / "exports" / project_id
        self.runtime_timeline_path = self.export_dir / "movie_runtime_rc1" / "timeline.json"
        self.fallback_timeline_path = self.export_dir / "native_timeline_model.json"
        self.output_dir = self.export_dir / "render_rc1"
        self.output_mp4 = self.output_dir / "franklin_render_rc1.mp4"
        self.report_path = self.output_dir / "render_report.json"
        self.manifest_path = self.output_dir / "render_manifest.json"
        self.skipped_path = self.output_dir / "skipped_missing_assets.json"
        self.temp_dir = self.output_dir / "_tmp"

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_path = shutil.which("ffmpeg")
        timeline_rows, timeline_source = self._load_timeline()

        clips, skipped = self._collect_assigned_clips(timeline_rows)
        self.skipped_path.write_text(json.dumps(skipped, ensure_ascii=False, indent=2), encoding="utf-8")

        report: dict[str, Any] = {
            "project_id": self.project_id,
            "state": "PENDING",
            "timeline_source": str(timeline_source),
            "target": {"resolution": "1920x1080", "fps": 30},
            "ffmpeg": ffmpeg_path,
            "clips_total": len(timeline_rows),
            "clips_renderable": len(clips),
            "clips_skipped": len(skipped),
            "output_mp4": str(self.output_mp4),
            "output_mp4_exists": False,
            "voice_over": None,
        }

        manifest: dict[str, Any] = {
            "project_id": self.project_id,
            "timeline_source": str(timeline_source),
            "output_dir": str(self.output_dir),
            "outputs": {
                "mp4": str(self.output_mp4),
                "render_report": str(self.report_path),
                "render_manifest": str(self.manifest_path),
                "skipped_missing_assets": str(self.skipped_path),
            },
            "clips": [clip.__dict__ for clip in clips],
            "skipped": skipped,
            "ffmpeg": ffmpeg_path,
        }

        if not ffmpeg_path:
            report["state"] = "FFMPEG_MISSING"
            report["error"] = "ffmpeg is not available in PATH"
            self._write_json_outputs(report, manifest)
            return report

        if not clips:
            report["state"] = "RENDERED"
            report["note"] = "No renderable clips found. Created reports only."
            self._write_json_outputs(report, manifest)
            return report

        try:
            self._reset_temp_dir()
            segment_paths = self._render_segments(ffmpeg_path, clips)
            concatenated_video = self._concat_segments(ffmpeg_path, segment_paths)
            voice_path = self._discover_voice_over()
            report["voice_over"] = str(voice_path) if voice_path else None

            if voice_path:
                video_duration = round(sum(clip.duration_sec for clip in clips), 3)
                self._mux_voice_over(ffmpeg_path, concatenated_video, voice_path, video_duration)
            else:
                shutil.copyfile(concatenated_video, self.output_mp4)

            report["state"] = "RENDERED"
            report["output_mp4_exists"] = self.output_mp4.exists()
            report["rendered_clips"] = len(segment_paths)
        except Exception as exc:
            report["state"] = "FAILED"
            report["error"] = str(exc)

        self._write_json_outputs(report, manifest)
        return report

    def _load_timeline(self) -> tuple[list[dict[str, Any]], Path]:
        source = self.runtime_timeline_path if self.runtime_timeline_path.exists() else self.fallback_timeline_path
        if not source.exists():
            raise FileNotFoundError(
                "Timeline not found. Expected one of: "
                f"{self.runtime_timeline_path} or {self.fallback_timeline_path}"
            )

        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = [dict(row) for row in payload]
            return rows, source

        tracks = payload.get("tracks", []) if isinstance(payload, dict) else []
        clips: list[dict[str, Any]] = []
        for track in tracks:
            if str(track.get("type", "")).lower() != "video":
                continue
            for clip in track.get("clips", []):
                clips.append(
                    {
                        "shot_id": clip.get("shot_id"),
                        "shot_index": clip.get("idx"),
                        "start_sec": clip.get("start"),
                        "end_sec": clip.get("end"),
                        "duration_sec": clip.get("duration"),
                        "status": clip.get("status"),
                        "asset_name": clip.get("asset"),
                        "asset_path": clip.get("asset_path"),
                        "media_type": clip.get("media_type"),
                    }
                )
        return clips, source

    def _collect_assigned_clips(self, rows: list[dict[str, Any]]) -> tuple[list[ClipSpec], list[dict[str, Any]]]:
        clips: list[ClipSpec] = []
        skipped: list[dict[str, Any]] = []

        for idx, row in enumerate(rows, start=1):
            shot_id = str(row.get("shot_id") or f"shot_{idx:04d}")
            shot_index = int(row.get("shot_index") or row.get("idx") or idx)
            media_type = str(row.get("media_type") or "").strip().lower()
            status = str(row.get("status") or "").strip().lower()
            asset = str(row.get("asset_name") or row.get("asset") or "").strip()
            asset_path = str(row.get("asset_path") or "").strip()

            duration_raw = row.get("duration_sec", row.get("duration"))
            if duration_raw is None:
                start = float(row.get("start_sec", row.get("start", 0.0)) or 0.0)
                end = float(row.get("end_sec", row.get("end", start)) or start)
                duration = max(0.01, end - start)
            else:
                duration = max(0.01, float(duration_raw))

            skip_reason = self._skip_reason(media_type, status, asset, asset_path)
            if skip_reason:
                skipped.append(
                    {
                        "shot_id": shot_id,
                        "shot_index": shot_index,
                        "reason": skip_reason,
                        "status": status,
                        "asset": asset,
                        "asset_path": asset_path,
                        "media_type": media_type,
                    }
                )
                continue

            path_obj = Path(asset_path)
            if not path_obj.exists() or not path_obj.is_file():
                skipped.append(
                    {
                        "shot_id": shot_id,
                        "shot_index": shot_index,
                        "reason": "asset_not_found",
                        "status": status,
                        "asset": asset,
                        "asset_path": asset_path,
                        "media_type": media_type,
                    }
                )
                continue

            clips.append(
                ClipSpec(
                    shot_id=shot_id,
                    shot_index=shot_index,
                    media_type=media_type,
                    asset=asset,
                    asset_path=asset_path,
                    duration_sec=round(duration, 3),
                )
            )

        clips.sort(key=lambda item: item.shot_index)
        return clips, skipped

    @staticmethod
    def _skip_reason(media_type: str, status: str, asset: str, asset_path: str) -> str | None:
        if status == "missing":
            return "status_missing"
        if asset == SKIP_ASSET_MARKER:
            return "asset_needs_creation"
        if not asset_path:
            return "asset_path_empty"
        if media_type not in {IMAGE_MEDIA_TYPE, VIDEO_MEDIA_TYPE}:
            return "media_type_not_supported"
        return None

    def _reset_temp_dir(self) -> None:
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _render_segments(self, ffmpeg_path: str, clips: list[ClipSpec]) -> list[Path]:
        segments: list[Path] = []
        for index, clip in enumerate(clips, start=1):
            out_segment = self.temp_dir / f"segment_{index:04d}.mp4"
            if clip.media_type == IMAGE_MEDIA_TYPE:
                cmd = [
                    ffmpeg_path,
                    "-y",
                    "-loop",
                    "1",
                    "-t",
                    str(clip.duration_sec),
                    "-i",
                    clip.asset_path,
                    "-r",
                    "30",
                    "-vf",
                    "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(out_segment),
                ]
            else:
                cmd = [
                    ffmpeg_path,
                    "-y",
                    "-i",
                    clip.asset_path,
                    "-t",
                    str(clip.duration_sec),
                    "-r",
                    "30",
                    "-vf",
                    "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(out_segment),
                ]
            self._run_ffmpeg(cmd, f"segment {clip.shot_id}")
            segments.append(out_segment)
        return segments

    def _concat_segments(self, ffmpeg_path: str, segments: list[Path]) -> Path:
        concat_input = self.temp_dir / "concat_input.txt"
        concat_lines = [f"file '{segment.as_posix()}'" for segment in segments]
        concat_input.write_text("\n".join(concat_lines), encoding="utf-8")

        output = self.temp_dir / "render_no_audio.mp4"
        cmd = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_input),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output),
        ]
        self._run_ffmpeg(cmd, "concat segments")
        return output

    def _discover_voice_over(self) -> Path | None:
        audio_dir = self.workspace_dir / "projects" / self.project_id / "01_Audio"
        if not audio_dir.exists():
            return None

        candidates = [
            path
            for path in sorted(audio_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        ]
        return candidates[0] if candidates else None

    def _mux_voice_over(self, ffmpeg_path: str, video_path: Path, audio_path: Path, video_duration: float) -> None:
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-t",
            str(video_duration),
            str(self.output_mp4),
        ]
        self._run_ffmpeg(cmd, "mux voice-over")

    @staticmethod
    def _run_ffmpeg(cmd: list[str], step: str) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            stderr_tail = "\n".join(proc.stderr.splitlines()[-10:])
            raise RuntimeError(f"ffmpeg failed during {step}: {stderr_tail}")

    def _write_json_outputs(self, report: dict[str, Any], manifest: dict[str, Any]) -> None:
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def run_render(project_id: str = "franklin") -> dict[str, Any]:
    return RenderEngineRC1(project_id=project_id).run()
