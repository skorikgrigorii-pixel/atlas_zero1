from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import ROOT


@dataclass(frozen=True)
class ProjectConfigRC2:
    project_id: str
    root_dir: Path = ROOT
    target_width: int = 1920
    target_height: int = 1080
    target_fps: int = 30
    minimum_unique_asset_ratio: float = 0.20
    maximum_average_asset_reuse: float = 5.0
    duration_tolerance_sec: float = 2.0
    minimum_video_shots: int = 1

    @property
    def workspace_dir(self) -> Path:
        return self.root_dir / "workspace"

    @property
    def project_dir(self) -> Path:
        return self.workspace_dir / "projects" / self.project_id

    @property
    def export_dir(self) -> Path:
        return self.workspace_dir / "exports" / self.project_id

    @property
    def rc2_dir(self) -> Path:
        return self.export_dir / "rc2"

    @property
    def timeline_path(self) -> Path:
        return self.export_dir / "movie_runtime_rc1" / "timeline.json"

    @property
    def temporal_summary_path(self) -> Path:
        return (
            self.export_dir
            / "semantic_director_v1_2_temporal"
            / "temporal_assignment_summary.json"
        )

    @property
    def master_audio_path(self) -> Path:
        return self.project_dir / "01_Audio" / "voice_master.m4a"

    @property
    def legacy_render_path(self) -> Path:
        return self.export_dir / "render_rc1" / f"{self.project_id}_render_rc1.mp4"

    @property
    def franklin_legacy_render_path(self) -> Path:
        return self.export_dir / "render_rc1" / "franklin_render_rc1.mp4"

    @property
    def canonical_render_path(self) -> Path:
        return self.rc2_dir / "render" / f"{self.project_id}_RC2.mp4"

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
