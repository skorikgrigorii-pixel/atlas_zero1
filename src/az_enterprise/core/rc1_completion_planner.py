from __future__ import annotations
import csv, json
from .database import Database
from .paths import EXPORTS

class RC1CompletionPlanner:
    """Turns readiness blockers into an execution plan.

    The goal is to stop endless version churn and produce an actionable list that can
    bring the OS from local Franklin workflow to real RC1 readiness.
    """
    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def plan(self) -> dict:
        assets = self.db.one('SELECT COUNT(*) c FROM assets WHERE project_id=?', (self.project_id,))['c']
        shots = self.db.one('SELECT COUNT(*) c FROM shots WHERE project_id=?', (self.project_id,))['c']
        assigned = self.db.one('SELECT COUNT(*) c FROM shots WHERE project_id=? AND assigned_asset_id IS NOT NULL', (self.project_id,))['c']
        missing = shots - assigned
        live_ready = self.db.one("SELECT COUNT(*) c FROM integration_profiles WHERE status LIKE '%live%' OR status='connected'")['c']
        visual_profiles = self.db.one('SELECT COUNT(*) c FROM visual_profiles WHERE project_id=?', (self.project_id,))['c']
        latest_qc = self.db.one('SELECT readiness FROM quality_reports WHERE project_id=? ORDER BY id DESC LIMIT 1', (self.project_id,))
        qc = float(latest_qc['readiness']) if latest_qc else 0

        tasks = []
        def add(priority, area, task, acceptance, owner='operator'):
            tasks.append({'priority': priority, 'area': area, 'task': task, 'acceptance': acceptance, 'owner': owner})
        if live_ready < 3:
            add(1, 'Live API', 'Подключить минимум Leonardo, ElevenLabs, OpenAI через ENV-ключи и пройти safe-live handshake', 'integration_health показывает connected/live-ready без ошибок')
        if missing > 0:
            add(1, 'Материалы', f'Закрыть {missing} missing-шотов через пакет capcut_missing_generation_batch.md', 'после повторного конвейера missing=0 или закрыты deliberate placeholders')
        if visual_profiles < max(1, assets//2):
            add(2, 'Visual Intelligence', 'Прогнать визуальный анализ по всем изображениям и видео', 'визуальный_анализ.csv содержит профиль для 90%+ ассетов')
        if qc < 90:
            add(2, 'Quality', 'Поднять QC readiness до 90%+', 'working_state_audit показывает local_production_ready=True и QC>=90')
        add(2, 'Timeline', 'Проверить capcut_operator_bridge.html и собрать первые 60 секунд в CapCut', 'CapCut draft содержит первые 60 секунд с правильными таймкодами')
        add(3, 'Release', 'Сформировать publish package после чернового монтажа', 'release center содержит название, описание, главы, теги, thumbnail brief')
        add(3, 'YouTube', 'Подключить YouTube Analytics после публикации тестового ролика', 'получены retention/CTR/AVD и сохранены в Project Brain')

        csv_path = self.export_dir / 'rc1_completion_plan.csv'
        with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=['priority','area','task','acceptance','owner'])
            w.writeheader(); w.writerows(tasks)
        json_path = self.export_dir / 'rc1_completion_plan.json'
        summary = {'assets': assets, 'shots': shots, 'assigned': assigned, 'missing': missing, 'qc': qc, 'live_ready_count': live_ready, 'tasks': tasks}
        json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        html_path = self.export_dir / 'rc1_completion_plan.html'
        rows = ''.join(f"<tr><td>P{t['priority']}</td><td>{t['area']}</td><td>{t['task']}</td><td>{t['acceptance']}</td><td>{t['owner']}</td></tr>" for t in tasks)
        html_path.write_text(f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>RC1 Completion Plan</title>
<style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e5e7eb;margin:24px;font-size:13px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #334155;padding:8px;vertical-align:top}}th{{background:#111827}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:14px;margin-bottom:14px}}</style>
<h1>ATLAS ZERO Enterprise RC1 — план доведения до полноценной работы</h1>
<div class='card'>Шоты: {shots} · Назначено: {assigned} · Missing: {missing} · QC: {qc:.2f}% · Live-ready интеграций: {live_ready}</div>
<table><tr><th>Приоритет</th><th>Зона</th><th>Задача</th><th>Критерий приёмки</th><th>Ответственный</th></tr>{rows}</table></html>""", encoding='utf-8')
        return {'tasks': len(tasks), 'missing': missing, 'qc': qc, 'html': str(html_path), 'csv': str(csv_path), 'json': str(json_path)}
