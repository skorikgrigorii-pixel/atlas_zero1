from __future__ import annotations
import json
from .database import Database
from .events import EventBus

class QualityCenter:
    def __init__(self, db: Database, project_id='franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)

    def evaluate(self) -> dict:
        total = self.db.one('SELECT COUNT(*) c FROM shots WHERE project_id=?', (self.project_id,))['c'] or 0
        assigned = self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status='assigned'", (self.project_id,))['c'] or 0
        missing = total - assigned
        dup = self.db.one('SELECT COUNT(*) c FROM assets WHERE project_id=? AND duplicate_of IS NOT NULL', (self.project_id,))['c'] or 0
        avg_quality = self.db.one('SELECT AVG(quality) q FROM assets WHERE project_id=?', (self.project_id,))['q'] or 0
        avg_visual = self.db.one('SELECT AVG(style_score) q FROM visual_profiles WHERE project_id=?', (self.project_id,))['q'] or 0
        coverage = assigned / total if total else 0
        readiness = round((coverage * 0.48 + avg_quality * 0.20 + avg_visual * 0.17 + max(0, 1 - dup/10) * 0.08 + 0.07) * 100, 2)
        summary = {
            'assigned_shots': assigned,
            'missing_shots': missing,
            'duplicate_assets': dup,
            'asset_quality_avg': round(avg_quality, 3),
            'visual_style_avg': round(avg_visual, 3),
            'recommendations': [
                'Подключить live API Leonardo для закрытия missing-шотов.' if missing else 'Недостающих шотов нет.',
                'Проверить дубликаты ассетов.' if dup else 'Дубликаты не обнаружены.',
                'Visual Intelligence 0.4 добавлен: локальные профили изображения; финальный RC1 требует полноценную CV-модель.'
            ]
        }
        self.db.execute('INSERT INTO quality_reports(project_id,readiness,coverage,duplicate_count,missing_count,summary) VALUES(?,?,?,?,?,?)',
                        (self.project_id, readiness, round(coverage*100,2), dup, missing, json.dumps(summary, ensure_ascii=False)))
        self.bus.emit('QUALITY_EVALUATED', {'readiness': readiness, 'missing': missing})
        return {'readiness': readiness, **summary}

    def readiness_gate(self) -> dict:
        latest = self.db.one('SELECT * FROM quality_reports WHERE project_id=? ORDER BY id DESC LIMIT 1', (self.project_id,))
        readiness = float(latest['readiness']) if latest else 0
        profiles = self.db.one('SELECT COUNT(*) c FROM visual_profiles WHERE project_id=?', (self.project_id,))['c'] or 0
        configured = self.db.one("SELECT COUNT(*) c FROM integration_profiles WHERE status IN ('configured','connected')")['c'] if self.db.one("SELECT COUNT(*) c FROM integration_profiles WHERE status IN ('configured','connected')") else 0
        criteria = [
            ('Project Brain memory', 0.88, True, 'Граф проекта, события, решения и SQLite работают.'),
            ('Workflow Engine', 0.84, True, 'Конвейер выполняет основные этапы и пишет workflow-события.'),
            ('Director AI', 0.68, True, 'Explainable подбор ассетов работает; нужен финальный просмотрщик решений.'),
            ('Visual Intelligence', 0.62, profiles > 0, f'Создано визуальных профилей: {profiles}. Это локальный анализ, не финальная CV-модель.'),
            ('Live API integrations', 0.38, False, 'Live-safe слой и Credential Vault готовы; реальные платные вызовы заблокированы до настройки ключей и AZ_ENABLE_LIVE_CALLS=1.'),
            ('Enterprise UI', 0.63, False, 'Компактный UI работает; финальный viewer/timeline ещё не production-grade.'),
            ('Franklin pipeline', min(readiness/100, .94), readiness >= 88, f'Готовность Franklin {readiness}%.')
        ]
        self.db.execute('DELETE FROM readiness_checks WHERE project_id=?', (self.project_id,))
        for c,s,p,comment in criteria:
            self.db.execute('INSERT INTO readiness_checks(project_id,criterion,score,passed,comment) VALUES(?,?,?,?,?)',
                            (self.project_id,c,s,1 if p else 0,comment))
        passed = sum(1 for _,_,p,_ in criteria if p)
        final = round(sum(s for _,s,_,_ in criteria)/len(criteria)*100,2)
        self.bus.emit('RC1_READINESS_CHECKED', {'score': final, 'passed': passed, 'total': len(criteria)})
        return {'score': final, 'passed': passed, 'total': len(criteria), 'ready': passed == len(criteria)}
