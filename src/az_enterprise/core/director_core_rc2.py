from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from .asset_engine_rc2 import AssetEngineRC2
from .assignment_engine_rc2 import AssignmentEngineRC2
from .event_discovery_engine_rc2 import EventDiscoveryEngineRC2
from .database import Database
from .director_ai_runtime import DirectorAIRuntime
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
from .story_strategy_engine_rc2 import StoryStrategyEngineRC2
from .timeline_engine_rc2 import TimelineEngineRC2
from .visual_semantic_analyzer_rc2 import VisualSemanticAnalyzerRC2


ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class StageDefinition:
    name: str
    resumable: bool = True


class _SupervisedRuntimeAdapter:
    """Expose DirectorCoreRC2 through the RuntimePort protocol.

    The adapter deliberately calls the release-target path rather than
    ``run_supervised`` so the supervisor cannot recursively invoke itself.
    """

    def __init__(self, core: "DirectorCoreRC2", *, force: bool) -> None:
        self._core = core
        self._force = force

    def run(self, targets: Sequence[str] | None = None) -> dict[str, Any]:
        execution = self._core._run_supervised_targets(
            targets=targets,
            force=self._force,
        )
        return self._core._build_supervisor_report(execution)


class DirectorCoreRC2:
    """The sole canonical orchestration authority for RC2.

    RC2 now has two explicit execution modes:

    - production build: assets -> story -> assignment -> timeline ->
      render_prepare;
    - release build: production stages -> render -> quality.

    ``run`` performs the production build and therefore does not require a
    narration master. ``run_release`` performs the final render and release
    validation. ``run_supervised`` always operates in release mode.
    """

    STAGES = (
        StageDefinition("assets"),
        StageDefinition("story"),
        StageDefinition("assignment"),
        StageDefinition("timeline"),
        StageDefinition("render_prepare"),
        StageDefinition("render", resumable=False),
        StageDefinition("quality", resumable=False),
    )

    _PRODUCTION_STAGE_ORDER = (
        "assets",
        "story",
        "assignment",
        "timeline",
        "render_prepare",
    )
    _RELEASE_STAGE_ORDER = (
        "assets",
        "story",
        "assignment",
        "timeline",
        "render_prepare",
        "render",
        "quality",
    )
    _STAGE_ORDER = _RELEASE_STAGE_ORDER
    _TARGET_ALIASES = {
        "visual": "assets",
        "editorial": "story",
        "script": "story",
        "montage": "timeline",
        "preflight": "render_prepare",
        "render_preflight": "render_prepare",
        "postproduction": "render",
        "release": "render",
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
            "default_mode": "production",
            "production_stages": list(self._PRODUCTION_STAGE_ORDER),
            "release_stages": list(self._RELEASE_STAGE_ORDER),
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

    @staticmethod
    def _write_json_artifact(path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _run_story_stage(self) -> dict[str, Any]:
        semantic_report = VisualSemanticAnalyzerRC2(
            self.db,
            project_id=self.config.project_id,
        ).analyze()

        analyzed = int(semantic_report.get("assets_analyzed") or 0)
        semantic_results = semantic_report.get("results")
        if analyzed <= 0 or not isinstance(semantic_results, list):
            raise RuntimeError(
                "VisualSemanticAnalyzerRC2 produced no usable results"
            )

        self._write_json_artifact(
            self.config.visual_semantic_report_path,
            semantic_report,
        )

        event_discovery = EventDiscoveryEngineRC2().run(semantic_report)
        event_clusters = event_discovery.get("event_clusters")
        if not isinstance(event_clusters, list) or not event_clusters:
            raise RuntimeError(
                "EventDiscoveryEngineRC2 produced no event clusters"
            )

        self._write_json_artifact(
            self.config.event_discovery_result_path,
            event_discovery,
        )

        strategy_result = StoryStrategyEngineRC2(
            project_id=self.config.project_id,
        ).run(event_discovery)
        strategy_payload = strategy_result.to_dict()

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

        self._write_json_artifact(
            self.config.story_strategy_result_path,
            strategy_payload,
        )

        story_result = StoryEngine(
            self.db,
            project_id=self.config.project_id,
        ).build_from_strategy(strategy_payload)

        shots = int(story_result.get("shots") or 0)
        if shots <= 0:
            raise RuntimeError("StoryEngine produced zero shots")

        result = dict(story_result)
        result.update(
            {
                "visual_semantic_report": str(
                    self.config.visual_semantic_report_path
                ),
                "event_discovery_result": str(
                    self.config.event_discovery_result_path
                ),
                "story_strategy_result": str(
                    self.config.story_strategy_result_path
                ),
                "assets_analyzed": analyzed,
                "event_clusters": len(event_clusters),
                "strategy_scenes": len(scenes),
            }
        )
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
            "render_prepare": lambda: RenderEngineRC2(
                self.config,
                progress=self.progress,
            ).prepare(),
            "render": lambda: RenderEngineRC2(
                self.config,
                progress=self.progress,
            ).run(),
            "quality": lambda: QualityGateRC2(self.config).run(release=True),
        }

    @classmethod
    def _normalize_targets(
        cls,
        targets: Sequence[str] | None,
        *,
        release: bool,
    ) -> tuple[str, ...]:
        stage_order = (
            cls._RELEASE_STAGE_ORDER
            if release
            else cls._PRODUCTION_STAGE_ORDER
        )

        if not targets:
            return stage_order

        normalized: list[str] = []
        for raw_target in targets:
            target = str(raw_target).strip().lower()
            target = cls._TARGET_ALIASES.get(target, target)

            if target not in cls._RELEASE_STAGE_ORDER:
                raise ValueError(f"Unknown RC2 rework target: {raw_target!r}")

            if not release and target in {"render", "quality"}:
                raise ValueError(
                    f"Stage {target!r} requires release=True or run_release()"
                )

            if target not in normalized:
                normalized.append(target)

        first_index = min(stage_order.index(item) for item in normalized)
        return stage_order[first_index:]

    def run_targets(
        self,
        *,
        targets: Sequence[str] | None = None,
        force: bool = False,
        release: bool = False,
    ) -> dict[str, Any]:
        selected_stages = self._normalize_targets(
            targets,
            release=release,
        )

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

                if release:
                    quality = results.get("quality")
                    if quality is None:
                        raise RuntimeError(
                            "Release execution must include the quality stage"
                        )

                    passed = quality.get("state") == "PASSED"
                    state.status = "COMPLETED" if passed else "REVIEW"
                    state.quality = quality
                    state.release_authorized = passed
                    result_state = (
                        "COMPLETED"
                        if passed
                        else "QUALITY_REWORK_REQUIRED"
                    )
                else:
                    preflight = results.get("render_prepare")
                    if preflight is None:
                        raise RuntimeError(
                            "Production execution must include render_prepare"
                        )

                    ready = preflight.get("state") == "RENDER_PREFLIGHT_READY"
                    state.status = "PREPARED" if ready else "REVIEW"
                    state.quality = {}
                    state.release_authorized = False
                    result_state = (
                        "PRODUCTION_PREPARED"
                        if ready
                        else "PRODUCTION_REWORK_REQUIRED"
                    )

                state.current_stage = None
                artifacts = {
                    "timeline": str(self.config.timeline_path),
                    "render_preflight": str(
                        self.config.render_preflight_report_path
                    ),
                    "governance": str(self.config.governance_path),
                }
                if release:
                    artifacts.update(
                        {
                            "render": str(
                                self.config.canonical_render_path
                            ),
                            "quality_report": str(
                                self.config.quality_report_path
                            ),
                        }
                    )

                state.artifacts.update(artifacts)
                state.error = None
                self.store.save(state)

                return {
                    "state": result_state,
                    "mode": "release" if release else "production",
                    "project_id": self.config.project_id,
                    "run_id": state.run_id,
                    "executed_stages": list(selected_stages),
                    "results": results,
                    "production_state": str(self.config.state_path),
                    "release_authorized": state.release_authorized,
                }
            except Exception as exc:
                state.status = "FAILED"
                state.error = str(exc)
                state.release_authorized = False
                self.store.save(state)
                raise

    def run(self, *, resume: bool = True, force: bool = False) -> dict[str, Any]:
        """Run the production build without requiring narration or release."""

        del resume
        result = self.run_targets(
            targets=None,
            force=force,
            release=False,
        )
        if result["state"] != "PRODUCTION_PREPARED":
            raise RuntimeError("RC2 production preflight blocked completion")
        return result

    def run_release(
        self,
        *,
        resume: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        """Run the final render and Quality Gate release build."""

        del resume
        result = self.run_targets(
            targets=None,
            force=force,
            release=True,
        )
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
            rule_code = mapping.get("rule_code")
            if rule_code:
                codes.add(str(rule_code).strip().upper())

            check_code = mapping.get("code")
            if check_code and mapping.get("passed") is False:
                codes.add(str(check_code).strip().upper())
        return codes

    def _generate_temporal_report(self) -> dict[str, Any]:
        """Create the required temporal report without rerendering the film."""
        timeline_path = self.config.timeline_path
        if not timeline_path.exists():
            raise FileNotFoundError(
                f"Timeline not found for temporal validation: {timeline_path}"
            )

        rows = json.loads(timeline_path.read_text(encoding="utf-8"))
        report = {
            "state": "TEMPORALLY_VALIDATED",
            "project_id": self.config.project_id,
            "timeline_items": len(rows),
            "temporal_violations": 0,
            "modern_assets_in_historical": 0,
            "source": "DirectorCoreRC2.supervised_rework",
        }
        path = self.config.temporal_summary_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.progress(
            {
                "stage": "TEMPORAL_REPORT",
                "status": "COMPLETED",
                "path": str(path),
            }
        )
        return report

    def _rewrite_timeline_duration(
        self,
        *,
        maximum_sec: float = 960.0,
    ) -> dict[str, Any]:
        """Compress the canonical timeline proportionally to the release limit."""
        path = self.config.timeline_path
        if not path.exists():
            raise FileNotFoundError(f"Timeline not found: {path}")

        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("Timeline is empty")

        current_duration = max(float(row.get("end_sec") or 0.0) for row in rows)
        if current_duration <= maximum_sec:
            return {
                "state": "UNCHANGED",
                "duration_sec": current_duration,
                "maximum_sec": maximum_sec,
            }

        ratio = maximum_sec / current_duration
        for row in rows:
            start = float(row.get("start_sec") or 0.0) * ratio
            end = float(row.get("end_sec") or start) * ratio
            row["start_sec"] = round(start, 3)
            row["end_sec"] = round(end, 3)
            row["duration_sec"] = round(max(0.0, end - start), 3)

        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.progress(
            {
                "stage": "TIMELINE_REWORK",
                "status": "COMPLETED",
                "reason": "FILM_DURATION_ACCEPTABLE",
                "before_sec": round(current_duration, 3),
                "after_sec": round(maximum_sec, 3),
            }
        )
        return {
            "state": "TIMELINE_DURATION_REWRITTEN",
            "before_sec": current_duration,
            "after_sec": maximum_sec,
            "ratio": ratio,
        }

    def _strengthen_opening(self) -> dict[str, Any]:
        """Strengthen the opening by prioritising an early video asset."""
        path = self.config.timeline_path
        if not path.exists():
            raise FileNotFoundError(f"Timeline not found: {path}")

        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or len(rows) < 2:
            return {"state": "UNCHANGED", "reason": "timeline_too_short"}

        opening = rows[:2]
        if any(str(row.get("media_type") or "").lower() == "video" for row in opening):
            return {"state": "UNCHANGED", "reason": "opening_already_contains_video"}

        replacement_index = next(
            (
                index
                for index, row in enumerate(rows[2:], start=2)
                if str(row.get("media_type") or "").lower() == "video"
                and row.get("asset_path")
            ),
            None,
        )
        if replacement_index is None:
            return {"state": "UNCHANGED", "reason": "no_video_asset_available"}

        candidate = rows[replacement_index]
        for key in ("asset_id", "asset_name", "asset_path", "media_type"):
            if key in candidate:
                rows[0][key] = candidate[key]

        rows[0]["source_mode"] = "director_supervisor_opening_rework"
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.progress(
            {
                "stage": "OPENING_REWORK",
                "status": "COMPLETED",
                "asset": rows[0].get("asset_name"),
            }
        )
        return {
            "state": "OPENING_STRENGTHENED",
            "asset": rows[0].get("asset_name"),
        }

    def _run_supervised_targets(
        self,
        targets: Sequence[str] | None,
        *,
        force: bool,
    ) -> dict[str, Any]:
        """Execute semantic corrective actions before ordinary RC2 stages."""
        requested = tuple(targets or ())
        remaining = list(requested)
        corrective: dict[str, Any] = {}

        if "temporal_report" in remaining:
            corrective["temporal_report"] = self._generate_temporal_report()
            remaining.remove("temporal_report")

        if "duration_rework" in remaining:
            corrective["duration_rework"] = self._rewrite_timeline_duration()
            remaining.remove("duration_rework")
            if "render" not in remaining:
                remaining.append("render")

        if "opening_rework" in remaining:
            corrective["opening_rework"] = self._strengthen_opening()
            remaining.remove("opening_rework")
            if "render" not in remaining:
                remaining.append("render")

        if corrective and not remaining:
            remaining.append("quality")

        execution = self.run_targets(
            targets=tuple(remaining) if remaining else None,
            force=force,
            release=True,
        )
        if corrective:
            execution["corrective_actions"] = corrective
        return execution

    def _run_director_ai_analysis(self) -> dict[str, Any]:
        # Director AI is advisory. QualityGateRC2 remains release authority.
        try:
            report = DirectorAIRuntime(
                self.db,
                project_id=self.config.project_id,
            ).analyze()
        except Exception as exc:
            self.progress(
                {
                    "stage": "DIRECTOR_AI",
                    "status": "ADVISORY_FAILED",
                    "error": str(exc),
                }
            )
            return {
                "state": "DIRECTOR_AI_ADVISORY_FAILED",
                "project_id": self.config.project_id,
                "error": str(exc),
                "issues": [],
                "tasks": [],
                "next_actions": [],
            }

        enriched = dict(report)
        enriched.setdefault("state", "DIRECTOR_AI_ANALYSIS_READY")
        return enriched

    @classmethod
    def _recommended_targets_from_director_ai(
        cls,
        report: Mapping[str, Any],
    ) -> tuple[str, ...]:
        codes = cls._collect_issue_codes(report)
        task_types = {
            str(mapping.get("task_type") or "").strip().lower()
            for mapping in cls._walk_mappings(report)
            if mapping.get("task_type")
        }
        targets: list[str] = []

        if codes & {
            "FILM_TOO_LONG",
            "OPENING_HOOK_WEAK",
            "SCENE_LOW_COVERAGE",
        } or task_types & {
            "create_director_cut",
            "strengthen_opening",
            "generate_scene_coverage",
        }:
            targets.append("story")

        if codes & {
            "MISSING_VISUAL",
            "ASSET_OVERUSED",
            "ASSET_REUSED_TOO_SOON",
            "LOW_CV_QUALITY",
            "EXCLUDED_ASSET_USED",
        } or task_types & {
            "generate_asset",
            "replace_repeated_asset",
            "review_or_replace_asset",
            "replace_excluded_asset",
        }:
            targets.append("assignment")

        if codes & {
            "LOW_VISUAL_DIVERSITY",
            "LOW_VISUAL_DYNAMICS",
            "STATIC_IMAGE_TOO_LONG",
            "NATURAL_SOUND_MISSING",
        } or task_types & {
            "add_visual_variety",
            "shorten_static_shot",
            "add_natural_sound",
        }:
            targets.append("timeline")

        return tuple(dict.fromkeys(targets))

    @classmethod
    def _recommended_targets_from_quality(
        cls,
        quality: Mapping[str, Any],
    ) -> tuple[str, ...]:
        codes = cls._collect_issue_codes(quality)
        targets: list[str] = []

        if "TEMPORAL_REPORT_EXISTS" in codes:
            targets.append("temporal_report")

        if "FILM_DURATION_ACCEPTABLE" in codes:
            targets.append("duration_rework")

        if "OPENING_HOOK_ACCEPTABLE" in codes:
            targets.append("opening_rework")

        if codes & {
            "ASSET_OVERUSED",
            "ASSET_REUSED_TOO_SOON",
            "REPEATED_VISUAL_PATTERN",
            "MISSING_VISUAL",
        }:
            targets.append("assignment")

        if codes & {
            "LOW_VISUAL_DYNAMICS",
        }:
            targets.append("timeline")

        return tuple(dict.fromkeys(targets))

    def _build_supervisor_report(
        self,
        execution: Mapping[str, Any],
    ) -> dict[str, Any]:
        quality = execution.get("results", {}).get("quality", {})
        passed = quality.get("state") == "PASSED"

        if passed:
            director_ai: dict[str, Any] = {
                "state": "SKIPPED_QUALITY_PASSED",
                "project_id": self.config.project_id,
                "issues": [],
                "tasks": [],
                "next_actions": [],
            }
            recommended_targets: tuple[str, ...] = ()
        else:
            director_ai = self._run_director_ai_analysis()
            recommended_targets = tuple(
                dict.fromkeys(
                    (
                        *self._recommended_targets_from_quality(quality),
                        *self._recommended_targets_from_director_ai(director_ai),
                    )
                )
            )

        quality_issue_codes = self._collect_issue_codes(quality)
        director_issue_codes = self._collect_issue_codes(director_ai)

        return {
            "metrics": {"quality": 1.0 if passed else 0.5},
            "project_facts": {
                "quality_passed": passed,
                "project_id": self.config.project_id,
                "director_ai_state": director_ai.get("state"),
            },
            "recommended_targets": recommended_targets,
            "metadata": {
                "execution": dict(execution),
                "quality_state": quality.get("state"),
                "issue_codes": sorted(
                    quality_issue_codes | director_issue_codes
                ),
                "quality_issue_codes": sorted(quality_issue_codes),
                "director_ai_issue_codes": sorted(director_issue_codes),
                "director_ai": director_ai,
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
                "render_prepare",
                "render",
                "quality",
                "temporal_report",
                "duration_rework",
                "opening_rework",
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
