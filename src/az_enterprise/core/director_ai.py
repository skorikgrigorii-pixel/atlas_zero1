from __future__ import annotations
import json
from collections import defaultdict
from .database import Database
from .events import EventBus

class DirectorAI:
    def __init__(self, db: Database, project_id='franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)
        self.usage = defaultdict(int)

    def _score(self, shot, asset):
        need = (shot['visual_need'] or '').lower().split()
        tags = json.loads(asset['tags'] or '[]')
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
        for shot in shots:
            ranked = sorted(((self._score(shot,a), a) for a in assets), key=lambda x: x[0], reverse=True)
            if ranked and ranked[0][0] >= 0.62:
                score, asset = ranked[0]
                self.usage[asset['id']] += 1
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
        self.bus.emit('DIRECTOR_DECISIONS_CREATED', {'assigned': assigned, 'missing': missing})
        return {'assigned': assigned, 'missing': missing}
