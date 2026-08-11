from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable

from .project_config_rc2 import ProjectConfigRC2
from .visual_renderer_rc2 import VisualRendererRC2


ProgressCallback = Callable[[dict[str, Any]], None]

SUPPORTED_MEDIA_TYPES = {"image", "video"}
MISSING_STATUSES = {"missing", "rejected", "excluded", "disabled"}
PLACEHOLDER_ASSET_NAMES = {
    "РќРЈР–РќРћ РЎРћР—Р”РђРўР¬",
    "РЎРћР—Р”РђРўР¬",
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

    alternative_assets: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    quality_flags: tuple[str, ...] = field(default_factory=tuple)
    source_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["natural_sound_windows"] = [
            {"start_sec": start, "end_sec": end}
            for start, end in self.natural_sound_windows
        ]
        payload["alternative_assets"] = [
            dict(item) for item in self.alternative_assets
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

    Responsibilities:
    - load only the canonical RC2 timeline;
    - build and validate the immutable RC2 render model;
    - support preflight before narration exists;
    - render a non-final preview when narration is absent;
    - publish the canonical final artifact only when narration exists;
    - verify every produced media artifact before publication.

    Legacy timeline artifacts are intentionally ignored.
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

        self.render_dir = self.config.render_dir
        self.render_dir.mkdir(parents=True, exist_ok=True)

        self.render_model_path = self.render_dir / "render_model_rc2.json"
        self.validation_report_path = self.render_dir / "render_validation_rc2.json"
        self.preflight_report_path = self.config.render_preflight_report_path
        self.render_report_path = self.render_dir / "render_report_rc2.json"
        self.editor_report_path = self.render_dir / "editor_pass_report_rc2.json"
        self.preview_render_path = self.config.preview_render_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prepare(self) -> dict[str, Any]:
        """Build and validate the render model without starting FFmpeg."""

        self._emit("RENDER_PREFLIGHT_START", project_id=self.config.project_id)

        rows, timeline_source = self.load_timeline()
        self._emit(
            "TIMELINE_LOADED",
            path=str(timeline_source),
            rows=len(rows),
        )

        model = self.build_render_model(rows, timeline_source)
        model, editor_report = self._editor_pass(model)
        self._write_json(self.editor_report_path, editor_report)
        self._write_json(self.render_model_path, model.to_dict())

        validation = self.validate_render_model(model, editor_report=editor_report)
        self._write_json(self.validation_report_path, validation)

        report = {
            "state": (
                "RENDER_PREFLIGHT_READY"
                if not validation["blocking_errors"]
                else "RENDER_PREFLIGHT_BLOCKED"
            ),
            "project_id": self.config.project_id,
            "timeline_source": str(timeline_source),
            "render_model_path": str(self.render_model_path),
            "editor_report_path": str(self.editor_report_path),
            "validation_report_path": str(self.validation_report_path),
            "expected_duration_sec": model.expected_duration_sec,
            "clips_total": len(rows),
            "clips_renderable": len(model.clips),
            "clips_skipped": len(model.skipped),
            "voice_ready": model.voice_path is not None,
            "music_ready": model.music_path is not None,
            "blocking_errors": list(validation["blocking_errors"]),
            "warnings": list(validation["warnings"]),
            "authority": "RenderEngineRC2",
            "backend": "VisualRendererRC2",
        }

        self._write_json(self.preflight_report_path, report)
        self._emit(
            "RENDER_PREFLIGHT_COMPLETE",
            state=report["state"],
            expected_duration_sec=model.expected_duration_sec,
        )
        return report

    def run(self) -> dict[str, Any]:
        """Render preview or final output from the canonical RC2 timeline.

        When narration is absent, the engine creates a verified preview with a
        silent compatibility track and does not overwrite the canonical final
        render. Once narration exists, the canonical final artifact is
        published atomically.
        """

        self._emit("RENDER_START", project_id=self.config.project_id)

        rows, timeline_source = self.load_timeline()
        self._emit(
            "TIMELINE_LOADED",
            path=str(timeline_source),
            rows=len(rows),
        )

        model = self.build_render_model(rows, timeline_source)
        model, editor_report = self._editor_pass(model)
        self._write_json(self.editor_report_path, editor_report)
        self._write_json(self.render_model_path, model.to_dict())

        validation = self.validate_render_model(model, editor_report=editor_report)
        self._write_json(self.validation_report_path, validation)

        self._emit(
            "MODEL_READY",
            clips_total=len(rows),
            clips_renderable=len(model.clips),
            clips_skipped=len(model.skipped),
            expected_duration_sec=model.expected_duration_sec,
            voice_ready=model.voice_path is not None,
        )

        if validation["blocking_errors"]:
            raise RuntimeError(
                "RenderEngineRC2 preflight failed: "
                + "; ".join(validation["blocking_errors"])
            )

        visual_report = self._run_native_visual_backend(model)
        visual_source = Path(str(visual_report["output_video"]))
        source, audio_mode = self._compose_phase4_audio(visual_source, model)

        self._emit("VERIFY_SOURCE", path=str(source))
        source_probe = self.probe(source)

        programme_audio_ready = bool(
            model.voice_path
            or model.music_path
            or any(
                clip.natural_sound_enabled
                and bool(clip.natural_sound_windows)
                for clip in model.clips
            )
        )
        final_mode = programme_audio_ready
        destination = (
            self.config.canonical_render_path
            if final_mode
            else self.preview_render_path
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.stem + ".partial" + destination.suffix)
        partial.unlink(missing_ok=True)

        shutil.copy2(source, partial)
        self._emit("VERIFY_COPY", path=str(partial))
        final_probe = self.probe(partial)

        source_duration_raw = source_probe.get("format", {}).get("duration")
        source_duration_sec = (
            float(source_duration_raw)
            if source_duration_raw not in (None, "")
            else None
        )
        self._validate_final_probe(
            final_probe,
            model,
            expected_duration_sec=source_duration_sec,
        )
        os.replace(partial, destination)

        report = {
            "state": (
                "RENDERED_VERIFIED"
                if final_mode
                else "RENDER_PREVIEW_VERIFIED"
            ),
            "project_id": self.config.project_id,
            "output": str(destination),
            "source": str(source),
            "timeline_source": str(timeline_source),
            "render_model_path": str(self.render_model_path),
            "editor_report_path": str(self.editor_report_path),
            "validation_report_path": str(self.validation_report_path),
            "source_probe": source_probe,
            "media_probe": final_probe,
            "expected_duration_sec": model.expected_duration_sec,
            "rendered_source_duration_sec": source_duration_sec,
            "clips_total": len(rows),
            "clips_renderable": len(model.clips),
            "clips_skipped": len(model.skipped),
            "voice_ready": model.voice_path is not None,
            "music_ready": model.music_path is not None,
            "audio_mode": audio_mode,
            "publish_mode": (
                "canonical_final"
                if final_mode
                else "non_final_preview"
            ),
            "authority": "RenderEngineRC2",
            "backend": "VisualRendererRC2",
            "migration_phase": "PHASE_7_NATIVE_AUDIO_COMPOSER",
            "visual_report": visual_report,
            "legacy_report": None,
        }

        self._write_json(self.render_report_path, report)
        self._emit(
            "RENDER_COMPLETE",
            path=str(destination),
            state=report["state"],
        )
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
        """Return canonical RC2 timeline locations only."""

        configured = Path(self.config.timeline_path)
        native_rc2 = self.config.rc2_dir / "timeline" / "timeline.json"

        ordered: list[Path] = []
        for path in (configured, native_rc2):
            normalized = Path(path)
            if normalized not in ordered:
                ordered.append(normalized)
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

        raw_natural_windows = row.get(
            "natural_sound_windows",
            row.get("natural_sound_window"),
        )

        # TimelineEngineRC2 historically emitted a boolean flag instead of
        # a concrete interval. True means that the complete rendered clip is
        # eligible for native source sound.
        if isinstance(raw_natural_windows, bool):
            natural_windows = (
                ((0.0, round(duration_sec, 3)),)
                if raw_natural_windows
                else tuple()
            )
        else:
            natural_windows = self._parse_natural_sound_windows(
                raw_natural_windows
            )

        # CHANGE-005:
        # Timeline supplies candidate availability only. RenderEngine makes
        # the final natural_sound_enabled editorial decision.
        natural_sound_candidate = self._as_bool(
            row.get(
                "natural_sound_candidate",
                row.get(
                    "natural_sound_enabled",
                    row.get("natural_audio_used"),
                ),
            ),
            default=bool(natural_windows),
        )

        natural_sound_enabled = natural_sound_candidate

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
            alternative_assets=self._parse_alternative_assets(
                row.get("alternative_assets")
            ),
            quality_flags=quality_flags,
            source_mode=self._optional_text(row.get("source_mode")),
        )

    @staticmethod
    def _parse_alternative_assets(value: Any) -> tuple[dict[str, Any], ...]:
        if value in (None, ""):
            return tuple()
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return tuple()
        if not isinstance(value, list):
            return tuple()

        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            path = str(item.get("asset_path") or item.get("path") or "").strip()
            name = str(item.get("asset_name") or item.get("filename") or "").strip()
            media_type = str(item.get("media_type") or "").strip().lower()
            identity = os.path.normcase(os.path.abspath(path)) if path else ""
            if (
                not identity
                or identity in seen
                or not name
                or media_type not in SUPPORTED_MEDIA_TYPES
                or not bool(item.get("verified", True))
            ):
                continue
            seen.add(identity)
            normalized = dict(item)
            normalized["asset_name"] = name
            normalized["asset_path"] = path
            normalized["media_type"] = media_type
            normalized["verified"] = True
            result.append(normalized)
        return tuple(result)

    @staticmethod
    def _alternative_fits_clip(
        alternative: dict[str, Any],
        clip: RenderClipRC2,
    ) -> bool:
        if str(alternative.get("media_type") or "").lower() != clip.media_type:
            return False
        path = Path(str(alternative.get("asset_path") or ""))
        if not path.exists() or not path.is_file():
            return False
        if clip.media_type == "video":
            try:
                duration = float(alternative.get("duration_sec") or 0.0)
            except (TypeError, ValueError):
                return False
            if duration + 0.10 < clip.duration_sec:
                return False
        return True

    @staticmethod
    def _asset_identity(clip: RenderClipRC2) -> str:
        """Return a stable identity for duplicate detection."""
        raw_path = str(clip.asset_path or "").strip()
        if raw_path:
            return os.path.normcase(os.path.abspath(raw_path))

        raw_name = str(clip.asset_name or "").strip()
        return raw_name.casefold()

    @staticmethod
    def _event_category(clip: RenderClipRC2) -> str | None:
        """Classify documentary source sound from semantic clip metadata."""

        haystack = " ".join(
            str(value or "")
            for value in (
                clip.asset_name,
                clip.scene_title,
                clip.block,
                clip.story_goal,
                clip.visual_need,
                clip.emotion,
                clip.source_mode,
                " ".join(clip.quality_flags),
            )
        ).casefold()

        # CHANGE-004:
        # Eligibility is not restricted to three festival-event types.
        # Any source sound with documentary, emotional or spatial meaning
        # may be considered by the editor.
        categories: tuple[tuple[str, tuple[str, ...]], ...] = (
            (
                "mascleta",
                (
                    "mascleta",
                    "masclet?",
                    "firecracker",
                    "pyrotechnic barrage",
                    "petard",
                    "explosion",
                    "blast",
                ),
            ),
            (
                "fireworks",
                (
                    "fireworks",
                    "firework",
                    "fuegos artificiales",
                    "feu d'artifice",
                    "salute",
                    "final blast",
                    "palmera",
                ),
            ),
            (
                "music_performance",
                (
                    "music_band",
                    "music band",
                    "marching band",
                    "brass band",
                    "orchestra",
                    "banda de m?sica",
                    "banda musica",
                    "live music",
                    "musician",
                    "concert",
                    "drum",
                    "drumming",
                ),
            ),
            (
                "crowd_reaction",
                (
                    "crowd",
                    "audience",
                    "applause",
                    "applauding",
                    "cheering",
                    "cheer",
                    "ovation",
                    "reaction",
                    "celebration",
                    "spectators",
                    "people shouting",
                ),
            ),
            (
                "parade_procession",
                (
                    "parade",
                    "procession",
                    "march",
                    "marching",
                    "desfile",
                    "cabalgata",
                    "festival street",
                    "street celebration",
                ),
            ),
            (
                "fire_burning",
                (
                    "fire",
                    "flame",
                    "flames",
                    "burning",
                    "bonfire",
                    "hoguera",
                    "crem?",
                    "crema",
                    "crackling",
                ),
            ),
            (
                "water_sea",
                (
                    "sea",
                    "ocean",
                    "wave",
                    "waves",
                    "surf",
                    "water",
                    "beach",
                    "shore",
                    "coast",
                    "splash",
                ),
            ),
            (
                "street_ambience",
                (
                    "street",
                    "city ambience",
                    "urban ambience",
                    "traffic",
                    "market",
                    "footsteps",
                    "walking",
                    "square",
                    "plaza",
                    "promenade",
                    "marina",
                ),
            ),
            (
                "emergency_activity",
                (
                    "siren",
                    "sirens",
                    "firefighter",
                    "firefighters",
                    "fire brigade",
                    "emergency",
                    "hose",
                    "water cannon",
                ),
            ),
            (
                "vehicle_movement",
                (
                    "car",
                    "bus",
                    "motorcycle",
                    "train",
                    "boat",
                    "ship",
                    "engine",
                    "vehicle",
                    "driving",
                    "passing",
                ),
            ),
            (
                "human_activity",
                (
                    "conversation",
                    "speaking",
                    "shouting",
                    "chanting",
                    "singing",
                    "laughing",
                    "children playing",
                    "vendor",
                    "performer",
                ),
            ),
        )

        for category, keywords in categories:
            if any(keyword in haystack for keyword in keywords):
                return category

        return None

    @staticmethod
    def _natural_sound_priority(
        clip: RenderClipRC2,
        category: str,
    ) -> float:
        """Deterministically rank natural-sound candidates."""
        base_by_category = {
            "mascleta": 3.4,
            "fireworks": 3.2,
            "crowd_reaction": 3.0,
            "music_performance": 2.9,
            "fire_burning": 2.8,
            "emergency_activity": 2.7,
            "parade_procession": 2.6,
            "water_sea": 2.3,
            "human_activity": 2.2,
            "street_ambience": 2.0,
            "vehicle_movement": 1.8,
        }
        score = base_by_category.get(category, 1.0)

        # Prefer longer usable clips, while preventing duration from
        # overwhelming event importance.
        score += min(max(float(clip.duration_sec), 0.0), 12.0) / 12.0

        # Existing concrete windows are stronger evidence than a bare flag.
        if clip.natural_sound_windows:
            score += 0.35

        # Small stable tie-breaker based on timeline position.
        score += 1.0 / (100000.0 + max(int(clip.shot_index), 0))
        return score

    def _load_editor_overrides(self) -> dict[str, Any]:
        """Load optional project-specific editorial corrections.

        The file is data, not hard-coded project logic. It is consumed once for
        the supervised correction render and can later be removed without
        changing the RC2 engine.
        """
        path = self.config.rc2_dir / "editor_overrides_rc2.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid editor override JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Editor override root must be an object: {path}")
        if payload.get("enabled", True) is False:
            return {}
        return payload

    @staticmethod
    def _clip_piece(
        clip: RenderClipRC2,
        *,
        offset_start: float,
        offset_end: float,
        suffix: str,
    ) -> RenderClipRC2:
        """Return a non-overlapping source fragment of a rendered clip."""
        offset_start = max(0.0, min(float(offset_start), clip.duration_sec))
        offset_end = max(offset_start, min(float(offset_end), clip.duration_sec))
        duration = round(offset_end - offset_start, 3)
        if duration <= 0:
            raise ValueError("Cannot create an empty editor clip fragment")

        windows: list[tuple[float, float]] = []
        for win_start, win_end in clip.natural_sound_windows:
            left = max(float(win_start), offset_start)
            right = min(float(win_end), offset_end)
            if right - left > 0.01:
                windows.append((round(left - offset_start, 3), round(right - offset_start, 3)))

        source_in = round(clip.source_in_sec + offset_start, 3)
        source_out = (
            round(clip.source_in_sec + offset_end, 3)
            if clip.media_type == "video"
            else None
        )
        flags = tuple(dict.fromkeys((*clip.quality_flags, "editor_timeline_split")))
        # A fragment can be shorter than the transition inherited from its
        # parent clip. Strict validation rejects such fragments, therefore the
        # transition is reduced to a safe value (or changed to a cut).
        transition = clip.transition
        transition_duration = max(0.0, float(clip.transition_duration_sec))
        safe_max = max(0.0, duration * 0.5)
        if transition_duration > safe_max:
            transition_duration = round(safe_max, 3)
        if transition_duration < 0.05:
            transition = "cut"
            transition_duration = 0.0

        return replace(
            clip,
            shot_id=f"{clip.shot_id}__{suffix}",
            start_sec=0.0,
            end_sec=duration,
            duration_sec=duration,
            source_in_sec=source_in,
            source_out_sec=source_out,
            transition=transition,
            transition_duration_sec=transition_duration,
            natural_sound_enabled=bool(windows),
            natural_sound_windows=tuple(windows),
            quality_flags=flags,
        )

    @staticmethod
    def _compact_clips(clips: Iterable[RenderClipRC2]) -> list[RenderClipRC2]:
        cursor = 0.0
        result: list[RenderClipRC2] = []
        for position, clip in enumerate(clips, start=1):
            start = round(cursor, 3)
            end = round(start + clip.duration_sec, 3)
            result.append(replace(
                clip,
                shot_index=position,
                start_sec=start,
                end_sec=end,
                duration_sec=round(end-start, 3),
            ))
            cursor = end
        return result

    @staticmethod
    def _normalize_override_ranges(value: Any) -> list[tuple[float, float]]:
        result: list[tuple[float, float]] = []
        if not isinstance(value, list):
            return result
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                start = float(item.get("start_sec"))
                end = float(item.get("end_sec"))
            except (TypeError, ValueError):
                continue
            if start >= 0 and end > start:
                result.append((round(start, 3), round(end, 3)))
        return result

    def _apply_editor_sound_overrides(
        self,
        clips: list[RenderClipRC2],
        overrides: dict[str, Any],
    ) -> tuple[list[RenderClipRC2], dict[str, Any]]:
        enable_ranges = self._normalize_override_ranges(overrides.get("natural_sound_enable"))
        disable_ranges = self._normalize_override_ranges(overrides.get("natural_sound_disable"))
        changed = 0
        forced_windows = 0
        result: list[RenderClipRC2] = []

        for clip in clips:
            windows = list(clip.natural_sound_windows)
            forced = False
            for abs_start, abs_end in enable_ranges:
                left = max(clip.start_sec, abs_start)
                right = min(clip.end_sec, abs_end)
                if right - left > 0.01 and clip.media_type == "video":
                    windows.append((round(left - clip.start_sec, 3), round(right - clip.start_sec, 3)))
                    forced = True
                    forced_windows += 1

            # Merge enabled windows first.
            merged: list[tuple[float, float]] = []
            for start, end in sorted(windows):
                start = max(0.0, min(float(start), clip.duration_sec))
                end = max(start, min(float(end), clip.duration_sec))
                if end - start <= 0.01:
                    continue
                if merged and start <= merged[-1][1] + 0.01:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))

            # Subtract explicit mute ranges from enabled source-sound windows.
            for abs_start, abs_end in disable_ranges:
                mute_left = max(0.0, abs_start - clip.start_sec)
                mute_right = min(clip.duration_sec, abs_end - clip.start_sec)
                if mute_right - mute_left <= 0.01:
                    continue
                next_windows: list[tuple[float, float]] = []
                for start, end in merged:
                    if mute_right <= start or mute_left >= end:
                        next_windows.append((start, end))
                        continue
                    if mute_left > start + 0.01:
                        next_windows.append((start, min(mute_left, end)))
                    if mute_right < end - 0.01:
                        next_windows.append((max(mute_right, start), end))
                merged = next_windows

            normalized = tuple((round(a, 3), round(b, 3)) for a, b in merged)
            flags = list(clip.quality_flags)
            if forced:
                flags.append("editor_natural_sound_forced")
            if normalized != clip.natural_sound_windows or bool(normalized) != clip.natural_sound_enabled:
                changed += 1
            result.append(replace(
                clip,
                natural_sound_enabled=bool(normalized),
                natural_sound_windows=normalized,
                quality_flags=tuple(dict.fromkeys(flags)),
            ))

        return result, {
            "enable_ranges": [{"start_sec": a, "end_sec": b} for a, b in enable_ranges],
            "disable_ranges": [{"start_sec": a, "end_sec": b} for a, b in disable_ranges],
            "clips_changed": changed,
            "forced_window_intersections": forced_windows,
        }

    def _apply_editor_timeline_overrides(
        self,
        clips: list[RenderClipRC2],
        overrides: dict[str, Any],
    ) -> tuple[list[RenderClipRC2], dict[str, Any]]:
        move = overrides.get("move") if isinstance(overrides.get("move"), dict) else {}
        move_ranges = self._normalize_override_ranges(move.get("ranges"))
        insert_at = max(0.0, float(move.get("insert_at_sec", 0.0) or 0.0))
        trim_end_raw = overrides.get("trim_end_sec")
        trim_end = float(trim_end_raw) if trim_end_raw not in (None, "") else None

        moved_groups: list[list[RenderClipRC2]] = [[] for _ in move_ranges]
        remaining: list[RenderClipRC2] = []

        # Split videos against move boundaries in the original compact timeline.
        # Still images are indivisible visual assets under the absolute one-use
        # policy. Assign a complete still to the range containing its midpoint
        # instead of creating two clips backed by the same image file.
        for clip in clips:
            if clip.media_type == "image":
                absolute_mid = clip.start_sec + (clip.duration_sec / 2.0)
                target_group = None
                for group_index, (start, end) in enumerate(move_ranges):
                    if start <= absolute_mid < end:
                        target_group = group_index
                        break
                if target_group is None:
                    remaining.append(clip)
                else:
                    moved_groups[target_group].append(clip)
                continue

            boundaries = {0.0, float(clip.duration_sec)}
            for start, end in move_ranges:
                if clip.start_sec < start < clip.end_sec:
                    boundaries.add(round(start - clip.start_sec, 6))
                if clip.start_sec < end < clip.end_sec:
                    boundaries.add(round(end - clip.start_sec, 6))
            points = sorted(boundaries)
            for index in range(len(points) - 1):
                left, right = points[index], points[index + 1]
                if right - left <= 0.01:
                    continue
                absolute_mid = clip.start_sec + ((left + right) / 2.0)
                target_group = None
                for group_index, (start, end) in enumerate(move_ranges):
                    if start <= absolute_mid < end:
                        target_group = group_index
                        break
                piece = self._clip_piece(
                    clip,
                    offset_start=left,
                    offset_end=right,
                    suffix=f"ed{index+1:02d}",
                ) if len(points) > 2 else clip
                if target_group is None:
                    remaining.append(piece)
                else:
                    moved_groups[target_group].append(piece)

        remaining = self._compact_clips(remaining)
        moved = [piece for group in moved_groups for piece in group]

        # Insert by splitting the remaining programme exactly at insert_at.
        before: list[RenderClipRC2] = []
        after: list[RenderClipRC2] = []
        for clip in remaining:
            if clip.end_sec <= insert_at + 0.001:
                before.append(clip)
            elif clip.start_sec >= insert_at - 0.001:
                after.append(clip)
            else:
                # Do not split a still image at the insertion point. Splitting
                # would create two timeline clips backed by the same image and
                # violate the absolute one-use visual policy. Keep the complete
                # still before the inserted montage; the insertion remains
                # close to the requested editorial time and total duration is
                # unchanged. Video may be split because each piece has a
                # distinct, non-overlapping source range.
                if clip.media_type == "image":
                    before.append(clip)
                else:
                    cut = insert_at - clip.start_sec
                    before.append(self._clip_piece(clip, offset_start=0.0, offset_end=cut, suffix="insA"))
                    after.append(self._clip_piece(clip, offset_start=cut, offset_end=clip.duration_sec, suffix="insB"))

        assembled = self._compact_clips([*before, *moved, *after])

        # Hard programme end: trim the last intersecting clip, then discard all later material.
        if trim_end is not None:
            trimmed: list[RenderClipRC2] = []
            for clip in assembled:
                if clip.start_sec >= trim_end - 0.001:
                    break
                if clip.end_sec <= trim_end + 0.001:
                    trimmed.append(clip)
                    continue
                keep = trim_end - clip.start_sec
                if keep > 0.01:
                    trimmed.append(self._clip_piece(clip, offset_start=0.0, offset_end=keep, suffix="trim"))
                break
            assembled = self._compact_clips(trimmed)

        return assembled, {
            "move_ranges": [{"start_sec": a, "end_sec": b} for a, b in move_ranges],
            "insert_at_sec": round(insert_at, 3),
            "moved_duration_sec": round(sum(c.duration_sec for c in moved), 3),
            "trim_end_sec": round(trim_end, 3) if trim_end is not None else None,
            "output_duration_sec": round(assembled[-1].end_sec, 3) if assembled else 0.0,
        }

    # ------------------------------------------------------------------
    # Conservative pre-render editor pass
    # ------------------------------------------------------------------

    def _editor_pass(
        self,
        model: RenderModelRC2,
    ) -> tuple[RenderModelRC2, dict[str, Any]]:
        """Keep every visual asset at most once and compact the film timeline.

        The first use of an asset is retained. A later use is replaced by an
        unused verified alternative when possible. If no such alternative
        exists, that montage position is removed. The remaining clips are
        packed back-to-back, so film duration is determined only by the
        available unique material.
        """
        ordered = sorted(model.clips, key=lambda item: (item.start_sec, item.shot_index))
        minimum_natural_gap_sec = max(
            0.0, float(getattr(self.config, "editor_natural_sound_gap_sec", 12.0))
        )

        kept_clips: list[RenderClipRC2] = []
        used_assets: set[str] = set()
        replacement_rows: list[dict[str, Any]] = []
        removed_rows: list[dict[str, Any]] = []
        cursor_sec = 0.0

        for original in ordered:
            clip = original
            identity = self._asset_identity(clip)

            if identity and identity in used_assets:
                chosen: dict[str, Any] | None = None
                rejection_reasons: list[dict[str, Any]] = []
                for alternative in clip.alternative_assets:
                    alt_identity = os.path.normcase(
                        os.path.abspath(str(alternative.get("asset_path") or ""))
                    )
                    reason = None
                    if not self._alternative_fits_clip(alternative, clip):
                        reason = "incompatible_or_missing"
                    elif alt_identity == identity:
                        reason = "same_asset"
                    elif alt_identity in used_assets:
                        reason = "already_used_in_film"
                    if reason is None:
                        chosen = alternative
                        break
                    rejection_reasons.append({
                        "asset_name": alternative.get("asset_name"),
                        "asset_path": alternative.get("asset_path"),
                        "reason": reason,
                    })

                if chosen is not None:
                    old_name = clip.asset_name
                    old_path = clip.asset_path
                    old_identity = identity
                    clip = replace(
                        clip,
                        asset_name=str(chosen.get("asset_name") or ""),
                        asset_path=str(chosen.get("asset_path") or ""),
                        media_type=str(chosen.get("media_type") or clip.media_type).lower(),
                        source_in_sec=0.0,
                        source_out_sec=(
                            round(clip.duration_sec, 3)
                            if str(chosen.get("media_type") or clip.media_type).lower() == "video"
                            else None
                        ),
                        quality_flags=tuple(
                            dict.fromkeys((*clip.quality_flags, "editor_duplicate_replaced"))
                        ),
                    )
                    identity = self._asset_identity(clip)
                    replacement_rows.append({
                        "shot_id": clip.shot_id,
                        "shot_index": clip.shot_index,
                        "old_asset_identity": old_identity,
                        "old_asset_name": old_name,
                        "old_asset_path": old_path,
                        "new_asset_identity": identity,
                        "new_asset_name": clip.asset_name,
                        "new_asset_path": clip.asset_path,
                        "assignment_score": chosen.get("assignment_score"),
                        "provenance": chosen.get("provenance"),
                        "status": "REPLACED_UNUSED_VERIFIED_ALTERNATIVE",
                    })
                else:
                    clip = replace(
                        clip,
                        quality_flags=tuple(
                            dict.fromkeys(
                                (
                                    *clip.quality_flags,
                                    "editor_repeated_asset_allowed",
                                )
                            )
                        ),
                    )

            compact_start = round(cursor_sec, 3)
            compact_end = round(compact_start + float(clip.duration_sec), 3)
            clip = replace(
                clip,
                start_sec=compact_start,
                end_sec=compact_end,
                duration_sec=round(compact_end - compact_start, 3),
            )
            kept_clips.append(clip)
            cursor_sec = compact_end
            if identity:
                used_assets.add(identity)

        editor_overrides = self._load_editor_overrides()
        kept_clips, timeline_override_report = self._apply_editor_timeline_overrides(
            kept_clips,
            editor_overrides,
        )
        kept_clips, sound_override_report = self._apply_editor_sound_overrides(
            kept_clips,
            editor_overrides,
        )

        candidates: list[tuple[float, int, RenderClipRC2, str]] = []
        for position, clip in enumerate(kept_clips):
            category = self._event_category(clip)
            if (
                clip.media_type == "video"
                and clip.natural_sound_enabled
                and category is not None
            ):
                candidates.append((self._natural_sound_priority(clip, category), position, clip, category))

        forced_clips = [
            clip for clip in kept_clips
            if "editor_natural_sound_forced" in clip.quality_flags
            and clip.media_type == "video"
            and bool(clip.natural_sound_windows)
        ]
        selected_ids: set[str] = {clip.shot_id for clip in forced_clips}
        selected_rows: list[dict[str, Any]] = [
            {
                "shot_id": clip.shot_id,
                "shot_index": clip.shot_index,
                "scene_key": str(clip.scene_id or clip.scene_title or clip.block or f"shot:{clip.shot_id}").strip().casefold(),
                "scene_id": clip.scene_id,
                "scene_title": clip.scene_title,
                "start_sec": clip.start_sec,
                "category": self._event_category(clip) or "editor_override",
                "score": 999.0,
                "selection": "editor_override",
            }
            for clip in forced_clips
        ]
        selected_scene_keys: set[str] = {str(item["scene_key"]) for item in selected_rows}
        category_counts: dict[str, int] = {}
        for item in selected_rows:
            category = str(item["category"])
            category_counts[category] = category_counts.get(category, 0) + 1

        for score, position, clip, category in sorted(
            candidates,
            key=lambda item: (-item[0], item[1]),
        ):
            if clip.shot_id in selected_ids:
                continue
            scene_key = str(
                clip.scene_id
                or clip.scene_title
                or clip.block
                or f"shot:{clip.shot_id}"
            ).strip().casefold()

            if scene_key in selected_scene_keys:
                continue
            if any(
                abs(float(clip.start_sec) - float(item["start_sec"]))
                < minimum_natural_gap_sec
                for item in selected_rows
            ):
                continue

            selected_ids.add(clip.shot_id)
            selected_scene_keys.add(scene_key)
            category_counts[category] = category_counts.get(category, 0) + 1
            selected_rows.append({
                "shot_id": clip.shot_id,
                "shot_index": clip.shot_index,
                "scene_key": scene_key,
                "scene_id": clip.scene_id,
                "scene_title": clip.scene_title,
                "start_sec": clip.start_sec,
                "category": category,
                "score": round(score, 3),
            })

        final_clips: list[RenderClipRC2] = []
        natural_sound_changed = 0
        for clip in kept_clips:
            category = self._event_category(clip)
            forced = "editor_natural_sound_forced" in clip.quality_flags
            should_enable = (
                clip.shot_id in selected_ids
                and clip.media_type == "video"
                and (category is not None or forced)
            )
            windows = clip.natural_sound_windows
            if should_enable and not windows:
                windows = ((0.0, round(clip.duration_sec, 3)),)
            if should_enable != clip.natural_sound_enabled or windows != clip.natural_sound_windows:
                natural_sound_changed += 1
            final_clips.append(replace(
                clip,
                natural_sound_enabled=should_enable,
                natural_sound_windows=windows if should_enable else tuple(),
            ))

        final_clips.sort(key=lambda item: (item.start_sec, item.shot_index))
        compact_duration = round(final_clips[-1].end_sec, 3) if final_clips else 0.0
        edited_model = replace(
            model,
            clips=tuple(final_clips),
            expected_duration_sec=compact_duration,
            skipped=tuple((*model.skipped, *removed_rows)),
        )
        selected_rows.sort(key=lambda item: (item["start_sec"], item["shot_index"]))

        report = {
            "schema": "atlas_zero.editor_pass.rc2.v5",
            "state": "EDITOR_PASS_COMPLETE",
            "project_id": model.project_id,
            "mode": "unique_assets_compact_timeline",
            "visual_mutation": "replace_or_remove_repeated_assets",
            "clips_input": len(model.clips),
            "clips_output": len(final_clips),
            "clips_removed": len(removed_rows),
            "duration_input_sec": round(float(model.expected_duration_sec), 3),
            "duration_output_sec": compact_duration,
            "duration_removed_sec": round(
                sum(float(row["duration_removed_sec"]) for row in removed_rows), 3
            ),
            "duplicate_candidates": len(replacement_rows) + len(removed_rows),
            "duplicates_replaced": len(replacement_rows),
            "duplicates_removed": len(removed_rows),
            "clips_replaced": len(replacement_rows),
            "replacement_actions": replacement_rows,
            "removed_repeated_clips": removed_rows,
            "replacement_blocked": [],
            "duplicate_groups_total": 0,
            "duplicate_groups": [],
            "duplicate_warnings": [],
            "natural_sound_candidates": len(candidates),
            "natural_sound_selected": len(selected_ids),
            "natural_sound_changed": natural_sound_changed,
            "natural_sound_selection_policy": "one_ranked_event_per_scene_with_strict_spacing",
            "natural_sound_ratio_limit": None,
            "natural_sound_scenes_selected": len(selected_scene_keys),
            "natural_sound_min_gap_sec": minimum_natural_gap_sec,
            "natural_sound_categories": category_counts,
            "selected_natural_sound": selected_rows,
            "asset_uniqueness_policy": "first_use_kept_repeat_replaced_or_removed",
            "timeline_policy": "compact_after_removal_with_optional_editor_overrides",
            "editor_overrides_loaded": bool(editor_overrides),
            "editor_sound_overrides": sound_override_report,
            "editor_timeline_overrides": timeline_override_report,
            "warnings": [],
            "authority": "RenderEngineRC2",
        }

        self._emit(
            "EDITOR_PASS_COMPLETE",
            duplicate_candidates=report["duplicate_candidates"],
            duplicates_replaced=len(replacement_rows),
            duplicates_removed=len(removed_rows),
            clips_output=len(final_clips),
            expected_duration_sec=compact_duration,
            natural_sound_candidates=len(candidates),
            natural_sound_selected=len(selected_ids),
            natural_sound_changed=natural_sound_changed,
        )
        return edited_model, report

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_render_model(
        self,
        model: RenderModelRC2,
        *,
        editor_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run strict Phase 3 preflight before any render backend is started.

        The editor report is part of the validation contract. Editorial defects
        detected before rendering must not be lost between EditorPassRC2 and the
        release gate.
        """

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

        editor_report = editor_report or {}
        remaining_duplicates = list(
            editor_report.get("duplicate_warnings")
            or editor_report.get("duplicate_groups")
            or []
        )
        replacement_blocked = list(editor_report.get("replacement_blocked") or [])
        if remaining_duplicates or replacement_blocked:
            duplicate_count = max(
                len(remaining_duplicates),
                len(replacement_blocked),
            )
            blocking.append(
                f"{duplicate_count} visual asset reuses remain after editor pass"
            )

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
                # A video asset may be split into non-overlapping editorial
                # fragments. Treat each concrete source range as the visual
                # identity; an exact repeated range is still blocked.
                if clip.media_type == "video":
                    source_end = (
                        clip.source_out_sec
                        if clip.source_out_sec is not None
                        else clip.source_in_sec + clip.duration_sec
                    )
                    asset_key += f"#{clip.source_in_sec:.3f}-{source_end:.3f}"
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
            warnings.append(
                f"{len(clip_issues)} render clips require runtime normalization; "
                "short video sources may be looped to editorial duration"
            )

        minimum_video_shots = max(
            0,
            int(getattr(self.config, "minimum_video_shots", 1)),
        )
        if video_shots < minimum_video_shots:
            warnings.append(
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

        reused_assets = {
            asset_path: use_count
            for asset_path, use_count in asset_use_count.items()
            if use_count > 1
        }
        repeated_uses_total = sum(
            use_count - 1 for use_count in reused_assets.values()
        )
        if reused_assets:
            warnings.append(
                f"{repeated_uses_total} visual asset reuses detected; "
                "reuse allowed for voice-led documentary production"
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

        scene_audio_validation = self._validate_scene_audio_policy(model)
        blocking.extend(scene_audio_validation["blocking_errors"])
        warnings.extend(scene_audio_validation["warnings"])

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
            "reused_assets": reused_assets,
            "repeated_uses_total": repeated_uses_total,
            "asset_uniqueness_policy": "absolute_one_use_per_film",
            "timeline_gaps": timeline_gaps,
            "timeline_overlaps": timeline_overlaps,
            "voice_path": model.voice_path,
            "music_path": model.music_path,
            "audio_validation": audio_validation,
            "scene_audio_validation": scene_audio_validation,
            "editor_validation": {
                "duplicate_warnings": remaining_duplicates,
                "replacement_blocked": replacement_blocked,
                "editor_report_state": editor_report.get("state"),
            },
            "blocking_errors": blocking,
            "warnings": warnings,
            "clip_issues": clip_issues,
            "asset_probes": asset_probes,
            "skipped": list(model.skipped),
            "authority": "RenderEngineRC2",
            "migration_phase": "PHASE_7_NATIVE_AUDIO_COMPOSER",
        }

    def _validate_scene_audio_policy(
        self,
        model: RenderModelRC2,
    ) -> dict[str, Any]:
        """Validate editorial source-sound decisions against scene structure."""

        blocking: list[str] = []
        warnings: list[str] = []
        events: list[dict[str, Any]] = []
        by_scene: dict[str, list[dict[str, Any]]] = {}

        for clip in sorted(
            model.clips,
            key=lambda item: (item.start_sec, item.shot_index),
        ):
            if not clip.natural_sound_enabled:
                continue

            category = self._event_category(clip)
            forced_editor_event = "editor_natural_sound_forced" in clip.quality_flags
            if category is None and forced_editor_event:
                category = "editor_override"
            scene_key = str(
                clip.scene_id
                or clip.scene_title
                or clip.block
                or ""
            ).strip().casefold()

            if category is None:
                blocking.append(
                    f"shot {clip.shot_index}: natural sound has no semantic event category"
                )

            if not scene_key:
                warnings.append(
                    f"shot {clip.shot_index}: natural sound event has no scene identity"
                )
                scene_key = f"shot:{clip.shot_id}"

            windows = clip.natural_sound_windows or (
                (0.0, round(float(clip.duration_sec), 3)),
            )
            for window_start, window_end in windows:
                event = {
                    "shot_id": clip.shot_id,
                    "forced_editor_event": forced_editor_event,
                    "shot_index": clip.shot_index,
                    "scene_key": scene_key,
                    "scene_id": clip.scene_id,
                    "scene_title": clip.scene_title,
                    "category": category,
                    "timeline_start_sec": round(
                        float(clip.start_sec) + float(window_start),
                        3,
                    ),
                    "timeline_end_sec": round(
                        float(clip.start_sec) + float(window_end),
                        3,
                    ),
                }
                events.append(event)
                by_scene.setdefault(scene_key, []).append(event)

        maximum_per_scene = max(
            1,
            int(getattr(self.config, "maximum_natural_sound_events_per_scene", 1)),
        )
        for scene_key, scene_events in by_scene.items():
            # Manual sound marks are supervised editorial ground truth for
            # this correction render. They intentionally may contain several
            # windows inside one act and must not be rejected by the normal
            # autonomous-selection density limit.
            autonomous_events = [
                event for event in scene_events
                if not bool(event.get("forced_editor_event"))
            ]
            if len(autonomous_events) > maximum_per_scene:
                blocking.append(
                    f"scene {scene_key!r} contains {len(autonomous_events)} autonomous natural-sound "
                    f"events; maximum is {maximum_per_scene}"
                )

        ordered_events = sorted(
            events,
            key=lambda item: (
                item["timeline_start_sec"],
                item["timeline_end_sec"],
                item["shot_index"],
            ),
        )
        overlaps: list[dict[str, Any]] = []
        previous: dict[str, Any] | None = None
        for event in ordered_events:
            if (
                previous is not None
                and float(event["timeline_start_sec"])
                < float(previous["timeline_end_sec"]) - 0.05
            ):
                overlap = {
                    "previous_shot_id": previous["shot_id"],
                    "shot_id": event["shot_id"],
                    "overlap_sec": round(
                        float(previous["timeline_end_sec"])
                        - float(event["timeline_start_sec"]),
                        3,
                    ),
                }
                overlaps.append(overlap)
            if (
                previous is None
                or float(event["timeline_end_sec"])
                > float(previous["timeline_end_sec"])
            ):
                previous = event

        if overlaps:
            blocking.append(
                f"{len(overlaps)} natural-sound timeline overlaps detected"
            )

        return {
            "blocking_errors": blocking,
            "warnings": warnings,
            "events": ordered_events,
            "events_by_scene": by_scene,
            "overlaps": overlaps,
            "maximum_events_per_scene": maximum_per_scene,
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

    @staticmethod
    def _audio_event_identity(
        source_path: Path,
        source_start_sec: float,
        source_end_sec: float,
    ) -> str:
        canonical = (
            f"{os.path.normcase(os.path.abspath(str(source_path)))}|"
            f"{source_start_sec:.6f}|{source_end_sec:.6f}"
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _render_timeline_hash(model: RenderModelRC2) -> str:
        payload = [
            {
                "shot_id": clip.shot_id,
                "asset_path": os.path.normcase(os.path.abspath(clip.asset_path)),
                "timeline_start_sec": round(float(clip.start_sec), 6),
                "timeline_end_sec": round(float(clip.end_sec), 6),
                "source_in_sec": round(float(clip.source_in_sec), 6),
                "source_out_sec": (
                    round(float(clip.source_out_sec), 6)
                    if clip.source_out_sec is not None
                    else None
                ),
            }
            for clip in model.clips
        ]
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _extract_audio_asset(
        self,
        *,
        ffmpeg: str,
        source_path: Path,
        source_start_sec: float,
        duration_sec: float,
        destination: Path,
    ) -> None:
        if destination.exists() and destination.stat().st_size > 0:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.stem + ".partial" + destination.suffix)
        partial.unlink(missing_ok=True)
        command = [
            ffmpeg,
            "-y",
            "-nostdin",
            "-ss",
            f"{source_start_sec:.6f}",
            "-t",
            f"{duration_sec:.6f}",
            "-i",
            str(source_path),
            "-vn",
            "-acodec",
            "pcm_s24le",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(partial),
        ]
        process = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            partial.unlink(missing_ok=True)
            tail = "\n".join(process.stderr.splitlines()[-30:])
            raise RuntimeError(
                "RC2 natural-sound extraction failed for "
                f"{source_path}:\n{tail}"
            )
        if not partial.exists() or partial.stat().st_size <= 0:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                f"RC2 extracted audio is empty: {partial}"
            )
        os.replace(partial, destination)

    _HOGUERAS_VOICE_STARTS: dict[str, float] = {
        "SC01": 4.000,
        "SC02": 39.000,
        "SC03": 77.000,
        "SC04": 113.000,
        "SC05": 180.000,
        "SC06": 222.000,
        "SC07": 302.000,
        "SC08": 344.000,
        "SC09": 380.000,
        "SC10": 415.000,
        "SC11": 463.000,
        "SC12": 501.000,
        "SC13": 536.000,
        "SC14": 566.000,
        "SC15": 589.700,
        "SC16": 618.800,
        "SC17": 640.000,
        "SC18": 658.200,
        "SC19": 691.000,
        "SC20": 767.500,
    }

    def _probe_media_duration(self, path: Path) -> float:
        process = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"Unable to probe media duration for {path}: "
                f"{process.stderr.strip()}"
            )
        try:
            duration = float(process.stdout.strip())
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Invalid media duration for {path}: {process.stdout!r}"
            ) from exc
        if duration <= 0:
            raise RuntimeError(f"Media duration is not positive: {path}")
        return duration

    def _load_voice_scene_placements(
        self,
        *,
        visual_duration_sec: float,
    ) -> list[dict[str, Any]]:
        """Return scene-level narration placements for the final film.

        A project sidecar is authoritative when present. For the current
        Hogueras correction render, a reviewed set of semantic anchors is used
        as a safe fallback. Each following scene is shifted only when required
        to prevent overlap, while preserving a short natural pause.
        """

        scene_dir = self.config.project_dir / "01_Audio" / "scenes"
        map_path = self.config.rc2_dir / "voice_placement_map_rc2.json"
        minimum_gap_sec = 0.8

        desired_starts: dict[str, float] = {}
        if map_path.exists():
            payload = json.loads(map_path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ValueError(f"Voice placement map must be an object: {map_path}")
            raw_rows = payload.get("placements") or []
            if not isinstance(raw_rows, list):
                raise ValueError(f"Voice placement rows must be a list: {map_path}")
            for row in raw_rows:
                if not isinstance(row, dict):
                    continue
                scene_id = str(row.get("scene_id") or "").strip()
                start = row.get("timeline_start_sec")
                if scene_id and start not in (None, ""):
                    desired_starts[scene_id] = float(start)
        elif self.config.project_id == "hogueras":
            desired_starts = dict(self._HOGUERAS_VOICE_STARTS)
        else:
            return []

        placements: list[dict[str, Any]] = []
        previous_end = 0.0

        for index in range(1, 100):
            scene_id = f"SC{index:02d}"
            audio_path = scene_dir / f"{scene_id}.wav"

            if scene_id not in desired_starts:
                if index == 1:
                    return []
                break

            if not audio_path.exists() or not audio_path.is_file():
                raise FileNotFoundError(
                    f"Voice scene required by placement map is missing: {audio_path}"
                )

            duration = self._probe_media_duration(audio_path)
            desired_start = max(0.0, float(desired_starts[scene_id]))
            start = max(desired_start, previous_end + minimum_gap_sec)
            end = start + duration

            placements.append({
                "scene_id": scene_id,
                "audio_path": str(audio_path),
                "desired_start_sec": round(desired_start, 6),
                "timeline_start_sec": round(start, 6),
                "duration_sec": round(duration, 6),
                "timeline_end_sec": round(end, 6),
                "shift_sec": round(start - desired_start, 6),
            })
            previous_end = end

        if not placements:
            return []

        overflow = placements[-1]["timeline_end_sec"] - visual_duration_sec
        if overflow > 0.001:
            raise RuntimeError(
                "Scene narration does not fit the final visual programme: "
                f"voice_end={placements[-1]['timeline_end_sec']:.3f}s, "
                f"visual={visual_duration_sec:.3f}s, "
                f"overflow={overflow:.3f}s"
            )

        payload = {
            "schema": "atlas_zero.voice_placement.rc2.v2",
            "state": "VOICE_PLACEMENT_READY",
            "project_id": self.config.project_id,
            "film_duration_sec": round(visual_duration_sec, 6),
            "minimum_gap_sec": minimum_gap_sec,
            "scene_count": len(placements),
            "placements": placements,
            "authority": "RenderEngineRC2",
        }
        self._write_json(map_path, payload)
        return placements

    def _compose_phase4_audio(
        self,
        visual_source: Path,
        model: RenderModelRC2,
    ) -> tuple[Path, str]:
        """Build the canonical RC2 programme soundtrack.

        Selected source-sound windows are extracted once into persistent WAV
        assets. Supervised editor events are anchored to source media
        coordinates and rebound to the final edited timeline on every render.
        Music, narration, and natural sound are mixed in one authoritative RC2
        route. A structured registry and synchronization report are written
        before muxing.
        """

        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            raise RuntimeError("ffmpeg and ffprobe are not available in PATH")

        output = self.render_dir / "phase4_av_master_rc2.mp4"
        output.unlink(missing_ok=True)

        duration_probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(visual_source),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if duration_probe.returncode != 0:
            raise RuntimeError(
                "Unable to determine RC2 visual master duration: "
                f"{duration_probe.stderr.strip()}"
            )
        try:
            visual_duration_sec = round(
                float(duration_probe.stdout.strip()),
                6,
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Invalid RC2 visual master duration returned by ffprobe: "
                f"{duration_probe.stdout!r}"
            ) from exc
        if visual_duration_sec <= 0:
            raise RuntimeError(
                f"RC2 visual master duration is invalid: {visual_duration_sec}"
            )

        audio_dir = self.config.rc2_dir / "audio"
        assets_dir = audio_dir / "audio_assets"
        registry_path = audio_dir / "audio_asset_registry_rc2.json"
        report_path = audio_dir / "audio_rebind_report_rc2.json"
        snapshot_path = audio_dir / "audio_events_bound_rc2.json"
        audio_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)

        timeline_hash = self._render_timeline_hash(model)

        def source_has_audio(path: Path) -> bool:
            process = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    str(path),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
            )
            return process.returncode == 0 and bool(process.stdout.strip())

        old_registry: dict[str, Any] = {}
        if registry_path.exists():
            try:
                payload = json.loads(registry_path.read_text(encoding="utf-8-sig"))
                if isinstance(payload, dict):
                    old_registry = payload
            except (OSError, json.JSONDecodeError):
                old_registry = {}

        old_events = [
            dict(item)
            for item in old_registry.get("events", [])
            if isinstance(item, dict)
        ]
        old_by_id = {
            str(item.get("audio_id")): item
            for item in old_events
            if item.get("audio_id")
        }

        current_events: dict[str, dict[str, Any]] = {}
        skipped_sources: list[dict[str, Any]] = []

        for clip in model.clips:
            if clip.media_type != "video" or not clip.natural_sound_enabled:
                continue
            category = self._event_category(clip)
            forced = "editor_natural_sound_forced" in clip.quality_flags
            if category is None and forced:
                category = "editor_override"
            if category is None:
                continue

            source_path = Path(clip.asset_path)
            if not source_path.exists() or not source_has_audio(source_path):
                skipped_sources.append({
                    "shot_id": clip.shot_id,
                    "source_path": str(source_path),
                    "reason": "missing_source_or_audio_stream",
                })
                continue

            windows = clip.natural_sound_windows or ((0.0, clip.duration_sec),)
            for window_start, window_end in windows:
                bounded_start = max(0.0, min(float(window_start), clip.duration_sec))
                bounded_end = max(bounded_start, min(float(window_end), clip.duration_sec))
                duration = bounded_end - bounded_start
                if duration <= 0.05:
                    continue

                source_start = float(clip.source_in_sec) + bounded_start
                source_end = source_start + duration
                audio_id = self._audio_event_identity(
                    source_path,
                    source_start,
                    source_end,
                )
                wav_path = assets_dir / f"natural_{audio_id}.wav"
                self._extract_audio_asset(
                    ffmpeg=ffmpeg,
                    source_path=source_path,
                    source_start_sec=source_start,
                    duration_sec=duration,
                    destination=wav_path,
                )
                current_events[audio_id] = {
                    "audio_id": audio_id,
                    "kind": "natural_sound",
                    "category": category,
                    "shot_id": clip.shot_id,
                    "scene_id": clip.scene_id,
                    "source_asset_path": str(source_path),
                    "source_start_sec": round(source_start, 6),
                    "source_end_sec": round(source_end, 6),
                    "duration_sec": round(duration, 6),
                    "timeline_start_sec": round(clip.start_sec + bounded_start, 6),
                    "timeline_end_sec": round(clip.start_sec + bounded_end, 6),
                    "audio_file": str(wav_path),
                    "preserve_sync": bool(forced),
                    "origin": "editor_override" if forced else "editor_selection",
                    "rebind_status": "current_selection",
                    "timeline_hash": timeline_hash,
                }

        # Preserve supervised source-anchored events across later timeline edits.
        unresolved: list[dict[str, Any]] = []
        rebound_count = 0
        for old in old_events:
            if not bool(old.get("preserve_sync")):
                continue
            audio_id = str(old.get("audio_id") or "")
            if not audio_id or audio_id in current_events:
                continue
            source_path_text = str(old.get("source_asset_path") or "")
            try:
                source_start = float(old.get("source_start_sec"))
                source_end = float(old.get("source_end_sec"))
            except (TypeError, ValueError):
                unresolved.append({
                    "audio_id": audio_id,
                    "reason": "invalid_source_coordinates",
                })
                continue

            source_identity = os.path.normcase(os.path.abspath(source_path_text))
            matches: list[RenderClipRC2] = []
            for clip in model.clips:
                if clip.media_type != "video":
                    continue
                if os.path.normcase(os.path.abspath(clip.asset_path)) != source_identity:
                    continue
                clip_source_end = (
                    float(clip.source_out_sec)
                    if clip.source_out_sec is not None
                    else float(clip.source_in_sec) + float(clip.duration_sec)
                )
                if (
                    source_start >= float(clip.source_in_sec) - 0.001
                    and source_end <= clip_source_end + 0.001
                ):
                    matches.append(clip)

            if not matches:
                unresolved.append({
                    "audio_id": audio_id,
                    "source_asset_path": source_path_text,
                    "source_start_sec": source_start,
                    "source_end_sec": source_end,
                    "reason": "source_interval_not_present_in_final_timeline",
                })
                continue

            clip = min(matches, key=lambda item: item.start_sec)
            duration = source_end - source_start
            timeline_start = float(clip.start_sec) + source_start - float(clip.source_in_sec)
            wav_path = Path(str(old.get("audio_file") or ""))
            if not wav_path.exists() or wav_path.stat().st_size <= 0:
                wav_path = assets_dir / f"natural_{audio_id}.wav"
                self._extract_audio_asset(
                    ffmpeg=ffmpeg,
                    source_path=Path(source_path_text),
                    source_start_sec=source_start,
                    duration_sec=duration,
                    destination=wav_path,
                )

            rebound = dict(old)
            rebound.update({
                "shot_id": clip.shot_id,
                "scene_id": clip.scene_id,
                "timeline_start_sec": round(timeline_start, 6),
                "timeline_end_sec": round(timeline_start + duration, 6),
                "duration_sec": round(duration, 6),
                "audio_file": str(wav_path),
                "rebind_status": "rebound",
                "timeline_hash": timeline_hash,
            })
            current_events[audio_id] = rebound
            rebound_count += 1

        if unresolved:
            report = {
                "schema": "atlas_zero.audio_rebind.rc2.v1",
                "state": "BLOCKED",
                "project_id": model.project_id,
                "timeline_hash": timeline_hash,
                "events_total": len(current_events),
                "events_rebound": rebound_count,
                "events_unresolved": len(unresolved),
                "unresolved": unresolved,
                "skipped_sources": skipped_sources,
            }
            self._write_json(report_path, report)
            details = "; ".join(
                f"{item.get('audio_id')}: {item.get('reason')}"
                for item in unresolved
            )
            raise RuntimeError(
                "RC2 final render blocked: preserved audio events could not "
                f"be rebound to the final timeline. {details}"
            )

        events = sorted(
            current_events.values(),
            key=lambda item: (
                float(item.get("timeline_start_sec", 0.0)),
                str(item.get("audio_id", "")),
            ),
        )

        registry_payload = {
            "schema": "atlas_zero.audio_asset_registry.rc2.v1",
            "project_id": model.project_id,
            "timeline_hash": timeline_hash,
            "events": events,
        }
        self._write_json(registry_path, registry_payload)
        self._write_json(snapshot_path, {
            "schema": "atlas_zero.audio_events_bound.rc2.v1",
            "project_id": model.project_id,
            "timeline_hash": timeline_hash,
            "events": events,
        })
        rebind_report = {
            "schema": "atlas_zero.audio_rebind.rc2.v1",
            "state": "READY",
            "project_id": model.project_id,
            "timeline_hash": timeline_hash,
            "previous_timeline_hash": old_registry.get("timeline_hash"),
            "events_total": len(events),
            "events_rebound": rebound_count,
            "events_unresolved": 0,
            "persistent_events": sum(1 for item in events if item.get("preserve_sync")),
            "skipped_sources": skipped_sources,
        }
        self._write_json(report_path, rebind_report)

        command: list[str] = [ffmpeg, "-y", "-i", str(visual_source)]
        next_input = 1
        voice_index: int | None = None
        music_index: int | None = None

        voice_placements = self._load_voice_scene_placements(
            visual_duration_sec=visual_duration_sec,
        )
        voice_scene_inputs: list[tuple[int, dict[str, Any]]] = []

        if voice_placements:
            for placement in voice_placements:
                audio_path = Path(str(placement["audio_path"]))
                voice_scene_inputs.append((next_input, placement))
                command.extend(["-i", str(audio_path)])
                next_input += 1
        elif model.voice_path:
            voice_index = next_input
            command.extend(["-i", str(model.voice_path)])
            next_input += 1

        if model.music_path:
            music_index = next_input
            command.extend(["-stream_loop", "-1", "-i", str(model.music_path)])
            next_input += 1

        event_inputs: list[tuple[int, dict[str, Any]]] = []
        for event in events:
            audio_file = Path(str(event.get("audio_file") or ""))
            if not audio_file.exists() or audio_file.stat().st_size <= 0:
                raise FileNotFoundError(f"RC2 audio asset missing: {audio_file}")
            event_inputs.append((next_input, event))
            command.extend(["-i", str(audio_file)])
            next_input += 1

        filters: list[str] = []
        natural_labels: list[str] = []
        for ordinal, (input_index, event) in enumerate(event_inputs, start=1):
            duration = float(event["duration_sec"])
            timeline_start = float(event["timeline_start_sec"])
            delay_ms = max(0, int(round(timeline_start * 1000)))
            category = str(event.get("category") or "")
            gain_db = -3.0 if category in {"mascleta", "fireworks"} else -5.0
            fade_duration = min(0.18, duration / 4.0)
            fade_out_start = max(0.0, duration - fade_duration)
            label = f"[natural_{ordinal}]"
            chain = (
                f"[{input_index}:a:0]atrim=0:{duration:.6f},"
                "asetpts=PTS-STARTPTS,aresample=48000,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"volume={gain_db:.2f}dB"
            )
            if fade_duration > 0.01:
                chain += (
                    f",afade=t=in:st=0:d={fade_duration:.6f},"
                    f"afade=t=out:st={fade_out_start:.6f}:d={fade_duration:.6f}"
                )
            chain += f",adelay={delay_ms}|{delay_ms}{label}"
            filters.append(chain)
            natural_labels.append(label)

        natural_mix: str | None = None
        if len(natural_labels) == 1:
            filters.append(f"{natural_labels[0]}anull[natural_mix]")
            natural_mix = "[natural_mix]"
        elif natural_labels:
            filters.append(
                "".join(natural_labels)
                + f"amix=inputs={len(natural_labels)}:duration=longest:"
                "dropout_transition=0:normalize=0[natural_mix]"
            )
            natural_mix = "[natural_mix]"

        voice_programme: str | None = None
        voice_sidechain: str | None = None

        if voice_scene_inputs:
            voice_labels: list[str] = []
            for ordinal, (input_index, placement) in enumerate(
                voice_scene_inputs,
                start=1,
            ):
                duration = float(placement["duration_sec"])
                delay_ms = max(
                    0,
                    int(round(float(placement["timeline_start_sec"]) * 1000)),
                )
                label = f"[voice_scene_{ordinal}]"
                filters.append(
                    f"[{input_index}:a:0]atrim=0:{duration:.6f},"
                    "asetpts=PTS-STARTPTS,aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"adelay={delay_ms}|{delay_ms}{label}"
                )
                voice_labels.append(label)

            if len(voice_labels) == 1:
                filters.append(f"{voice_labels[0]}anull[voice_scene_mix]")
            else:
                filters.append(
                    "".join(voice_labels)
                    + f"amix=inputs={len(voice_labels)}:duration=longest:"
                    "dropout_transition=0:normalize=0[voice_scene_mix]"
                )
            need_voice_sidechain = bool(natural_mix or music_index is not None)
            if need_voice_sidechain:
                filters.append(
                    f"[voice_scene_mix]atrim=0:{visual_duration_sec:.6f},"
                    f"apad=pad_dur={visual_duration_sec:.6f},"
                    "asplit=2[voice_sidechain][voice_programme]"
                )
                voice_sidechain = "[voice_sidechain]"
            else:
                filters.append(
                    f"[voice_scene_mix]atrim=0:{visual_duration_sec:.6f},"
                    f"apad=pad_dur={visual_duration_sec:.6f},"
                    "anull[voice_programme]"
                )
            voice_programme = "[voice_programme]"
        elif voice_index is not None:
            need_voice_sidechain = bool(natural_mix or music_index is not None)
            if need_voice_sidechain:
                filters.append(
                    f"[{voice_index}:a:0]atrim=0:{visual_duration_sec:.6f},"
                    "asetpts=PTS-STARTPTS,aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    "asplit=2[voice_sidechain][voice_programme]"
                )
                voice_sidechain = "[voice_sidechain]"
            else:
                filters.append(
                    f"[{voice_index}:a:0]atrim=0:{visual_duration_sec:.6f},"
                    "asetpts=PTS-STARTPTS,aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    "anull[voice_programme]"
                )
            voice_programme = "[voice_programme]"

        music_programme: str | None = None
        if music_index is not None:
            filters.append(
                f"[{music_index}:a:0]atrim=0:{visual_duration_sec:.6f},"
                "asetpts=PTS-STARTPTS,aresample=48000,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                "volume=-16dB[music_programme]"
            )
            music_programme = "[music_programme]"

        if voice_sidechain and natural_mix:
            filters.append(
                f"{natural_mix}{voice_sidechain}sidechaincompress="
                "threshold=0.025:ratio=6:attack=20:release=450:makeup=1"
                "[natural_ducked]"
            )
            natural_mix = "[natural_ducked]"
        if voice_sidechain and music_programme:
            filters.append(
                f"{music_programme}{voice_sidechain}sidechaincompress="
                "threshold=0.020:ratio=8:attack=25:release=600:makeup=1"
                "[music_ducked]"
            )
            music_programme = "[music_ducked]"

        programme_labels = [
            label
            for label in (voice_programme, music_programme, natural_mix)
            if label
        ]

        if programme_labels:
            if len(programme_labels) == 1:
                filters.append(f"{programme_labels[0]}anull[programme_mix]")
            else:
                filters.append(
                    "".join(programme_labels)
                    + f"amix=inputs={len(programme_labels)}:duration=longest:"
                    "dropout_transition=0:normalize=0[programme_mix]"
                )
            filters.append(
                f"[programme_mix]atrim=0:{visual_duration_sec:.6f},"
                f"apad=pad_dur={visual_duration_sec:.6f},"
                "alimiter=limit=0.95[audio_final]"
            )
            command.extend([
                "-filter_complex", ";".join(filters),
                "-map", "0:v:0",
                "-map", "[audio_final]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "256k",
                "-ar", "48000",
                "-ac", "2",
                "-t", f"{visual_duration_sec:.6f}",
                "-movflags", "+faststart",
                str(output),
            ])
            components = []
            if voice_programme:
                components.append("voice")
            if music_programme:
                components.append("music")
            if natural_mix:
                components.append("source_audio")
            mode = "plus".join(components)
        else:
            command.extend([
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-map", "0:v:0",
                "-map", f"{next_input}:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-t", f"{visual_duration_sec:.6f}",
                "-shortest",
                "-movflags", "+faststart",
                str(output),
            ])
            mode = "silent_compatibility_track"

        self._emit(
            "PHASE4_AUDIO_MUX_START",
            mode=mode,
            visual_source=str(visual_source),
            timeline_hash=timeline_hash,
            natural_sound_events=len(events),
            natural_sound_rebound=rebound_count,
            music_ready=model.music_path is not None,
            voice_ready=bool(voice_scene_inputs or model.voice_path),
            voice_scene_placements=len(voice_scene_inputs),
        )

        diagnostic_command_path = self.render_dir / "phase4_ffmpeg_command_rc2.txt"
        diagnostic_command_path.write_text(
            subprocess.list2cmdline(command),
            encoding="utf-8",
        )
        self._run_ffmpeg(command, step="Phase 4 canonical RC2 audio composition")

        if not output.exists() or not output.is_file():
            raise FileNotFoundError(f"Phase 4 audio mux output missing: {output}")

        audio_report = {
            "schema": "atlas_zero.audio_report.rc2.v1",
            "state": "AUDIO_RENDERED",
            "project_id": model.project_id,
            "mode": mode,
            "output": str(output),
            "timeline_hash": timeline_hash,
            "voice_path": model.voice_path,
            "voice_placement_mode": (
                "scene_timeline"
                if voice_scene_inputs
                else "continuous_master"
            ),
            "voice_scene_placements": [
                dict(placement)
                for _, placement in voice_scene_inputs
            ],
            "music_path": model.music_path,
            "events_total": len(events),
            "events_rebound": rebound_count,
            "events": events,
            "registry_path": str(registry_path),
            "rebind_report_path": str(report_path),
            "snapshot_path": str(snapshot_path),
        }
        self._write_json(audio_dir / "audio_report_rc2.json", audio_report)

        self._emit(
            "PHASE4_AUDIO_MUX_COMPLETE",
            mode=mode,
            output=str(output),
            natural_sound_events=len(events),
            timeline_hash=timeline_hash,
        )
        return output, mode

    @staticmethod
    def _run_ffmpeg(command: list[str], *, step: str) -> None:
        if "-nostdin" not in command:
            command = [command[0], "-nostdin", *command[1:]]

        output_path = Path(command[-1])
        log_path = output_path.with_name(
            f"{output_path.stem}_ffmpeg_stderr.txt"
        )
        executed_command_path = output_path.with_name(
            f"{output_path.stem}_ffmpeg_command_executed.txt"
        )

        executed_command_path.write_text(
            subprocess.list2cmdline(command),
            encoding="utf-8",
        )

        process = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )

        log_path.write_text(
            process.stderr or "",
            encoding="utf-8",
        )

        print("=" * 120)
        print(f"FFMPEG STEP: {step}")
        print(f"FFmpeg return code: {process.returncode}")
        print(f"FFmpeg command: {executed_command_path}")
        print(f"FFmpeg stderr:  {log_path}")
        print("=" * 120)

        if process.returncode != 0:
            stderr_tail = "\n".join(
                process.stderr.splitlines()[-30:]
            )
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
        *,
        expected_duration_sec: float | None = None,
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
        expected = float(
            expected_duration_sec
            if expected_duration_sec is not None
            else model.expected_duration_sec
        )
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
            "soft dissolve": "dissolve",
            "soft_dissolve": "dissolve",
            "fade_from_black": "fade",
            "fade from black": "fade",
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
            "static_hold": "static",
            "static hold": "static",
            "hold": "static",
            "slow push-in 100в†’108%": "push_in",
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

