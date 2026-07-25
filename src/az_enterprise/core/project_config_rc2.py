from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import ROOT


@dataclass(frozen=True)
class ProjectConfigRC2:
    """Canonical filesystem and render configuration for ATLAS ZERO RC2."""

    project_id: str
    root_dir: Path = ROOT

    target_width: int = 1920
    target_height: int = 1080
    target_fps: int = 30

    minimum_unique_asset_ratio: float = 0.20
    maximum_average_asset_reuse: float = 5.0
    duration_tolerance_sec: float = 2.0
    minimum_video_shots: int = 1

    media_source_dir: Path | None = None

    @property
    def workspace_dir(self) -> Path:
        return Path(self.root_dir) / "workspace"

    @property
    def project_dir(self) -> Path:
        return self.workspace_dir / "projects" / self.project_id

    @property
    def effective_media_source_dir(self) -> Path:
        """Read-only media source used by the RC2 asset indexing stage."""
        if self.media_source_dir is not None:
            return Path(self.media_source_dir)
        return self.project_dir

    @property
    def export_dir(self) -> Path:
        return self.workspace_dir / "exports" / self.project_id

    @property
    def rc2_dir(self) -> Path:
        """Canonical root for all RC2 production artifacts."""
        return self.export_dir / "rc2"

    @property
    def visual_semantic_report_path(self) -> Path:
        """Canonical per-asset semantic analysis report."""
        return (
            self.rc2_dir
            / "visual_semantic"
            / "visual_semantic_report.json"
        )

    @property
    def event_discovery_result_path(self) -> Path:
        """Canonical event clustering and exclusion report."""
        return (
            self.rc2_dir
            / "event_discovery"
            / "event_discovery_result.json"
        )

    @property
    def story_strategy_result_path(self) -> Path:
        """Canonical documentary story strategy consumed by StoryEngine."""
        return (
            self.rc2_dir
            / "story_strategy"
            / "story_strategy_result.json"
        )

    @property
    def timeline_dir(self) -> Path:
        """Canonical timeline directory owned by TimelineEngineRC2."""
        return self.rc2_dir / "timeline"

    @property
    def timeline_path(self) -> Path:
        """Canonical production timeline consumed by RenderEngineRC2."""
        return self.timeline_dir / "timeline.json"

    @property
    def native_timeline_model_path(self) -> Path:
        """Optional operator/viewer model; not a render authority."""
        return self.export_dir / "native_timeline_model.json"

    @property
    def temporal_summary_path(self) -> Path:
        return (
            self.export_dir
            / "semantic_director_v1_2_temporal"
            / "temporal_assignment_summary.json"
        )

    @property
    def master_audio_path(self) -> Path:
        """Canonical narration produced by VoiceProductionEngineRC2."""
        return self.project_dir / "01_Audio" / "voice_master.wav"


    @property
    def render_dir(self) -> Path:
        """Canonical render artifact directory."""
        return self.rc2_dir / "render"

    @property
    def render_preflight_report_path(self) -> Path:
        """Canonical preflight validation report."""
        return self.render_dir / "render_preflight_rc2.json"

    @property
    def preview_render_path(self) -> Path:
        """Preview render produced before narration is available."""
        return self.render_dir / "render_preview_rc2.mp4"

    @property
    def canonical_render_path(self) -> Path:
        """Verified final video artifact produced by RenderEngineRC2."""
        return self.render_dir / f"{self.project_id}_RC2.mp4"

    @property
    def state_path(self) -> Path:
        return self.rc2_dir / "production_state.json"

    @property
    def run_lock_path(self) -> Path:
        return self.rc2_dir / "director_core.lock"

    @property
    def governance_path(self) -> Path:
        return self.rc2_dir / "runtime_governance.json"

    @property
    def quality_report_path(self) -> Path:
        return self.rc2_dir / "quality_report.json"
