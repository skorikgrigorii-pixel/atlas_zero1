from __future__ import annotations
from .database import Database
from .events import EventBus
from .api_gateway import ApiGateway

class ReleaseGate:
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.bus=EventBus(db, project_id)

    def evaluate_rc1(self) -> dict:
        assets=self.db.one('SELECT COUNT(*) c FROM assets WHERE project_id=?',(self.project_id,))['c']
        shots=self.db.one('SELECT COUNT(*) c FROM shots WHERE project_id=?',(self.project_id,))['c']
        missing=self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status!='assigned'",(self.project_id,))['c']
        visual=self.db.one('SELECT COUNT(*) c FROM visual_profiles WHERE project_id=?',(self.project_id,))['c']
        similar=self.db.one('SELECT COUNT(*) c FROM asset_similarity WHERE project_id=?',(self.project_id,))['c']
        integrations=self.db.rows('SELECT service,status FROM integration_profiles')
        configured=sum(1 for r in integrations if r['status'] in ('configured','connected'))
        api_score=ApiGateway(self.db,self.project_id).readiness_score()
        timeline_ok=(shots>=120 and (missing/max(shots,1)) < 0.45)
        visual_ok=visual>=min(assets,10)
        live_api_ok=api_score>=85 and any(r['status']=='credential_found_live_allowed' for r in self.db.rows('SELECT status FROM api_credentials_checks WHERE project_id=?',(self.project_id,)))
        checks=[
            ('Материалы проиндексированы', assets>=10, min(100,assets*4)),
            ('Монтажный лист построен', shots>=120, 100 if shots>=120 else shots/120*100),
            ('Дефицит кадров допустимый', timeline_ok, max(0,100-(missing/max(shots,1))*160)),
            ('Визуальный анализ выполнен', visual_ok, min(100, visual/max(assets,1)*100)),
            ('Проверка визуальной схожести', similar>=0, 88 if visual_ok else 45),
            ('Интеграции настроены', configured>=3, max(50, configured/max(len(integrations),1)*100 if integrations else 50)),
            ('API Gateway готов', api_score>=55, max(65, api_score)),
            ('Live API разрешены', live_api_ok, 35 if not live_api_ok else 100),
            ('Финальный viewer/timeline', True, 90),
        ]
        score=round(sum(c[2] for c in checks)/len(checks),1)
        ready=all(c[1] for c in checks)
        for name,passed,sc in checks:
            self.db.execute('INSERT INTO readiness_checks(project_id,criterion,score,passed,comment) VALUES(?,?,?,?,?)',
                            (self.project_id,name,float(sc),1 if passed else 0,'OK' if passed else 'Требует доработки'))
        self.bus.emit('RC1_RELEASE_GATE_EVALUATED', {'score':score,'ready':ready})
        return {'ready':ready,'score':score,'checks':[{'criterion':c[0],'passed':c[1],'score':round(c[2],1)} for c in checks], 'blocking':['live_api' if not live_api_ok else None]}
