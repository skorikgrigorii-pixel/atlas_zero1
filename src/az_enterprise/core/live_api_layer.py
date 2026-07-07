from __future__ import annotations
import json, os, time, urllib.request, urllib.error
from dataclasses import dataclass
from typing import Any
from .database import Database
from .events import EventBus

@dataclass(frozen=True)
class LiveServiceContract:
    service: str
    env_key: str
    base_url: str
    primary_action: str
    paid_risk: str
    can_validate_without_spend: bool = True

CONTRACTS = {
    'Leonardo': LiveServiceContract('Leonardo','LEONARDO_API_KEY','https://cloud.leonardo.ai/api/rest/v1','generate_image','paid_generation'),
    'ElevenLabs': LiveServiceContract('ElevenLabs','ELEVENLABS_API_KEY','https://api.elevenlabs.io/v1','text_to_speech','paid_generation'),
    'OpenAI': LiveServiceContract('OpenAI','OPENAI_API_KEY','https://api.openai.com/v1','vision_and_reasoning','paid_request'),
    'YouTube': LiveServiceContract('YouTube','YOUTUBE_OAUTH_TOKEN','https://www.googleapis.com/youtube/v3','analytics_and_upload','oauth_request'),
    'Suno': LiveServiceContract('Suno','SUNO_API_KEY','https://api.suno.ai','music_generation','paid_generation'),
    'Canva': LiveServiceContract('Canva','CANVA_API_KEY','https://api.canva.com/rest/v1','design_assets','oauth_request'),
}

class LiveApiLayer:
    """Safe live API layer for RC1.

    Default mode is guarded. It never spends credits unless both are true:
    1) AZ_ENABLE_LIVE_CALLS=1
    2) explicit method receives allow_paid=True.

    This makes it usable for integration testing without accidental paid jobs.
    """
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.bus=EventBus(db, project_id)

    @property
    def live_enabled(self) -> bool:
        return os.getenv('AZ_ENABLE_LIVE_CALLS') == '1'

    def inspect(self) -> dict[str, Any]:
        rows=[]
        for c in CONTRACTS.values():
            key=os.getenv(c.env_key)
            status='missing'
            if key and self.live_enabled:
                status='live_ready_guarded_paid'
            elif key:
                status='credential_present_live_disabled'
            rows.append({
                'service': c.service,
                'env_key': c.env_key,
                'credential_present': bool(key),
                'live_enabled': self.live_enabled,
                'primary_action': c.primary_action,
                'paid_risk': c.paid_risk,
                'status': status,
                'base_url': c.base_url,
            })
        summary={
            'services': len(rows),
            'credentials_present': sum(1 for r in rows if r['credential_present']),
            'live_enabled': self.live_enabled,
            'paid_generation_blocked_by_default': True,
            'rows': rows,
        }
        self.bus.emit('LIVE_API_LAYER_INSPECTED', {k:v for k,v in summary.items() if k!='rows'})
        return summary

    def validate_http_health(self, service: str, timeout: int = 5) -> dict[str, Any]:
        """Optional non-paid health call. Network may be unavailable; failures are logged, not fatal."""
        c = CONTRACTS[service]
        if not os.getenv(c.env_key):
            return {'service': service, 'status': 'missing_credential'}
        if not self.live_enabled:
            return {'service': service, 'status': 'live_disabled', 'detail': 'Set AZ_ENABLE_LIVE_CALLS=1 to validate live endpoint.'}
        try:
            req=urllib.request.Request(c.base_url, method='GET')
            # headers differ by vendor; this health call is intentionally generic and may return 401/404.
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {'service': service, 'status': 'reachable', 'http_status': resp.status}
        except urllib.error.HTTPError as e:
            # 401/403 still proves endpoint is reachable; auth validation is service-specific.
            return {'service': service, 'status': 'reachable_http_error', 'http_status': e.code}
        except Exception as e:
            return {'service': service, 'status': 'unreachable', 'error': str(e)}

    def guarded_execute(self, service: str, payload: dict[str, Any], allow_paid: bool=False) -> dict[str, Any]:
        c=CONTRACTS[service]
        record={
            'service': service,
            'payload_preview': payload,
            'live_enabled': self.live_enabled,
            'allow_paid': allow_paid,
            'paid_risk': c.paid_risk,
        }
        if not os.getenv(c.env_key):
            status='blocked_missing_credential'
        elif not self.live_enabled:
            status='blocked_live_disabled'
        elif c.paid_risk.startswith('paid') and not allow_paid:
            status='blocked_paid_confirmation_required'
        else:
            # RC1 Alpha does not execute paid generation yet; it emits a ready-to-send contract.
            status='ready_for_adapter_execution'
        self.db.execute('INSERT INTO integration_runs(project_id,service,mode,status,request_json,response_json) VALUES(?,?,?,?,?,?)',
                        (self.project_id, service, 'guarded_live', status, json.dumps(record,ensure_ascii=False), json.dumps({'status':status},ensure_ascii=False)))
        self.bus.emit('LIVE_API_GUARDED_EXECUTION', {'service': service, 'status': status})
        return {'service': service, 'status': status, 'contract': record}

    def export_report(self, export_dir) -> dict[str, Any]:
        report=self.inspect()
        path=export_dir/'live_api_layer_report.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        md=export_dir/'live_api_setup_ru.md'
        lines=['# Настройка live API для ATLAS ZERO Enterprise RC1','', 'По умолчанию ОС не делает платные запросы. Для live-режима нужны переменные окружения:','']
        for r in report['rows']:
            lines.append(f"## {r['service']}")
            lines.append(f"ENV: `{r['env_key']}`")
            lines.append(f"Действие: {r['primary_action']}")
            lines.append(f"Статус: {r['status']}")
            lines.append('')
        lines.append('Для включения live-проверок установите `AZ_ENABLE_LIVE_CALLS=1`. Платные генерации всё равно требуют отдельного подтверждения allow_paid=True в коде адаптера.')
        md.write_text('\n'.join(lines), encoding='utf-8')
        return {'json': str(path), 'guide': str(md), 'credentials_present': report['credentials_present']}
