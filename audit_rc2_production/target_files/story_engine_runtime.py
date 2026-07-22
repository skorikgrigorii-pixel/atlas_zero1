from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .database import Database
from .paths import EXPORTS


class StoryEngineRuntime:
    """Story Engine 2.3 — automatic scene construction and montage sheet.

    Inputs: story_scenes/shots from StoryEngine, assigned assets from Director AI,
    CV metadata from CV Runtime. Outputs: scene model, montage sheet, missing
    requirements, HTML operator views and JSON/CSV artifacts.
    """

    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.db.conn.executescript('''
        CREATE TABLE IF NOT EXISTS story_beats(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          block TEXT,
          start_sec REAL,
          end_sec REAL,
          shot_count INTEGER,
          assigned_count INTEGER,
          missing_count INTEGER,
          dominant_need TEXT,
          emotion TEXT,
          summary TEXT,
          risk TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS story_runtime_reports(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          readiness REAL,
          report_json TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS story_montage_items(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          shot_id TEXT NOT NULL,
          scene_id TEXT,
          scene_title TEXT,
          shot_index INTEGER,
          start_sec REAL,
          end_sec REAL,
          duration_sec REAL,
          narration_cue TEXT,
          visual_need TEXT,
          emotion TEXT,
          asset_id TEXT,
          asset_filename TEXT,
          asset_type TEXT,
          cv_grade REAL,
          transition TEXT,
          camera_motion TEXT,
          status TEXT,
          action TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS story_missing_requirements(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL,
          scene_id TEXT,
          scene_title TEXT,
          visual_need TEXT,
          priority INTEGER,
          prompt TEXT,
          reason TEXT,
          status TEXT DEFAULT 'open',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        self.db.conn.commit()

    def build(self) -> dict[str, Any]:
        scenes = [dict(r) for r in self.db.rows('SELECT * FROM story_scenes WHERE project_id=? ORDER BY idx', (self.project_id,))]
        shots = [dict(r) for r in self.db.rows('''
            SELECT s.*, a.filename asset_name, a.media_type asset_type, a.category asset_category, a.quality asset_quality
            FROM shots s LEFT JOIN assets a ON a.id=s.assigned_asset_id
            WHERE s.project_id=? ORDER BY s.idx
        ''', (self.project_id,))]
        if not scenes and shots:
            scenes = self._fallback_scenes_from_shots(shots)
        cv = [dict(r) for r in self.db.rows('SELECT * FROM cv_asset_metadata WHERE project_id=?', (self.project_id,))]
        cv_by_asset = {r['asset_id']: r for r in cv}
        scene_for_shot = self._map_shots_to_scenes(scenes, shots)

        self.db.execute('DELETE FROM story_beats WHERE project_id=?', (self.project_id,))
        self.db.execute('DELETE FROM story_montage_items WHERE project_id=?', (self.project_id,))
        self.db.execute('DELETE FROM story_missing_requirements WHERE project_id=?', (self.project_id,))

        scene_reports = []
        montage = []
        missing_requirements = []
        by_scene = defaultdict(list)
        for s in shots:
            scene = scene_for_shot.get(s['id'])
            by_scene[scene['id'] if scene else 'UNASSIGNED'].append(s)

        for scene in scenes:
            items = by_scene.get(scene['id'], [])
            scene_report = self._scene_report(scene, items, cv_by_asset)
            scene_reports.append(scene_report)
            self.db.execute('''INSERT INTO story_beats(project_id,block,start_sec,end_sec,shot_count,assigned_count,missing_count,dominant_need,emotion,summary,risk)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                            (self.project_id, scene_report['block'], scene_report['start_sec'], scene_report['end_sec'], scene_report['shot_count'], scene_report['assigned_count'], scene_report['missing_count'], scene_report['dominant_need'], scene_report['emotion'], scene_report['summary'], scene_report['risk']))
            try:
                self.db.execute('UPDATE story_scenes SET coverage=?, status=? WHERE id=? AND project_id=?',
                                (scene_report['coverage'], scene_report['status'], scene['id'], self.project_id))
            except Exception:
                pass

        for shot in shots:
            scene = scene_for_shot.get(shot['id']) or {}
            cv_meta = cv_by_asset.get(shot.get('assigned_asset_id') or '')
            item = self._montage_item(shot, scene, cv_meta)
            montage.append(item)
            self.db.execute('''INSERT INTO story_montage_items(project_id,shot_id,scene_id,scene_title,shot_index,start_sec,end_sec,duration_sec,narration_cue,visual_need,emotion,asset_id,asset_filename,asset_type,cv_grade,transition,camera_motion,status,action)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (self.project_id, item['shot_id'], item['scene_id'], item['scene_title'], item['shot_index'], item['start_sec'], item['end_sec'], item['duration_sec'], item['narration_cue'], item['visual_need'], item['emotion'], item['asset_id'], item['asset_filename'], item['asset_type'], item['cv_grade'], item['transition'], item['camera_motion'], item['status'], item['action']))
            if item['status'] == 'missing':
                req = self._missing_requirement(item)
                missing_requirements.append(req)
                self.db.execute('''INSERT INTO story_missing_requirements(project_id,scene_id,scene_title,visual_need,priority,prompt,reason,status)
                                   VALUES(?,?,?,?,?,?,?,?)''',
                                (self.project_id, req['scene_id'], req['scene_title'], req['visual_need'], req['priority'], req['prompt'], req['reason'], 'open'))

        assigned = sum(1 for m in montage if m['status'] == 'ready')
        missing = len(montage) - assigned
        readiness = round(assigned / max(len(montage), 1) * 100, 2)
        cv_summary = {
            'assets_with_cv': len(cv),
            'faces_total': sum(int(r.get('face_count') or 0) for r in cv),
            'scene_candidates_total': sum(int(r.get('scene_count') or 0) for r in cv),
            'avg_cinematic_grade': round(sum(float(r.get('cinematic_grade') or 0) for r in cv) / max(len(cv), 1), 3),
        }
        report = {
            'version': '2.3',
            'project_id': self.project_id,
            'scenes': len(scene_reports),
            'shots': len(montage),
            'assigned': assigned,
            'missing': missing,
            'readiness': readiness,
            'scene_reports': scene_reports,
            'montage_items': montage,
            'missing_requirements': missing_requirements,
            'cv_summary': cv_summary,
            'recommendations': self._recommendations(scene_reports, missing_requirements, cv_summary),
        }
        self.db.execute('INSERT INTO story_runtime_reports(project_id,readiness,report_json) VALUES(?,?,?)',
                        (self.project_id, readiness, json.dumps(report, ensure_ascii=False)))
        self._export(report)
        return report

    def _map_shots_to_scenes(self, scenes: list[dict[str, Any]], shots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        mapping = {}
        for shot in shots:
            assigned = None
            for scene in scenes:
                if float(scene['start_sec']) <= float(shot['start_sec']) < float(scene['end_sec']) + 0.001:
                    assigned = scene
                    break
            if not assigned and scenes:
                assigned = scenes[-1]
            mapping[shot['id']] = assigned
        return mapping

    def _fallback_scenes_from_shots(self, shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped = defaultdict(list)
        for s in shots:
            grouped[s.get('block') or 'B00'].append(s)
        scenes = []
        for idx, (block, items) in enumerate(sorted(grouped.items()), start=1):
            scenes.append({'id': f'{block}_AUTO', 'idx': idx, 'block': block, 'title': f'{block} автоматическая сцена', 'start_sec': items[0]['start_sec'], 'end_sec': items[-1]['end_sec'], 'duration_sec': items[-1]['end_sec'] - items[0]['start_sec'], 'target_shots': len(items), 'narrative_goal': items[0].get('story_goal') or '', 'emotional_goal': items[0].get('emotion') or 'neutral', 'visual_strategy': 'fallback grouping', 'required_assets': '[]'})
        return scenes

    def _scene_report(self, scene: dict[str, Any], shots: list[dict[str, Any]], cv_by_asset: dict[str, dict[str, Any]]) -> dict[str, Any]:
        assigned = [s for s in shots if s.get('assigned_asset_id')]
        missing = [s for s in shots if not s.get('assigned_asset_id')]
        needs = Counter(s.get('visual_need') or 'unknown' for s in shots)
        emotions = Counter(s.get('emotion') or scene.get('emotional_goal') or 'neutral' for s in shots)
        grades = [float((cv_by_asset.get(s.get('assigned_asset_id') or '') or {}).get('cinematic_grade') or 0) for s in assigned]
        coverage = round(len(assigned) / max(len(shots), 1) * 100, 2)
        avg_grade = round(sum(grades) / max(len(grades), 1), 3) if grades else 0
        dominant_need = needs.most_common(1)[0][0] if needs else 'unknown'
        risk = self._risk_text(scene, len(shots), len(assigned), len(missing), avg_grade)
        status = 'ready' if not missing else ('partial' if assigned else 'missing')
        summary = f"{scene.get('title')}: {len(shots)} шотов, покрытие {coverage}%, средняя CV-оценка {avg_grade}. Цель: {scene.get('narrative_goal')}"
        return {
            'scene_id': scene['id'],
            'idx': scene.get('idx'),
            'block': scene.get('block'),
            'title': scene.get('title'),
            'start_sec': scene.get('start_sec'),
            'end_sec': scene.get('end_sec'),
            'duration_sec': scene.get('duration_sec'),
            'shot_count': len(shots),
            'assigned_count': len(assigned),
            'missing_count': len(missing),
            'coverage': coverage,
            'avg_cv_grade': avg_grade,
            'dominant_need': dominant_need,
            'emotion': emotions.most_common(1)[0][0] if emotions else scene.get('emotional_goal') or 'neutral',
            'summary': summary,
            'risk': risk,
            'status': status,
            'visual_strategy': scene.get('visual_strategy') or '',
        }

    def _montage_item(self, shot: dict[str, Any], scene: dict[str, Any], cv_meta: dict[str, Any] | None) -> dict[str, Any]:
        duration = round(float(shot['end_sec']) - float(shot['start_sec']), 3)
        asset_id = shot.get('assigned_asset_id') or ''
        status = 'ready' if asset_id else 'missing'
        grade = round(float(cv_meta.get('cinematic_grade') or 0), 3) if cv_meta else 0
        action = 'use_asset' if status == 'ready' else 'generate_or_find_asset'
        if status == 'ready' and grade and grade < 0.45:
            action = 'review_asset_quality'
        return {
            'scene_id': scene.get('id') or '',
            'scene_title': scene.get('title') or '',
            'shot_id': shot['id'],
            'shot_index': shot['idx'],
            'start_sec': shot['start_sec'],
            'end_sec': shot['end_sec'],
            'duration_sec': duration,
            'narration_cue': self._narration_cue(scene, shot),
            'visual_need': shot.get('visual_need') or '',
            'emotion': shot.get('emotion') or scene.get('emotional_goal') or 'neutral',
            'asset_id': asset_id,
            'asset_filename': shot.get('asset_name') or '',
            'asset_type': shot.get('asset_type') or '',
            'cv_grade': grade,
            'transition': shot.get('transition') or 'cut',
            'camera_motion': shot.get('camera_motion') or 'static',
            'status': status,
            'action': action,
        }

    def _narration_cue(self, scene: dict[str, Any], shot: dict[str, Any]) -> str:
        title = scene.get('title') or shot.get('block') or ''
        goal = scene.get('narrative_goal') or shot.get('story_goal') or ''
        return f"{title}: {goal[:110]}"

    def _missing_requirement(self, item: dict[str, Any]) -> dict[str, Any]:
        priority = 5 if item['shot_index'] <= 12 else 4
        if any(x in item['visual_need'].lower() for x in ['document', 'note', 'bones', 'underwater', 'sonar']):
            priority = max(priority, 5)
        prompt = (
            f"Ultra photorealistic historical documentary frame. Scene: {item['scene_title']}. "
            f"Required visual: {item['visual_need']}. Emotion: {item['emotion']}. "
            "Cold blue-gray palette, restrained BBC/Netflix documentary realism, no fantasy, no modern objects unless the scene requires modern research tools."
        )
        return {
            'scene_id': item['scene_id'],
            'scene_title': item['scene_title'],
            'visual_need': item['visual_need'],
            'priority': priority,
            'prompt': prompt,
            'reason': f"Шот {item['shot_index']} не имеет назначенного материала; нужен для сцены '{item['scene_title']}'.",
        }

    def _risk_text(self, scene: dict[str, Any], shots: int, assigned: int, missing: int, avg_grade: float) -> str:
        if shots == 0:
            return 'нет шотов в сцене'
        miss_pct = missing / max(shots, 1)
        if missing == 0 and avg_grade >= 0.55:
            return 'низкий: сцена закрыта материалами и CV-качество приемлемое'
        if miss_pct > 0.4:
            return 'высокий: сцена визуально не закрыта, требуется генерация/поиск материалов'
        if missing > 0:
            return 'средний: есть дефицит отдельных планов'
        return 'средний: материалы есть, но требуется ручная проверка качества'

    def _recommendations(self, scenes, missing, cv_summary):
        rec = []
        if missing:
            top = Counter(m['scene_title'] for m in missing).most_common(3)
            rec.append('Закрыть дефицит в сценах: ' + ', '.join(f'{name} ({count})' for name, count in top))
        weak = [s for s in scenes if s['coverage'] < 70]
        if weak:
            rec.append('Пересобрать или догенерировать сцены с покрытием ниже 70%: ' + ', '.join(s['scene_id'] for s in weak[:5]))
        if cv_summary['assets_with_cv']:
            rec.append(f"Использовать CV-оценку при финальном выборе кадров: средний grade {cv_summary['avg_cinematic_grade']}.")
        rec.append('После добавления недостающих материалов повторить: CV Runtime → Director AI → Story Engine → QC.')
        return rec

    def _export(self, report: dict[str, Any]) -> None:
        def write_json(name: str, data: Any):
            (self.export_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

        write_json('story_engine_2_3_report.json', report)
        write_json('story_scenes.json', report['scene_reports'])
        write_json('montage_sheet.json', report['montage_items'])
        write_json('missing_story_requirements.json', report['missing_requirements'])
        # Backward-compatible filenames.
        write_json('story_engine_runtime.json', report)

        self._write_csv('story_scenes.csv', report['scene_reports'], ['scene_id','idx','block','title','start_sec','end_sec','duration_sec','shot_count','assigned_count','missing_count','coverage','avg_cv_grade','dominant_need','emotion','status','risk','summary'])
        self._write_csv('montage_sheet.csv', report['montage_items'], ['shot_index','scene_id','scene_title','start_sec','end_sec','duration_sec','narration_cue','visual_need','emotion','asset_filename','asset_type','cv_grade','transition','camera_motion','status','action'])
        self._write_csv('missing_story_requirements.csv', report['missing_requirements'], ['priority','scene_id','scene_title','visual_need','reason','prompt'])
        # Russian operator filenames.
        self._write_csv('монтажный_лист_story_engine.csv', report['montage_items'], ['shot_index','scene_id','scene_title','start_sec','end_sec','duration_sec','narration_cue','visual_need','emotion','asset_filename','asset_type','cv_grade','transition','camera_motion','status','action'])
        self._write_missing_md(report['missing_requirements'])
        self._write_html(report)

    def _write_csv(self, name: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
        with (self.export_dir / name).open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)

    def _write_missing_md(self, missing: list[dict[str, Any]]) -> None:
        parts = ['# ATLAS ZERO — недостающие материалы Story Engine 2.3\n']
        for i, m in enumerate(sorted(missing, key=lambda x: (-x['priority'], x['scene_id'])), start=1):
            parts.append(f"## {i}. {m['scene_title']} · priority {m['priority']}\n")
            parts.append(f"**Нужно:** {m['visual_need']}\n\n**Причина:** {m['reason']}\n\n```text\n{m['prompt']}\n```\n")
        (self.export_dir / 'missing_story_requirements.md').write_text('\n'.join(parts), encoding='utf-8')

    def _write_html(self, report: dict[str, Any]) -> None:
        scene_cards = ''.join(
            f"<section class='scene {s['status']}'><h2>{s['scene_id']} · {s['title']}</h2><p><b>{s['block']}</b> · {s['start_sec']}–{s['end_sec']} сек · {s['shot_count']} шотов</p><div class='bar'><span style='width:{s['coverage']}%'></span></div><p>Назначено: {s['assigned_count']} · Дефицит: {s['missing_count']} · CV grade: {s['avg_cv_grade']}</p><p>{s['summary']}</p><p class='risk'>{s['risk']}</p></section>"
            for s in report['scene_reports']
        )
        rec = ''.join(f'<li>{x}</li>' for x in report['recommendations'])
        missing_rows = ''.join(
            f"<tr><td>{m['priority']}</td><td>{m['scene_title']}</td><td>{m['visual_need']}</td><td>{m['reason']}</td></tr>"
            for m in report['missing_requirements'][:120]
        )
        html = f"""<!doctype html><meta charset='utf-8'><title>ATLAS ZERO Story Engine 2.3</title>
<style>
body{{font-family:Segoe UI,Arial;background:#08111f;color:#eaf2ff;margin:22px;font-size:14px}}
h1,h2{{margin:.2em 0}} .kpi{{display:flex;gap:10px;flex-wrap:wrap}} .kpi div{{background:#0b1424;border:1px solid #334155;border-radius:14px;padding:12px 18px;min-width:140px}}
.scene{{background:#101b2d;border:1px solid #26364d;border-radius:16px;padding:15px;margin:12px 0}} .ready{{border-color:#22c55e}} .partial{{border-color:#f59e0b}} .missing{{border-color:#ef4444}}
.bar{{height:8px;background:#172033;border-radius:99px;overflow:hidden}} .bar span{{display:block;height:8px;background:#38bdf8}} .risk{{color:#fbbf24}} table{{border-collapse:collapse;width:100%;margin-top:12px}}td,th{{border-bottom:1px solid #334155;padding:8px;text-align:left}}
</style>
<h1>ATLAS ZERO — Story Engine 2.3</h1>
<div class='kpi'><div>Сцен<br><b>{report['scenes']}</b></div><div>Шотов<br><b>{report['shots']}</b></div><div>Назначено<br><b>{report['assigned']}</b></div><div>Дефицит<br><b>{report['missing']}</b></div><div>Готовность<br><b>{report['readiness']}%</b></div></div>
<h2>Рекомендации</h2><ul>{rec}</ul>
<h2>Сцены</h2>{scene_cards}
<h2>Недостающие материалы</h2><table><tr><th>Приоритет</th><th>Сцена</th><th>Потребность</th><th>Причина</th></tr>{missing_rows}</table>
"""
        (self.export_dir / 'story_engine_2_3.html').write_text(html, encoding='utf-8')
        # Backward-compatible filename used by old UI/smoke tests.
        (self.export_dir / 'story_engine_runtime.html').write_text(html, encoding='utf-8')
