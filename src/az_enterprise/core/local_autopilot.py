from __future__ import annotations
import json, csv
from .database import Database
from .paths import EXPORTS
from .events import EventBus

class LocalAutopilot:
    """Creates the exact local action plan to finish Franklin without live API.

    The goal is practical: make the current project executable today using local
    exports, CapCut, and generated prompt batches.
    """
    def __init__(self, db: Database, project_id: str='franklin'):
        self.db=db; self.project_id=project_id; self.export_dir=EXPORTS/project_id; self.export_dir.mkdir(parents=True, exist_ok=True); self.bus=EventBus(db,project_id)

    def build(self) -> dict:
        shots=self.db.rows('SELECT idx,start_sec,end_sec,block,visual_need,status,assigned_asset_id FROM shots WHERE project_id=? ORDER BY idx',(self.project_id,))
        assets=self.db.one('SELECT COUNT(*) c FROM assets WHERE project_id=?',(self.project_id,))['c'] if self._table('assets') else 0
        missing=[dict(s) for s in shots if s['status']!='assigned']
        assigned=len(shots)-len(missing)
        critical=[]
        if missing:
            critical.append({'title':'Создать недостающие материалы','count':len(missing),'file':'capcut_missing_generation_batch.md'})
        critical.append({'title':'Собрать черновик в CapCut по операторскому мосту','count':len(shots),'file':'capcut_operator_bridge.html'})
        critical.append({'title':'Проверить монтажную мастерскую','count':len(shots),'file':'montage_workbench.html'})
        critical.append({'title':'Экспортировать черновик и сделать QC-проход','count':1,'file':'working_state_audit.html'})
        report={
            'project':self.project_id,
            'local_finishable': assets>=10 and len(shots)>=120,
            'assets':assets,
            'shots':len(shots),
            'assigned':assigned,
            'missing':len(missing),
            'coverage_pct':round(assigned/max(len(shots),1)*100,1),
            'critical_actions':critical,
            'next_30_minutes':[x['title'] for x in critical[:3]],
            'expert_status':'Franklin можно довести до чернового монтажа локально. Полная автономность требует live API.'
        }
        (self.export_dir/'local_autopilot_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self._write_md(report)
        self._write_csv(report)
        self.bus.emit('LOCAL_AUTOPILOT_BUILT', {'finishable': report['local_finishable'], 'missing': len(missing)})
        return report

    def _table(self, name):
        return bool(self.db.one('SELECT name FROM sqlite_master WHERE type="table" AND name=?',(name,)))

    def _write_csv(self, report):
        p=self.export_dir/'local_autopilot_tasks.csv'
        with p.open('w', newline='', encoding='utf-8-sig') as f:
            w=csv.writer(f); w.writerow(['Приоритет','Действие','Количество','Файл'])
            for i,a in enumerate(report['critical_actions'],1): w.writerow([i,a['title'],a['count'],a['file']])

    def _write_md(self, r):
        lines=['# ATLAS ZERO · Local Autopilot Franklin','',f"Локальная готовность к завершению чернового монтажа: {'ДА' if r['local_finishable'] else 'НЕТ'}",f"Покрытие: {r['coverage_pct']}%",f"Шотов: {r['shots']}",f"Нужно создать: {r['missing']}",'','## Что делать следующие 30 минут']
        for i,a in enumerate(r['next_30_minutes'],1): lines.append(f"{i}. {a}")
        lines += ['','## Ключевые файлы']
        for a in r['critical_actions']: lines.append(f"- `{a['file']}` — {a['title']}")
        lines += ['','## Экспертный статус',r['expert_status']]
        (self.export_dir/'operator_next_30_minutes.md').write_text('\n'.join(lines), encoding='utf-8')
