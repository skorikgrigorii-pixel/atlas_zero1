from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from .audio_renderer_rc2 import AudioRendererRC2
from .audio_timeline_rc2 import (
    AudioEventRC2,
    AudioTimelineBuilderRC2,
    AudioTimelineValidatorRC2,
    VideoTimelineRC2,
)
from .mux_engine_rc2 import MuxEngineRC2


class NativeAudioComposerRC2:
    """Coordinates RC2 audio rebinding, rendering, validation, and final mux."""

    def __init__(self, *, project_id: str, output_dir: Path) -> None:
        self.project_id = project_id
        self.output_dir = Path(output_dir)
        self.renderer = AudioRendererRC2(
            project_id=project_id,
            output_dir=self.output_dir,
        )
        self.muxer = MuxEngineRC2(output_dir=self.output_dir)
        self.rebind_report_path = (
            self.output_dir / "audio_rebind_report_rc2.json"
        )
        self.events_snapshot_path = (
            self.output_dir / "audio_events_bound_rc2.json"
        )

    def run(
        self,
        *,
        visual_master: Path,
        audio_items: Iterable[Any] | None = None,
        audio_events: Iterable[AudioEventRC2] | None = None,
        target_duration_sec: float,
        video_timeline: Iterable[Any] | None = None,
        video_timeline_hash: str | None = None,
        strict_audio_sync: bool = True,
    ) -> dict[str, Any]:
        """
        Render RC2 audio.

        For synchronized source-anchored events, video_timeline is mandatory.
        Timeline-locked music/SFX remains backward compatible.
        """
        raw_events = (
            list(audio_events)
            if audio_events is not None
            else AudioTimelineBuilderRC2.build(audio_items or [])
        )

        synchronized_events = [
            event for event in raw_events if event.preserve_sync
        ]

        if synchronized_events and video_timeline is None:
            raise RuntimeError(
                "RC2 final render blocked: synchronized audio events exist, "
                "but the final video timeline was not supplied."
            )

        if video_timeline is not None:
            timeline_items = list(video_timeline)
            current_hash = (
                video_timeline_hash
                or VideoTimelineRC2.digest(timeline_items)
            )
            events, rebind_report = AudioTimelineBuilderRC2.rebind(
                raw_events,
                video_timeline=timeline_items,
                timeline_hash=current_hash,
                strict=strict_audio_sync,
            )
        else:
            current_hash = video_timeline_hash
            events = raw_events
            rebind_report = {
                "schema": "atlas_zero.audio_rebind.rc2.v1",
                "timeline_hash": current_hash,
                "clips_total": 0,
                "events_total": len(events),
                "events_rebound": 0,
                "events_unresolved": 0,
                "unresolved": [],
                "mode": "timeline_locked_only",
            }

        events = AudioTimelineValidatorRC2.validate_against_video(
            events,
            target_duration_sec=target_duration_sec,
            require_resolved_sync=strict_audio_sync,
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.rebind_report_path, rebind_report)
        self._write_json(
            self.events_snapshot_path,
            {
                "schema": "atlas_zero.audio_events_bound.rc2.v1",
                "project_id": self.project_id,
                "video_timeline_hash": current_hash,
                "events": [event.to_dict() for event in events],
            },
        )

        audio_report = self.renderer.run(
            events,
            target_duration_sec=target_duration_sec,
            video_timeline_hash=current_hash,
            rebind_report=rebind_report,
        )
        mux_report = self.muxer.run(
            visual_path=Path(visual_master),
            audio_path=Path(audio_report["output_audio"]),
        )
        return {
            "state": "PHASE_7_COMPLETE",
            "schema": "atlas_zero.native_audio_composer.rc2.v2",
            "project_id": self.project_id,
            "video_timeline_hash": current_hash,
            "audio_rebind_report": rebind_report,
            "audio_events_snapshot": str(self.events_snapshot_path),
            "audio_report": audio_report,
            "mux_report": mux_report,
        }

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
