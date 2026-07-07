from __future__ import annotations
import json, os, time, urllib.request, urllib.error
from dataclasses import dataclass
from typing import Any
from .database import Database
from .events import EventBus
from .paths import EXPORTS

@dataclass(frozen=True)
class ConnectorSpec:
    service: str
    env_key: str
    base_url: str
    validate_path: str
    auth_header: str
    paid_actions: tuple[str, ...]

SPECS = {
    'Leonardo': ConnectorSpec('Leonardo','LEONARDO_API_KEY','https://cloud.leonardo.ai/api/rest/v1','/me','Authorization',('image_generation','image_to_video')),
    'ElevenLabs': ConnectorSpec('ElevenLabs','ELEVENLABS_API_KEY','https://api.elevenlabs.io/v1','/user','xi-api-key',('text_to_speech',)),
    'OpenAI': ConnectorSpec('OpenAI','OPENAI_API_KEY','https://api.openai.com/v1','/models','Authorization',('chat','vision','embedding')),
    'YouTube': ConnectorSpec('YouTube','YOUTUBE_OAUTH_TOKEN','https://www.googleapis.com/youtube/v3','/channels?part=id&mine=true','Authorization',('analytics','upload')),
    'Suno': ConnectorSpec('Suno','SUNO_API_KEY','https://api.suno.ai','/v1/me','Authorization',('music_generation',)),
    'Canva': ConnectorSpec('Canva','CANVA_API_KEY','https://api.canva.com/rest/v1','/users/me','Authorization',('design_export',)),
}

class LiveConnectorHub:
    """RC1 Alpha 1.8 live API layer.

    This is the first real connector implementation contract. It can validate credentials
    with non-generation endpoint calls when network and keys are available. Paid generation
    remains blocked unless AZ_ENABLE_LIVE_CALLS=1 and AZ_ALLOW_PAID_API=1.
    """
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.bus=EventBus(db, project_id)
        self.export_dir=EXPORTS/project_id; self.export_dir.mkdir(parents=True, exist_ok=True)

    @property
    def live_enabled(self) -> bool:
        return os.getenv('AZ_ENABLE_LIVE_CALLS') == '1'

    @property
    def paid_allowed(self) -> bool:
        return os.getenv('AZ_ALLOW_PAID_API') == '1'

    def _headers(self, spec: ConnectorSpec) -> dict[str,str]:
        key=os.getenv(spec.env_key,'')
        if spec.service in ('Leonardo','OpenAI','YouTube','Suno','Canva'):
            return {spec.auth_header: f'Bearer {key}', 'Accept':'application/json'}
        if spec.service == 'ElevenLabs':
            return {spec.auth_header: key, 'Accept':'application/json'}
        return {}

    def validate_service(self, service: str, timeout: int=8) -> dict[str,Any]:
        spec=SPECS[service]
        key_present=bool(os.getenv(spec.env_key))
        result={'service':service,'env_key':spec.env_key,'credential_present':key_present,'live_enabled':self.live_enabled,'status':'not_checked','http_status':None,'error':None}
        if not key_present:
            result['status']='missing_credential'
        elif not self.live_enabled:
            result['status']='credential_present_live_disabled'
        else:
            try:
                url=spec.base_url + spec.validate_path
                req=urllib.request.Request(url, headers=self._headers(spec), method='GET')
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    result['http_status']=resp.status
                    result['status']='validated' if 200 <= resp.status < 300 else 'reachable'
            except urllib.error.HTTPError as e:
                result['http_status']=e.code
                result['status']='auth_failed_or_endpoint_reachable' if e.code in (401,403,404) else 'http_error'
                result['error']=str(e)
            except Exception as e:
                result['status']='network_unavailable_or_endpoint_error'
                result['error']=str(e)
        self.db.execute('INSERT INTO integration_runs(project_id,service,mode,status,request_json,response_json) VALUES(?,?,?,?,?,?)',
                        (self.project_id, service, 'live_validate', result['status'], json.dumps({'validate_path':spec.validate_path}, ensure_ascii=False), json.dumps(result, ensure_ascii=False)))
        return result

    def validate_all(self) -> dict[str,Any]:
        rows=[self.validate_service(s) for s in SPECS]
        ready=sum(1 for r in rows if r['status'] in ('validated','reachable','auth_failed_or_endpoint_reachable'))
        usable=sum(1 for r in rows if r['credential_present'] and r['live_enabled'])
        summary={'services':len(rows),'validated_or_reachable':ready,'credential_live_enabled':usable,'paid_allowed':self.paid_allowed,'rows':rows}
        self.bus.emit('LIVE_CONNECTORS_VALIDATED', {k:v for k,v in summary.items() if k!='rows'})
        return summary

    def plan_generation_payload(self, service: str, job_type: str, prompt: str, metadata: dict|None=None) -> dict[str,Any]:
        spec=SPECS[service]
        paid_risk=job_type in spec.paid_actions
        status='ready_to_submit'
        if paid_risk and not self.paid_allowed:
            status='blocked_paid_confirmation_required'
        if not self.live_enabled:
            status='blocked_live_disabled'
        if not os.getenv(spec.env_key):
            status='blocked_missing_credential'
        payload={'service':service,'job_type':job_type,'prompt':prompt,'metadata':metadata or {},'paid_risk':paid_risk,'status':status,'created_at':time.time()}
        self.db.execute('INSERT INTO integration_runs(project_id,service,mode,status,request_json,response_json) VALUES(?,?,?,?,?,?)',
                        (self.project_id, service, 'generation_payload', status, json.dumps(payload, ensure_ascii=False), json.dumps({'status':status}, ensure_ascii=False)))
        return payload

    def export_report(self) -> dict[str,Any]:
        report=self.validate_all()
        p=self.export_dir/'live_connectors_report.json'
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        md=self.export_dir/'live_connectors_setup_ru.md'
        lines=['# Live API connectors RC1 Alpha 1.8','', 'Безопасность:', '- `AZ_ENABLE_LIVE_CALLS=1` включает сетевые проверки.', '- `AZ_ALLOW_PAID_API=1` дополнительно разрешает платные действия.', '', 'Сервисы:']
        for r in report['rows']:
            lines.append(f"- {r['service']}: `{r['env_key']}` → {r['status']}")
        md.write_text('\n'.join(lines), encoding='utf-8')
        return {'json':str(p),'guide':str(md),'summary':{k:v for k,v in report.items() if k!='rows'}}
