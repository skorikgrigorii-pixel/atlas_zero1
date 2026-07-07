from __future__ import annotations
import json
from .database import Database
from .paths import EXPORTS

class FranklinE2ERuntime:
    """Final project-level report: did Franklin really reach a usable handoff?"""
    def __init__(self, db: Database, project_id: str='franklin'):
        self.db=db; self.project_id=project_id; self.export_dir=EXPORTS/project_id; self.export_dir.mkdir(parents=True,exist_ok=True)

    def evaluate(self):
        def one(sql, params=()):
            r=self.db.one(sql,params); return r
        assets=one('SELECT COUNT(*) c FROM assets WHERE project_id=?',(self.project_id,))['c']
        shots=one('SELECT COUNT(*) c FROM shots WHERE project_id=?',(self.project_id,))['c']
        assigned=one('SELECT COUNT(*) c FROM shots WHERE project_id=? AND assigned_asset_id IS NOT NULL',(self.project_id,))['c']
        missing=shots-assigned
        cv=one('SELECT COUNT(*) c, AVG(cinematic_grade) g FROM cv_asset_metadata WHERE project_id=?',(self.project_id,))
        api=one('SELECT COUNT(*) c FROM api_jobs WHERE project_id=?',(self.project_id,))['c'] if one("SELECT name FROM sqlite_master WHERE type='table' AND name='api_jobs'") else 0
        required=['story_engine_runtime.html','native_viewer_pro.html','pipeline_graph.html','pipeline_run_report.html','capcut_operator_bridge.html','FINAL_ASSEMBLY_PACK/index.html']
        artifacts={x:(self.export_dir/x).exists() for x in required}
        local_ready=assets>0 and shots>=100 and assigned>0 and cv['c']>0 and all(artifacts.values())
        score=0
        score += 20 if assets>0 else 0
        score += 20 if shots>=100 else 0
        score += min(25, round((assigned/max(shots,1))*25,2))
        score += 15 if cv['c']>0 else 0
        score += 20 if all(artifacts.values()) else round(sum(artifacts.values())/len(artifacts)*20,2)
        report={'project_id':self.project_id,'score':round(score,2),'local_e2e_ready':bool(local_ready),'assets':assets,'shots':shots,'assigned':assigned,'missing':missing,'cv_assets':cv['c'],'cv_avg_grade':round(cv['g'] or 0,3),'api_jobs':api,'artifacts':artifacts,'next_actions':self._actions(missing, artifacts)}
        (self.export_dir/'franklin_e2e_runtime.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        self._html(report)
        return report

    def _actions(self, missing, artifacts):
        actions=[]
        if missing: actions.append(f'Закрыть {missing} недостающих шотов через генерацию или подбор материалов.')
        for k,v in artifacts.items():
            if not v: actions.append('Пересобрать артефакт: '+k)
        if not actions: actions.append('Franklin готов к локальному handoff: можно переходить в CapCut/монтаж.')
        return actions

    def _html(self, r):
        arts=''.join(f"<li>{k}: {'OK' if v else 'MISSING'}</li>" for k,v in r['artifacts'].items())
        acts=''.join(f'<li>{x}</li>' for x in r['next_actions'])
        html=f"""<!doctype html><meta charset='utf-8'><title>Franklin E2E Runtime</title><style>body{{font-family:Segoe UI,Arial;background:#08111f;color:#eaf2ff;margin:24px}}.card{{background:#101b2d;border:1px solid #334155;border-radius:16px;padding:16px;margin:12px 0}}b{{font-size:28px;color:#38bdf8}}</style><h1>Franklin End-to-End Runtime</h1><div class='card'>Готовность: <b>{r['score']}%</b><br>Local E2E Ready: <b>{'ДА' if r['local_e2e_ready'] else 'НЕТ'}</b></div><div class='card'>Материалы {r['assets']} · Шоты {r['shots']} · Назначено {r['assigned']} · Дефицит {r['missing']} · CV {r['cv_assets']}</div><h2>Артефакты</h2><ul>{arts}</ul><h2>Следующие действия</h2><ul>{acts}</ul>"""
        (self.export_dir/'franklin_e2e_runtime.html').write_text(html,encoding='utf-8')
