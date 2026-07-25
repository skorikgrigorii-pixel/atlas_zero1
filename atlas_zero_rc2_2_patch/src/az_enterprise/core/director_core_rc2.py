from __future__ import annotations

from typing import Any, Callable

from .asset_engine_rc2 import AssetEngineRC2
from .assignment_engine_rc2 import AssignmentEngineRC2
from .database import Database
from .production_state_rc2 import ProductionStateRC2, ProductionStateStoreRC2
from .project_config_rc2 import ProjectConfigRC2
from .quality_gate_rc2 import QualityGateRC2
from .render_engine_rc2 import RenderEngineRC2
from .timeline_engine_rc2 import TimelineEngineRC2


ProgressCallback = Callable[[dict[str, Any]], None]


class DirectorCoreRC2:
    """The only new orchestration authority for RC2."""

    STAGES = ("assets", "assignment", "timeline", "render", "quality")

    def __init__(
        self,
        project_id: str,
        *,
        root_dir=None,
        progress: ProgressCallback | None = None,
    ) -> None:
        kwargs = {"project_id": project_id}
        if root_dir is not None:
            kwargs["root_dir"] = root_dir
        self.config = ProjectConfigRC2(**kwargs)
        self.progress = progress or self._default_progress
        self.db = Database()
        self.db.init()
        self.store = ProductionStateStoreRC2(
            self.config.state_path,
            project_id=project_id,
        )

    @staticmethod
    def _default_progress(payload: dict[str, Any]) -> None:
        stage = payload.get("stage", "INFO")
        rest = " ".join(
            f"{key}={value}"
            for key, value in payload.items()
            if key != "stage"
        )
        print(f"[RC2 {stage}] {rest}".rstrip(), flush=True)

    def _run_stage(
        self,
        state: ProductionStateRC2,
        name: str,
        callable_,
    ) -> dict[str, Any]:
        self.store.start_stage(state, name)
        self.progress({"stage": name.upper(), "status": "RUNNING"})
        try:
            result = callable_()
        except Exception as exc:
            self.store.fail_stage(state, name, str(exc))
            self.progress({"stage": name.upper(), "status": "FAILED", "error": str(exc)})
            raise
        self.store.complete_stage(state, name, result)
        self.progress({"stage": name.upper(), "status": "COMPLETED"})
        return result

    def run(self) -> dict[str, Any]:
        state = self.store.load()
        state.status = "RUNNING"
        state.error = None
        self.store.save(state)

        try:
            assets = self._run_stage(
                state,
                "assets",
                lambda: AssetEngineRC2(self.db, self.config).run(),
            )
            assignment = self._run_stage(
                state,
                "assignment",
                lambda: AssignmentEngineRC2(self.db, self.config).run(),
            )
            timeline = self._run_stage(
                state,
                "timeline",
                lambda: TimelineEngineRC2(self.db, self.config).run(),
            )
            render = self._run_stage(
                state,
                "render",
                lambda: RenderEngineRC2(self.config, progress=self.progress).run(),
            )
            quality = self._run_stage(
                state,
                "quality",
                lambda: QualityGateRC2(self.config).run(),
            )

            if quality.get("state") != "PASSED":
                raise RuntimeError("Quality Gate RC2 blocked release")

            state.status = "COMPLETED"
            state.current_stage = None
            state.artifacts["timeline"] = str(self.config.timeline_path)
            state.artifacts["render"] = str(self.config.canonical_render_path)
            state.quality = quality
            state.release_authorized = True
            self.store.save(state)

            return {
                "state": "COMPLETED",
                "project_id": self.config.project_id,
                "assets": assets,
                "assignment": assignment,
                "timeline": timeline,
                "render": render,
                "quality": quality,
                "production_state": str(self.config.state_path),
            }
        except Exception as exc:
            state.status = "FAILED"
            state.error = str(exc)
            state.release_authorized = False
            self.store.save(state)
            raise
