from __future__ import annotations
import csv, json, os
from pathlib import Path
from .database import Database
from .events import EventBus
from .paths import EXPORTS, WORKSPACE, FRANKLIN

class OperatorConsole:
    """RC1 Alpha 1.0 operator layer.

    Goal: make one real project (Franklin) executable by a human operator today,
    without pretending that full autonomous live API execution is complete.
    Produces runbooks, task queue, validation and handoff checklist.
    """
    REQUIRED_EXPORTS = [
        'монтажный_лист.csv', 'timeline_enterprise.json', 'timeline_viewer.html',
        'capcut_пакет.csv', 'capcut_guide.md', 'missing_prioritized.csv',
        'визуальный_анализ.csv', 'решения_режиссера.json', 'franklin_acceptance.html',
        'preflight_report.html', 'command_center.html', 'release_center.html'
    ]

    def __init__(self, db: Database, project_id: str='franklin'):
        self.db=db; self.project_id=project_id; self.bus=EventBus(db, project_id)
        self.export_dir=EXPORTS/project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def build_operator_plan(self) -> dict:
        self.db.execute('DELETE FROM operator_tasks WHERE project_id=?', (self.project_id,))
        self.db.execute('DELETE FROM runbook_items WHERE project_id=?', (self.project_id,))
        self.db.execute('DELETE FROM export_validations WHERE project_id=?', (self.project_id,))
        validation=self.validate_exports()
        tasks=[]
        missing=self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status!='assigned'", (self.project_id,))['c']
        duplicates=self.db.one("SELECT COUNT(*) c FROM asset_similarity WHERE project_id=? AND score>=0.92", (self.project_id,))['c']
        api_ready=self.db.one("SELECT COUNT(*) c FROM api_credentials_checks WHERE project_id=? AND status LIKE 'credential_found%'", (self.project_id,))
        api_count=api_ready['c'] if api_ready else 0
        if missing:
            tasks.append((1,'Закрыть недостающие материалы',f'Сгенерировать или заменить {missing} шотов из missing_prioritized.csv'))
        if duplicates:
            tasks.append((2,'Проверить похожие ассеты',f'Найдено потенциальных повторов: {duplicates}. Проверить файл похожие_ассеты.csv'))
        if api_count == 0:
            tasks.append((1,'Подключить live API', 'Добавить ключи в .env: LEONARDO_API_KEY, ELEVENLABS_API_KEY, OPENAI_API_KEY, YOUTUBE credentials'))
        tasks += [
            (1,'Импортировать CapCut-пакет', 'Открыть capcut_guide.md и последовательно импортировать capcut_пакет.csv в CapCut'),
            (2,'Проверить первые 60 секунд', 'Собрать вступление Franklin вручную по timeline_viewer.html и проверить удержание внимания'),
            (3,'Сделать финальный QC-проход', 'После монтажа экспортировать preview и прогнать контроль качества заново')
        ]
        for priority,title,details in tasks:
            self.db.execute('INSERT INTO operator_tasks(project_id,priority,title,status,details) VALUES(?,?,?,?,?)',
                            (self.project_id, priority, title, 'open', details))
        self._create_runbook()
        self._export_files(validation)
        self.bus.emit('OPERATOR_PLAN_BUILT', {'tasks':len(tasks), 'missing':missing, 'export_validations':len(validation)})
        return {'tasks':len(tasks),'missing':missing,'duplicates':duplicates,'api_credentials_found':api_count,'exports_checked':len(validation),'operator_ready':True}

    def validate_exports(self) -> list[dict]:
        rows=[]
        for name in self.REQUIRED_EXPORTS:
            p=self.export_dir/name
            exists=p.exists()
            size=p.stat().st_size if exists else 0
            comment='OK' if exists and size>0 else 'Нужно пересоздать экспорт'
            self.db.execute('INSERT INTO export_validations(project_id,artifact,exists_flag,size_bytes,comment) VALUES(?,?,?,?,?)',
                            (self.project_id, name, 1 if exists else 0, size, comment))
            rows.append({'artifact':name,'exists':exists,'size_bytes':size,'comment':comment})
        return rows

    def _create_runbook(self):
        steps=[
            ('Подготовка',1,'Запустить start_pipeline.bat','Созданы exports/franklin и отчёты','start_pipeline.bat'),
            ('Проверка',2,'Открыть preflight_report.html','Понятны блокеры рабочей станции','workspace/exports/franklin/preflight_report.html'),
            ('Материалы',3,'Открыть visual_contact_sheet.jpg и визуальный_анализ.csv','Проверена визуальная библиотека','workspace/exports/franklin/визуальный_анализ.csv'),
            ('Монтаж',4,'Открыть timeline_viewer.html','Понятен видеоряд 165 шотов','workspace/exports/franklin/timeline_viewer.html'),
            ('CapCut',5,'Открыть capcut_guide.md','Понятны шаги импорта в CapCut','workspace/exports/franklin/capcut_guide.md'),
            ('Недостающее',6,'Открыть missing_prioritized.csv','Понятно, какие кадры генерировать первыми','workspace/exports/franklin/missing_prioritized.csv'),
            ('Контроль',7,'Открыть franklin_acceptance.html','Проверена локальная готовность Franklin','workspace/exports/franklin/franklin_acceptance.html'),
            ('API',8,'Заполнить .env и проверить api_готовность.json','Интеграции подготовлены к live-режиму','.env.example'),
            ('Финал',9,'После сборки в CapCut экспортировать preview и обновить QC','Фильм готовится к публикации','06_Export')
        ]
        for stage,no,action,expected,artifact in steps:
            self.db.execute('INSERT INTO runbook_items(project_id,stage,step_no,action,expected_result,artifact_path) VALUES(?,?,?,?,?,?)',
                            (self.project_id,stage,no,action,expected,artifact))

    def _export_files(self, validation: list[dict]):
        # tasks csv
        rows=self.db.rows('SELECT priority,title,status,details FROM operator_tasks WHERE project_id=? ORDER BY priority,id',(self.project_id,))
        p=self.export_dir/'операторские_задачи.csv'
        with p.open('w', newline='', encoding='utf-8-sig') as f:
            w=csv.writer(f); w.writerow(['Приоритет','Задача','Статус','Детали'])
            for r in rows: w.writerow([r['priority'],r['title'],r['status'],r['details']])
        # runbook md
        rb=self.db.rows('SELECT stage,step_no,action,expected_result,artifact_path FROM runbook_items WHERE project_id=? ORDER BY step_no',(self.project_id,))
        md=['# ATLAS ZERO Franklin — операторский runbook\n']
        for r in rb:
            md.append(f"## {r['step_no']}. {r['stage']}\n**Действие:** {r['action']}\n\n**Результат:** {r['expected_result']}\n\n**Артефакт:** `{r['artifact_path']}`\n")
        (self.export_dir/'franklin_operator_runbook.md').write_text('\n'.join(md), encoding='utf-8')
        # validation json/html
        (self.export_dir/'export_validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')
        html_rows=''.join(f"<tr><td>{v['artifact']}</td><td>{'Да' if v['exists'] else 'Нет'}</td><td>{v['size_bytes']}</td><td>{v['comment']}</td></tr>" for v in validation)
        (self.export_dir/'operator_console.html').write_text(f'''<!doctype html><meta charset="utf-8"><title>Операторский центр Franklin</title>
<style>body{{font-family:Arial;background:#0f172a;color:#e5e7eb;padding:24px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #334155;padding:8px;text-align:left}}.ok{{color:#22c55e}}.bad{{color:#f97316}}</style>
<h1>Операторский центр Franklin</h1><p>Цель: довести один проект до рабочего монтажного состояния без ложного статуса полной автономии.</p>
<h2>Проверка экспортов</h2><table><tr><th>Артефакт</th><th>Есть</th><th>Размер</th><th>Комментарий</th></tr>{html_rows}</table>
<p>Следующее: открыть <b>franklin_operator_runbook.md</b> и выполнить пункты сверху вниз.</p>''', encoding='utf-8')
