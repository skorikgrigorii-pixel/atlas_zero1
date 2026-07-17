from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import Database
from .events import EventBus
from .paths import EXPORTS
from .project_config_rc2 import ProjectConfigRC2
from .postproduction_quality_rc2 import PostProductionQualityRC2


@dataclass(frozen=True)
class DirectorRule:
    code: str
    title: str
    severity: str
    task_type: str


RULES = {
    'MISSING_VISUAL': DirectorRule('MISSING_VISUAL', 'Не найден материал под визуальную потребность', 'high', 'generate_asset'),
    'SCENE_LOW_COVERAGE': DirectorRule('SCENE_LOW_COVERAGE', 'Низкое покрытие сцены материалами', 'high', 'generate_scene_coverage'),
    'ASSET_OVERUSED': DirectorRule('ASSET_OVERUSED', 'Материал используется слишком часто', 'medium', 'replace_repeated_asset'),
    'LOW_CV_QUALITY': DirectorRule('LOW_CV_QUALITY', 'Материал имеет низкую техническую оценку', 'medium', 'review_or_replace_asset'),
    'LOW_VISUAL_DIVERSITY': DirectorRule('LOW_VISUAL_DIVERSITY', 'Недостаточно разнообразия планов', 'medium', 'add_visual_variety'),
    'API_NOT_READY': DirectorRule('API_NOT_READY', 'API не подключён для автоматического исполнения', 'blocking', 'connect_api'),
    'FILM_TOO_LONG': DirectorRule('FILM_TOO_LONG', 'Фильм превышает целевую длительность', 'high', 'create_director_cut'),
    'OPENING_HOOK_WEAK': DirectorRule('OPENING_HOOK_WEAK', 'Слабое вступление', 'high', 'strengthen_opening'),
    'STATIC_IMAGE_TOO_LONG': DirectorRule('STATIC_IMAGE_TOO_LONG', 'Статичное изображение показывается слишком долго', 'medium', 'shorten_static_shot'),
    'EXCLUDED_ASSET_USED': DirectorRule('EXCLUDED_ASSET_USED', 'Использован запрещённый материал', 'blocking', 'replace_excluded_asset'),
    'NATURAL_SOUND_MISSING': DirectorRule('NATURAL_SOUND_MISSING', 'Не используется натуральный звук', 'medium', 'add_natural_sound'),
    'ASSET_REUSED_TOO_SOON': DirectorRule('ASSET_REUSED_TOO_SOON', 'Материал повторяется слишком быстро', 'medium', 'replace_repeated_asset'),
}


class DirectorAIRuntime:
    """Director AI 2.5.

    This module is intentionally not a UI-only report. It consumes Story Engine 2.3
    outputs, CV metadata, shot assignments and live API readiness, then creates a
    concrete decision matrix and executable production tasks.

    Design goals:
    - project quality analysis;
    - decision making for missing/repeated/weak material;
    - automatic task creation in director_tasks, operator_tasks and api_jobs;
    - exportable reports for the operator and pipeline.
    """

    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.bus = EventBus(db, project_id)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.db.conn.executescript('''
        CREATE TABLE IF NOT EXISTS director_quality_reports(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          version TEXT NOT NULL,
          quality_score REAL,
          coverage_score REAL,
          diversity_score REAL,
          cv_score REAL,
          repetition_score REAL,
          api_score REAL,
          report_json TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS director_issues(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          rule_code TEXT NOT NULL,
          severity TEXT NOT NULL,
          scene_id TEXT,
          shot_id TEXT,
          asset_id TEXT,
          title TEXT NOT NULL,
          reason TEXT,
          recommendation TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS director_tasks(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          issue_id INTEGER,
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
        CREATE TABLE IF NOT EXISTS director_decision_matrix(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          scene_id TEXT,
          shot_id TEXT,
          asset_id TEXT,
          decision TEXT NOT NULL,
          score REAL DEFAULT 0,
          reason TEXT,
          action TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        self.db.conn.commit()

    def analyze(self) -> dict[str, Any]:
        self._clear_previous()
        scenes = self._rows('SELECT * FROM story_scenes WHERE project_id=? ORDER BY idx', (self.project_id,))
        montage = self._rows('SELECT * FROM story_montage_items WHERE project_id=? ORDER BY shot_index', (self.project_id,))
        if not montage:
            # Fallback: Director AI should still work after older pipelines.
            montage = self._fallback_montage_from_shots()
        missing_reqs = self._rows('SELECT * FROM story_missing_requirements WHERE project_id=? ORDER BY priority DESC,id', (self.project_id,))
        cv_rows = self._rows('SELECT * FROM cv_asset_metadata WHERE project_id=?', (self.project_id,)) if self._table_exists('cv_asset_metadata') else []
        api_state = self._api_state()
        postproduction = self._postproduction_analysis()

        quality = self._quality_scores(scenes, montage, cv_rows, api_state)
        issues: list[dict[str, Any]] = []
        tasks: list[dict[str, Any]] = []
        matrix: list[dict[str, Any]] = []

        issues += self._issues_for_missing(missing_reqs, montage)
        issues += self._issues_for_scene_coverage(scenes, montage)
        issues += self._issues_for_repetition(montage)
        issues += self._issues_for_cv_quality(montage)
        issues += self._issues_for_diversity(scenes, montage)
        issues += postproduction.get('issues', [])
        if not api_state['ready_for_generation']:
            issues.append({
                'rule_code': 'API_NOT_READY', 'severity': 'blocking', 'scene_id': None, 'shot_id': None, 'asset_id': None,
                'title': RULES['API_NOT_READY'].title,
                'reason': f"Подключено {api_state['configured']}/{api_state['total']} сервисов. Live generation disabled.",
                'recommendation': 'Добавить ключи OpenAI/Leonardo/ElevenLabs/YouTube в .env и повторить Live API Test.'
            })

        # Persist issues and convert them to tasks.
        for issue in issues:
            issue_id = self._insert_issue(issue)
            task = self._task_from_issue(issue_id, issue, api_state)
            tasks.append(task)
            self._insert_task(task)
            matrix.append(self._matrix_from_issue(issue, task))

        # Add positive decisions for ready montage shots.
        matrix += self._positive_decisions(montage)
        for row in matrix:
            self._insert_matrix(row)

        report = {
            'version': '2.5',
            'project_id': self.project_id,
            'quality': quality,
            'postproduction': postproduction,
            'summary': {
                'scenes': len(scenes),
                'montage_items': len(montage),
                'issues': len(issues),
                'tasks': len(tasks),
                'blocking': sum(1 for i in issues if i['severity'] == 'blocking'),
                'high': sum(1 for i in issues if i['severity'] == 'high'),
                'medium': sum(1 for i in issues if i['severity'] == 'medium'),
                'api_ready_for_generation': api_state['ready_for_generation'],
            },
            'issues': issues,
            'tasks': tasks,
            'decision_matrix': matrix[:500],
            'next_actions': self._next_actions(issues, tasks, quality, api_state),
            'api_state': api_state,
        }
        self.db.execute('''INSERT INTO director_quality_reports(project_id,version,quality_score,coverage_score,diversity_score,cv_score,repetition_score,api_score,report_json)
                           VALUES(?,?,?,?,?,?,?,?,?)''',
                        (self.project_id, '2.5', quality['overall'], quality['coverage'], quality['diversity'], quality['cv_quality'], quality['repetition'], quality['api'], json.dumps(report, ensure_ascii=False)))
        self.bus.emit('DIRECTOR_AI_2_5_COMPLETED', {'quality': quality['overall'], 'issues': len(issues), 'tasks': len(tasks)})
        self._export(report)
        return report

    def _postproduction_analysis(self) -> dict[str, Any]:
        try:
            config = ProjectConfigRC2(project_id=self.project_id)
            return PostProductionQualityRC2(config).analyze()
        except Exception as exc:
            self.bus.emit(
                'DIRECTOR_AI_POSTPRODUCTION_ANALYSIS_FAILED',
                {'error': str(exc)},
            )
            return {
                'state': 'FAILED',
                'metrics': {},
                'issues': [{
                    'rule_code': 'POSTPRODUCTION_ANALYSIS_FAILED',
                    'severity': 'blocking',
                    'title': 'Не выполнен постпродакшн-анализ',
                    'reason': str(exc),
                    'recommendation': 'Проверить конфигурацию и финальный таймлайн.',
                }],
            }

    def _clear_previous(self) -> None:
        for table in ['director_issues', 'director_tasks', 'director_decision_matrix']:
            self.db.execute(f'DELETE FROM {table} WHERE project_id=?', (self.project_id,))

    def _rows(self, sql: str, params=()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.rows(sql, params)]

    def _table_exists(self, table: str) -> bool:
        return bool(self.db.one('SELECT name FROM sqlite_master WHERE type="table" AND name=?', (table,)))

    def _fallback_montage_from_shots(self) -> list[dict[str, Any]]:
        rows = self._rows('''SELECT s.*, a.filename asset_filename, a.media_type asset_type, a.quality cv_grade
                             FROM shots s LEFT JOIN assets a ON a.id=s.assigned_asset_id
                             WHERE s.project_id=? ORDER BY s.idx''', (self.project_id,))
        out = []
        for r in rows:
            out.append({
                'scene_id': r.get('block'), 'scene_title': r.get('block'), 'shot_id': r['id'], 'shot_index': r['idx'],
                'start_sec': r['start_sec'], 'end_sec': r['end_sec'], 'duration_sec': float(r['end_sec']) - float(r['start_sec']),
                'visual_need': r.get('visual_need'), 'emotion': r.get('emotion'), 'asset_id': r.get('assigned_asset_id'),
                'asset_filename': r.get('asset_filename'), 'asset_type': r.get('asset_type'), 'cv_grade': r.get('cv_grade') or 0,
                'status': 'ready' if r.get('assigned_asset_id') else 'missing', 'action': 'use' if r.get('assigned_asset_id') else 'generate'
            })
        return out

    def _api_state(self) -> dict[str, Any]:
        services = {
            'openai': 'OPENAI_API_KEY',
            'elevenlabs': 'ELEVENLABS_API_KEY',
            'leonardo': 'LEONARDO_API_KEY',
            'youtube': 'YOUTUBE_CLIENT_SECRET',
            'suno': 'SUNO_API_KEY',
            'canva': 'CANVA_API_KEY',
        }
        rows = []
        for service, env_key in services.items():
            present = bool(os.getenv(env_key))
            rows.append({'service': service, 'env_key': env_key, 'configured': present})
        configured = sum(1 for r in rows if r['configured'])
        live_enabled = os.getenv('AZ_ENABLE_LIVE_API') == '1'
        paid_allowed = os.getenv('AZ_ALLOW_PAID_CALLS') == '1'
        ready = live_enabled and configured >= 2
        return {'total': len(rows), 'configured': configured, 'live_enabled': live_enabled, 'paid_allowed': paid_allowed, 'ready_for_generation': ready, 'rows': rows}

    def _quality_scores(self, scenes: list[dict[str, Any]], montage: list[dict[str, Any]], cv_rows: list[dict[str, Any]], api_state: dict[str, Any]) -> dict[str, float]:
        total = max(len(montage), 1)
        ready = sum(1 for m in montage if m.get('status') == 'ready' or m.get('asset_id'))
        coverage = ready / total * 100
        needs = [str(m.get('visual_need') or 'unknown').lower() for m in montage]
        diversity = min(100.0, len(set(needs)) / max(len(needs), 1) * 320)
        asset_ids = [m.get('asset_id') for m in montage if m.get('asset_id')]
        usage = Counter(asset_ids)
        overused = sum(1 for _, c in usage.items() if c > 4)
        repetition = max(0.0, 100.0 - overused * 12.0 - sum(max(c - 5, 0) for c in usage.values()) * 4.0)
        grades = []
        for m in montage:
            try:
                if m.get('cv_grade') is not None:
                    grades.append(float(m.get('cv_grade') or 0))
            except Exception:
                pass
        if not grades and cv_rows:
            grades = [float(r.get('cinematic_grade') or 0) for r in cv_rows]
        cv_quality = min(100.0, (sum(grades) / max(len(grades), 1)) * 100) if grades else 0
        api = 100 if api_state['ready_for_generation'] else round(api_state['configured'] / max(api_state['total'], 1) * 100, 2)
        overall = round(coverage * 0.34 + diversity * 0.16 + repetition * 0.16 + cv_quality * 0.22 + api * 0.12, 2)
        return {'overall': overall, 'coverage': round(coverage, 2), 'diversity': round(diversity, 2), 'repetition': round(repetition, 2), 'cv_quality': round(cv_quality, 2), 'api': round(api, 2)}

    def _issues_for_missing(self, missing_reqs: list[dict[str, Any]], montage: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues = []
        if missing_reqs:
            for r in missing_reqs:
                issues.append({
                    'rule_code': 'MISSING_VISUAL', 'severity': 'high', 'scene_id': r.get('scene_id'), 'shot_id': None, 'asset_id': None,
                    'title': f"Создать материал: {r.get('visual_need')}",
                    'reason': r.get('reason') or 'Story Engine сообщил о дефиците материала.',
                    'recommendation': r.get('prompt') or self._prompt(r.get('visual_need'), r.get('scene_title'), '')
                })
        else:
            for m in montage:
                if m.get('status') == 'missing' or not m.get('asset_id'):
                    issues.append({
                        'rule_code': 'MISSING_VISUAL', 'severity': 'high', 'scene_id': m.get('scene_id'), 'shot_id': m.get('shot_id'), 'asset_id': None,
                        'title': f"Нет материала для шота {m.get('shot_index')}",
                        'reason': f"Потребность: {m.get('visual_need')}",
                        'recommendation': self._prompt(m.get('visual_need'), m.get('scene_title'), m.get('emotion'))
                    })
        return issues

    def _issues_for_scene_coverage(self, scenes: list[dict[str, Any]], montage: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_scene = defaultdict(list)
        for m in montage:
            by_scene[m.get('scene_id') or 'UNASSIGNED'].append(m)
        issues = []
        for s in scenes:
            items = by_scene.get(s.get('id'), [])
            if not items:
                continue
            ready = sum(1 for i in items if i.get('asset_id'))
            coverage = ready / max(len(items), 1)
            if coverage < 0.65:
                issues.append({
                    'rule_code': 'SCENE_LOW_COVERAGE', 'severity': 'high', 'scene_id': s.get('id'), 'shot_id': None, 'asset_id': None,
                    'title': f"Низкое покрытие сцены: {s.get('title')}",
                    'reason': f"Покрытие {round(coverage*100,1)}%, готово {ready}/{len(items)}.",
                    'recommendation': f"Добавить 2–4 материала для сцены '{s.get('title')}', включая общий план, крупную деталь и переходный B-roll."
                })
        return issues

    def _issues_for_repetition(self, montage: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_asset = defaultdict(list)
        for m in montage:
            if m.get('asset_id'):
                by_asset[m['asset_id']].append(m)
        issues = []
        for asset_id, items in by_asset.items():
            if len(items) > 4:
                sample = items[0]
                issues.append({
                    'rule_code': 'ASSET_OVERUSED', 'severity': 'medium', 'scene_id': sample.get('scene_id'), 'shot_id': sample.get('shot_id'), 'asset_id': asset_id,
                    'title': f"Повтор материала: {sample.get('asset_filename') or asset_id}",
                    'reason': f"Материал используется {len(items)} раз. Это снижает визуальное разнообразие.",
                    'recommendation': 'Оставить 1–2 лучших использования, остальные заменить на B-roll или сгенерировать альтернативы.'
                })
        return issues

    def _issues_for_cv_quality(self, montage: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues = []
        for m in montage:
            if not m.get('asset_id'):
                continue
            try:
                grade = float(m.get('cv_grade') or 0)
            except Exception:
                grade = 0
            if 0 < grade < 0.45:
                issues.append({
                    'rule_code': 'LOW_CV_QUALITY', 'severity': 'medium', 'scene_id': m.get('scene_id'), 'shot_id': m.get('shot_id'), 'asset_id': m.get('asset_id'),
                    'title': f"Низкое качество материала: {m.get('asset_filename')}",
                    'reason': f"CV grade={grade}. Возможны размытие, плохой контраст или слабая композиция.",
                    'recommendation': 'Проверить материал вручную; при необходимости заменить или отправить на повторную генерацию.'
                })
        return issues

    def _issues_for_diversity(self, scenes: list[dict[str, Any]], montage: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues = []
        by_scene = defaultdict(list)
        for m in montage:
            by_scene[m.get('scene_id') or 'UNASSIGNED'].append(m)
        for scene_id, items in by_scene.items():
            if len(items) < 4:
                continue
            types = Counter(self._need_bucket(i.get('visual_need')) for i in items)
            if len(types) <= 1:
                title = next((s.get('title') for s in scenes if s.get('id') == scene_id), scene_id)
                issues.append({
                    'rule_code': 'LOW_VISUAL_DIVERSITY', 'severity': 'medium', 'scene_id': scene_id, 'shot_id': None, 'asset_id': None,
                    'title': f"Однообразие планов: {title}",
                    'reason': f"В сцене доминирует один тип визуального материала: {types.most_common(1)[0][0]}.",
                    'recommendation': 'Добавить контраст: общий план + крупная деталь + карта/документ + движение камеры.'
                })
        return issues

    def _need_bucket(self, need: Any) -> str:
        text = str(need or '').lower()
        if any(w in text for w in ['map', 'route', 'карта']): return 'map'
        if any(w in text for w in ['document', 'note', 'paper', 'archive', 'letter']): return 'document'
        if any(w in text for w in ['crew', 'face', 'portrait', 'people']): return 'people'
        if any(w in text for w in ['close', 'detail', 'spoon', 'object']): return 'detail'
        if any(w in text for w in ['wide', 'drone', 'arctic', 'horizon']): return 'wide'
        if any(w in text for w in ['ship', 'boat', 'hull']): return 'ship'
        return 'other'

    def _task_from_issue(self, issue_id: int, issue: dict[str, Any], api_state: dict[str, Any]) -> dict[str, Any]:
        rule = RULES.get(issue['rule_code'], RULES['MISSING_VISUAL'])
        priority = {'blocking': 1, 'high': 2, 'medium': 3, 'low': 4}.get(issue['severity'], 3)
        service = None
        status = 'queued'
        prompt = issue.get('recommendation') or ''
        if rule.task_type in ('generate_asset', 'generate_scene_coverage', 'add_visual_variety'):
            service = 'leonardo'
            if not api_state['ready_for_generation']:
                status = 'waiting_api'
            self._insert_api_job_if_needed(service, rule.task_type, status, issue, prompt)
        elif rule.task_type == 'connect_api':
            service = 'operator'
            status = 'operator_required'
        else:
            service = 'operator'
        return {
            'task_uid': f"DIR-24-{issue_id:04d}", 'task_type': rule.task_type, 'priority': priority, 'status': status,
            'service': service, 'scene_id': issue.get('scene_id'), 'shot_id': issue.get('shot_id'), 'asset_id': issue.get('asset_id'),
            'title': issue['title'], 'prompt': prompt,
            'payload': {'rule': issue['rule_code'], 'reason': issue.get('reason'), 'recommendation': issue.get('recommendation')}
        }

    def _insert_api_job_if_needed(self, service: str, job_type: str, status: str, issue: dict[str, Any], prompt: str) -> None:
        payload = {'source': 'Director AI 2.5', 'issue': issue, 'prompt': prompt, 'style': 'cold blue cinematic historical documentary'}
        self.db.execute('INSERT INTO api_jobs(project_id,service,job_type,status,payload) VALUES(?,?,?,?,?)',
                        (self.project_id, service, job_type, status, json.dumps(payload, ensure_ascii=False)))

    def _insert_issue(self, issue: dict[str, Any]) -> int:
        cur = self.db.execute('''INSERT INTO director_issues(project_id,rule_code,severity,scene_id,shot_id,asset_id,title,reason,recommendation)
                                 VALUES(?,?,?,?,?,?,?,?,?)''',
                              (self.project_id, issue['rule_code'], issue['severity'], issue.get('scene_id'), issue.get('shot_id'), issue.get('asset_id'), issue['title'], issue.get('reason'), issue.get('recommendation')))
        return int(cur.lastrowid)

    def _insert_task(self, task: dict[str, Any]) -> None:
        self.db.execute('''INSERT INTO director_tasks(project_id,issue_id,task_uid,task_type,priority,status,service,scene_id,shot_id,asset_id,title,prompt,payload_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (self.project_id, int(task['task_uid'].split('-')[-1]), task['task_uid'], task['task_type'], task['priority'], task['status'], task.get('service'), task.get('scene_id'), task.get('shot_id'), task.get('asset_id'), task['title'], task.get('prompt'), json.dumps(task.get('payload') or {}, ensure_ascii=False)))
        self.db.execute('INSERT INTO operator_tasks(project_id,priority,title,status,owner,details) VALUES(?,?,?,?,?,?)',
                        (self.project_id, task['priority'], f"Director AI: {task['title']}", task['status'], task.get('service') or 'operator', task.get('prompt') or json.dumps(task.get('payload') or {}, ensure_ascii=False)))

    def _matrix_from_issue(self, issue: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
        return {
            'scene_id': issue.get('scene_id'), 'shot_id': issue.get('shot_id'), 'asset_id': issue.get('asset_id'),
            'decision': issue['title'], 'score': 0, 'reason': issue.get('reason'), 'action': f"{task['task_type']} · {task['status']} · {task.get('service') or 'operator'}"
        }

    def _positive_decisions(self, montage: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for m in montage:
            if m.get('asset_id'):
                try: score = float(m.get('cv_grade') or 0)
                except Exception: score = 0
                rows.append({
                    'scene_id': m.get('scene_id'), 'shot_id': m.get('shot_id'), 'asset_id': m.get('asset_id'),
                    'decision': f"Использовать {m.get('asset_filename')}", 'score': round(score, 3),
                    'reason': f"Материал закрывает потребность: {m.get('visual_need')}", 'action': 'use_asset'
                })
        return rows[:300]

    def _insert_matrix(self, row: dict[str, Any]) -> None:
        self.db.execute('''INSERT INTO director_decision_matrix(project_id,scene_id,shot_id,asset_id,decision,score,reason,action)
                           VALUES(?,?,?,?,?,?,?,?)''',
                        (self.project_id, row.get('scene_id'), row.get('shot_id'), row.get('asset_id'), row.get('decision'), row.get('score') or 0, row.get('reason'), row.get('action')))

    def _prompt(self, visual_need: Any, scene_title: Any, emotion: Any) -> str:
        return (f"Ultra photorealistic historical documentary frame. Scene: {scene_title or 'Franklin Expedition'}. "
                f"Need: {visual_need or 'cinematic B-roll'}. Emotion: {emotion or 'cold investigation'}. "
                "1845 Franklin Expedition, Arctic, cold blue-grey palette, realistic materials, no fantasy, no modern objects.")

    def _next_actions(self, issues: list[dict[str, Any]], tasks: list[dict[str, Any]], quality: dict[str, float], api_state: dict[str, Any]) -> list[str]:
        actions = []
        if quality['coverage'] < 80:
            actions.append('Закрыть дефицит визуальных материалов: выполнить задачи Director AI со статусом waiting_api/queued.')
        if quality['repetition'] < 85:
            actions.append('Сократить повторяемость ассетов: заменить часто используемые кадры альтернативами или генерацией.')
        if quality['cv_quality'] < 55:
            actions.append('Провести ручной отбор материалов с низким CV grade и заменить слабые кадры.')
        if not api_state['ready_for_generation']:
            actions.append('Подключить Live API для Leonardo/OpenAI/ElevenLabs или продолжить в режиме Local Only с ручной генерацией.')
        if not actions:
            actions.append('Качество приемлемое: перейти к Alpha 2.5 Franklin Production RC и финальному handoff.')
        return actions

    def _export(self, report: dict[str, Any]) -> None:
        (self.export_dir / 'director_ai_2_5_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self._write_csv(self.export_dir / 'director_issues.csv', report['issues'], ['rule_code','severity','scene_id','shot_id','asset_id','title','reason','recommendation'])
        self._write_csv(self.export_dir / 'director_tasks.csv', report['tasks'], ['task_uid','task_type','priority','status','service','scene_id','shot_id','asset_id','title','prompt'])
        self._write_csv(self.export_dir / 'director_decision_matrix.csv', report['decision_matrix'], ['scene_id','shot_id','asset_id','decision','score','reason','action'])
        (self.export_dir / 'director_ai_2_5.html').write_text(self._html(report), encoding='utf-8')

    def _write_csv(self, path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader(); w.writerows(rows)

    def _html(self, report: dict[str, Any]) -> str:
        q = report['quality']; s = report['summary']
        issue_rows = ''.join(f"<tr><td>{i['severity']}</td><td>{i['rule_code']}</td><td>{i.get('scene_id') or ''}</td><td>{i['title']}</td><td>{i.get('reason') or ''}</td></tr>" for i in report['issues'][:250])
        task_rows = ''.join(f"<tr><td>{t['priority']}</td><td>{t['task_uid']}</td><td>{t['task_type']}</td><td>{t['status']}</td><td>{t.get('service') or ''}</td><td>{t['title']}</td></tr>" for t in report['tasks'][:250])
        actions = ''.join(f"<li>{a}</li>" for a in report['next_actions'])
        return f"""<!doctype html><meta charset='utf-8'><title>Director AI 2.5</title>
<style>body{{font-family:Segoe UI,Arial;background:#08111f;color:#e5edf8;margin:24px;font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}}.card{{background:#111827;border:1px solid #334155;border-radius:14px;padding:14px}}.v{{font-size:24px;font-weight:800;color:#7dd3fc}}table{{border-collapse:collapse;width:100%;margin-top:12px}}td,th{{border-bottom:1px solid #334155;padding:7px;text-align:left;vertical-align:top}}h2{{margin-top:26px}}li{{margin:8px 0}}</style>
<h1>ATLAS ZERO — Director AI 2.5</h1><div class='grid'>
<div class='card'><div>Общее качество</div><div class='v'>{q['overall']}%</div></div>
<div class='card'><div>Покрытие</div><div class='v'>{q['coverage']}%</div></div>
<div class='card'><div>Разнообразие</div><div class='v'>{q['diversity']}%</div></div>
<div class='card'><div>CV качество</div><div class='v'>{q['cv_quality']}%</div></div>
<div class='card'><div>Повторы</div><div class='v'>{q['repetition']}%</div></div>
<div class='card'><div>Задачи</div><div class='v'>{s['tasks']}</div></div></div>
<h2>Следующие действия</h2><ul>{actions}</ul>
<h2>Проблемы</h2><table><tr><th>Критичность</th><th>Правило</th><th>Сцена</th><th>Проблема</th><th>Причина</th></tr>{issue_rows}</table>
<h2>Задачи Director AI</h2><table><tr><th>P</th><th>ID</th><th>Тип</th><th>Статус</th><th>Сервис</th><th>Задача</th></tr>{task_rows}</table>"""
