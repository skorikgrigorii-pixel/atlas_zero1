from __future__ import annotations
import csv, json
from .database import Database
from .paths import EXPORTS, FRANKLIN
from .events import EventBus

class AcceptanceCenter:
    """Local acceptance layer for getting one real project to working state."""
    def __init__(self, db: Database, project_id: str='franklin'):
        self.db=db; self.project_id=project_id; self.bus=EventBus(db, project_id)
        self.export_dir=EXPORTS/project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def evaluate_franklin_working_state(self) -> dict:
        assets=self._count('assets')
        shots=self._count('shots')
        decisions=self._count('director_decisions')
        qc=self.db.one('SELECT readiness,summary FROM quality_reports WHERE project_id=? ORDER BY id DESC LIMIT 1',(self.project_id,))
        api_jobs=self._count('api_jobs')
        exports=list((EXPORTS/self.project_id).glob('*')) if (EXPORTS/self.project_id).exists() else []
        assigned=self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status='assigned'", (self.project_id,))['c'] if shots else 0
        missing=shots-assigned
        checks=[
            ('Проект Franklin обнаружен', FRANKLIN.exists()),
            ('Материалы проиндексированы', assets>=8),
            ('Монтажный лист построен', shots>=120),
            ('Решения режиссёра созданы', decisions>=min(shots, 80)),
            ('Контроль качества выполнен', qc is not None),
            ('Очередь недостающих материалов создана', api_jobs>=max(1, missing//2) if missing else True),
            ('Экспортный пакет создан', len(exports)>=6),
            ('CapCut handoff доступен', (self.export_dir/'capcut_пакет.csv').exists() or (self.export_dir/'capcut_guide.md').exists()),
        ]
        passed=sum(1 for _, ok in checks if ok)
        working_ready=passed==len(checks)
        report={
            'project_id': self.project_id,
            'franklin_local_working_ready': working_ready,
            'score': round(passed/len(checks)*100,1),
            'assets': assets,
            'shots': shots,
            'assigned': assigned,
            'missing': missing,
            'qc_readiness': float(qc['readiness']) if qc else 0.0,
            'checks': [{'criterion':k,'passed':bool(v)} for k,v in checks],
            'important_note': 'Это готовность локального производственного пакета Franklin, не готовность всей Enterprise ОС к полноценной автономной работе.',
            'next_actions': self._next_actions(missing)
        }
        (self.export_dir/'franklin_acceptance_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        self._write_html(report)
        self.bus.emit('FRANKLIN_ACCEPTANCE_EVALUATED', report)
        return report

    def build_capcut_handoff(self) -> dict:
        shots=self.db.rows("""SELECT s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,s.emotion,s.status,s.transition,s.camera_motion,a.filename,a.path,a.media_type
            FROM shots s LEFT JOIN assets a ON s.assigned_asset_id=a.id WHERE s.project_id=? ORDER BY s.idx""",(self.project_id,))
        path=self.export_dir/'capcut_пакет.csv'
        with path.open('w', newline='', encoding='utf-8-sig') as f:
            w=csv.writer(f)
            w.writerow(['№','Начало','Конец','Длительность','Блок','Смысл','Визуальная задача','Эмоция','Материал','Тип','Путь','Камера','Переход','Статус'])
            for r in shots:
                w.writerow([r['idx'], self.tc(r['start_sec']), self.tc(r['end_sec']), round(r['end_sec']-r['start_sec'],2), r['block'], r['story_goal'], r['visual_need'], r['emotion'], r['filename'] or 'СОЗДАТЬ', r['media_type'] or '', r['path'] or '', r['camera_motion'], r['transition'], r['status']])
        md=self.export_dir/'capcut_guide.md'
        md.write_text(self._capcut_guide_text(shots),encoding='utf-8')
        missing=self.export_dir/'missing_prioritized.csv'
        rows=[r for r in shots if r['status']!='assigned']
        with missing.open('w', newline='', encoding='utf-8-sig') as f:
            w=csv.writer(f); w.writerow(['Приоритет','Шот','Таймкод','Что создать','Эмоция','Промпт Leonardo'])
            for i,r in enumerate(rows,1):
                prompt=f"Ultra photorealistic historical documentary frame. {r['visual_need']}. {r['story_goal']}. Emotion: {r['emotion']}. Franklin Expedition, Arctic realism, cold blue-gray palette, BBC/Netflix documentary quality."
                w.writerow([i,r['idx'],self.tc(r['start_sec']),r['visual_need'],r['emotion'],prompt])
        return {'capcut_csv':str(path),'guide':str(md),'missing':str(missing),'shots':len(shots),'missing_count':len(rows)}

    def _capcut_guide_text(self, shots) -> str:
        assigned=sum(1 for r in shots if r['status']=='assigned')
        missing=len(shots)-assigned
        return f"""# ATLAS ZERO — CapCut handoff Franklin

## Статус пакета
- Всего шотов: {len(shots)}
- Назначено материалов: {assigned}
- Требуется создать/заменить: {missing}

## Порядок работы в CapCut
1. Импортируй все материалы из `workspace/projects/franklin/02_Images` и `03_Video`.
2. Импортируй аудио из `01_Audio`.
3. Открой файл `capcut_пакет.csv`.
4. Собирай дорожку по строкам: таймкод → материал → движение камеры → переход.
5. Все строки со статусом `missing` закрывай из `missing_prioritized.csv`.
6. После сборки сделай экспорт черновика и верни его на анализ QC.

## Важно
Это рабочий handoff-пакет. Он не заменяет нативный CapCut API, которого для desktop-монтажа в полном виде нет в открытом доступе.
"""

    def _write_html(self, report: dict):
        checks=''.join(f"<tr><td>{c['criterion']}</td><td class='{'ok' if c['passed'] else 'bad'}'>{'Да' if c['passed'] else 'Нет'}</td></tr>" for c in report['checks'])
        actions=''.join(f"<li>{a}</li>" for a in report['next_actions'])
        html=f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>Franklin Acceptance</title>
<style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e5e7eb;margin:24px;font-size:13px}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:16px;margin:12px 0}}.ok{{color:#22c55e}}.bad{{color:#ef4444}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #334155;padding:8px}}</style>
<h1>Franklin — рабочая готовность локального проекта</h1>
<div class='card'><b>Готовность:</b> {report['score']}%<br><b>Статус:</b> {'ГОТОВ к локальной производственной работе' if report['franklin_local_working_ready'] else 'НЕ ГОТОВ'}<br><b>Материалы:</b> {report['assets']} · <b>Шоты:</b> {report['shots']} · <b>Назначено:</b> {report['assigned']} · <b>Нужно создать:</b> {report['missing']}<br><p>{report['important_note']}</p></div>
<div class='card'><h2>Проверки</h2><table><tr><th>Критерий</th><th>Пройден</th></tr>{checks}</table></div>
<div class='card'><h2>Следующие действия</h2><ol>{actions}</ol></div>
</html>"""
        (self.export_dir/'franklin_acceptance.html').write_text(html,encoding='utf-8')

    def _next_actions(self, missing:int) -> list[str]:
        if missing:
            return [f'Закрыть {missing} недостающих шотов по файлу missing_prioritized.csv.', 'Открыть capcut_пакет.csv и собрать черновой монтаж.', 'После черновика прогнать QC повторно.']
        return ['Открыть capcut_пакет.csv.', 'Собрать финальный монтаж в CapCut/DaVinci.', 'Провести финальный QC.']

    def tc(self, sec: float) -> str:
        sec=max(0,float(sec)); h=int(sec//3600); m=int((sec%3600)//60); s=int(sec%60); ms=int((sec-int(sec))*1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    def _count(self, table:str) -> int:
        row=self.db.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
        if not row: return 0
        try:
            if table in ('assets','shots','director_decisions','api_jobs'):
                return self.db.one(f'SELECT COUNT(*) c FROM {table} WHERE project_id=?',(self.project_id,))['c']
            return self.db.one(f'SELECT COUNT(*) c FROM {table}')['c']
        except Exception:
            return 0
