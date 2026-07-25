from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .audio_renderer_rc2 import AudioRendererRC2
from .audio_timeline_rc2 import AudioEventRC2, AudioTimelineBuilderRC2
from .mux_engine_rc2 import MuxEngineRC2


class NativeAudioComposerRC2:
    """Coordinates timeline loading, native audio rendering, and final mux."""

    def __init__(self, *, project_id: str, output_dir: Path) -> None:
        self.project_id = project_id
        self.output_dir = Path(output_dir)
        self.renderer = AudioRendererRC2(
            project_id=project_id,
            output_dir=self.output_dir,
        )
        self.muxer = MuxEngineRC2(output_dir=self.output_dir)

    def run(
        self,
        *,
        visual_master: Path,
        audio_items: Iterable[Any] | None = None,
        audio_events: Iterable[AudioEventRC2] | None = None,
        target_duration_sec: float,
    ) -> dict[str, Any]:
        if audio_events is not None:
            events = list(audio_events)
        else:
            events = AudioTimelineBuilderRC2.build(audio_items or [])

        audio_report = self.renderer.run(
            events,
            target_duration_sec=target_duration_sec,
        )
        mux_report = self.muxer.run(
            visual_path=Path(visual_master),
            audio_path=Path(audio_report["output_audio"]),
        )
        return {
            "state": "PHASE_7_COMPLETE",
            "schema": "atlas_zero.native_audio_composer.rc2.v1",
            "project_id": self.project_id,
            "audio_report": audio_report,
            "mux_report": mux_report,
        }
