from __future__ import annotations
import json
from collections import defaultdict
from typing import Any

from .database import Database
from .events import EventBus
from .story_engine_runtime import StoryEngineRuntime
from .director_ai_runtime import DirectorAIRuntime


PRODUCTION_STAGES = [
    'NEW',
    'RESEARCH_READY',
    'SCRIPT_READY',
    'VOICE_READY',
    'VISUAL_READY',
    'EDIT_READY',
    'PACKAGING_READY',
    'FINAL_READY',
]

STAGE_LABELS = {
    'NEW': 'Project created',
    'RESEARCH_READY': 'Research complete',
    'SCRIPT_READY': 'Script ready',
    'VOICE_READY': 'Voice assets ready',
    'VISUAL_READY': 'Visual assets ready',
    'EDIT_READY': 'Edit ready',
    'PACKAGING_READY': 'Packaging ready',
    'FINAL_READY': 'Final package ready',
    'FAILED': 'Failed',
}

NEXT_STAGE_RULES = {
    'NEW': ['RESEARCH_READY'],
    'RESEARCH_READY': ['SCRIPT_READY'],
    'SCRIPT_READY': ['VOICE_READY'],
    'VOICE_READY': ['VISUAL_READY'],
    'VISUAL_READY': ['EDIT_READY'],
    'EDIT_READY': ['PACKAGING_READY'],
    'PACKAGING_READY': ['FINAL_READY'],
}


class DirectorAI:
    def __init__(self, db: Database, project_id='franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)
        self.usage = defaultdict(int)
        self._ensure_state_schema()
        self._ensure_task_schema()
        self._initialize_project_state()

    def _ensure_state_schema(self) -> None:
        self.db.conn.executescript('''
        CREATE TABLE IF NOT EXISTS director_project_state(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          current_stage TEXT NOT NULL DEFAULT 'NEW',
          completion_percent REAL NOT NULL DEFAULT 0,
          overall_status TEXT NOT NULL DEFAULT 'PENDING',
          next_required_action TEXT,
          blocking_reason TEXT,
          estimated_completion TEXT,
          details TEXT,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS director_project_history(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          action TEXT NOT NULL,
          from_stage TEXT,
          to_stage TEXT,
          reason TEXT,
          details TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS director_project_modules(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          module_name TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'failed',
          error_message TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        self.db.conn.commit()
        self._ensure_project_columns()

    def _ensure_project_columns(self) -> None:
        existing = {row[1] for row in self.db.conn.execute('PRAGMA table_info(projects)')}
        for column_name, definition in {
            'current_stage': 'TEXT DEFAULT "NEW"',
            'completion_percent': 'REAL DEFAULT 0',
            'overall_status': 'TEXT DEFAULT "PENDING"',
            'next_required_action': 'TEXT',
            'blocking_reason': 'TEXT',
            'estimated_completion': 'TEXT',
            'state_details': 'TEXT',
        }.items():
            if column_name not in existing:
                self.db.execute(f'ALTER TABLE projects ADD COLUMN {column_name} {definition}')

    def _ensure_task_schema(self) -> None:
        self.db.conn.executescript('''
        CREATE TABLE IF NOT EXISTS director_tasks(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          task_uid TEXT NOT NULL,
          task_type TEXT NOT NULL,
          priority INTEGER NOT NULL DEFAULT 3,
          status TEXT NOT NULL DEFAULT 'queued',
          service TEXT,
          scene_id TEXT,
          shot_id TEXT,
          asset_id TEXT,
          title TEXT NOT NULL,
          prompt TEXT,
          payload_json TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS operator_tasks(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          priority INTEGER NOT NULL DEFAULT 3,
          title TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open',
          owner TEXT DEFAULT 'operator',
          details TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        self.db.conn.commit()

    def _initialize_project_state(self) -> None:
        self.db.execute("INSERT OR IGNORE INTO projects(id, title, status) VALUES(?,?,?)", (self.project_id, self.project_id, 'active'))
        self.db.execute("UPDATE projects SET status=? WHERE id=?", ('active', self.project_id))
        current_stage = self.db.one("SELECT current_stage FROM projects WHERE id=?", (self.project_id,))
        if not current_stage or not current_stage['current_stage']:
            self._persist_state('NEW', 'Project initialized', 'Director AI initialized the production state model.')

    def _score(self, shot, asset):
        need = (shot['visual_need'] or '').lower().split()
        raw_tags = asset['tags'] or '[]'
        try:
            tags = json.loads(raw_tags)
        except (TypeError, ValueError):
            tags = [item.strip("'\"") for item in str(raw_tags).strip('[]').split(',') if item.strip()]
        if not isinstance(tags, list):
            tags = [str(tags)]
        hay = ' '.join([asset['filename'].lower(), asset['category'] or '', asset['emotion'] or '', ' '.join(tags)])
        match = sum(1 for w in need if w in hay)
        score = float(asset['quality'] or 0) + match * 0.18
        if shot['emotion'] and shot['emotion'] == asset['emotion']:
            score += 0.12
        if self.usage[asset['id']] >= 4:
            score -= 0.4
        if asset['duplicate_of']:
            score -= 0.25
        return round(max(score, 0), 4)

    def assign_assets(self) -> dict:
        self.db.execute('DELETE FROM director_decisions WHERE project_id=?', (self.project_id,))
        shots = self.db.rows('SELECT * FROM shots WHERE project_id=? ORDER BY idx', (self.project_id,))
        assets = self.db.rows("SELECT * FROM assets WHERE project_id=? AND media_type IN ('image','video')", (self.project_id,))
        assigned = 0
        missing = 0
        self.usage.clear()
        used_asset_ids: set[str] = set()
        for shot in shots:
            available_assets = [a for a in assets if a['id'] not in used_asset_ids]
            ranked = sorted(((self._score(shot,a), a) for a in available_assets), key=lambda x: x[0], reverse=True)
            if ranked and ranked[0][0] >= 0.62:
                score, asset = ranked[0]
                self.usage[asset['id']] += 1
                used_asset_ids.add(asset['id'])
                reason = f"Выбран материал '{asset['filename']}' для потребности '{shot['visual_need']}'. Совпадение по тегам/эмоции, качество={asset['quality']}. Использований={self.usage[asset['id']]}"
                alternatives = [r[1]['filename'] for r in ranked[1:4]]
                self.db.execute('UPDATE shots SET assigned_asset_id=?, status=? WHERE id=?', (asset['id'], 'assigned', shot['id']))
                self.db.execute('INSERT INTO director_decisions(project_id,shot_id,asset_id,score,reason,alternatives) VALUES(?,?,?,?,?,?)',
                                (self.project_id, shot['id'], asset['id'], score, reason, json.dumps(alternatives, ensure_ascii=False)))
                assigned += 1
            else:
                prompt = f"Нужен материал: {shot['visual_need']}. История: {shot['story_goal']}. Эмоция: {shot['emotion']}. Стиль: cold blue cinematic historical documentary."
                self.db.execute('UPDATE shots SET assigned_asset_id=NULL, status=? WHERE id=?', ('missing', shot['id']))
                self.db.execute('INSERT INTO director_decisions(project_id,shot_id,asset_id,score,reason,alternatives) VALUES(?,?,?,?,?,?)',
                                (self.project_id, shot['id'], None, 0, 'Подходящий материал не найден. Создать через генерацию.', prompt))
                missing += 1

        analysis = self._analyze_completeness()
        task_count = self.db.one('SELECT COUNT(*) c FROM director_tasks WHERE project_id=?', (self.project_id,))['c']
        self.bus.emit('DIRECTOR_DECISIONS_CREATED', {'assigned': assigned, 'missing': missing, 'tasks': task_count})
        return {
            'assigned': assigned,
            'missing': missing,
            'tasks_generated': task_count,
            'quality': analysis.get('quality', {}),
            'analysis': analysis,
        }

    def _analyze_completeness(self) -> dict:
        try:
            StoryEngineRuntime(self.db, self.project_id).build()
            analysis = DirectorAIRuntime(self.db, self.project_id).analyze()
            self._materialize_runtime_tasks(analysis)
            return analysis
        except Exception as exc:
            self.bus.emit('DIRECTOR_AI_ANALYSIS_FAILED', {'error': str(exc)})
            return {'error': str(exc)}

    def _materialize_runtime_tasks(self, analysis: dict[str, Any]) -> None:
        for task in analysis.get('tasks', []):
            self.db.execute('''
                INSERT INTO director_tasks(project_id,task_uid,task_type,priority,status,service,scene_id,shot_id,asset_id,title,prompt,payload_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                self.project_id,
                task.get('task_uid'),
                task.get('task_type'),
                task.get('priority', 3),
                task.get('status', 'queued'),
                task.get('service'),
                task.get('scene_id'),
                task.get('shot_id'),
                task.get('asset_id'),
                task.get('title'),
                task.get('prompt'),
                json.dumps(task.get('payload') or {}, ensure_ascii=False),
            ))
            self.db.execute('INSERT INTO operator_tasks(project_id,priority,title,status,owner,details) VALUES(?,?,?,?,?,?)',
                            (self.project_id, task.get('priority', 3), f"Director AI: {task.get('title')}", task.get('status', 'queued'), task.get('service') or 'operator', task.get('prompt') or json.dumps(task.get('payload') or {}, ensure_ascii=False)))

    def transition_project_state(self, new_stage: str, reason: str = '') -> dict[str, Any]:
        current_stage = self.get_project_state()['current_stage']
        if new_stage not in PRODUCTION_STAGES:
            raise ValueError(f"Unknown state '{new_stage}'.")
        if current_stage == 'FAILED':
            raise ValueError('Cannot transition from FAILED state. Resolve blocking errors first.')
        if current_stage == new_stage:
            return self.get_project_state()
        if current_stage not in NEXT_STAGE_RULES or new_stage not in NEXT_STAGE_RULES[current_stage]:
            raise ValueError(f"Invalid transition from {current_stage} to {new_stage}.")
        if self._blocking_errors():
            raise ValueError('Cannot transition while blocking errors are present.')
        from_stage = current_stage
        self._persist_state(new_stage, reason or f'Advanced to {new_stage}', f'Transitioned from {from_stage} to {new_stage}.')
        self._log_history('transition', from_stage, new_stage, reason or f'Advanced to {new_stage}', f'Transitioned from {from_stage} to {new_stage}.')
        self.bus.emit('DIRECTOR_AI_PROJECT_STATE_CHANGED', self.get_project_state())
        return self.get_project_state()

    def record_module_failure(self, module_name: str, error_message: str) -> dict[str, Any]:
        self.db.execute('INSERT INTO director_project_modules(project_id,module_name,status,error_message) VALUES(?,?,?,?)',
                        (self.project_id, module_name, 'failed', error_message))
        current_stage = self.get_project_state()['current_stage']
        self._persist_state('FAILED', f'{module_name} failed', error_message)
        self._log_history('module_failure', current_stage, 'FAILED', f'{module_name} failed', error_message)
        self.bus.emit('DIRECTOR_AI_PROJECT_STATE_CHANGED', self.get_project_state())
        return self.get_project_state()

    def get_project_state(self) -> dict[str, Any]:
        self._initialize_project_state()
        row = self.db.one('SELECT current_stage, completion_percent, overall_status, next_required_action, blocking_reason, estimated_completion, state_details FROM projects WHERE id=?', (self.project_id,))
        current_stage = (row['current_stage'] if row and row['current_stage'] else 'NEW')
        completion_percent = float(row['completion_percent'] or self._completion_percent_for_stage(current_stage)) if row else self._completion_percent_for_stage(current_stage)
        blocking_errors = self._blocking_errors()
        blocking_reason = row['blocking_reason'] if row and row['blocking_reason'] else '; '.join(blocking_errors) if blocking_errors else ''
        overall_status = self._derive_overall_status(current_stage, blocking_errors, completion_percent)
        next_required_action = self._next_required_action(current_stage, blocking_errors)
        estimated_completion = self._estimate_completion(completion_percent)
        state = {
            'project_id': self.project_id,
            'current_stage': current_stage,
            'completion_percent': round(completion_percent, 2),
            'overall_status': overall_status,
            'next_required_action': next_required_action,
            'blocking_reason': blocking_reason,
            'estimated_completion': estimated_completion,
            'missing_modules': self._missing_modules(current_stage),
            'blocking_errors': blocking_errors,
            'history': self._history_rows(),
        }
        if row and row['state_details']:
            state['details'] = row['state_details']
        self._persist_state(current_stage, next_required_action, blocking_reason, state.get('details', ''))
        return state

    def evaluate_project_readiness(self) -> dict[str, Any]:
        state = self.get_project_state()
        if state['overall_status'] == 'FAILED':
            state['next_required_action'] = state['next_required_action'] or 'Resolve blocking errors and restart the workflow.'
        return state

    def _persist_state(self, stage: str, action: str, details: str, reason: str = '') -> None:
        completion_percent = self._completion_percent_for_stage(stage)
        overall_status = self._derive_overall_status(stage, self._blocking_errors(), completion_percent)
        next_required_action = self._next_required_action(stage, self._blocking_errors())
        estimated_completion = self._estimate_completion(completion_percent)
        self.db.execute('''
            UPDATE projects
            SET current_stage=?, completion_percent=?, overall_status=?, next_required_action=?, blocking_reason=?, estimated_completion=?, state_details=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        ''', (stage, completion_percent, overall_status, next_required_action, reason or self._blocking_reason(), estimated_completion, details, self.project_id))
        self.db.execute('''
            INSERT INTO director_project_state(project_id,current_stage,completion_percent,overall_status,next_required_action,blocking_reason,estimated_completion,details)
            VALUES(?,?,?,?,?,?,?,?)
        ''', (self.project_id, stage, completion_percent, overall_status, next_required_action, reason or self._blocking_reason(), estimated_completion, details))

    def _blocking_errors(self) -> list[str]:
        rows = self.db.rows('SELECT module_name, error_message FROM director_project_modules WHERE project_id=? AND status="failed" ORDER BY id DESC', (self.project_id,))
        return [f"{r['module_name']}: {r['error_message']}" for r in rows] if rows else []

    def _blocking_reason(self) -> str:
        return '; '.join(self._blocking_errors())

    def _completion_percent_for_stage(self, stage: str) -> float:
        if stage == 'FAILED':
            return 0.0
        try:
            index = PRODUCTION_STAGES.index(stage)
        except ValueError:
            return 0.0
        if index <= 0:
            return 0.0
        return round((index / (len(PRODUCTION_STAGES) - 1)) * 100.0, 2)

    def _derive_overall_status(self, stage: str, blocking_errors: list[str], completion_percent: float) -> str:
        if stage == 'FAILED' or blocking_errors:
            return 'FAILED'
        if stage == 'FINAL_READY' and completion_percent >= 100.0:
            return 'READY'
        if stage == 'NEW':
            return 'PENDING'
        return 'IN_PROGRESS'

    def _next_required_action(self, stage: str, blocking_errors: list[str]) -> str:
        if blocking_errors:
            return 'Resolve blocking errors before continuing the workflow.'
        if stage == 'FAILED':
            return 'Resolve blocking errors before continuing the workflow.'
        if stage == 'FINAL_READY':
            return 'Project is complete and ready for handoff.'
        next_stage = self._next_stage_for(stage)
        if next_stage:
            return f'Advance to {next_stage}.'
        return 'No further action required.'

    def _next_stage_for(self, stage: str) -> str | None:
        return NEXT_STAGE_RULES.get(stage, [None])[0] if stage in NEXT_STAGE_RULES else None

    def _missing_modules(self, stage: str) -> list[str]:
        if stage == 'FAILED':
            return [module for module in ['research', 'script', 'voice', 'visual', 'edit', 'packaging'] if module]
        stage_index = PRODUCTION_STAGES.index(stage) if stage in PRODUCTION_STAGES else 0
        return [name for name, current in zip(['research', 'script', 'voice', 'visual', 'edit', 'packaging', 'final'], PRODUCTION_STAGES[1:]) if PRODUCTION_STAGES.index(current) > stage_index]

    def _estimate_completion(self, completion_percent: float) -> str:
        return f'{round(max(0.0, 100.0 - completion_percent), 2)}% remaining'

    def _log_history(self, action: str, from_stage: str, to_stage: str, reason: str, details: str) -> None:
        self.db.execute('INSERT INTO director_project_history(project_id,action,from_stage,to_stage,reason,details) VALUES(?,?,?,?,?,?)',
                        (self.project_id, action, from_stage, to_stage, reason, details))

    def _history_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.rows('SELECT action, from_stage, to_stage, reason, details, created_at FROM director_project_history WHERE project_id=? ORDER BY id DESC LIMIT 12', (self.project_id,))]
