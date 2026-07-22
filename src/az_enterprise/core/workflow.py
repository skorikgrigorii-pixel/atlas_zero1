from __future__ import annotations
import csv, json
from pathlib import Path
from .database import Database
from .asset_intelligence import AssetIntelligence
from .story_engine import StoryEngine
from .director_ai import DirectorAI
from .quality import QualityCenter
from .integrations import IntegrationRegistry
from .visual_intelligence import VisualIntelligence
from .events import EventBus
from .paths import EXPORTS
from .timeline_studio import TimelineStudio
from .release_gate import ReleaseGate
from .production_state import ProductionState
from .acceptance_center import AcceptanceCenter
from .preflight import PreflightCenter
from .api_gateway import ApiGateway
from .operator_console import OperatorConsole
from .live_api_layer import LiveApiLayer
from .final_timeline_viewer import FinalTimelineViewer
from .working_state_auditor import WorkingStateAuditor
from .capcut_bridge import CapCutBridge
from .control_layer_rc2 import RC2ReadinessPlanner
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

class WorkflowEngine:
    def __init__(self, db: Database, project_id='franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _job(self, stage: str, status: str, details: dict):
        self.db.execute('INSERT INTO workflow_jobs(project_id,stage,status,details) VALUES(?,?,?,?)',
                        (self.project_id, stage, status, json.dumps(details, ensure_ascii=False)))

    def run_pipeline(self) -> dict:
        self.bus.emit('PIPELINE_STARTED', {})
        self.db.init()
        preflight_start = PreflightCenter(self.db, self.project_id).run(); self._job('preflight_start','done',preflight_start)
        scan = AssetIntelligence(self.db, self.project_id).scan(); self._job('scan_assets','done',scan)
        visual = VisualIntelligence(self.db, self.project_id).analyze_assets(); self._job('visual_intelligence','done',visual)
        shots = StoryEngine(self.db, self.project_id).build_shots(); self._job('build_shots','done',shots)
        decisions = DirectorAI(self.db, self.project_id).assign_assets(); self._job('director_ai','done',decisions)
        integrations = IntegrationRegistry(self.db, self.project_id).refresh(); self._job('integrations','done',integrations)
        api_gateway = ApiGateway(self.db, self.project_id).check_credentials(); self._job('api_gateway','done',api_gateway)
        api_jobs = IntegrationRegistry(self.db, self.project_id).create_api_jobs_for_missing(); self._job('api_jobs','done',api_jobs)
        api_run = IntegrationRegistry(self.db, self.project_id).run_api_jobs(mode='dry_run', limit=25); self._job('api_jobs_dry_run','done',api_run)
        qc = QualityCenter(self.db, self.project_id).evaluate(); self._job('quality','done',qc)
        gate = QualityCenter(self.db, self.project_id).readiness_gate(); self._job('readiness_gate','done',gate)
        timeline_package = TimelineStudio(self.db, self.project_id).export_timeline_package(); self._job('timeline_package','done',timeline_package)
        rc2_gate = RC2ReadinessPlanner(self.db, self.project_id).evaluate(); self._job('rc2_release_gate','done',rc2_gate)
        production_state = ProductionState(self.db, self.project_id).summarize(); self._job('production_state','done',production_state)
        self.db.execute('INSERT INTO production_snapshots(project_id,summary_json) VALUES(?,?)', (self.project_id, json.dumps(production_state, ensure_ascii=False)))
        handoff = AcceptanceCenter(self.db, self.project_id).build_capcut_handoff(); self._job('capcut_handoff','done',handoff)
        acceptance = AcceptanceCenter(self.db, self.project_id).evaluate_franklin_working_state(); self._job('franklin_acceptance','done',acceptance)
        preflight_final = PreflightCenter(self.db, self.project_id).run(); self._job('preflight_final','done',preflight_final)
        operator = OperatorConsole(self.db, self.project_id).build_operator_plan(); self._job('operator_console','done',operator)
        live_api = LiveApiLayer(self.db, self.project_id).export_report(self.export_dir); self._job('live_api_layer','done',live_api)
        final_viewer = FinalTimelineViewer(self.db, self.project_id).build(); self._job('final_timeline_viewer','done',final_viewer)
        working_audit = WorkingStateAuditor(self.db, self.project_id).audit(); self._job('working_state_audit','done',working_audit)
        capcut_bridge = CapCutBridge(self.db, self.project_id).build(); self._job('capcut_bridge','done',capcut_bridge)
        completion_plan = RC2ReadinessPlanner(self.db, self.project_id).plan(); self._job('rc2_completion_plan','done',completion_plan)
        montage_workbench = MontageWorkbench(self.db, self.project_id).build(); self._job('montage_workbench','done',montage_workbench)
        local_autopilot = LocalAutopilot(self.db, self.project_id).build(); self._job('local_autopilot','done',local_autopilot)
        native_timeline = NativeTimelineModel(self.db, self.project_id).build(); self._job('native_timeline_model','done',native_timeline)
        final_pack = FinalAssemblyPack(self.db, self.project_id).build(); self._job('final_assembly_pack','done',final_pack)
        cv_model = CVModel(self.db, self.project_id).analyze(); self._job('cv_model_1_5','done',cv_model)
        live_connectors = LiveConnectorHub(self.db, self.project_id).export_report(); self._job('live_connectors_1_5','done',live_connectors)
        native_viewer_rc = NativeViewerRC(self.db, self.project_id).build_model(); self._job('native_viewer_rc_1_5','done',native_viewer_rc)
        live_api_test = LiveApiTestSuite(self.db, self.project_id).run(); self._job('live_api_test_suite_1_7','done',live_api_test)
        cv_review = CVReviewBoard(self.db, self.project_id).build(); self._job('cv_review_board_1_7','done',cv_review)
        timeline_viewer_2 = TimelineViewer2(self.db, self.project_id).build(); self._job('timeline_viewer_2_2_7','done',timeline_viewer_2)
        test_center = TestCenter(self.db, self.project_id).run(); self._job('rc1_test_center_1_7','done',test_center)
        rc2_gate_final = RC2ReadinessPlanner(self.db, self.project_id).evaluate(); self._job('rc2_release_gate_final','done',rc2_gate_final)
        exports = self.export_all(); self._job('export','done',exports)
        self.bus.emit('PIPELINE_FINISHED', {'readiness': rc2_gate_final['score'], 'rc2_ready': rc2_gate_final['ready']})
        return {'scan': scan, 'visual': visual, 'shots': shots, 'decisions': decisions, 'integrations': integrations, 'api_gateway': api_gateway, 'api_jobs': api_jobs, 'api_run': api_run, 'qc': qc, 'gate': gate, 'timeline_package': timeline_package, 'rc2_gate': rc2_gate, 'production_state': production_state, 'handoff': handoff, 'acceptance': acceptance, 'preflight': preflight_final, 'operator': operator, 'live_api': live_api, 'final_viewer': final_viewer, 'working_audit': working_audit, 'capcut_bridge': capcut_bridge, 'completion_plan': completion_plan, 'montage_workbench': montage_workbench, 'local_autopilot': local_autopilot, 'native_timeline': native_timeline, 'final_pack': final_pack, 'cv_model': cv_model, 'live_connectors': live_connectors, 'native_viewer_rc': native_viewer_rc, 'live_api_test': live_api_test, 'cv_review': cv_review, 'timeline_viewer_2': timeline_viewer_2, 'test_center': test_center, 'rc2_gate_final': rc2_gate_final, 'exports': exports}

    def export_all(self) -> dict:
        files = []
        shots = self.db.rows('''SELECT s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,s.emotion,s.status,a.filename as asset
            FROM shots s LEFT JOIN assets a ON s.assigned_asset_id=a.id WHERE s.project_id=? ORDER BY s.idx''', (self.project_id,))
        timeline_csv = self.export_dir / 'монтажный_лист.csv'
        with timeline_csv.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f); writer.writerow(['№','Начало','Конец','Блок','Смысл','Потребность','Эмоция','Статус','Материал'])
            for r in shots: writer.writerow([r['idx'], r['start_sec'], r['end_sec'], r['block'], r['story_goal'], r['visual_need'], r['emotion'], r['status'], r['asset'] or ''])
        files.append(str(timeline_csv))
        decisions = self.db.rows('SELECT shot_id,asset_id,score,reason,alternatives FROM director_decisions WHERE project_id=?', (self.project_id,))
        decisions_json = self.export_dir / 'решения_режиссера.json'
        decisions_json.write_text(json.dumps([dict(r) for r in decisions], ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(str(decisions_json))
        readiness = self.db.rows('SELECT criterion,score,passed,comment FROM readiness_checks WHERE project_id=?', (self.project_id,))
        readiness_json = self.export_dir / 'готовность_rc1.json'
        readiness_json.write_text(json.dumps([dict(r) for r in readiness], ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(str(readiness_json))
        production_state = ProductionState(self.db, self.project_id).summarize()
        production_json = self.export_dir / 'production_state.json'
        production_json.write_text(json.dumps(production_state, ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(str(production_json))
        self._write_command_center_html(production_state)
        files.append(str(self.export_dir / 'command_center.html'))
        for extra in ['franklin_acceptance_report.json','franklin_acceptance.html','capcut_пакет.csv','capcut_guide.md','missing_prioritized.csv','preflight_report.json','preflight_report.html','операторские_задачи.csv','franklin_operator_runbook.md','export_validation.json','operator_console.html','timeline_operator_view.html','timeline_operator_view.json','working_state_audit.html','working_state_audit.json','live_api_layer_report.json','live_api_setup_ru.md','capcut_manual_build_order.csv','capcut_operator_bridge.html','capcut_bins.csv','capcut_missing_generation_batch.md','rc1_completion_plan.html','rc1_completion_plan.csv','rc1_completion_plan.json','montage_workbench.html','montage_workbench.json','operator_timeline_board.csv','local_autopilot_report.json','local_autopilot_tasks.csv','operator_next_30_minutes.md','native_timeline_model.json','native_timeline_view.html','cv_model_report.json','native_viewer_model_rc.json','native_viewer_rc.html','native_viewer_tracks.csv','live_connectors_report.json','live_connectors_setup_ru.md','live_api_test_suite.json','live_api_test_suite.html','cv_review_board.csv','cv_review_board.html','timeline_viewer_2_model.json','timeline_viewer_2.html','rc1_test_report.json','rc1_test_cases.csv','rc1_test_center.html']:
            p=self.export_dir/extra
            if p.exists(): files.append(str(p))
        pack=self.export_dir/'FINAL_ASSEMBLY_PACK'
        if pack.exists(): files.append(str(pack/'index.html'))
        api_jobs = self.db.rows('SELECT service,job_type,status,payload FROM api_jobs WHERE project_id=?', (self.project_id,))
        api_json = self.export_dir / 'очередь_api.json'
        api_json.write_text(json.dumps([dict(r) for r in api_jobs], ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(str(api_json))
        # Visual profiles export
        visual_rows = self.db.rows('SELECT a.filename,v.plan_type,v.palette,v.style_score,v.profile_json FROM visual_profiles v JOIN assets a ON a.id=v.asset_id WHERE v.project_id=? ORDER BY v.style_score DESC', (self.project_id,))
        visual_csv = self.export_dir / 'визуальный_анализ.csv'
        with visual_csv.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f); writer.writerow(['Файл','Тип плана','Палитра','Стиль','Профиль JSON'])
            for r in visual_rows: writer.writerow([r['filename'], r['plan_type'], r['palette'], r['style_score'], r['profile_json']])
        files.append(str(visual_csv))
        # Credential and integration health report
        integ_rows = self.db.rows('SELECT service,status,env_key,capabilities FROM integration_profiles WHERE 1=1 ORDER BY service')
        integ_json = self.export_dir / 'интеграции.json'
        integ_json.write_text(json.dumps([dict(r) for r in integ_rows], ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(str(integ_json))
        run_rows = self.db.rows('SELECT service,mode,status,response_json,created_at FROM integration_runs WHERE project_id=? ORDER BY id DESC LIMIT 100', (self.project_id,))
        runs_json = self.export_dir / 'api_запуски.json'
        runs_json.write_text(json.dumps([dict(r) for r in run_rows], ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(str(runs_json))
        cred_rows = self.db.rows('SELECT service,status,detail_json,created_at FROM api_credentials_checks WHERE project_id=? ORDER BY service', (self.project_id,))
        cred_json = self.export_dir / 'api_готовность.json'
        cred_json.write_text(json.dumps([dict(r) for r in cred_rows], ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(str(cred_json))
        # Similarity export
        sim_rows = self.db.rows('''SELECT aa.filename a, bb.filename b, s.score, s.reason FROM asset_similarity s
            JOIN assets aa ON aa.id=s.asset_id_a JOIN assets bb ON bb.id=s.asset_id_b WHERE s.project_id=? ORDER BY s.score DESC''', (self.project_id,))
        sim_csv = self.export_dir / 'похожие_ассеты.csv'
        with sim_csv.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f); writer.writerow(['Ассет A','Ассет B','Сходство','Причина'])
            for r in sim_rows: writer.writerow([r['a'], r['b'], r['score'], r['reason']])
        files.append(str(sim_csv))
        cs = self.export_dir/'visual_contact_sheet.jpg'
        if cs.exists(): files.append(str(cs))
        html = self.export_dir / 'release_center.html'
        latest_qc = self.db.one('SELECT * FROM quality_reports WHERE project_id=? ORDER BY id DESC LIMIT 1', (self.project_id,))
        qc_summary = json.loads(latest_qc['summary']) if latest_qc else {}
        rows_html = ''.join(f"<tr><td>{r['idx']}</td><td>{r['start_sec']:.1f}</td><td>{r['block']}</td><td>{r['status']}</td><td>{r['asset'] or 'Нужно создать'}</td></tr>" for r in shots[:80])
        html.write_text(f'''<!doctype html><meta charset="utf-8"><title>ATLAS ZERO RC1 Alpha 1.8</title>
<style>body{{font-family:Arial;background:#111827;color:#e5e7eb;font-size:13px}}.card{{background:#1f2937;padding:14px;border-radius:12px;margin:12px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #374151;padding:6px}}.ok{{color:#22c55e}}.warn{{color:#f59e0b}}</style>
<h1>ATLAS ZERO Enterprise RC1 Alpha 1.8</h1><div class="card"><b>Готовность Franklin:</b> {latest_qc['readiness'] if latest_qc else 0}%<br><b>Недостающих:</b> {qc_summary.get('missing_shots','?')}<br><b>Рекомендации:</b><ul>{''.join('<li>'+x+'</li>' for x in qc_summary.get('recommendations',[]))}</ul></div>
<div class="card"><h2>Монтажный лист</h2><table><tr><th>№</th><th>Старт</th><th>Блок</th><th>Статус</th><th>Материал</th></tr>{rows_html}</table></div>''', encoding='utf-8')
        files.append(str(html))
        return {'files': files}
    def _write_command_center_html(self, ps: dict):
        blockers = ''.join(f"<li><b>{b['title']}</b> — {b['comment']} ({b['score']}%)</li>" for b in ps.get('blockers', []))
        actions = ''.join(f"<li>{a}</li>" for a in ps.get('next_actions', []))
        html = f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>ATLAS ZERO Command Center</title>
<style>body{{background:#0f172a;color:#e5e7eb;font-family:Segoe UI,Arial;margin:24px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:16px}}.num{{font-size:28px;font-weight:700}}h1,h2{{margin:8px 0}}li{{margin:8px 0}}</style>
<h1>ATLAS ZERO Enterprise RC1 — командный центр</h1>
<div class='grid'>
<div class='card'><div>Материалы</div><div class='num'>{ps['assets']}</div></div>
<div class='card'><div>Шоты</div><div class='num'>{ps['shots']}</div></div>
<div class='card'><div>Покрытие</div><div class='num'>{ps['coverage_pct']}%</div></div>
<div class='card'><div>QC</div><div class='num'>{ps['qc_readiness']}%</div></div>
</div>
<h2>Блокеры полноценной работы</h2><ul>{blockers}</ul>
<h2>Следующие действия</h2><ol>{actions}</ol>
<p>Статус: {'готова' if ps.get('full_work_ready') else 'не готова'} к полноценной работе.</p>
</html>"""
        (self.export_dir/'command_center.html').write_text(html, encoding='utf-8')

