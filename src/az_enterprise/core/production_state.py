from __future__ import annotations
import json
from .database import Database
from .events import EventBus

class ProductionState:
    """Enterprise RC1 production state aggregator.

    Converts raw database objects into operational studio decisions:
    what is blocked, what is next, what can be automated, and what still
    prevents full production readiness.
    """
    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)

    def summarize(self) -> dict:
        assets = self._count('assets')
        shots = self._count('shots')
        assigned = self._scalar("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status='assigned'", 0)
        missing = self._scalar("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status!='assigned'", 0)
        api_ready = self._scalar("SELECT COUNT(*) c FROM api_jobs WHERE project_id=? AND status IN ('ready_for_live_or_dry_run','queued','dry_run')", 0)
        visual = self._count('visual_profiles')
        latest_qc = self.db.one('SELECT readiness,summary FROM quality_reports WHERE project_id=? ORDER BY id DESC LIMIT 1', (self.project_id,))
        latest_gate = self.db.rows('SELECT criterion,score,passed,comment FROM readiness_checks WHERE project_id=? ORDER BY id DESC LIMIT 12', (self.project_id,))
        blockers = self.blockers(latest_gate, missing, shots)
        next_actions = self.next_actions(blockers, api_ready)
        result = {
            'project_id': self.project_id,
            'assets': assets,
            'shots': shots,
            'assigned': assigned,
            'missing': missing,
            'coverage_pct': round(assigned / max(shots, 1) * 100, 1),
            'visual_profiles': visual,
            'api_jobs_ready': api_ready,
            'qc_readiness': float(latest_qc['readiness']) if latest_qc else 0.0,
            'blockers': blockers,
            'next_actions': next_actions,
            'full_work_ready': False if blockers else True,
        }
        self.bus.emit('PRODUCTION_STATE_SUMMARIZED', result)
        return result

    def blockers(self, gate_rows, missing: int, shots: int) -> list[dict]:
        blockers = []
        for r in gate_rows:
            if not r['passed']:
                blockers.append({'type': 'release_gate', 'title': r['criterion'], 'score': round(float(r['score']),1), 'comment': r['comment']})
        ratio = missing / max(shots, 1)
        if ratio > 0.30:
            blockers.append({'type': 'coverage', 'title': 'Высокий дефицит видеоряда', 'score': round((1-ratio)*100,1), 'comment': f'Нужно закрыть {missing} шотов.'})
        # explicit RC1 blockers agreed in the project conversation
        blockers.append({'type': 'live_api', 'title': 'Live API ещё не включены', 'score': 0, 'comment': 'Нужны реальные ключи и подтверждение платных вызовов.'})
        blockers.append({'type': 'cv_model', 'title': 'Полная CV-модель не подключена', 'score': 45, 'comment': 'Сейчас используется локальный эвристический анализ, не полноценное зрение.'})
        return blockers

    def next_actions(self, blockers: list[dict], api_ready: int) -> list[str]:
        actions=[]
        if api_ready:
            actions.append(f'Проверить очередь генерации: {api_ready} заданий готовы к dry-run/live.')
        for b in blockers[:5]:
            if b['type']=='live_api':
                actions.append('Подключить ключи Leonardo / ElevenLabs / OpenAI / YouTube через .env.')
            elif b['type']=='cv_model':
                actions.append('Подключить Vision-модель и пересчитать визуальные профили ассетов.')
            elif b['type']=='coverage':
                actions.append('Закрыть недостающие шоты через Leonardo/Kling или вручную добавить материалы.')
            else:
                actions.append(f"Закрыть блокер: {b['title']}.")
        if not actions:
            actions.append('Запустить финальный RC1 acceptance test.')
        return actions

    def _count(self, table: str) -> int:
        row = self.db.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not row: return 0
        if table in ('assets','shots','visual_profiles'):
            return self.db.one(f'SELECT COUNT(*) c FROM {table} WHERE project_id=?', (self.project_id,))['c']
        return self.db.one(f'SELECT COUNT(*) c FROM {table}')['c']

    def _scalar(self, sql: str, default=0):
        try:
            row = self.db.one(sql, (self.project_id,))
            return row['c'] if row else default
        except Exception:
            return default
