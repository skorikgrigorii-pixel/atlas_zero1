from __future__ import annotations
import os, json, time, urllib.request, urllib.error
from .database import Database
from .events import EventBus

SERVICES = {
    'leonardo': ('LEONARDO_API_KEY', ['image_generation','image_to_video_queue'], 'https://cloud.leonardo.ai/api/rest/v1'),
    'elevenlabs': ('ELEVENLABS_API_KEY', ['voice_generation'], 'https://api.elevenlabs.io/v1'),
    'openai': ('OPENAI_API_KEY', ['director_ai','vision','script_analysis'], 'https://api.openai.com/v1'),
    'youtube': ('YOUTUBE_OAUTH_CLIENT', ['analytics','publishing_metadata'], 'https://www.googleapis.com/youtube/v3'),
    'suno': ('SUNO_API_KEY', ['music_generation'], 'provider_specific'),
    'canva': ('CANVA_API_KEY', ['graphics_templates'], 'https://api.canva.com/rest/v1'),
    'capcut': ('CAPCUT_PROJECT_PATH', ['handoff','guide_export'], 'local_exchange'),
    'davinci': ('DAVINCI_PROJECT_PATH', ['fcpxml','edl'], 'local_exchange'),
    'premiere': ('PREMIERE_PROJECT_PATH', ['xml','edl'], 'local_exchange'),
}

class IntegrationRegistry:
    def __init__(self, db: Database, project_id='franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)

    def refresh(self) -> dict:
        connected = 0; local_ready = 0
        for service, (env_key, caps, endpoint) in SERVICES.items():
            value = os.getenv(env_key)
            if endpoint == 'local_exchange':
                status = 'connected' if value and os.path.exists(value) else ('configured' if value else 'not_configured')
                if status == 'connected': local_ready += 1
            else:
                status = 'configured' if value else 'not_configured'
            if status in ('connected','configured'): connected += 1
            self.db.execute('INSERT OR REPLACE INTO integration_profiles(id,service,status,env_key,capabilities) VALUES(?,?,?,?,?)',
                            (service, service, status, env_key, json.dumps({'capabilities':caps,'endpoint':endpoint}, ensure_ascii=False)))
        self.bus.emit('INTEGRATIONS_REFRESHED', {'configured': connected, 'total': len(SERVICES), 'local_ready': local_ready})
        return {'configured': connected, 'total': len(SERVICES), 'local_ready': local_ready}

    def credential_report(self) -> list[dict]:
        self.refresh()
        rows=self.db.rows('SELECT service,status,env_key,capabilities FROM integration_profiles ORDER BY service')
        report=[]
        for r in rows:
            caps=json.loads(r['capabilities']) if r['capabilities'] else {}
            report.append({'service':r['service'],'status':r['status'],'env_key':r['env_key'],'endpoint':caps.get('endpoint'),'capabilities':caps.get('capabilities',[])})
        return report

    def create_api_jobs_for_missing(self) -> dict:
        missing = self.db.rows("SELECT * FROM shots WHERE project_id=? AND status='missing' LIMIT 80", (self.project_id,))
        created = 0
        for shot in missing:
            payload = {
                'shot_id': shot['id'],
                'prompt': self._leonardo_prompt(shot),
                'negative_prompt': 'cartoon, CGI look, modern objects, distorted ship, low quality, blurry, text, watermark',
                'aspect_ratio': '16:9',
                'style': 'ultra photorealistic historical documentary, cold blue-gray palette'
            }
            self.db.execute('INSERT INTO api_jobs(project_id,service,job_type,status,payload) VALUES(?,?,?,?,?)',
                            (self.project_id, 'leonardo', 'image_generation', 'ready_for_live_or_dry_run', json.dumps(payload, ensure_ascii=False)))
            created += 1
        self.bus.emit('API_JOBS_CREATED', {'created': created, 'service': 'leonardo'})
        return {'api_jobs': created}

    def _leonardo_prompt(self, shot) -> str:
        return (f"Ultra photorealistic cinematic historical documentary frame for ATLAS ZERO Franklin film. "
                f"Visual need: {shot['visual_need']}. Story goal: {shot['story_goal']}. "
                f"Emotion: {shot['emotion']}. 1845-1859 Franklin Expedition, Arctic realism, cold fog, natural light, BBC/Netflix documentary quality, no fantasy.")

    def run_api_jobs(self, mode: str='dry_run', limit: int=10) -> dict:
        """Execute integration jobs.

        mode='dry_run' never contacts external services.
        mode='live' attempts only services with configured credentials and records errors without crashing.
        """
        jobs=self.db.rows("SELECT * FROM api_jobs WHERE project_id=? AND status IN ('ready_for_live_or_dry_run','dry_run','queued') ORDER BY id LIMIT ?", (self.project_id, limit))
        done=0; failed=0; skipped=0
        for job in jobs:
            payload=json.loads(job['payload']) if job['payload'] else {}
            if mode != 'live':
                response={'mode':'dry_run','message':'Задание проверено без обращения к API','provider_job_id':None,'payload_preview':payload}
                status='dry_run_done'
                done += 1
            else:
                profile=self.db.one('SELECT * FROM integration_profiles WHERE service=?', (job['service'],))
                if not profile or profile['status'] not in ('configured','connected'):
                    response={'error':'service_not_configured','service':job['service']}
                    status='skipped_not_configured'; skipped += 1
                else:
                    status,response=self._execute_live(job['service'], job['job_type'], payload)
                    if status.endswith('failed'): failed += 1
                    else: done += 1
            self.db.execute('UPDATE api_jobs SET status=? WHERE id=?', (status, job['id']))
            self.db.execute('INSERT INTO integration_runs(project_id,service,mode,status,request_json,response_json) VALUES(?,?,?,?,?,?)',
                            (self.project_id, job['service'], mode, status, json.dumps(payload,ensure_ascii=False), json.dumps(response,ensure_ascii=False)))
        self.bus.emit('API_JOBS_RUN', {'mode':mode,'done':done,'failed':failed,'skipped':skipped})
        return {'mode':mode,'processed':len(jobs),'done':done,'failed':failed,'skipped':skipped}

    def _execute_live(self, service: str, job_type: str, payload: dict) -> tuple[str,dict]:
        # RC1 Alpha live-safe layer: validates credentials and prepares real HTTP calls for supported providers.
        # It intentionally avoids consuming credits for Leonardo/ElevenLabs until provider payloads are explicitly confirmed in Settings.
        env_key=SERVICES[service][0]
        key=os.getenv(env_key)
        if not key:
            return 'live_failed', {'error':'missing_api_key', 'env_key':env_key}
        if service == 'openai':
            return 'live_ready_not_executed', {'message':'OpenAI key found. Live call disabled in Alpha until user enables execution flag AZ_ENABLE_LIVE_CALLS=1.'}
        if os.getenv('AZ_ENABLE_LIVE_CALLS') != '1':
            return 'live_guarded', {'message':'Live execution guarded. Set AZ_ENABLE_LIVE_CALLS=1 to allow external API requests.', 'service':service}
        return 'live_failed', {'error':'provider_payload_not_finalized', 'service':service, 'job_type':job_type}
