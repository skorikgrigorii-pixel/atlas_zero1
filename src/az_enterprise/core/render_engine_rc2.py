from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .project_config_rc2 import ProjectConfigRC2
from .visual_renderer_rc2 import VisualRendererRC2
from .audio_composer_rc2 import NativeAudioComposerRC2


ProgressCallback = Callable[[dict[str, Any]], None]

SUPPORTED_MEDIA_TYPES = {"image", "video"}
MISSING_STATUSES = {"missing", "rejected", "excluded", "disabled"}
PLACEHOLDER_ASSET_NAMES = {
    "НУЖНО СОЗДАТЬ",
    "СОЗДАТЬ",
    "NEEDS_CREATION",
    "MISSING",
}


@dataclass(frozen=True)
class RenderClipRC2:
    """Canonical render item used by the RC2 render pipeline.

    Phase 1 introduces the complete data contract while keeping
    RenderEngineRC1 as the temporary FFmpeg execution backend.
    Later phases can consume this model directly without changing
    the public RenderEngineRC2 interface.
    """

    shot_id: str
    shot_index: int
    scene_id: str | None
    scene_title: str | None
    block: str | None

    start_sec: float
    end_sec: float
    duration_sec: float

    asset_name: str
    asset_path: str
    media_type: str
    status: str

    source_in_sec: float
    source_out_sec: float | None

    story_goal: str | None
    visual_need: str | None
    emotion: str | None

    camera_motion: str
    transition: str
    transition_duration_sec: float

    natural_sound_enabled: bool
    natural_sound_windows: tuple[tuple[float, float], ...]

    voice_path: str | None
    music_path: str | None

    quality_flags: tuple[str, ...] = field(default_factory=tuple)
    source_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["natural_sound_windows"] = [
            {"start_sec": start, "end_sec": end}
            for start, end in self.natural_sound_windows
        ]
        return payload


@dataclass(frozen=True)
class RenderModelRC2:
    """Immutable project-level render model."""

    project_id: str
    timeline_path: str
    target_width: int
    target_height: int
    target_fps: int
    expected_duration_sec: float
    voice_path: str | None
    music_path: str | None
    clips: tuple[RenderClipRC2, ...]
    skipped: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "atlas_zero.render_model.rc2.v1",
            "project_id": self.project_id,
            "timeline_path": self.timeline_path,
            "target_width": self.target_width,
            "target_height": self.target_height,
            "target_fps": self.target_fps,
            "expected_duration_sec": self.expected_duration_sec,
            "voice_path": self.voice_path,
            "music_path": self.music_path,
            "clips": [clip.to_dict() for clip in self.clips],
            "skipped": list(self.skipped),
        }


class RenderEngineRC2:
    """Canonical RC2 render orchestrator.

    Phase 4 responsibilities:
    - load and normalize the canonical RC2 timeline;
    - block invalid projects through the strict Phase 3 validator;
    - render all visual segments through VisualRendererRC2;
    - concatenate a native RC2 video master without RenderEngineRC1;
    - attach narration temporarily until the Phase 7 Audio Composer exists;
    - verify and atomically publish the final RC2 artifact.

    Camera motion and transition effects remain deferred to Phase 5 and 6.
    """

    def __init__(
        self,
        config: ProjectConfigRC2,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.progress = progress or (lambda payload: None)

        self.ffprobe = shutil.which("ffprobe")
        if not self.ffprobe:
            raise RuntimeError("ffprobe is not available in PATH")

        self.render_dir = self.config.canonical_render_path.parent
        self.render_dir.mkdir(parents=True, exist_ok=True)

        self.render_model_path = self.render_dir / "render_model_rc2.json"
        self.validation_report_path = self.render_dir / "render_validation_rc2.json"
        self.render_report_path = self.render_dir / "render_report_rc2.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        self._emit("RENDER_START", project_id=self.config.project_id)

        rows, timeline_source = self.load_timeline()
        self._emit(
            "TIMELINE_LOADED",
            path=str(timeline_source),
            rows=len(rows),
        )

        model = self.build_render_model(rows, timeline_source)
        self._write_json(self.render_model_path, model.to_dict())

        validation = self.validate_render_model(model)
        self._write_json(self.validation_report_path, validation)

        self._emit(
            "MODEL_READY",
            clips_total=len(rows),
            clips_renderable=len(model.clips),
            clips_skipped=len(model.skipped),
            expected_duration_sec=model.expected_duration_sec,
        )

        if validation["blocking_errors"]:
            raise RuntimeError(
                "RenderEngineRC2 preflight failed: "
                + "; ".join(validation["blocking_errors"])
            )

        visual_report = self._run_native_visual_backend(model)
        visual_source = Path(str(visual_report["output_video"]))
        source = self._compose_phase4_audio(visual_source, model)

        self._emit("VERIFY_SOURCE", path=str(source))
        source_probe = self.probe(source)

        destination = self.config.canonical_render_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".partial")
        partial.unlink(missing_ok=True)

        shutil.copy2(source, partial)
        self._emit("VERIFY_COPY", path=str(partial))
        final_probe = self.probe(partial)

        self._validate_final_probe(final_probe, model)
        os.replace(partial, destination)

        report = {
            "state": "RENDERED_VERIFIED",
            "project_id": self.config.project_id,
            "output": str(destination),
            "source": str(source),
            "timeline_source": str(timeline_source),
            "render_model_path": str(self.render_model_path),
            "validation_report_path": str(self.validation_report_path),
            "source_probe": source_probe,
            "media_probe": final_probe,
            "expected_duration_sec": model.expected_duration_sec,
            "clips_total": len(rows),
            "clips_renderable": len(model.clips),
            "clips_skipped": len(model.skipped),
            "authority": "RenderEngineRC2",
            "backend": "VisualRendererRC2",
            "migration_phase": "PHASE_7_NATIVE_AUDIO_COMPOSER",
            "visual_report": visual_report,
            "legacy_report": None,
        }

        self._write_json(self.render_report_path, report)
        self._emit("RENDER_COMPLETE", path=str(destination))
        return report

    # ------------------------------------------------------------------
    # Timeline loading and render model construction
    # ------------------------------------------------------------------

    def load_timeline(self) -> tuple[list[dict[str, Any]], Path]:
        candidates = self._timeline_candidates()
        source = next((path for path in candidates if path.exists()), None)

        if source is None:
            expected = ", ".join(str(path) for path in candidates)
            raise FileNotFoundError(
                "RenderEngineRC2 timeline not found. Expected one of: "
                f"{expected}"
            )

        try:
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid timeline JSON: {source}") from exc

        rows = self._extract_video_rows(payload)
        if not rows:
            raise ValueError(f"Timeline contains no video rows: {source}")

        return rows, source

    def _timeline_candidates(self) -> tuple[Path, ...]:
        native_rc2 = self.config.rc2_dir / "timeline" / "timeline.json"
        configured = self.config.timeline_path
        legacy_native = self.config.export_dir / "native_timeline_model.json"

        ordered: list[Path] = []
        for path in (native_rc2, configured, legacy_native):
            if path not in ordered:
                ordered.append(path)
        return tuple(ordered)

    @staticmethod
    def _extract_video_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [dict(row) for row in payload if isinstance(row, dict)]

        if not isinstance(payload, dict):
            raise ValueError("Timeline JSON root must be a list or object")

        if isinstance(payload.get("timeline"), list):
            return [
                dict(row)
                for row in payload["timeline"]
                if isinstance(row, dict)
            ]

        clips: list[dict[str, Any]] = []
        for track in payload.get("tracks", []):
            if not isinstance(track, dict):
                continue
            if str(track.get("type", "")).strip().lower() != "video":
                continue
            for clip in track.get("clips", []):
                if not isinstance(clip, dict):
                    continue
                clips.append(
                    {
                        **clip,
                        "shot_index": clip.get("shot_index", clip.get("idx")),
                        "start_sec": clip.get("start_sec", clip.get("start")),
                        "end_sec": clip.get("end_sec", clip.get("end")),
                        "duration_sec": clip.get("duration_sec", clip.get("duration")),
                        "asset_name": clip.get("asset_name", clip.get("asset")),
                    }
                )
        return clips

    def build_render_model(
        self,
        rows: Iterable[dict[str, Any]],
        timeline_source: Path,
    ) -> RenderModelRC2:
        voice_path = self._discover_voice_path()
        music_path = self._discover_music_path()

        clips: list[RenderClipRC2] = []
        skipped: list[dict[str, Any]] = []

        for position, raw in enumerate(rows, start=1):
            row = dict(raw)
            try:
                clip = self._normalize_clip(
                    row=row,
                    position=position,
                    voice_path=voice_path,
                    music_path=music_path,
                )
            except (TypeError, ValueError) as exc:
                skipped.append(
                    self._skip_record(row, position, "invalid_timeline_row", str(exc))
                )
                continue

            skip_reason = self._clip_skip_reason(clip)
            if skip_reason:
                skipped.append(
                    self._skip_record(row, position, skip_reason, None)
                )
                continue

            clips.append(clip)

        clips.sort(key=lambda item: (item.start_sec, item.shot_index))
        expected_duration = max((clip.end_sec for clip in clips), default=0.0)

        return RenderModelRC2(
            project_id=self.config.project_id,
            timeline_path=str(timeline_source),
            target_width=int(self.config.target_width),
            target_height=int(self.config.target_height),
            target_fps=int(self.config.target_fps),
            expected_duration_sec=round(expected_duration, 3),
            voice_path=str(voice_path) if voice_path else None,
            music_path=str(music_path) if music_path else None,
            clips=tuple(clips),
            skipped=tuple(skipped),
        )

    def _normalize_clip(
        self,
        *,
        row: dict[str, Any],
        position: int,
        voice_path: Path | None,
        music_path: Path | None,
    ) -> RenderClipRC2:
        shot_id = str(row.get("shot_id") or f"shot_{position:04d}").strip()
        shot_index = self._as_int(row.get("shot_index", row.get("idx")), position)

        start_sec = self._as_float(
            row.get("start_sec", row.get("start")),
            default=0.0,
        )

        duration_value = row.get("duration_sec", row.get("duration"))
        end_value = row.get("end_sec", row.get("end"))

        if duration_value is None and end_value is None:
            raise ValueError("duration_sec or end_sec is required")

        if duration_value is None:
            end_sec = self._as_float(end_value, default=start_sec)
            duration_sec = end_sec - start_sec
        else:
            duration_sec = self._as_float(duration_value, default=0.0)
            end_sec = (
                self._as_float(end_value, default=start_sec + duration_sec)
                if end_value is not None
                else start_sec + duration_sec
            )

        if duration_sec <= 0:
            raise ValueError(f"duration must be positive, got {duration_sec}")

        if end_sec <= start_sec:
            end_sec = start_sec + duration_sec

        # Timeline duration remains authoritative if the two fields disagree.
        duration_sec = round(end_sec - start_sec, 3)

        asset_path = str(row.get("asset_path") or "").strip()
        asset_name = str(
            row.get("asset_name")
            or row.get("asset")
            or (Path(asset_path).name if asset_path else "")
        ).strip()

        media_type = str(row.get("media_type") or "").strip().lower()
        status = str(row.get("status") or "assigned").strip().lower()

        source_in_sec = max(
            0.0,
            self._as_float(
                row.get("source_in_sec", row.get("source_start_sec")),
                default=0.0,
            ),
        )

        source_out_raw = row.get("source_out_sec", row.get("source_end_sec"))
        source_out_sec = (
            self._as_float(source_out_raw, default=source_in_sec + duration_sec)
            if source_out_raw is not None
            else None
        )

        transition = self._normalize_transition(row.get("transition"))
        transition_duration = self._transition_duration(row, transition)
        camera_motion = self._normalize_camera_motion(row.get("camera_motion"))

        natural_windows = self._parse_natural_sound_windows(
            row.get("natural_sound_windows", row.get("natural_sound_window"))
        )
        natural_sound_enabled = self._as_bool(
            row.get("natural_sound_enabled", row.get("natural_audio_used")),
            default=bool(natural_windows),
        )

        quality_flags = self._normalize_quality_flags(row.get("quality_flags"))

        return RenderClipRC2(
            shot_id=shot_id,
            shot_index=shot_index,
            scene_id=self._optional_text(row.get("scene_id")),
            scene_title=self._optional_text(row.get("scene_title")),
            block=self._optional_text(row.get("block")),
            start_sec=round(start_sec, 3),
            end_sec=round(end_sec, 3),
            duration_sec=round(duration_sec, 3),
            asset_name=asset_name,
            asset_path=asset_path,
            media_type=media_type,
            status=status,
            source_in_sec=round(source_in_sec, 3),
            source_out_sec=(round(source_out_sec, 3) if source_out_sec is not None else None),
            story_goal=self._optional_text(row.get("story_goal")),
            visual_need=self._optional_text(row.get("visual_need")),
            emotion=self._optional_text(row.get("emotion")),
            camera_motion=camera_motion,
            transition=transition,
            transition_duration_sec=transition_duration,
            natural_sound_enabled=natural_sound_enabled,
            natural_sound_windows=natural_windows,
            voice_path=str(voice_path) if voice_path else None,
            music_path=str(music_path) if music_path else None,
            quality_flags=quality_flags,
            source_mode=self._optional_text(row.get("source_mode")),
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_render_model(self, model: RenderModelRC2) -> dict[str, Any]:
        """Run strict Phase 3 preflight before any render backend is started."""

        blocking: list[str] = []
        warnings: list[str] = []
        clip_issues: list[dict[str, Any]] = []
        asset_probes: list[dict[str, Any]] = []

        if not model.clips:
            blocking.append("no renderable clips")

        if model.expected_duration_sec <= 0:
            blocking.append("expected duration is zero")

        if model.target_width <= 0 or model.target_height <= 0:
            blocking.append("invalid target resolution")

        if model.target_fps <= 0:
            blocking.append("invalid target frame rate")

        ordered = sorted(
            model.clips,
            key=lambda clip: (clip.start_sec, clip.shot_index),
        )

        shot_ids: set[str] = set()
        shot_indexes: set[int] = set()
        asset_use_count: dict[str, int] = {}
        previous_end = 0.0
        timeline_gaps: list[dict[str, Any]] = []
        timeline_overlaps: list[dict[str, Any]] = []
        video_shots = 0

        allowed_transitions = {
            "cut",
            "dissolve",
            "fade",
            "dip_to_black",
            "wipe",
        }
        allowed_camera_motion = {
            "static",
            "push_in",
            "push_out",
            "slow_push",
            "slow_pan",
            "pan_left",
            "pan_right",
            "tilt_up",
            "tilt_down",
            "slow_drift",
            "parallax",
            "ken_burns",
            "slow_pull",
            "pan_up",
            "pan_down",
            "custom",
        }

        for position, clip in enumerate(ordered, start=1):
            issues: list[str] = []
            probe_payload: dict[str, Any] | None = None

            if clip.shot_id in shot_ids:
                issues.append("duplicate shot_id")
            shot_ids.add(clip.shot_id)

            if clip.shot_index in shot_indexes:
                issues.append("duplicate shot_index")
            shot_indexes.add(clip.shot_index)

            if clip.media_type not in SUPPORTED_MEDIA_TYPES:
                issues.append(f"unsupported media_type={clip.media_type!r}")

            if clip.media_type == "video":
                video_shots += 1

            if clip.status in MISSING_STATUSES:
                issues.append(f"non-renderable status={clip.status!r}")

            if not clip.asset_path:
                issues.append("asset_path is empty")
                path = None
            else:
                path = Path(clip.asset_path)
                if not path.exists() or not path.is_file():
                    issues.append("asset file is missing")

            if clip.duration_sec <= 0:
                issues.append("duration is not positive")

            if clip.start_sec < 0:
                issues.append("start_sec is negative")

            if clip.end_sec <= clip.start_sec:
                issues.append("end_sec must be greater than start_sec")

            derived_duration = clip.end_sec - clip.start_sec
            if abs(derived_duration - clip.duration_sec) > 0.05:
                issues.append(
                    "duration_sec does not match end_sec-start_sec"
                )

            if clip.source_in_sec < 0:
                issues.append("source_in_sec is negative")

            if (
                clip.source_out_sec is not None
                and clip.source_out_sec <= clip.source_in_sec
            ):
                issues.append(
                    "source_out_sec must be greater than source_in_sec"
                )

            if clip.transition not in allowed_transitions:
                warnings.append(
                    f"shot {clip.shot_index}: unknown transition "
                    f"{clip.transition!r}; native backend may fall back to cut"
                )

            if clip.transition == "cut" and clip.transition_duration_sec > 0.001:
                warnings.append(
                    f"shot {clip.shot_index}: cut has non-zero "
                    f"transition duration {clip.transition_duration_sec:.3f}s"
                )

            if clip.transition_duration_sec < 0:
                issues.append("transition duration is negative")

            if clip.transition_duration_sec > clip.duration_sec * 0.5:
                issues.append(
                    "transition duration exceeds half of clip duration"
                )

            if clip.camera_motion not in allowed_camera_motion:
                warnings.append(
                    f"shot {clip.shot_index}: unknown camera motion "
                    f"{clip.camera_motion!r}; native backend may use static"
                )

            for window_index, (window_start, window_end) in enumerate(
                clip.natural_sound_windows,
                start=1,
            ):
                if window_start < 0 or window_end <= window_start:
                    issues.append(
                        f"invalid natural sound window #{window_index}"
                    )
                    continue
                if window_end > clip.duration_sec + 0.05:
                    issues.append(
                        f"natural sound window #{window_index} exceeds "
                        "clip duration"
                    )

            if clip.start_sec < previous_end - 0.05:
                overlap = round(previous_end - clip.start_sec, 3)
                timeline_overlaps.append(
                    {
                        "shot_id": clip.shot_id,
                        "shot_index": clip.shot_index,
                        "overlap_sec": overlap,
                    }
                )
                issues.append(f"timeline overlap of {overlap:.3f}s")

            if clip.start_sec > previous_end + 0.05:
                gap = round(clip.start_sec - previous_end, 3)
                timeline_gaps.append(
                    {
                        "shot_id": clip.shot_id,
                        "shot_index": clip.shot_index,
                        "gap_sec": gap,
                    }
                )

            previous_end = max(previous_end, clip.end_sec)

            if path is not None and path.exists() and path.is_file():
                asset_key = str(path.resolve()).lower()
                asset_use_count[asset_key] = (
                    asset_use_count.get(asset_key, 0) + 1
                )

                try:
                    probe_payload = self.probe_source(path)
                    source_duration = probe_payload.get("duration_sec")

                    if clip.media_type == "video":
                        if not probe_payload.get("has_video"):
                            issues.append(
                                "declared video asset has no video stream"
                            )

                        if source_duration is None:
                            issues.append(
                                "source video duration is unavailable"
                            )
                        else:
                            required_out = (
                                clip.source_out_sec
                                if clip.source_out_sec is not None
                                else clip.source_in_sec + clip.duration_sec
                            )
                            if required_out > float(source_duration) + 0.10:
                                issues.append(
                                    "requested source range exceeds "
                                    f"asset duration ({required_out:.3f}s > "
                                    f"{float(source_duration):.3f}s)"
                                )

                    elif clip.media_type == "image":
                        if not probe_payload.get("has_video"):
                            issues.append(
                                "image asset could not be decoded as video/image"
                            )

                except Exception as exc:
                    issues.append(f"ffprobe source check failed: {exc}")

            asset_probes.append(
                {
                    "shot_id": clip.shot_id,
                    "shot_index": clip.shot_index,
                    "asset_path": clip.asset_path,
                    "probe": probe_payload,
                }
            )

            if issues:
                clip_issues.append(
                    {
                        "position": position,
                        "shot_id": clip.shot_id,
                        "shot_index": clip.shot_index,
                        "scene_id": clip.scene_id,
                        "asset_path": clip.asset_path,
                        "issues": issues,
                    }
                )

        if clip_issues:
            blocking.append(
                f"{len(clip_issues)} render clips failed strict validation"
            )

        minimum_video_shots = max(
            0,
            int(getattr(self.config, "minimum_video_shots", 1)),
        )
        if video_shots < minimum_video_shots:
            blocking.append(
                f"video shots below minimum: "
                f"{video_shots} < {minimum_video_shots}"
            )

        unique_assets = len(asset_use_count)
        total_asset_uses = sum(asset_use_count.values())
        unique_ratio = (
            unique_assets / len(ordered)
            if ordered
            else 0.0
        )
        average_reuse = (
            total_asset_uses / unique_assets
            if unique_assets
            else 0.0
        )

        minimum_unique_ratio = float(
            getattr(self.config, "minimum_unique_asset_ratio", 0.20)
        )
        if ordered and unique_ratio < minimum_unique_ratio:
            warnings.append(
                "unique asset ratio below target: "
                f"{unique_ratio:.3f} < {minimum_unique_ratio:.3f}"
            )

        maximum_average_reuse = float(
            getattr(self.config, "maximum_average_asset_reuse", 5.0)
        )
        if average_reuse > maximum_average_reuse:
            warnings.append(
                "average asset reuse above target: "
                f"{average_reuse:.3f} > {maximum_average_reuse:.3f}"
            )

        if timeline_overlaps:
            blocking.append(
                f"{len(timeline_overlaps)} timeline overlaps detected"
            )

        if timeline_gaps:
            total_gap = round(
                sum(item["gap_sec"] for item in timeline_gaps),
                3,
            )
            warnings.append(
                f"{len(timeline_gaps)} timeline gaps detected "
                f"({total_gap:.3f}s total)"
            )

        audio_validation = self._validate_audio_inputs(model)
        blocking.extend(audio_validation["blocking_errors"])
        warnings.extend(audio_validation["warnings"])

        if model.skipped:
            warnings.append(
                f"{len(model.skipped)} timeline rows were skipped "
                "before strict validation"
            )

        return {
            "state": "VALID" if not blocking else "INVALID",
            "project_id": model.project_id,
            "schema": "atlas_zero.render_validation.rc2.v2",
            "timeline_path": model.timeline_path,
            "clips_renderable": len(model.clips),
            "clips_skipped": len(model.skipped),
            "expected_duration_sec": model.expected_duration_sec,
            "video_shots": video_shots,
            "unique_assets": unique_assets,
            "unique_asset_ratio": round(unique_ratio, 6),
            "average_asset_reuse": round(average_reuse, 6),
            "timeline_gaps": timeline_gaps,
            "timeline_overlaps": timeline_overlaps,
            "voice_path": model.voice_path,
            "music_path": model.music_path,
            "audio_validation": audio_validation,
            "blocking_errors": blocking,
            "warnings": warnings,
            "clip_issues": clip_issues,
            "asset_probes": asset_probes,
            "skipped": list(model.skipped),
            "authority": "RenderEngineRC2",
            "migration_phase": "PHASE_7_NATIVE_AUDIO_COMPOSER",
        }

    def _validate_audio_inputs(
        self,
        model: RenderModelRC2,
    ) -> dict[str, Any]:
        blocking: list[str] = []
        warnings: list[str] = []
        probes: dict[str, Any] = {}

        if model.voice_path is None:
            warnings.append("voice master was not discovered")
        else:
            voice = Path(model.voice_path)
            if not voice.exists() or not voice.is_file():
                blocking.append("voice master path does not exist")
            else:
                try:
                    voice_probe = self.probe_source(voice)
                    probes["voice"] = voice_probe
                    if not voice_probe.get("has_audio"):
                        blocking.append("voice master has no audio stream")
                    duration = voice_probe.get("duration_sec")
                    if duration is not None:
                        delta = abs(
                            float(duration)
                            - float(model.expected_duration_sec)
                        )
                        tolerance = max(
                            float(
                                getattr(
                                    self.config,
                                    "duration_tolerance_sec",
                                    2.0,
                                )
                            ),
                            0.25,
                        )
                        if delta > tolerance:
                            warnings.append(
                                "voice duration differs from timeline: "
                                f"voice={float(duration):.3f}s, "
                                f"timeline={model.expected_duration_sec:.3f}s, "
                                f"delta={delta:.3f}s"
                            )
                except Exception as exc:
                    blocking.append(
                        f"voice master ffprobe failed: {exc}"
                    )

        if model.music_path is not None:
            music = Path(model.music_path)
            if not music.exists() or not music.is_file():
                warnings.append("music path does not exist")
            else:
                try:
                    music_probe = self.probe_source(music)
                    probes["music"] = music_probe
                    if not music_probe.get("has_audio"):
                        warnings.append("music file has no audio stream")
                except Exception as exc:
                    warnings.append(f"music ffprobe failed: {exc}")

        return {
            "blocking_errors": blocking,
            "warnings": warnings,
            "probes": probes,
        }

    # ------------------------------------------------------------------
    # Native Phase 4 visual backend
    # ------------------------------------------------------------------

    def _run_native_visual_backend(
        self,
        model: RenderModelRC2,
    ) -> dict[str, Any]:
        self._emit(
            "BACKEND_START",
            backend="VisualRendererRC2",
            renderable_clips=len(model.clips),
        )

        renderer = VisualRendererRC2(
            project_id=self.config.project_id,
            output_dir=self.render_dir,
            target_width=model.target_width,
            target_height=model.target_height,
            target_fps=model.target_fps,
            progress=self.progress,
        )
        report = renderer.run(model.clips)

        self._emit(
            "BACKEND_COMPLETE",
            backend="VisualRendererRC2",
            state=report.get("state"),
            segments_rendered=report.get("segments_rendered"),
        )

        if report.get("state") != "VISUAL_RENDERED":
            raise RuntimeError(str(report))

        output = Path(str(report.get("output_video") or ""))
        if not output.exists() or not output.is_file():
            raise FileNotFoundError(
                f"VisualRendererRC2 output missing: {output}"
            )
        return report

    def _compose_phase4_audio(
        self,
        visual_source: Path,
        model: RenderModelRC2,
    ) -> Path:
        """Attach narration until the native Phase 7 mixer is implemented.

        Phase 4 owns only the visual backend. This compatibility mux prevents
        the existing final artifact contract from losing its audio stream.
        """

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is not available in PATH")

        output = self.render_dir / "phase4_av_master_rc2.mp4"
        output.unlink(missing_ok=True)

        if model.voice_path:
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(visual_source),
                "-i",
                str(model.voice_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-t",
                f"{model.expected_duration_sec:.6f}",
                "-movflags",
                "+faststart",
                str(output),
            ]
            mode = "voice_master"
        else:
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(visual_source),
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-t",
                f"{model.expected_duration_sec:.6f}",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output),
            ]
            mode = "silent_compatibility_track"

        self._emit(
            "PHASE4_AUDIO_MUX_START",
            mode=mode,
            visual_source=str(visual_source),
        )
        self._run_ffmpeg(command, step="Phase 4 compatibility audio mux")

        if not output.exists() or not output.is_file():
            raise FileNotFoundError(
                f"Phase 4 audio mux output missing: {output}"
            )

        self._emit(
            "PHASE4_AUDIO_MUX_COMPLETE",
            mode=mode,
            output=str(output),
        )
        return output

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
            stderr_tail = "\n".join(process.stderr.splitlines()[-30:])
            raise RuntimeError(
                f"ffmpeg failed during {step}: {stderr_tail}"
            )

    # ------------------------------------------------------------------
    # Media discovery
    # ------------------------------------------------------------------

    def _discover_voice_path(self) -> Path | None:
        audio_dir = self.config.project_dir / "01_Audio"
        candidates = [
            audio_dir / "voice_master.wav",
            self.config.master_audio_path,
            audio_dir / "voice_master.m4a",
            audio_dir / "voice_master.mp3",
        ]
        return self._first_existing_file(candidates)

    def _discover_music_path(self) -> Path | None:
        audio_dir = self.config.project_dir / "01_Audio"
        candidates = [
            audio_dir / "music_master.wav",
            audio_dir / "music_master.m4a",
            audio_dir / "music_master.mp3",
            audio_dir / "music.wav",
            audio_dir / "music.m4a",
            audio_dir / "music.mp3",
        ]
        return self._first_existing_file(candidates)

    @staticmethod
    def _first_existing_file(candidates: Iterable[Path]) -> Path | None:
        seen: set[Path] = set()
        for candidate in candidates:
            path = Path(candidate)
            if path in seen:
                continue
            seen.add(path)
            if path.exists() and path.is_file():
                return path
        return None

    # ------------------------------------------------------------------
    # Probe and final verification
    # ------------------------------------------------------------------

    def probe_source(self, path: Path) -> dict[str, Any]:
        """Probe a source asset without requiring both video and audio."""

        proc = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,size,format_name",
                "-show_entries",
                (
                    "stream=index,codec_type,codec_name,width,height,"
                    "r_frame_rate,sample_rate,channels"
                ),
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                proc.stderr.strip()
                or f"ffprobe failed for source: {path}"
            )

        payload = json.loads(proc.stdout or "{}")
        streams = payload.get("streams", [])
        duration_raw = payload.get("format", {}).get("duration")

        duration_sec = None
        if duration_raw not in (None, "", "N/A"):
            try:
                duration_sec = round(float(duration_raw), 6)
            except (TypeError, ValueError):
                duration_sec = None

        video_streams = [
            row
            for row in streams
            if row.get("codec_type") == "video"
        ]
        audio_streams = [
            row
            for row in streams
            if row.get("codec_type") == "audio"
        ]

        return {
            "path": str(path),
            "duration_sec": duration_sec,
            "size_bytes": self._safe_int(
                payload.get("format", {}).get("size")
            ),
            "format_name": payload.get("format", {}).get("format_name"),
            "has_video": bool(video_streams),
            "has_audio": bool(audio_streams),
            "video_streams": video_streams,
            "audio_streams": audio_streams,
        }

    def probe(self, path: Path) -> dict[str, Any]:
        proc = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,size,format_name",
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,r_frame_rate",
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "ffprobe failed")

        payload = json.loads(proc.stdout)
        streams = payload.get("streams", [])

        if not any(row.get("codec_type") == "video" for row in streams):
            raise RuntimeError("Rendered artifact has no video stream")
        if not any(row.get("codec_type") == "audio" for row in streams):
            raise RuntimeError("Rendered artifact has no audio stream")

        return payload

    def _validate_final_probe(
        self,
        probe: dict[str, Any],
        model: RenderModelRC2,
    ) -> None:
        duration_raw = probe.get("format", {}).get("duration")
        if duration_raw in (None, ""):
            raise RuntimeError("Final artifact duration is unavailable")

        duration = float(duration_raw)
        if duration <= 0:
            raise RuntimeError("Final artifact duration is zero")

        tolerance = max(
            float(getattr(self.config, "duration_tolerance_sec", 2.0)),
            2.0,
        )

        # Phase 4 uses the native visual backend, so final duration must closely
        # follow the canonical render model.
        expected = float(model.expected_duration_sec)
        if expected > 0 and abs(duration - expected) > tolerance:
            raise RuntimeError(
                "Final artifact duration differs from native render model: "
                f"actual={duration:.3f}s, expected={expected:.3f}s, "
                f"tolerance={tolerance:.3f}s"
            )

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clip_skip_reason(clip: RenderClipRC2) -> str | None:
        if clip.status in MISSING_STATUSES:
            return f"status_{clip.status}"
        if clip.asset_name.upper() in PLACEHOLDER_ASSET_NAMES:
            return "asset_needs_creation"
        if not clip.asset_path:
            return "asset_path_empty"
        if clip.media_type not in SUPPORTED_MEDIA_TYPES:
            return "media_type_not_supported"
        path = Path(clip.asset_path)
        if not path.exists() or not path.is_file():
            return "asset_not_found"
        return None

    @staticmethod
    def _skip_record(
        row: dict[str, Any],
        position: int,
        reason: str,
        details: str | None,
    ) -> dict[str, Any]:
        return {
            "shot_id": str(row.get("shot_id") or f"shot_{position:04d}"),
            "shot_index": row.get("shot_index", row.get("idx", position)),
            "reason": reason,
            "details": details,
            "status": row.get("status"),
            "asset_name": row.get("asset_name", row.get("asset")),
            "asset_path": row.get("asset_path"),
            "media_type": row.get("media_type"),
        }

    @staticmethod
    def _normalize_transition(value: Any) -> str:
        text = str(value or "cut").strip().lower()
        aliases = {
            "": "cut",
            "none": "cut",
            "hard_cut": "cut",
            "crossfade": "dissolve",
            "cross_fade": "dissolve",
            "cross dissolve": "dissolve",
            "cross_dissolve": "dissolve",
            "fade_to_black": "fade",
            "fade to black": "fade",
            "dip_to_black": "fade",
        }
        return aliases.get(text, text)

    @staticmethod
    def _transition_duration(row: dict[str, Any], transition: str) -> float:
        raw = row.get("transition_duration_sec")
        if raw is None:
            raw = row.get("transition_duration")
        if raw is None:
            return 0.0 if transition == "cut" else 0.5
        try:
            value = max(0.0, float(raw))
        except (TypeError, ValueError):
            value = 0.0 if transition == "cut" else 0.5
        return round(min(value, 3.0), 3)

    @staticmethod
    def _normalize_camera_motion(value: Any) -> str:
        text = str(value or "static").strip().lower()
        aliases = {
            "": "static",
            "none": "static",
            "no_motion": "static",
            "slow push-in 100→108%": "push_in",
            "slow push-in": "push_in",
            "push in": "push_in",
            "slow push-out": "push_out",
            "push out": "push_out",
            "slow cinematic motion": "slow_drift",
            "slow aerial drift / ken burns": "slow_drift",
            "static + subtle parallax": "parallax",
        }
        return aliases.get(text, text.replace(" ", "_"))

    @classmethod
    def _parse_natural_sound_windows(
        cls,
        value: Any,
    ) -> tuple[tuple[float, float], ...]:
        if value in (None, "", [], {}):
            return tuple()

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return tuple()
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                # Accept compact forms such as "2.0-5.5".
                if "-" in text:
                    left, right = text.split("-", 1)
                    try:
                        start = max(0.0, float(left.strip()))
                        end = float(right.strip())
                    except ValueError:
                        return tuple()
                    return ((round(start, 3), round(end, 3)),) if end > start else tuple()
                return tuple()

        if isinstance(value, dict):
            value = [value]

        windows: list[tuple[float, float]] = []
        if isinstance(value, (list, tuple)):
            for item in value:
                start: Any = None
                end: Any = None

                if isinstance(item, dict):
                    start = item.get("start_sec", item.get("start"))
                    end = item.get("end_sec", item.get("end"))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    start, end = item[0], item[1]

                try:
                    start_f = max(0.0, float(start))
                    end_f = float(end)
                except (TypeError, ValueError):
                    continue

                if end_f > start_f:
                    windows.append((round(start_f, 3), round(end_f, 3)))

        return tuple(windows)

    @staticmethod
    def _normalize_quality_flags(value: Any) -> tuple[str, ...]:
        if value in (None, "", [], {}):
            return tuple()
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return tuple()
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = [part.strip() for part in text.split(",") if part.strip()]
            value = decoded
        if isinstance(value, dict):
            return tuple(sorted(str(key) for key, enabled in value.items() if enabled))
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item).strip() for item in value if str(item).strip())
        return (str(value).strip(),)

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled"}:
            return False
        return default

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        if value in (None, ""):
            return float(default)
        return float(value)

    @staticmethod
    def _as_int(value: Any, default: int) -> int:
        if value in (None, ""):
            return int(default)
        return int(value)

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value in (None, "", "N/A"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _emit(self, stage: str, **details: Any) -> None:
        self.progress({"stage": stage, **details})

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
