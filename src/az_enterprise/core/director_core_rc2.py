from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from .asset_engine_rc2 import AssetEngineRC2
from .assignment_engine_rc2 import AssignmentEngineRC2
from .database import Database
from .director_policy_alpha293 import (
    DirectorPolicy,
    ProjectObjective,
    ProjectType,
    QualityProfile,
)
from .director_policy_evaluator_alpha293 import PolicyDecisionEvaluator
from .director_supervisor_alpha292 import DirectorSupervisor
from .production_state_rc2 import ProductionStateRC2, ProductionStateStoreRC2
from .project_config_rc2 import ProjectConfigRC2
from .quality_gate_rc2 import QualityGateRC2
from .render_engine_rc2 import RenderEngineRC2
from .runtime_governance_rc2 import governance_report
from .story_engine import StoryEngine
from .timeline_engine_rc2 import TimelineEngineRC2


ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class StageDefinition:
    name: str
    resumable: bool = True


class _SupervisedRuntimeAdapter:
    """Expose DirectorCoreRC2 through the RuntimePort protocol.

    The adapter deliberately calls ``run_targets`` rather than ``run_supervised``
    so the supervisor cannot recursively invoke itself.
    """

    def __init__(self, core: "DirectorCoreRC2", *, force: bool) -> None:
        self._core = core
        self._force = force

    def run(self, targets: Sequence[str] | None = None) -> dict[str, Any]:
        execution = self._core.run_targets(targets=targets, force=self._force)
        return self._core._build_supervisor_report(execution)


class DirectorCoreRC2:
    """The sole canonical orchestration authority for RC2.

    ``run`` preserves the existing one-pass behaviour.
    ``run_supervised`` adds bounded DirectorSupervisor rework cycles without
    changing the current stage implementations.
    """

    STAGES = (
        StageDefinition("assets"),
        StageDefinition("story"),
        StageDefinition("assignment"),
        StageDefinition("timeline"),
        StageDefinition("render", resumable=False),
        StageDefinition("quality", resumable=False),
    )

    _STAGE_ORDER = tuple(item.name for item in STAGES)
    _TARGET_ALIASES = {
        "visual": "assets",
        "editorial": "story",
        "script": "story",
        "montage": "timeline",
        "postproduction": "render",
    }

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

    def plan(self) -> dict[str, Any]:
        state = self.store.load()
        return {
            "project_id": self.config.project_id,
            "canonical_orchestrator": "DirectorCoreRC2",
            "stages": list(self._STAGE_ORDER),
            "supervised_mode_available": True,
            "current_state": state.status,
            "resume_from": self._first_incomplete_stage(state),
            "governance": governance_report(),
        }

    def _first_incomplete_stage(self, state: ProductionStateRC2) -> str | None:
        for definition in self.STAGES:
            stage = state.stages.get(definition.name)
            if stage is None or stage.status != "COMPLETED":
                return definition.name
        return None

    @contextmanager
    def _exclusive_run(self):
        self.config.run_lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(
                self.config.run_lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as exc:
            raise RuntimeError(
                "Another DirectorCoreRC2 run is active: "
                f"{self.config.run_lock_path}"
            ) from exc
        try:
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            yield
        finally:
            self.config.run_lock_path.unlink(missing_ok=True)

    def _run_stage(
        self,
        state: ProductionStateRC2,
        name: str,
        callable_: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        self.store.start_stage(state, name)
        self.progress({"stage": name.upper(), "status": "RUNNING"})
        try:
            result = callable_()
        except Exception as exc:
            self.store.fail_stage(state, name, str(exc))
            self.progress(
                {
                    "stage": name.upper(),
                    "status": "FAILED",
                    "error": str(exc),
                }
            )
            raise
        self.store.complete_stage(state, name, result)
        self.progress({"stage": name.upper(), "status": "COMPLETED"})
        return result

    def _run_story_stage(self) -> dict[str, Any]:
        strategy_path = self.config.story_strategy_result_path

        if not strategy_path.exists():
            raise FileNotFoundError(
                f"Story strategy file not found: {strategy_path}"
            )

        try:
            strategy_payload = json.loads(
                strategy_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Invalid story strategy JSON: {strategy_path}"
            ) from exc

        if strategy_payload.get("state") != "STORY_STRATEGY_READY":
            raise RuntimeError(
                "Story strategy is not ready: "
                f"{strategy_payload.get('state')!r}"
            )

        strategy_project_id = strategy_payload.get("project_id")
        if strategy_project_id != self.config.project_id:
            raise RuntimeError(
                "Story strategy project mismatch: "
                f"expected {self.config.project_id!r}, "
                f"got {strategy_project_id!r}"
            )

        scenes = strategy_payload.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise RuntimeError("Story strategy contains no scenes")

        result = StoryEngine(
            self.db,
            project_id=self.config.project_id,
        ).build_from_strategy(strategy_payload)

        shots = int(result.get("shots") or 0)
        if shots <= 0:
            raise RuntimeError("StoryEngine produced zero shots")

        return result

    def _stage_services(self) -> dict[str, Callable[[], dict[str, Any]]]:
        return {
            "assets": lambda: AssetEngineRC2(self.db, self.config).run(),
            "story": self._run_story_stage,
            "assignment": lambda: AssignmentEngineRC2(
                self.db,
                self.config,
            ).run(),
            "timeline": lambda: TimelineEngineRC2(
                self.db,
                self.config,
            ).run(),
            "render": lambda: RenderEngineRC2(
                self.config,
                progress=self.progress,
            ).run(),
            "quality": lambda: QualityGateRC2(self.config).run(),
        }

    @classmethod
    def _normalize_targets(
        cls,
        targets: Sequence[str] | None,
    ) -> tuple[str, ...]:
        if not targets:
            return cls._STAGE_ORDER

        normalized: list[str] = []
        for raw_target in targets:
            target = str(raw_target).strip().lower()
            target = cls._TARGET_ALIASES.get(target, target)
            if target not in cls._STAGE_ORDER:
                raise ValueError(f"Unknown RC2 rework target: {raw_target!r}")
            if target not in normalized:
                normalized.append(target)

        # Every upstream change invalidates all downstream artifacts.
        first_index = min(cls._STAGE_ORDER.index(item) for item in normalized)
        return cls._STAGE_ORDER[first_index:]

    def run_targets(
        self,
        *,
        targets: Sequence[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        selected_stages = self._normalize_targets(targets)

        with self._exclusive_run():
            self.config.governance_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.governance_path.write_text(
                json.dumps(
                    governance_report(),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            state = self.store.load()
            self.store.reset_for_run(state, force=force)
            services = self._stage_services()
            results: dict[str, Any] = {}

            try:
                for stage_name in selected_stages:
                    results[stage_name] = self._run_stage(
                        state,
                        stage_name,
                        services[stage_name],
                    )

                quality = results.get("quality")
                if quality is None:
                    raise RuntimeError(
                        "Targeted RC2 execution must include the quality stage"
                    )

                passed = quality.get("state") == "PASSED"
                state.status = "COMPLETED" if passed else "REVIEW"
                state.current_stage = None
                state.artifacts.update(
                    {
                        "timeline": str(self.config.timeline_path),
                        "render": str(self.config.canonical_render_path),
                        "quality_report": str(self.config.quality_report_path),
                        "governance": str(self.config.governance_path),
                    }
                )
                state.quality = quality
                state.release_authorized = passed
                state.error = None
                self.store.save(state)

                return {
                    "state": "COMPLETED" if passed else "QUALITY_REWORK_REQUIRED",
                    "project_id": self.config.project_id,
                    "run_id": state.run_id,
                    "executed_stages": list(selected_stages),
                    "results": results,
                    "production_state": str(self.config.state_path),
                }
            except Exception as exc:
                state.status = "FAILED"
                state.error = str(exc)
                state.release_authorized = False
                self.store.save(state)
                raise

    def run(self, *, resume: bool = True, force: bool = False) -> dict[str, Any]:
        """Preserve the previous one-pass RC2 contract."""
        del resume  # Resume remains disabled until fingerprints are implemented.
        result = self.run_targets(targets=None, force=force)
        if result["state"] != "COMPLETED":
            raise RuntimeError("Quality Gate RC2 blocked release")
        return result

    @staticmethod
    def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
        if isinstance(value, Mapping):
            yield value
            for nested in value.values():
                yield from DirectorCoreRC2._walk_mappings(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from DirectorCoreRC2._walk_mappings(nested)

    @staticmethod
    def _collect_issue_codes(quality: Mapping[str, Any]) -> set[str]:
        codes: set[str] = set()
        for mapping in DirectorCoreRC2._walk_mappings(quality):
            code = mapping.get("rule_code")
            if code:
                codes.add(str(code).strip().upper())
        return codes

    @classmethod
    def _recommended_targets_from_quality(
        cls,
        quality: Mapping[str, Any],
    ) -> tuple[str, ...]:
        codes = cls._collect_issue_codes(quality)
        targets: list[str] = []

        if codes & {
            "FILM_TOO_LONG",
            "OPENING_HOOK_WEAK",
            "SCENE_LOW_COVERAGE",
        }:
            targets.append("story")

        if codes & {
            "ASSET_OVERUSED",
            "ASSET_REUSED_TOO_SOON",
            "REPEATED_VISUAL_PATTERN",
            "MISSING_VISUAL",
        }:
            targets.append("assignment")

        if codes & {"LOW_VISUAL_DYNAMICS"}:
            targets.append("timeline")

        if not targets:
            targets.append("timeline")

        return tuple(dict.fromkeys(targets))

    def _build_supervisor_report(
        self,
        execution: Mapping[str, Any],
    ) -> dict[str, Any]:
        quality = execution.get("results", {}).get("quality", {})
        passed = quality.get("state") == "PASSED"
        recommended_targets = () if passed else self._recommended_targets_from_quality(
            quality
        )

        return {
            "metrics": {"quality": 1.0 if passed else 0.5},
            "project_facts": {
                "quality_passed": passed,
                "project_id": self.config.project_id,
            },
            "recommended_targets": recommended_targets,
            "metadata": {
                "execution": dict(execution),
                "quality_state": quality.get("state"),
                "issue_codes": sorted(self._collect_issue_codes(quality)),
            },
        }

    @staticmethod
    def default_supervisor_policy() -> DirectorPolicy:
        """Safe first integration policy.

        A passed QualityGate is approved. A failed QualityGate is always sent
        to bounded rework rather than being released or silently ignored.
        """
        return DirectorPolicy(
            project_type=ProjectType.DOCUMENTARY,
            objective=ProjectObjective.BALANCED,
            quality_profile=QualityProfile(
                weights={"quality": 1.0},
                release_threshold=1.0,
                rework_threshold=0.5,
            ),
            allowed_rework_targets=(
                "assets",
                "story",
                "assignment",
                "timeline",
                "render",
                "quality",
            ),
            metadata={
                "integration_stage": "director_supervisor_rc2_v1",
                "quality_authority": "QualityGateRC2",
            },
        )

    def run_supervised(
        self,
        *,
        policy: DirectorPolicy | None = None,
        max_rework_cycles: int = 2,
        initial_targets: Sequence[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Run RC2 under DirectorSupervisor with bounded targeted rework."""
        active_policy = policy or self.default_supervisor_policy()
        supervisor = DirectorSupervisor(
            _SupervisedRuntimeAdapter(self, force=force),
            PolicyDecisionEvaluator(active_policy),
            max_rework_cycles=max_rework_cycles,
        )
        result = supervisor.run_project(initial_targets=initial_targets)

        latest_runtime = result.runtime_results[-1]
        execution = latest_runtime.get("metadata", {}).get("execution", {})
        return {
            "state": result.final_decision.status.value,
            "project_id": self.config.project_id,
            "cycles": result.cycles,
            "final_decision": {
                "status": result.final_decision.status.value,
                "reason": result.final_decision.reason,
                "confidence": result.final_decision.confidence,
                "metadata": dict(result.final_decision.metadata),
            },
            "decisions": [
                {
                    "sequence": record.sequence,
                    "created_at": record.created_at,
                    "status": record.decision.status.value,
                    "reason": record.decision.reason,
                    "targets": [
                        action.target for action in record.decision.actions
                    ],
                }
                for record in result.decisions
            ],
            "latest_execution": execution,
        }
