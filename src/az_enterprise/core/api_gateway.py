from __future__ import annotations
import os, json, time
from .database import Database
from .events import EventBus
from .integrations import SERVICES

class ApiGateway:
    """RC1 Alpha 0.9 live-readiness gateway.

    This module does not spend paid credits by default. It validates environment keys,
    creates normalized service health records and exposes a single contract for future
    live adapters. External calls remain guarded by AZ_ENABLE_LIVE_CALLS=1.
    """
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.bus=EventBus(db, project_id)

    def check_credentials(self) -> dict:
        self.db.execute('DELETE FROM api_credentials_checks WHERE project_id=?', (self.project_id,))
        ready=0; guarded=0; missing=0; local=0
        rows=[]
        for service,(env_key,caps,endpoint) in SERVICES.items():
            value=os.getenv(env_key)
            detail={'env_key':env_key,'endpoint':endpoint,'capabilities':caps,'live_enabled':os.getenv('AZ_ENABLE_LIVE_CALLS')=='1'}
            if endpoint == 'local_exchange':
                if value and os.path.exists(value): status='connected'; ready+=1; local+=1
                elif value: status='configured_path_missing'; guarded+=1
                else: status='missing'; missing+=1
            else:
                if value:
                    status='credential_found_guarded' if os.getenv('AZ_ENABLE_LIVE_CALLS')!='1' else 'credential_found_live_allowed'
                    ready += 1
                    if os.getenv('AZ_ENABLE_LIVE_CALLS')!='1': guarded += 1
                else:
                    status='missing'; missing += 1
            rows.append({'service':service,'status':status,**detail})
            self.db.execute('INSERT INTO api_credentials_checks(project_id,service,status,detail_json) VALUES(?,?,?,?)',
                            (self.project_id,service,status,json.dumps(detail,ensure_ascii=False)))
        summary={'services':len(SERVICES),'ready_or_configured':ready,'guarded':guarded,'missing':missing,'local_connected':local,'live_enabled':os.getenv('AZ_ENABLE_LIVE_CALLS')=='1','rows':rows}
        self.bus.emit('API_GATEWAY_CHECKED', {k:v for k,v in summary.items() if k!='rows'})
        return summary

    def readiness_score(self) -> float:
        r=self.check_credentials()
        # Local exchange and guarded credentials are partial readiness; missing live services remain blockers.
        base=(r['ready_or_configured']/max(r['services'],1))*100
        if not r['live_enabled']:
            base=min(base,72)
        return round(base,1)
