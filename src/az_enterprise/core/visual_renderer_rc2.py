from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

from .camera_motion_rc2 import CameraMotionEngine, FFmpegMotionBuilder
from .transition_engine_rc2 import (
    FFmpegTransitionGraphBuilder,
    TransitionEngineRC2,
    TransitionProfile,
)


ProgressCallback = Callable[[dict[str, Any]], None]


class VisualRendererRC2:
    """Native RC2 visual backend with camera motion and transition composition."""

    def __init__(
        self,
        *,
        project_id: str,
        output_dir: Path,
        target_width: int = 1920,
        target_height: int = 1080,
        target_fps: int = 30,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.project_id = project_id
        self.output_dir = Path(output_dir)
        self.target_width = int(target_width)
        self.target_height = int(target_height)
        self.target_fps = int(target_fps)
        self.progress = progress or (lambda payload: None)

        self.ffmpeg = shutil.which("ffmpeg")
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg is not available in PATH")
        if self.target_width <= 0 or self.target_height <= 0:
            raise ValueError("Target resolution must be positive")
        if self.target_fps <= 0:
            raise ValueError("Target frame rate must be positive")

        self.motion_engine = CameraMotionEngine(fps=self.target_fps)
        self.motion_builder = FFmpegMotionBuilder(
            width=self.target_width,
            height=self.target_height,
            fps=self.target_fps,
        )

        self.temp_dir = self.output_dir / "_native_visual_tmp"
        self.segment_dir = self.temp_dir / "segments"
        self.group_dir = self.temp_dir / "transition_groups"
        self.output_video = self.output_dir / "visual_master_rc2.mp4"
        self.report_path = self.output_dir / "visual_render_report_rc2.json"
        self.concat_manifest_path = self.temp_dir / "concat_input.txt"

    def run(self, clips: Iterable[Any]) -> dict[str, Any]:
        ordered = sorted(
            list(clips),
            key=lambda clip: (
                float(getattr(clip, "start_sec", 0.0)),
                int(getattr(clip, "shot_index", 0)),
            ),
        )
        if not ordered:
            raise RuntimeError("VisualRendererRC2 received zero clips")

        self._reset_workspace()
        self._emit(
            "VISUAL_RENDER_START",
            project_id=self.project_id,
            clips=len(ordered),
            resolution=f"{self.target_width}x{self.target_height}",
            fps=self.target_fps,
            migration_phase="PHASE_6_NATIVE_TRANSITION_ENGINE",
        )

        segments: list[Path] = []
        durations: list[float] = []
        records: list[dict[str, Any]] = []

        for position, clip in enumerate(ordered, start=1):
            profile = self.motion_engine.build_profile(clip)
            segment = self._render_segment(position, clip, profile)
            duration = float(getattr(clip, "duration_sec", 0.0))
            segments.append(segment)
            durations.append(duration)
            records.append(
                {
                    "position": position,
                    "shot_id": str(getattr(clip, "shot_id", f"shot_{position:04d}")),
                    "shot_index": int(getattr(clip, "shot_index", position)),
                    "media_type": str(getattr(clip, "media_type", "")),
                    "asset_path": str(getattr(clip, "asset_path", "")),
                    "source_in_sec": float(getattr(clip, "source_in_sec", 0.0)),
                    "source_out_sec": getattr(clip, "source_out_sec", None),
                    "duration_sec": duration,
                    "camera_motion": profile.to_dict(),
                    "output": str(segment),
                    "output_size_bytes": segment.stat().st_size,
                }
            )

        transition_profiles = self._build_transition_profiles(ordered, durations)
        composed_parts = self._compose_transition_groups(
            segments,
            durations,
            transition_profiles,
        )
        final_visual = self._concat_segments(composed_parts)
        self._verify_video_output(final_visual)

        temporary = self.output_video.with_suffix(self.output_video.suffix + ".partial")
        temporary.unlink(missing_ok=True)
        shutil.copy2(final_visual, temporary)
        self._verify_video_output(temporary)
        os.replace(temporary, self.output_video)

        moving = sum(1 for row in records if row["camera_motion"]["enabled"])
        enabled_transitions = sum(1 for p in transition_profiles if p.enabled)
        report: dict[str, Any] = {
            "state": "VISUAL_RENDERED",
            "schema": "atlas_zero.visual_render.rc2.v3",
            "project_id": self.project_id,
            "backend": "VisualRendererRC2",
            "migration_phase": "PHASE_6_NATIVE_TRANSITION_ENGINE",
            "output_video": str(self.output_video),
            "output_exists": self.output_video.exists(),
            "output_size_bytes": self.output_video.stat().st_size,
            "target": {
                "width": self.target_width,
                "height": self.target_height,
                "fps": self.target_fps,
                "pixel_format": "yuv420p",
                "video_codec": "libx264",
            },
            "clips_total": len(ordered),
            "segments_rendered": len(segments),
            "motion_segments": moving,
            "static_segments": len(records) - moving,
            "transitions_total": len(transition_profiles),
            "transitions_enabled": enabled_transitions,
            "hard_cuts": len(transition_profiles) - enabled_transitions,
            "transition_profiles": [p.to_dict() for p in transition_profiles],
            "segments": records,
            "concat_manifest": str(self.concat_manifest_path),
            "camera_motion_mode": "native_phase_5",
            "transition_mode": "native_phase_6",
        }
        self._write_json(self.report_path, report)
        self._emit(
            "VISUAL_RENDER_COMPLETE",
            output=str(self.output_video),
            segments=len(segments),
            motion_segments=moving,
            transitions_enabled=enabled_transitions,
        )
        return report

    def _build_transition_profiles(
        self,
        clips: list[Any],
        durations: list[float],
    ) -> list[TransitionProfile]:
        profiles: list[TransitionProfile] = []
        for index in range(len(clips) - 1):
            profile = TransitionEngineRC2.build_profile(
                clips[index],
                left_duration_sec=durations[index],
                right_duration_sec=durations[index + 1],
            )

            # RC2 duration-preservation policy:
            # visual transitions must never shorten the voice-led timeline.
            # Until duration-compensated xfade is implemented, render
            # overlapping transitions as hard cuts.
            if profile.enabled:
                from dataclasses import replace
                profile = replace(
                    profile,
                    transition_type="cut",
                    duration_sec=0.0,
                    enabled=False,
                    ffmpeg_name="cut",
                )

            profiles.append(profile)
            self._emit(
                "TRANSITION_PROFILE",
                left_shot=str(getattr(clips[index], "shot_id", index + 1)),
                right_shot=str(getattr(clips[index + 1], "shot_id", index + 2)),
                transition=profile.transition_type,
                duration_sec=profile.duration_sec,
                enabled=profile.enabled,
                fallback_used=profile.fallback_used,
            )
        return profiles

    def _compose_transition_groups(
        self,
        segments: list[Path],
        durations: list[float],
        profiles: list[TransitionProfile],
    ) -> list[Path]:
        if len(segments) <= 1:
            return segments

        self.group_dir.mkdir(parents=True, exist_ok=True)
        result: list[Path] = []
        start = 0

        while start < len(segments):
            end = start
            while end < len(profiles) and profiles[end].enabled:
                end += 1

            if end == start:
                result.append(segments[start])
                start += 1
                continue

            group_segments = segments[start : end + 1]
            group_durations = durations[start : end + 1]
            group_profiles = profiles[start:end]
            output = self.group_dir / f"group_{start + 1:04d}_{end + 1:04d}.mp4"
            self._render_transition_group(
                group_segments,
                group_durations,
                group_profiles,
                output,
            )
            result.append(output)
            start = end + 1

        return result

    def _render_transition_group(
        self,
        segments: list[Path],
        durations: list[float],
        profiles: list[TransitionProfile],
        output: Path,
    ) -> None:
        graph, output_label, expected_duration = FFmpegTransitionGraphBuilder.build(
            segment_durations=durations,
            profiles=profiles,
        )
        command = [self.ffmpeg, "-y"]
        for segment in segments:
            command.extend(["-i", str(segment)])
        command.extend(
            [
                "-filter_complex", graph,
                "-map", output_label,
                "-an",
                "-r", str(self.target_fps),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output),
            ]
        )
        self._run_ffmpeg(command, step=f"Phase 6 transition group {output.name}")
        self._verify_video_output(output)
        self._emit(
            "TRANSITION_GROUP_COMPLETE",
            output=str(output),
            inputs=len(segments),
            transitions=len(profiles),
            expected_duration_sec=round(expected_duration, 6),
        )

    def _reset_workspace(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.segment_dir.mkdir(parents=True, exist_ok=True)

    def _render_segment(self, position: int, clip: Any, profile: Any) -> Path:
        media_type = str(getattr(clip, "media_type", "")).strip().lower()
        asset_path = Path(str(getattr(clip, "asset_path", "")))
        duration = round(float(getattr(clip, "duration_sec", 0.0)), 6)
        source_in = max(0.0, round(float(getattr(clip, "source_in_sec", 0.0)), 6))
        source_out_raw = getattr(clip, "source_out_sec", None)

        if media_type not in {"image", "video"}:
            raise RuntimeError(f"Unsupported media type: {media_type!r}")
        if not asset_path.exists() or not asset_path.is_file():
            raise FileNotFoundError(f"Visual asset is missing: {asset_path}")
        if duration <= 0:
            raise RuntimeError(f"Invalid clip duration: {getattr(clip, 'shot_id', position)}")

        shot_id = self._safe_name(str(getattr(clip, "shot_id", f"shot_{position:04d}")))
        output = self.segment_dir / f"{position:04d}_{shot_id}.mp4"
        video_filter = self.motion_builder.build(profile)

        common_output = [
            "-map_metadata", "-1",
            "-an",
            "-r", str(self.target_fps),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]

        if media_type == "image":
            command = [
                self.ffmpeg, "-y",
                "-loop", "1",
                "-framerate", str(self.target_fps),
                "-i", str(asset_path),
                "-t", self._format_seconds(duration),
                "-vf", video_filter,
                *common_output,
            ]
        else:
            # RC2 SHORT VIDEO POLICY
            #
            # Editorial shot duration is authoritative.
            # If a source video is shorter than the requested shot,
            # FFmpeg loops the source until the complete timeline slot
            # has been filled. The result is then trimmed exactly to
            # the requested editorial duration.
            #
            # This is especially important for short AI-generated
            # documentary inserts.

            requested_duration = duration

            if requested_duration <= 0:
                raise RuntimeError(
                    f"Empty source range: "
                    f"{getattr(clip, 'shot_id', position)}"
                )

            command = [
                self.ffmpeg, "-y",
                "-stream_loop", "-1",
                "-ss", self._format_seconds(source_in),
                "-i", str(asset_path),
                "-t", self._format_seconds(requested_duration),
                "-vf", video_filter,
                *common_output,
            ]

        self._run_ffmpeg(command, step=f"Phase 6 segment {getattr(clip, 'shot_id', position)}")
        self._verify_video_output(output)
        return output

    def _concat_segments(self, segments: list[Path]) -> Path:
        if not segments:
            raise RuntimeError("No native visual segments to concatenate")
        if len(segments) == 1:
            return segments[0]

        lines = [f"file '{self._concat_escape(segment.resolve())}'" for segment in segments]
        self.concat_manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        output = self.temp_dir / "visual_concat_rc2.mp4"
        command = [
            self.ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(self.concat_manifest_path),
            "-an",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", str(self.target_fps),
            "-movflags", "+faststart",
            str(output),
        ]
        self._run_ffmpeg(command, step="Phase 6 native visual concat")
        return output

    def _verify_video_output(self, path: Path) -> None:
        if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"Invalid native visual output: {path}")
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise RuntimeError("ffprobe is not available in PATH")
        process = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration,size",
                "-show_entries", "stream=codec_type,width,height,r_frame_rate",
                "-of", "json", str(path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or f"ffprobe failed for {path}")
        payload = json.loads(process.stdout or "{}")
        if not any(row.get("codec_type") == "video" for row in payload.get("streams", [])):
            raise RuntimeError(f"No video stream: {path}")
        duration_raw = payload.get("format", {}).get("duration")
        if duration_raw in (None, "", "N/A") or float(duration_raw) <= 0:
            raise RuntimeError(f"Invalid output duration: {path}")

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in value).strip("_")
        return safe[:80] or "shot"

    @staticmethod
    def _concat_escape(path: Path) -> str:
        return path.as_posix().replace("'", "'\\''")

    @staticmethod
    def _format_seconds(value: float) -> str:
        return f"{max(0.0, float(value)):.6f}"

    @staticmethod
    def _run_ffmpeg(command: list[str], *, step: str) -> None:
        if "-nostdin" not in command:
            command = [command[0], "-nostdin", *command[1:]]
        process = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            tail = "\n".join(process.stderr.splitlines()[-30:])
            raise RuntimeError(f"ffmpeg failed during {step}: {tail}")

    def _emit(self, stage: str, **details: Any) -> None:
        self.progress({"stage": stage, **details})

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
