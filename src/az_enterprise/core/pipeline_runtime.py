from __future__ import annotations

import json
import os
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .database import Database
from .asset_intelligence import AssetIntelligence
from .story_engine import StoryEngine
from .director_ai import DirectorAI
from .quality import QualityCenter
from .integrations import IntegrationRegistry
from .visual_intelligence import VisualIntelligence
from .timeline_studio import TimelineStudio
from .release_gate import ReleaseGate
from .production_state import ProductionState
from .acceptance_center import AcceptanceCenter
from .preflight import PreflightCenter
from .operator_console import OperatorConsole
from .final_timeline_viewer import FinalTimelineViewer
from .working_state_auditor import WorkingStateAuditor
from .capcut_bridge import CapCutBridge
from .montage_workbench import MontageWorkbench
from .local_autopilot import LocalAutopilot
from .native_timeline import NativeTimelineModel
from .final_assembly_pack import FinalAssemblyPack
from .live_connectors import LiveConnectorHub
from .cv_model import CVModel
from .native_viewer_rc import NativeViewerRC
from .live_api_test_suite import LiveApiTestSuite
from .cv_review_board import CVReviewBoard
from .timeline_viewer_2 import TimelineViewer2
from .test_center import TestCenter
from .story_engine_runtime import StoryEngineRuntime
from .director_ai_runtime import DirectorAIRuntime
from .native_viewer_pro import NativeViewerPro
from .franklin_e2e_runtime import FranklinE2ERuntime
from .workflow import WorkflowEngine
from .paths import EXPORTS
from .module_registry_alpha31 import ModuleRegistryAlpha31
from .dependency_resolver_alpha31 import DependencyResolverAlpha31

ProgressCallback = Callable[[dict[str, Any]], None]


class PipelineRunManager:
    """Enterprise RC1 Alpha 3.1 runtime.

    This version is no longer a static status viewer. It creates a real run, builds a
    task queue, executes each stage, emits live progress, stores task events, supports
    retrying failed tasks, runs a local CV pass, checks live API readiness, and produces
    a Franklin end-to-end local handoff/export pack.

    Safety rule: paid generation is never executed unless BOTH environment variables
    are set explicitly:
        AZ_ENABLE_LIVE_API=1
        AZ_ALLOW_PAID_CALLS=1
    """

    def __init__(self, db: Database, project_id: str = "franklin"):
        self.db = db
        self.project_id = project_id
        self.db.init()
        self._ensure_schema()
        self.workflow = WorkflowEngine(db, project_id)
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.module_registry = ModuleRegistryAlpha31()
        self._register_runtime_modules()
        self.dependency_resolver = DependencyResolverAlpha31(self.module_registry)

    def _ensure_schema(self) -> None:
        self.db.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pipeline_runs(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_uid TEXT,
              project_id TEXT NOT NULL,
              status TEXT NOT NULL,
              progress REAL DEFAULT 0,
              current_step TEXT,
              started_at TEXT DEFAULT CURRENT_TIMESTAMP,
              finished_at TEXT,
              result_json TEXT,
              error TEXT
            );
            CREATE TABLE IF NOT EXISTS pipeline_task_queue(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL,
              task_uid TEXT,
              project_id TEXT NOT NULL,
              step_order INTEGER NOT NULL,
              step_key TEXT NOT NULL,
              title TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              attempts INTEGER DEFAULT 0,
              max_attempts INTEGER DEFAULT 2,
              progress REAL DEFAULT 0,
              result_json TEXT,
              error TEXT,
              started_at TEXT,
              finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS pipeline_task_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL,
              task_id INTEGER,
              project_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              message TEXT NOT NULL,
              progress REAL DEFAULT 0,
              payload_json TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS pipeline_logs(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL,
              project_id TEXT NOT NULL,
              level TEXT NOT NULL,
              message TEXT NOT NULL,
              payload_json TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS pipeline_stage_graph(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL,
              project_id TEXT NOT NULL,
              step_order INTEGER NOT NULL,
              step_key TEXT NOT NULL,
              title TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              progress REAL DEFAULT 0,
              started_at TEXT,
              finished_at TEXT,
              duration_sec REAL DEFAULT 0,
              result_summary TEXT,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Upgrade existing Alpha databases without destructive migration.
        for table, coldef in [
            ('pipeline_runs', 'run_uid TEXT'),
            ('pipeline_runs', 'current_step TEXT'),
            ('pipeline_task_queue', 'task_uid TEXT'),
            ('pipeline_task_queue', 'attempts INTEGER DEFAULT 0'),
            ('pipeline_task_queue', 'max_attempts INTEGER DEFAULT 2'),
        ]:
            try:
                self.db.conn.execute(f'ALTER TABLE {table} ADD COLUMN {coldef}')
            except Exception:
                pass
        self.db.conn.commit()

    def _register_runtime_modules(self) -> None:
        # Register the RC1 Alpha 3.1 runtime graph.
        # Dependencies preserve the legacy static execution order.
        modules = [
            ("preflight_start", "Preflight: проверка рабочей станции", self._step_preflight),
            ("scan_assets", "Анализ материалов: чтение файлов, хеши, метаданные", self._step_scan_assets),
            ("cv_model", "CV Runtime: OpenCV/Pillow анализ изображений", self._step_cv_model),
            ("visual_intelligence", "Visual Intelligence: профиль стиля", self._step_visual_intelligence),
            ("build_shots", "Story Engine: построение монтажной структуры", self._step_build_shots),
            ("director_ai", "Director AI 2.5: подбор материалов, проверка полноты и задачи", self._step_director_ai),
            ("story_runtime", "Story Engine 2.3: сцены и монтажный лист", self._step_story_runtime),
            ("director_ai_2_4", "Director AI 2.4: качество, решения, задачи", self._step_director_ai_runtime),
            ("live_api_test", "Live API: проверка ключей и read-only endpoints", self._step_live_api_test),
            ("integrations", "Integration Registry: состояние сервисов", self._step_integrations),
            ("api_queue", "API Queue: задания для недостающих кадров", self._step_api_queue),
            ("api_safe_run", "API Runner: dry/live-safe выполнение очереди", self._step_api_safe_run),
            ("quality", "Quality Control: готовность, повторы, дефицит", self._step_quality),
            ("readiness_gate", "Release Gate RC1: строгая проверка", self._step_readiness_gate),
            ("timeline_package", "Timeline Studio: монтажный пакет", self._step_timeline_package),
            ("native_timeline", "Native Timeline: модель треков", self._step_native_timeline),
            ("native_viewer", "Native Viewer RC: модель viewer", self._step_native_viewer),
            ("native_viewer_pro", "Native Viewer Pro 2.2: просмотр фильма и CV", self._step_native_viewer_pro),
            ("timeline_viewer_2", "Timeline Viewer 2: HTML/JSON viewer", self._step_timeline_viewer_2),
            ("cv_review_board", "CV Review Board: визуальная доска", self._step_cv_review_board),
            ("capcut_bridge", "CapCut Bridge: порядок укладки", self._step_capcut_bridge),
            ("final_assembly_pack", "Final Assembly Pack: handoff в монтаж", self._step_final_assembly_pack),
            ("montage_workbench", "Монтажная мастерская", self._step_montage_workbench),
            ("local_autopilot", "Local Autopilot: ближайшие действия", self._step_local_autopilot),
            ("operator_console", "Операторский центр", self._step_operator_console),
            ("acceptance", "Acceptance Center: Franklin local E2E", self._step_acceptance),
            ("test_center", "Центр тестирования RC1", self._step_test_center),
            ("production_state", "Production State: снимок состояния", self._step_production_state),
            ("working_state_audit", "Working State Auditor", self._step_working_state_audit),
            ("franklin_e2e", "Franklin E2E Runtime: финальная проверка проекта", self._step_franklin_e2e),
            ("export_all", "Export Engine: полный экспорт", self._step_export_all),
        ]

        previous: str | None = None
        for name, title, callback in modules:
            dependencies = [previous] if previous else []
            self.module_registry.register(
                name=name,
                title=title,
                callback=callback,
                dependencies=dependencies,
            )
            previous = name

    def _steps(self) -> list[tuple[str, str, Callable[[], dict[str, Any]]]]:
        order = self.dependency_resolver.resolve()
        return [
            (module.name, module.title, module.callback)
            for module in (self.module_registry.get(name) for name in order)
        ]

    def module_registry_snapshot(self) -> list[dict[str, Any]]:
        # Return a JSON-safe description of the active Alpha 3.1 graph.
        order = self.dependency_resolver.resolve()
        return [
            {
                "name": module.name,
                "title": module.title,
                "enabled": module.enabled,
                "dependencies": list(module.dependencies),
            }
            for module in (self.module_registry.get(name) for name in order)
        ]

    # --- Real step wrappers. Each wrapper performs actual work and returns measured results.
    def _step_preflight(self):
        return PreflightCenter(self.db, self.project_id).run()

    def _step_scan_assets(self):
        before = self._counts()
        result = AssetIntelligence(self.db, self.project_id).scan()
        after = self._counts()
        result = result if isinstance(result, dict) else {"result": result}
        result.update({"before": before, "after": after})
        return result

    def _step_cv_model(self):
        result = CVModel(self.db, self.project_id).analyze()
        return result if isinstance(result, dict) else {"result": result}

    def _step_visual_intelligence(self):
        result = VisualIntelligence(self.db, self.project_id).analyze_assets()
        return result if isinstance(result, dict) else {"result": result}

    def _step_build_shots(self):
        result = StoryEngine(self.db, self.project_id).build_shots()
        return result if isinstance(result, dict) else {"shots": self._counts().get("shots", 0)}

    def _step_story_runtime(self):
        return StoryEngineRuntime(self.db, self.project_id).build()

    def _step_director_ai_runtime(self):
        return DirectorAIRuntime(self.db, self.project_id).analyze()

    def _step_director_ai(self):
        result = DirectorAI(self.db, self.project_id).assign_assets()
        return result if isinstance(result, dict) else {"result": result, "counts": self._counts()}

    def _step_live_api_test(self):
        return LiveApiTestSuite(self.db, self.project_id).run()

    def _step_integrations(self):
        return IntegrationRegistry(self.db, self.project_id).refresh()

    def _step_api_queue(self):
        return IntegrationRegistry(self.db, self.project_id).create_api_jobs_for_missing()

    def _step_api_safe_run(self):
        # Safe default. True paid generation requires explicit opt-in.
        live_enabled = os.getenv("AZ_ENABLE_LIVE_API") == "1"
        paid_allowed = os.getenv("AZ_ALLOW_PAID_CALLS") == "1"
        mode = "live_safe" if live_enabled and paid_allowed else "dry_run"
        return IntegrationRegistry(self.db, self.project_id).run_api_jobs(mode=mode, limit=25)

    def _step_quality(self):
        return QualityCenter(self.db, self.project_id).evaluate()

    def _step_readiness_gate(self):
        return ReleaseGate(self.db, self.project_id).evaluate_rc1()

    def _step_timeline_package(self):
        return TimelineStudio(self.db, self.project_id).export_timeline_package()

    def _step_native_timeline(self):
        return NativeTimelineModel(self.db, self.project_id).build()

    def _step_native_viewer(self):
        return NativeViewerRC(self.db, self.project_id).build_model()

    def _step_native_viewer_pro(self):
        return NativeViewerPro(self.db, self.project_id).build()

    def _step_timeline_viewer_2(self):
        return TimelineViewer2(self.db, self.project_id).build()

    def _step_cv_review_board(self):
        return CVReviewBoard(self.db, self.project_id).build()

    def _step_capcut_bridge(self):
        return CapCutBridge(self.db, self.project_id).build()

    def _step_final_assembly_pack(self):
        return FinalAssemblyPack(self.db, self.project_id).build()

    def _step_montage_workbench(self):
        return MontageWorkbench(self.db, self.project_id).build()

    def _step_local_autopilot(self):
        return LocalAutopilot(self.db, self.project_id).build()

    def _step_operator_console(self):
        return OperatorConsole(self.db, self.project_id).build_operator_plan()

    def _step_acceptance(self):
        return AcceptanceCenter(self.db, self.project_id).evaluate_franklin_working_state()

    def _step_test_center(self):
        return TestCenter(self.db, self.project_id).run()

    def _step_production_state(self):
        return ProductionState(self.db, self.project_id).summarize()

    def _step_working_state_audit(self):
        return WorkingStateAuditor(self.db, self.project_id).audit()

    def _step_franklin_e2e(self):
        return FranklinE2ERuntime(self.db, self.project_id).evaluate()

    def _step_export_all(self):
        return self.workflow.export_all()

    def _counts(self) -> dict[str, int]:
        def count(sql, params=()):
            try:
                r = self.db.one(sql, params)
                return int(r["c"] if r else 0)
            except Exception:
                return 0
        return {
            "assets": count("SELECT COUNT(*) c FROM assets WHERE project_id=?", (self.project_id,)),
            "images": count("SELECT COUNT(*) c FROM assets WHERE project_id=? AND media_type='image'", (self.project_id,)),
            "videos": count("SELECT COUNT(*) c FROM assets WHERE project_id=? AND media_type='video'", (self.project_id,)),
            "audio": count("SELECT COUNT(*) c FROM assets WHERE project_id=? AND media_type='audio'", (self.project_id,)),
            "shots": count("SELECT COUNT(*) c FROM shots WHERE project_id=?", (self.project_id,)),
            "assigned": count("SELECT COUNT(*) c FROM shots WHERE project_id=? AND assigned_asset_id IS NOT NULL", (self.project_id,)),
            "missing": count("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status='missing'", (self.project_id,)),
            "api_jobs": count("SELECT COUNT(*) c FROM api_jobs WHERE project_id=?", (self.project_id,)),
        }

    def _log(self, run_id: int, level: str, message: str, payload: dict | None = None, cb: ProgressCallback | None = None) -> None:
        self.db.execute(
            "INSERT INTO pipeline_logs(run_id,project_id,level,message,payload_json) VALUES(?,?,?,?,?)",
            (run_id, self.project_id, level, message, json.dumps(payload or {}, ensure_ascii=False)),
        )
        if cb:
            cb({"type": "log", "run_id": run_id, "level": level, "message": message, "payload": payload or {}, "time": datetime.now().strftime("%H:%M:%S")})

    def _event(self, run_id: int, task_id: int | None, event_type: str, message: str, progress: float, payload: dict | None, cb: ProgressCallback | None) -> None:
        self.db.execute(
            "INSERT INTO pipeline_task_events(run_id,task_id,project_id,event_type,message,progress,payload_json) VALUES(?,?,?,?,?,?,?)",
            (run_id, task_id, self.project_id, event_type, message, progress, json.dumps(payload or {}, ensure_ascii=False)),
        )
        if cb:
            cb({"type": event_type, "run_id": run_id, "task_id": task_id, "message": message, "progress": progress, "payload": payload or {}, "time": datetime.now().strftime("%H:%M:%S")})

    def _resource_snapshot(self) -> dict[str, Any]:
        """Lightweight runtime telemetry.

        Alpha 2.4 intentionally avoids blocking psutil calls inside live UI progress.
        Some Windows/Python builds can freeze on repeated psutil.cpu_percent calls during
        long Tkinter worker runs. The pipeline must never block on telemetry.
        """
        snap = {"cpu_pct": None, "ram_pct": None, "rss_mb": None}
        try:
            import os, resource  # type: ignore
            # ru_maxrss is cheap and non-blocking on Unix-like systems; on Windows this
            # falls back safely. Values are advisory only.
            if hasattr(resource, "getrusage"):
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                snap["rss_mb"] = round(float(rss) / 1024, 1) if rss else None
        except Exception:
            pass
        return snap

    def _update_graph(self, run_id: int, step_key: str, status: str, progress: float, result: dict | None = None, duration_sec: float | None = None) -> None:
        summary = ''
        if result:
            try:
                summary = json.dumps({k: result[k] for k in list(result)[:8]}, ensure_ascii=False)[:800]
            except Exception:
                summary = str(result)[:800]
        extra = []
        params: list[Any] = [status, progress, summary]
        if status == 'running':
            extra.append('started_at=COALESCE(started_at,CURRENT_TIMESTAMP)')
        if status in ('completed','failed'):
            extra.append('finished_at=CURRENT_TIMESTAMP')
            if duration_sec is not None:
                extra.append('duration_sec=?')
                params.append(duration_sec)
        extra_sql = (', ' + ', '.join(extra)) if extra else ''
        params.extend([run_id, step_key])
        self.db.execute(f"UPDATE pipeline_stage_graph SET status=?, progress=?, result_summary=?, updated_at=CURRENT_TIMESTAMP{extra_sql} WHERE run_id=? AND step_key=?", params)

    def _emit_subprogress(self, run_id: int, task_id: int, title: str, step_start_pct: float, step_end_pct: float, cb: ProgressCallback | None) -> None:
        """UI-only subprogress.

        Alpha 2.4 keeps database writes for task start/completion and avoids writing
        every micro-progress tick to SQLite. This prevents Windows/Tkinter test runs
        from stalling on frequent autocommit writes while preserving live UI updates.
        """
        markers = [(0.20, "инициализация"), (0.50, "обработка"), (0.80, "запись"), (0.95, "проверка")]
        for frac, label in markers:
            pct = round(step_start_pct + (step_end_pct - step_start_pct) * frac, 2)
            try:
                self.db.conn.execute("UPDATE pipeline_task_queue SET progress=? WHERE id=?", (pct, task_id))
                self.db.conn.execute("UPDATE pipeline_runs SET progress=? WHERE id=?", (pct, run_id))
                self.db.conn.commit()
            except Exception:
                pass
            if cb:
                cb({"type": "task_progress", "run_id": run_id, "task_id": task_id, "message": f"{title}: {label}", "progress": pct, "payload": {"phase": label}, "time": datetime.now().strftime("%H:%M:%S")})
            time.sleep(0.04)

    def run(self, cb: ProgressCallback | None = None, retry_failed: bool = True) -> dict[str, Any]:
        steps = self._steps()
        run_uid = f"RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        cur = self.db.execute(
            "INSERT INTO pipeline_runs(run_uid,project_id,status,progress,current_step) VALUES(?,?,?,?,?)",
            (run_uid, self.project_id, "running", 0, "queued"),
        )
        run_id = int(cur.lastrowid)
        task_ids: dict[str, int] = {}
        self.db.execute("DELETE FROM pipeline_stage_graph WHERE project_id=? AND run_id=?", (self.project_id, run_id))
        for i, (key, title, _) in enumerate(steps, start=1):
            tcur = self.db.execute(
                """INSERT INTO pipeline_task_queue(run_id,task_uid,project_id,step_order,step_key,title,status,progress,max_attempts)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (run_id, f"TASK-{i:03d}-{key}", self.project_id, i, key, title, "queued", 0, 2),
            )
            task_ids[key] = int(tcur.lastrowid)
            self.db.execute(
                """INSERT INTO pipeline_stage_graph(run_id,project_id,step_order,step_key,title,status,progress)
                   VALUES(?,?,?,?,?,?,?)""",
                (run_id, self.project_id, i, key, title, "queued", 0),
            )
        self._export_pipeline_graph(run_id)
        self._log(run_id, "INFO", f"Конвейер запущен. {run_uid}", {"steps": len(steps), "counts_before": self._counts(), "resources": self._resource_snapshot()}, cb)
        self._event(run_id, None, "run_started", f"Создан запуск {run_uid}", 0, {"steps": len(steps)}, cb)

        final_result: dict[str, Any] = {"run_id": run_id, "run_uid": run_uid, "steps": []}
        try:
            for i, (key, title, fn) in enumerate(steps, start=1):
                task_id = task_ids[key]
                pct_start = round((i - 1) / len(steps) * 100, 2)
                pct_end = round(i / len(steps) * 100, 2)
                self.db.execute(
                    "UPDATE pipeline_task_queue SET status=?, attempts=attempts+1, progress=?, started_at=CURRENT_TIMESTAMP WHERE id=?",
                    ("running", pct_start, task_id),
                )
                self._update_graph(run_id, key, "running", pct_start)
                self.db.execute("UPDATE pipeline_runs SET progress=?, current_step=? WHERE id=?", (pct_start, key, run_id))
                if cb:
                    cb({"type": "step_start", "run_id": run_id, "task_id": task_id, "step": key, "title": title, "progress": pct_start})
                self._log(run_id, "INFO", f"▶ {title}", {"step": key, "task_id": task_id}, cb)
                self._event(run_id, task_id, "task_started", title, pct_start, {"step": key}, cb)
                t0 = time.time()
                try:
                    self._emit_subprogress(run_id, task_id, title, pct_start, pct_end, cb)
                    result = fn()
                    safe_result = self._safe_json(result)
                    elapsed = round(time.time() - t0, 2)
                    self.db.execute(
                        """UPDATE pipeline_task_queue
                           SET status=?, progress=?, result_json=?, error=NULL, finished_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        ("completed", pct_end, json.dumps(safe_result, ensure_ascii=False), task_id),
                    )
                    self._update_graph(run_id, key, "completed", pct_end, safe_result, elapsed)
                    self.db.execute(
                        "INSERT INTO workflow_jobs(project_id,stage,status,details) VALUES(?,?,?,?)",
                        (self.project_id, key, "done", json.dumps({"run_id": run_id, "run_uid": run_uid, "elapsed_sec": elapsed, "result": safe_result}, ensure_ascii=False)),
                    )
                    self.db.execute("UPDATE pipeline_runs SET progress=?, current_step=? WHERE id=?", (pct_end, key, run_id))
                    final_result["steps"].append({"step": key, "title": title, "status": "completed", "elapsed_sec": elapsed, "result": safe_result})
                    self._log(run_id, "INFO", f"✓ {title} завершён ({elapsed} сек.)", {"step": key, "progress": pct_end, "result": safe_result}, cb)
                    self._event(run_id, task_id, "task_completed", title, pct_end, {"elapsed_sec": elapsed, "result": safe_result}, cb)
                    if cb:
                        cb({"type": "step_done", "run_id": run_id, "task_id": task_id, "step": key, "title": title, "progress": pct_end, "result": safe_result})
                except Exception as step_error:
                    err = traceback.format_exc()
                    self.db.execute(
                        "UPDATE pipeline_task_queue SET status=?, error=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                        ("failed", err, task_id),
                    )
                    self._update_graph(run_id, key, "failed", pct_start, {"error": str(step_error)})
                    self._log(run_id, "ERROR", f"Этап провален: {title}: {step_error}", {"traceback": err}, cb)
                    self._event(run_id, task_id, "task_failed", f"{title}: {step_error}", pct_start, {"traceback": err}, cb)
                    if retry_failed:
                        self._log(run_id, "WARN", f"Повторный запуск этапа: {title}", {"step": key}, cb)
                        self.db.execute("UPDATE pipeline_task_queue SET status=?, started_at=CURRENT_TIMESTAMP, attempts=attempts+1 WHERE id=?", ("running", task_id))
                        result = fn()
                        safe_result = self._safe_json(result)
                        elapsed = round(time.time() - t0, 2)
                        self.db.execute(
                            "UPDATE pipeline_task_queue SET status=?, progress=?, result_json=?, error=NULL, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                            ("completed", pct_end, json.dumps(safe_result, ensure_ascii=False), task_id),
                        )
                        final_result["steps"].append({"step": key, "title": title, "status": "completed_after_retry", "elapsed_sec": elapsed, "result": safe_result})
                        self._event(run_id, task_id, "task_completed", f"{title} завершён после повтора", pct_end, {"elapsed_sec": elapsed}, cb)
                    else:
                        raise

            final_result["status"] = "done"
            final_result["counts_after"] = self._counts()
            self.db.execute(
                "UPDATE pipeline_runs SET status=?, progress=?, current_step=?, finished_at=CURRENT_TIMESTAMP, result_json=? WHERE id=?",
                ("done", 100, "completed", json.dumps(final_result, ensure_ascii=False), run_id),
            )
            self._export_pipeline_graph(run_id)
            self._export_run_report(run_id, final_result)
            self._log(run_id, "INFO", "Конвейер завершён. Franklin обработан до экспортов и handoff-пакета.", {"status": "done", "counts_after": final_result["counts_after"], "resources": self._resource_snapshot()}, cb)
            self._event(run_id, None, "run_finished", "Конвейер завершён", 100, final_result, cb)
            if cb:
                cb({"type": "finished", "run_id": run_id, "run_uid": run_uid, "progress": 100, "result": final_result})
            return final_result
        except Exception as e:
            err = traceback.format_exc()
            self.db.execute("UPDATE pipeline_runs SET status=?, error=?, finished_at=CURRENT_TIMESTAMP WHERE id=?", ("error", err, run_id))
            self.db.execute(
                "INSERT INTO workflow_jobs(project_id,stage,status,details) VALUES(?,?,?,?)",
                (self.project_id, "pipeline_runtime", "error", json.dumps({"run_id": run_id, "run_uid": run_uid, "error": str(e), "traceback": err}, ensure_ascii=False)),
            )
            self._log(run_id, "ERROR", f"Ошибка конвейера: {e}", {"traceback": err}, cb)
            self._event(run_id, None, "run_failed", f"Ошибка конвейера: {e}", 0, {"traceback": err}, cb)
            if cb:
                cb({"type": "error", "run_id": run_id, "run_uid": run_uid, "message": str(e), "traceback": err})
            raise

    def retry_failed_tasks(self, run_id: int, cb: ProgressCallback | None = None) -> dict[str, Any]:
        failed = self.db.rows("SELECT step_key,title FROM pipeline_task_queue WHERE run_id=? AND status='failed' ORDER BY step_order", (run_id,))
        if not failed:
            return {"run_id": run_id, "retried": 0, "message": "Нет проваленных задач"}
        step_map = {k: (t, fn) for k, t, fn in self._steps()}
        retried = []
        for r in failed:
            key = r["step_key"]
            if key not in step_map:
                continue
            title, fn = step_map[key]
            self._log(run_id, "INFO", f"Повтор задачи {title}", {"step": key}, cb)
            res = fn()
            self.db.execute("UPDATE pipeline_task_queue SET status=?, result_json=?, error=NULL, finished_at=CURRENT_TIMESTAMP WHERE run_id=? AND step_key=?", ("completed", json.dumps(self._safe_json(res), ensure_ascii=False), run_id, key))
            retried.append(key)
        return {"run_id": run_id, "retried": len(retried), "steps": retried}

    def _safe_json(self, obj: Any) -> Any:
        try:
            json.dumps(obj, ensure_ascii=False)
            return obj
        except Exception:
            return str(obj)

    def _export_pipeline_graph(self, run_id: int) -> None:
        rows = [dict(r) for r in self.db.rows("SELECT step_order,step_key,title,status,progress,duration_sec,result_summary,started_at,finished_at FROM pipeline_stage_graph WHERE run_id=? ORDER BY step_order", (run_id,))]
        (self.export_dir / "pipeline_graph.json").write_text(json.dumps({"run_id": run_id, "version": "RC1 Alpha 3.1", "nodes": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        status_class = {"queued":"queued", "running":"running", "completed":"done", "failed":"failed"}
        cards = ""
        for r in rows:
            cls = status_class.get(r.get('status'), 'queued')
            cards += f"<div class='node {cls}'><div class='n'>{r['step_order']:02d}</div><div class='t'>{r['title']}</div><div class='s'>{r['status']} · {r['progress']}%</div></div>"
        html=f"""<!doctype html><meta charset='utf-8'><title>ATLAS ZERO Pipeline Graph</title>
<style>body{{font-family:Segoe UI,Arial;background:#08111f;color:#e5edf8;margin:24px;font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}.node{{border:1px solid #26364d;border-radius:14px;padding:14px;background:#111827}}.n{{color:#7dd3fc;font-size:22px;font-weight:800}}.t{{font-weight:700;margin:6px 0}}.s{{color:#a9b8cc}}.queued{{opacity:.55}}.running{{border-color:#38bdf8;box-shadow:0 0 0 1px #38bdf8 inset}}.done{{border-color:#22c55e}}.failed{{border-color:#ef4444;background:#2a1117}}</style>
<h1>ATLAS ZERO — Pipeline Graph / Run #{run_id}</h1><div class='grid'>{cards}</div>"""
        (self.export_dir / "pipeline_graph.html").write_text(html, encoding="utf-8")

    def _export_run_report(self, run_id: int, result: dict[str, Any]) -> None:
        logs = [dict(r) for r in self.db.rows("SELECT level,message,payload_json,created_at FROM pipeline_logs WHERE run_id=? ORDER BY id", (run_id,))]
        tasks = [dict(r) for r in self.db.rows("SELECT id,task_uid,step_order,step_key,title,status,attempts,progress,result_json,error,started_at,finished_at FROM pipeline_task_queue WHERE run_id=? ORDER BY step_order", (run_id,))]
        events = [dict(r) for r in self.db.rows("SELECT task_id,event_type,message,progress,payload_json,created_at FROM pipeline_task_events WHERE run_id=? ORDER BY id", (run_id,))]
        report = {"version": "RC1 Alpha 3.1", "run_id": run_id, "project_id": self.project_id, "status": "done", "tasks": tasks, "events": events, "logs": logs, "result": result}
        (self.export_dir / "pipeline_run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.export_dir / "pipeline_task_queue.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.export_dir / "pipeline_task_events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        html_rows = "".join(
            f"<tr class='{t['status']}'><td>{t['step_order']}</td><td>{t['task_uid']}</td><td>{t['title']}</td><td>{t['status']}</td><td>{t['attempts']}</td><td>{t['progress']}%</td></tr>"
            for t in tasks
        )
        html_logs = "".join(f"<div><span>{l['created_at']}</span> <b>{l['level']}</b> {l['message']}</div>" for l in logs[-250:])
        (self.export_dir / "pipeline_run_report.html").write_text(
            f"""<!doctype html><meta charset='utf-8'><title>ATLAS ZERO Pipeline Run</title>
<style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e5e7eb;margin:24px;font-size:14px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #334155;padding:8px;text-align:left}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:14px;margin:12px 0}}span{{color:#94a3b8}}.completed td{{color:#86efac}}.failed td{{color:#fca5a5}}</style>
<h1>ATLAS ZERO — Pipeline Run #{run_id}</h1><div class='card'>Статус: <b>done</b><br>Версия: RC1 Alpha 3.1<br>Файлов после запуска: {result.get('counts_after',{})}</div><h2>Очередь задач</h2><table><tr><th>#</th><th>Task ID</th><th>Этап</th><th>Статус</th><th>Попытки</th><th>Прогресс</th></tr>{html_rows}</table><h2>Журнал</h2><div class='card'>{html_logs}</div>""",
            encoding="utf-8",
        )
