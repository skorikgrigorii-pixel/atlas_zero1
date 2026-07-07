from __future__ import annotations
import os, json, urllib.request, urllib.error
from pathlib import Path
from .paths import EXPORTS


def load_env_file():
    """Small .env loader: does not require python-dotenv."""
    candidates = []
    try:
        from .paths import ROOT
        candidates.append(ROOT / '.env')
    except Exception:
        pass
    candidates.append(Path.cwd() / '.env')
    for p in candidates:
        if p.exists():
            for line in p.read_text(encoding='utf-8', errors='ignore').splitlines():
                line=line.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                k,v=line.split('=',1)
                k=k.strip(); v=v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k]=v

SERVICES = {
    'OpenAI': {'env':'OPENAI_API_KEY','url':'https://api.openai.com/v1/models','paid': False},
    'ElevenLabs': {'env':'ELEVENLABS_API_KEY','url':'https://api.elevenlabs.io/v1/user','paid': False},
    'YouTube': {'env':'YOUTUBE_API_KEY','url':'https://www.googleapis.com/youtube/v3/channels?part=id&mine=true','paid': False},
    'Leonardo': {'env':'LEONARDO_API_KEY','url':'https://cloud.leonardo.ai/api/rest/v1/me','paid': False},
    'Suno': {'env':'SUNO_API_KEY','url':None,'paid': False},
    'Canva': {'env':'CANVA_API_KEY','url':None,'paid': False},
}

class LiveApiTestSuite:
    """Safe live readiness tester.

    It never runs paid generation. Network calls are only executed when
    AZ_ENABLE_LIVE_API=1. Otherwise it produces a readiness report from env keys.
    """
    def __init__(self, db, project_id='franklin'):
        self.db = db
        self.project_id = project_id
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _request(self, service, spec):
        key = os.getenv(spec['env'], '')
        if not key:
            return {'service':service,'status':'not_configured','env':spec['env'],'detail':'ключ отсутствует'}
        if os.getenv('AZ_ENABLE_LIVE_API') != '1':
            return {'service':service,'status':'credential_found_dry','env':spec['env'],'detail':'ключ найден; live-проверка выключена'}
        if not spec.get('url'):
            return {'service':service,'status':'manual_live_test_required','env':spec['env'],'detail':'нет безопасного read-only endpoint'}
        try:
            headers = {'Authorization': f'Bearer {key}'}
            if service == 'ElevenLabs': headers = {'xi-api-key': key}
            req = urllib.request.Request(spec['url'], headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {'service':service,'status':'reachable','env':spec['env'],'http_status':resp.status,'detail':'read-only live check ok'}
        except Exception as e:
            return {'service':service,'status':'error','env':spec['env'],'detail':str(e)[:240]}

    def run(self):
        load_env_file()
        rows = [self._request(s, spec) for s, spec in SERVICES.items()]
        configured = sum(1 for r in rows if r['status'] in ('credential_found_dry','reachable','manual_live_test_required'))
        reachable = sum(1 for r in rows if r['status'] == 'reachable')
        report = {
            'mode': 'live' if os.getenv('AZ_ENABLE_LIVE_API') == '1' else 'dry_safe',
            'configured': configured,
            'reachable': reachable,
            'services_total': len(rows),
            'paid_calls_allowed': os.getenv('AZ_ALLOW_PAID_CALLS') == '1',
            'rows': rows,
            'ready_for_live_generation': os.getenv('AZ_ENABLE_LIVE_API') == '1' and configured >= 4,
            'note': 'Платные операции не запускаются без AZ_ALLOW_PAID_CALLS=1.'
        }
        p = self.export_dir/'live_api_test_suite.json'
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        html_rows=''.join(f"<tr><td>{r['service']}</td><td>{r['status']}</td><td>{r['env']}</td><td>{r.get('detail','')}</td></tr>" for r in rows)
        html=f"""<!doctype html><meta charset='utf-8'><title>Live API Test Suite</title>
<style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e5e7eb;font-size:13px}}table{{width:100%;border-collapse:collapse}}td,th{{border-bottom:1px solid #334155;padding:8px}}.card{{background:#111827;border-radius:12px;padding:14px;margin:12px}}</style>
<h1>ATLAS ZERO — Live API Test Suite</h1><div class='card'>Режим: <b>{report['mode']}</b><br>Сконфигурировано: {configured}/{len(rows)}<br>Reachable: {reachable}<br>{report['note']}</div><table><tr><th>Сервис</th><th>Статус</th><th>ENV</th><th>Деталь</th></tr>{html_rows}</table>"""
        (self.export_dir/'live_api_test_suite.html').write_text(html, encoding='utf-8')
        try:
            self.db.execute('INSERT INTO workflow_jobs(project_id,stage,status,details) VALUES(?,?,?,?)', (self.project_id,'live_api_test_suite','done',json.dumps(report, ensure_ascii=False)))
        except Exception:
            pass
        return report
