from __future__ import annotations
import json
from .database import Database
from .paths import EXPORTS
from .events import EventBus

class WorkingStateAuditor:
    """Separates local production readiness from full autonomous Enterprise readiness."""
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.export_dir=EXPORTS/project_id; self.bus=EventBus(db,project_id)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def audit(self) -> dict:
        assets=self._count('assets')
        shots=self._count('shots')
        assigned=self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status='assigned'",(self.project_id,))['c'] if shots else 0
        exports_required=['монтажный_лист.csv','capcut_пакет.csv','capcut_guide_ru.md','timeline_operator_view.html','franklin_acceptance.html','operator_console.html']
        export_status=[]
        for name in exports_required:
            p=self.export_dir/name
            export_status.append({'file':name,'exists':p.exists(),'size':p.stat().st_size if p.exists() else 0})
        local_ready = assets>=10 and shots>=120 and assigned>=1 and all(x['exists'] for x in export_status[:3])
        live_ready = self._live_ready()
        report={
            'project': self.project_id,
            'local_production_ready': local_ready,
            'full_autonomous_ready': False if not live_ready else local_ready,
            'assets': assets,
            'shots': shots,
            'assigned_shots': assigned,
            'coverage_pct': round(assigned/max(shots,1)*100,1),
            'exports': export_status,
            'live_api_ready': live_ready,
            'expert_status': 'Franklin можно вести локально до монтажного handoff. Полная автономная работа заблокирована live API и финальной CV-моделью.' if local_ready and not live_ready else 'Требуется локальная доводка.',
            'next_actions': [
                'Открыть timeline_operator_view.html и проверить дефицитные шоты.',
                'Сгенерировать недостающие материалы из missing_prioritized.csv.',
                'После подключения API заполнить .env и включить AZ_ENABLE_LIVE_CALLS=1 только для проверок.',
                'Импортировать capcut_пакет.csv / capcut_guide_ru.md в ручной монтажный процесс.'
            ]
        }
        (self.export_dir/'working_state_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (self.export_dir/'working_state_audit.html').write_text(self._html(report), encoding='utf-8')
        self.bus.emit('WORKING_STATE_AUDITED', {'local_ready': local_ready, 'full_ready': report['full_autonomous_ready']})
        return report

    def _count(self, table):
        try: return self.db.one(f'SELECT COUNT(*) c FROM {table} WHERE project_id=?',(self.project_id,))['c']
        except Exception: return 0

    def _live_ready(self):
        try:
            rows=self.db.rows('SELECT status FROM api_credentials_checks WHERE project_id=?',(self.project_id,))
            return any(r['status']=='credential_found_live_allowed' for r in rows)
        except Exception: return False

    def _html(self, r):
        rows=''.join(f"<tr><td>{x['file']}</td><td>{'Да' if x['exists'] else 'Нет'}</td><td>{x['size']}</td></tr>" for x in r['exports'])
        actions=''.join(f"<li>{a}</li>" for a in r['next_actions'])
        return f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>Working State Audit</title><style>body{{background:#0b1220;color:#e5e7eb;font-family:Segoe UI,Arial;padding:24px}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:16px;margin:12px 0}}.ok{{color:#22c55e}}.bad{{color:#f97316}}td,th{{padding:7px 10px;border-bottom:1px solid #334155}}table{{border-collapse:collapse;width:100%}}</style></head><body><h1>ATLAS ZERO · Аудит рабочего состояния</h1><div class='card'><b>Локальная production-готовность:</b> <span class='{'ok' if r['local_production_ready'] else 'bad'}'>{'Да' if r['local_production_ready'] else 'Нет'}</span><br><b>Полная автономная готовность:</b> <span class='{'ok' if r['full_autonomous_ready'] else 'bad'}'>{'Да' if r['full_autonomous_ready'] else 'Нет'}</span><br><b>Покрытие:</b> {r['coverage_pct']}%<br><b>Экспертный статус:</b> {r['expert_status']}</div><div class='card'><h2>Экспорты</h2><table><tr><th>Файл</th><th>Есть</th><th>Размер</th></tr>{rows}</table></div><div class='card'><h2>Следующие действия</h2><ol>{actions}</ol></div></body></html>"""
