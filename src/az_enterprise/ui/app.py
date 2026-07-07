from __future__ import annotations
import json, subprocess, sys, webbrowser, threading, queue
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from az_enterprise.core.database import Database
from az_enterprise.core.workflow import WorkflowEngine
from az_enterprise.core.pipeline_runtime import PipelineRunManager
from az_enterprise.core.paths import EXPORTS, DB_PATH

BG = '#08111f'; PANEL = '#0b1424'; CARD = '#101b2d'; CARD2 = '#14243a'; TEXT = '#e8eef8'; MUTED = '#91a3ba'; ACCENT = '#38bdf8'; GOOD='#22c55e'; WARN='#f59e0b'; BAD='#ef4444'

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ATLAS ZERO Enterprise RC1 Alpha 2.4 — Director AI Runtime')
        self.geometry('1366x820')
        self.configure(bg=BG)
        self.db = Database(); self.db.init()
        self.pipeline_queue = queue.Queue()
        self.pipeline_running = False
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('.', font=('Segoe UI', 8), background=BG, foreground=TEXT)
        self.style.configure('Treeview', font=('Segoe UI', 7), rowheight=20, background='#0b1220', fieldbackground='#0b1220', foreground=TEXT)
        self.style.configure('Treeview.Heading', font=('Segoe UI', 7, 'bold'), background='#d9d7cf', foreground='#111827')
        self.style.configure('TButton', font=('Segoe UI', 8), padding=5)
        self.sections = ['Командный центр','Проектный мозг','Граф конвейера','Story Engine','Director AI 2.4','Native Viewer Pro','Franklin E2E','Конвейер','Live Run Console','Менеджер задач','Материалы','Визуальный анализ','Шоты','Решения','Интеграции','API-очередь','API-запуски','Preflight','Оператор','Рабочее состояние','Live API','Операторский таймлайн','Монтажная мастерская','Local Autopilot','Native Timeline','Native Viewer RC','CV Runtime 2.2','Live Connectors','Live API Test','CV Review Board','Timeline Viewer 2','Центр тестирования','Final Assembly Pack','CapCut Bridge','План RC1','Готовность RC1','События','Production State','Franklin готовность','Экспорт']
        self._build()
        self.show('Командный центр')

    def _build(self):
        top = tk.Frame(self,bg='#020617',height=42); top.pack(fill='x')
        tk.Label(top,text='ATLAS ZERO ENTERPRISE RC1',bg='#020617',fg=TEXT,font=('Segoe UI',11,'bold')).pack(side='left',padx=14)
        tk.Label(top,text='Franklin · Alpha 2.4 · Director AI / quality / tasks',bg='#020617',fg=MUTED,font=('Segoe UI',8)).pack(side='left')
        tk.Button(top,text='Запустить конвейер',command=self.run_pipeline,bg='#075985',fg='white',font=('Segoe UI',8),relief='flat').pack(side='right',padx=6,pady=6)
        tk.Button(top,text='Открыть экспорт',command=self.open_exports,bg='#334155',fg='white',font=('Segoe UI',8),relief='flat').pack(side='right',padx=6,pady=6)
        body = tk.Frame(self,bg=BG); body.pack(fill='both',expand=True)
        side = tk.Frame(body,bg=PANEL,width=218); side.pack(side='left',fill='y'); side.pack_propagate(False)

        # Scrollable menu: no hidden items on 1366x768 screens.
        menu_canvas = tk.Canvas(side, bg=PANEL, highlightthickness=0, width=218)
        menu_scroll = ttk.Scrollbar(side, orient='vertical', command=menu_canvas.yview)
        menu_canvas.configure(yscrollcommand=menu_scroll.set)
        menu_canvas.pack(side='left', fill='both', expand=True)
        menu_scroll.pack(side='right', fill='y')
        menu_frame = tk.Frame(menu_canvas, bg=PANEL)
        menu_canvas.create_window((0, 0), window=menu_frame, anchor='nw')
        menu_frame.bind('<Configure>', lambda e: menu_canvas.configure(scrollregion=menu_canvas.bbox('all')))
        menu_canvas.bind_all('<MouseWheel>', lambda e: menu_canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

        self.nav_buttons = {}
        for section_name in self.sections:
            b = tk.Button(menu_frame, text=section_name, anchor='w', command=lambda x=section_name:self.show(x),
                          bg=PANEL, fg=TEXT, activebackground=CARD, activeforeground='white',
                          font=('Segoe UI',7), relief='flat', padx=8, pady=4)
            b.pack(fill='x', padx=6, pady=1)
            self.nav_buttons[section_name] = b
        self.main = tk.Frame(body,bg=BG); self.main.pack(side='left',fill='both',expand=True)
        self.status = tk.Label(self,bg='#020617',fg=MUTED,text='Готово',anchor='w',font=('Segoe UI',8)); self.status.pack(fill='x')

    def clear(self):
        for w in self.main.winfo_children(): w.destroy()
        if hasattr(self, 'nav_buttons'):
            for b in self.nav_buttons.values(): b.configure(bg=PANEL, fg=TEXT)

    def title_label(self, text):
        tk.Label(self.main,text=text,bg=BG,fg=TEXT,font=('Segoe UI',13,'bold')).pack(anchor='w',padx=16,pady=(14,8))

    def card(self, parent, title, value, note=''):
        f=tk.Frame(parent,bg=CARD,highlightbackground='#334155',highlightthickness=1)
        tk.Label(f,text=title,bg=CARD,fg=MUTED,font=('Segoe UI',8)).pack(anchor='w',padx=10,pady=(8,0))
        tk.Label(f,text=value,bg=CARD,fg=TEXT,font=('Segoe UI',14,'bold')).pack(anchor='w',padx=10)
        tk.Label(f,text=note,bg=CARD,fg=MUTED,font=('Segoe UI',8)).pack(anchor='w',padx=10,pady=(0,8))
        return f

    def table(self, columns, rows):
        frame=tk.Frame(self.main,bg=BG); frame.pack(fill='both',expand=True,padx=16,pady=8)
        tree=ttk.Treeview(frame,columns=columns,show='headings')
        vs=ttk.Scrollbar(frame,orient='vertical',command=tree.yview); tree.configure(yscrollcommand=vs.set)
        for c in columns:
            tree.heading(c,text=c); tree.column(c,width=140,anchor='w')
        for r in rows:
            tree.insert('', 'end', values=r)
        tree.pack(side='left',fill='both',expand=True); vs.pack(side='right',fill='y')

    def show(self, name):
        self.clear(); self.title_label(name)
        if hasattr(self, 'nav_buttons') and name in self.nav_buttons:
            self.nav_buttons[name].configure(bg=CARD2, fg=ACCENT)
        if name=='Командный центр': self.command_center()
        elif name=='Проектный мозг': self.project_brain()
        elif name=='Граф конвейера': self.pipeline_graph()
        elif name=='Story Engine': self.story_runtime()
        elif name=='Director AI 2.4': self.director_ai_2_4()
        elif name=='Native Viewer Pro': self.native_viewer_pro()
        elif name=='Franklin E2E': self.franklin_e2e_runtime()
        elif name=='Конвейер': self.workflow()
        elif name=='Live Run Console': self.live_run_console()
        elif name=='Менеджер задач': self.task_manager()
        elif name=='Материалы': self.assets()
        elif name=='Визуальный анализ': self.visual_analysis()
        elif name=='Шоты': self.shots()
        elif name=='Решения': self.decisions()
        elif name=='Интеграции': self.integrations()
        elif name=='API-очередь': self.api_jobs()
        elif name=='API-запуски': self.api_runs()
        elif name=='Preflight': self.preflight()
        elif name=='Оператор': self.operator_console()
        elif name=='Рабочее состояние': self.working_state()
        elif name=='Live API': self.live_api()
        elif name=='Операторский таймлайн': self.operator_timeline()
        elif name=='Монтажная мастерская': self.montage_workbench()
        elif name=='Local Autopilot': self.local_autopilot()
        elif name=='Native Timeline': self.native_timeline()
        elif name=='Native Viewer RC': self.native_viewer_rc()
        elif name=='CV Runtime 2.2': self.cv_model()
        elif name=='Live Connectors': self.live_connectors()
        elif name=='Live API Test': self.live_api_test()
        elif name=='CV Review Board': self.cv_review_board()
        elif name=='Timeline Viewer 2': self.timeline_viewer_2()
        elif name=='Центр тестирования': self.test_center()
        elif name=='Final Assembly Pack': self.final_assembly_pack()
        elif name=='CapCut Bridge': self.capcut_bridge()
        elif name=='План RC1': self.rc1_plan()
        elif name=='Готовность RC1': self.readiness()
        elif name=='Production State': self.production_state()
        elif name=='Franklin готовность': self.franklin_acceptance()
        elif name=='События': self.events()
        elif name=='Экспорт': self.exports()

    def command_center(self):
        # Professional dashboard: current runtime, last run and production readiness.
        assets=self.db.one('SELECT COUNT(*) c FROM assets')['c'] if self.db.one('SELECT name FROM sqlite_master WHERE type="table" AND name="assets"') else 0
        shots=self.db.one('SELECT COUNT(*) c FROM shots')['c'] if self.db.one('SELECT name FROM sqlite_master WHERE type="table" AND name="shots"') else 0
        missing=self.db.one("SELECT COUNT(*) c FROM shots WHERE status='missing'")['c'] if shots else 0
        qc=self.db.one('SELECT readiness FROM quality_reports ORDER BY id DESC LIMIT 1')
        last=self.db.one('SELECT id,run_uid,status,progress,current_step,started_at,finished_at FROM pipeline_runs ORDER BY id DESC LIMIT 1') if self.db.one('SELECT name FROM sqlite_master WHERE type="table" AND name="pipeline_runs"') else None
        cv=self.db.one('SELECT COUNT(*) c, AVG(cinematic_grade) g, SUM(face_count) faces, SUM(scene_count) scenes FROM cv_asset_metadata WHERE project_id=?',('franklin',)) if self.db.one('SELECT name FROM sqlite_master WHERE type="table" AND name="cv_asset_metadata"') else None
        row=tk.Frame(self.main,bg=BG); row.pack(fill='x',padx=14,pady=6)
        cards=[('Материалы',str(assets),'в библиотеке'),('Шоты',str(shots),'структура фильма'),('Дефицит',str(missing),'нужно создать'),('QC',f"{qc['readiness'] if qc else 0}%",'готовность'),('Runtime', (last['status'] if last else 'idle'), (last['run_uid'] if last else 'нет запусков'))]
        for t,v,n in cards: self.card(row,t,v,n).pack(side='left',fill='x',expand=True,padx=4)
        row2=tk.Frame(self.main,bg=BG); row2.pack(fill='x',padx=14,pady=6)
        self.card(row2,'CV Runtime', 'готов' if cv else 'нет данных', f"grade {round(cv['g'] or 0,2) if cv else 0} · faces {cv['faces'] or 0 if cv else 0} · scenes {cv['scenes'] or 0 if cv else 0}").pack(side='left',fill='x',expand=True,padx=4)
        self.card(row2,'Последний Run', str(last['id']) if last else '—', f"{last['progress'] if last else 0}% · {last['current_step'] if last else 'idle'}").pack(side='left',fill='x',expand=True,padx=4)
        self.card(row2,'Live API', self._api_summary()[0], self._api_summary()[1]).pack(side='left',fill='x',expand=True,padx=4)
        graph=tk.Frame(self.main,bg=CARD,highlightbackground='#24364e',highlightthickness=1); graph.pack(fill='both',expand=True,padx=14,pady=8)
        tk.Label(graph,text='ГРАФ КОНВЕЙЕРА',bg=CARD,fg=TEXT,font=('Segoe UI',9,'bold')).pack(anchor='w',padx=10,pady=(8,4))
        self._draw_pipeline_graph(graph, last['id'] if last else None, compact=True)

    def _api_summary(self):
        try:
            rows=self.db.rows('SELECT status FROM integration_profiles')
            if not rows: return ('не настроен','0 сервисов')
            ok=sum(1 for r in rows if r['status'] in ('configured','connected'))
            return (f'{ok}/{len(rows)}', 'configured/connected')
        except Exception:
            return ('—','нет данных')

    def _draw_pipeline_graph(self, parent, run_id=None, compact=False):
        """Render pipeline graph safely. This method is intentionally self-contained
        so the UI can never crash if graph data is missing or the DB is old."""
        try:
            if run_id:
                rows = self.db.rows(
                    "SELECT step_order,title,status,progress FROM pipeline_stage_graph WHERE run_id=? ORDER BY step_order",
                    (run_id,),
                )
            else:
                rows = []
            if not rows:
                rows = [
                    {"step_order":1,"title":"Preflight","status":"queued","progress":0},
                    {"step_order":2,"title":"Анализ материалов","status":"queued","progress":0},
                    {"step_order":3,"title":"CV Runtime","status":"queued","progress":0},
                    {"step_order":4,"title":"Director AI","status":"queued","progress":0},
                    {"step_order":5,"title":"Timeline","status":"queued","progress":0},
                    {"step_order":6,"title":"Экспорт","status":"queued","progress":0},
                ]
            wrap = tk.Frame(parent, bg=CARD)
            wrap.pack(fill='both', expand=True, padx=8, pady=6)
            max_cols = 4 if compact else 3
            color = {'queued':'#334155','running':'#0ea5e9','completed':'#16a34a','done':'#16a34a','failed':'#dc2626','error':'#dc2626'}
            for idx, r in enumerate(rows):
                status = (r['status'] if isinstance(r, dict) else r['status']) or 'queued'
                title = (r['title'] if isinstance(r, dict) else r['title']) or ''
                order = (r['step_order'] if isinstance(r, dict) else r['step_order']) or idx+1
                progress = (r['progress'] if isinstance(r, dict) else r['progress']) or 0
                box = tk.Frame(wrap, bg='#0b1220', highlightbackground=color.get(status, '#334155'), highlightthickness=2)
                box.grid(row=idx//max_cols, column=idx%max_cols, sticky='nsew', padx=5, pady=5)
                tk.Label(box, text=f"{int(order):02d}", bg='#0b1220', fg=ACCENT, font=('Segoe UI',9,'bold')).pack(anchor='w', padx=8, pady=(6,0))
                tk.Label(box, text=title[:48], bg='#0b1220', fg=TEXT, font=('Segoe UI',8,'bold'), wraplength=260, justify='left').pack(anchor='w', padx=8)
                tk.Label(box, text=f"{status} · {float(progress):.1f}%", bg='#0b1220', fg=MUTED, font=('Segoe UI',7)).pack(anchor='w', padx=8, pady=(0,6))
            for col in range(max_cols):
                wrap.grid_columnconfigure(col, weight=1)
        except Exception as e:
            tk.Label(parent, text=f'Граф конвейера недоступен: {e}', bg=CARD, fg=BAD, font=('Segoe UI',8)).pack(anchor='w', padx=10, pady=8)

    def pipeline_graph(self):
        try:
            last = self.db.one('SELECT id,run_uid,status,progress,current_step FROM pipeline_runs ORDER BY id DESC LIMIT 1')
        except Exception:
            last = None
        header = tk.Frame(self.main, bg=CARD, highlightbackground='#334155', highlightthickness=1)
        header.pack(fill='x', padx=16, pady=8)
        if last:
            txt = f"Последний запуск: {last['run_uid']} · {last['status']} · {last['progress']}% · {last['current_step']}"
        else:
            txt = 'Запусков пока нет. Нажмите «Запустить конвейер».'
        tk.Label(header, text=txt, bg=CARD, fg=TEXT, font=('Segoe UI',9,'bold')).pack(anchor='w', padx=10, pady=10)
        graph = tk.Frame(self.main, bg=CARD, highlightbackground='#24364e', highlightthickness=1)
        graph.pack(fill='both', expand=True, padx=16, pady=8)
        self._draw_pipeline_graph(graph, last['id'] if last else None, compact=False)


    def story_runtime(self):
        try:
            from az_enterprise.core.story_engine_runtime import StoryEngineRuntime
            report = StoryEngineRuntime(self.db).build()
            rows=[
                ('Версия', report.get('version','2.3')),
                ('Сцен построено', report['scenes']),
                ('Шотов в монтажном листе', report['shots']),
                ('Назначено материалов', report['assigned']),
                ('Недостаёт материалов', report['missing']),
                ('Готовность Story Engine', str(report['readiness'])+'%'),
                ('CV', f"assets {report['cv_summary']['assets_with_cv']} · faces {report['cv_summary']['faces_total']} · scenes {report['cv_summary']['scene_candidates_total']} · grade {report['cv_summary']['avg_cinematic_grade']}"),
            ]
            rows += [(f"Сцена {s['scene_id']} · {s['title']}", f"{s['shot_count']} шотов · покрытие {s['coverage']}% · дефицит {s['missing_count']} · {s['risk']}") for s in report['scene_reports']]
            rows += [('Рекомендация', x) for x in report['recommendations']]
            rows += [('HTML', str(EXPORTS/'franklin'/'story_engine_2_3.html'))]
            rows += [('Монтажный лист CSV', str(EXPORTS/'franklin'/'montage_sheet.csv'))]
            rows += [('Недостающие материалы', str(EXPORTS/'franklin'/'missing_story_requirements.md'))]
            self.table(['Пункт','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def native_viewer_pro(self):
        try:
            from az_enterprise.core.native_viewer_pro import NativeViewerPro
            report = NativeViewerPro(self.db).build()
            rows=[('Шотов',report['shots']),('Назначено',report['assigned']),('Дефицит',report['missing']),('HTML',report['html']),('JSON',report['json']),('Действие','Откройте native_viewer_pro.html из экспорта для просмотра фильма с CV-метаданными')]
            self.table(['Пункт','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def franklin_e2e_runtime(self):
        try:
            from az_enterprise.core.franklin_e2e_runtime import FranklinE2ERuntime
            report = FranklinE2ERuntime(self.db).evaluate()
            rows=[('E2E готовность', str(report['score'])+'%'),('Local E2E Ready','Да' if report['local_e2e_ready'] else 'Нет'),('Материалы',report['assets']),('Шоты',report['shots']),('Назначено',report['assigned']),('Дефицит',report['missing']),('CV assets',report['cv_assets'])]
            rows += [(f"Артефакт {k}", 'OK' if v else 'MISSING') for k,v in report['artifacts'].items()]
            rows += [('Следующее действие', a) for a in report['next_actions']]
            rows += [('HTML', str(EXPORTS/'franklin'/'franklin_e2e_runtime.html'))]
            self.table(['Пункт','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def project_brain(self):
        rows=self.db.rows('SELECT criterion,score,passed,comment FROM readiness_checks ORDER BY id')
        self.table(['Критерий','Оценка','Пройден','Комментарий'], [(r['criterion'], f"{r['score']:.2f}", 'Да' if r['passed'] else 'Нет', r['comment']) for r in rows])

    def workflow(self):
        rows=self.db.rows('SELECT stage,status,details,created_at FROM workflow_jobs ORDER BY id DESC LIMIT 100')
        self.table(['Этап','Статус','Детали','Время'], [(r['stage'],r['status'],r['details'],r['created_at']) for r in rows])


    def task_manager(self):
        top=tk.Frame(self.main,bg=BG); top.pack(fill='x',padx=14,pady=4)
        tk.Button(top,text='Обновить',command=lambda:self.show('Менеджер задач'),bg='#24364e',fg='white',font=('Segoe UI',7),relief='flat').pack(side='left')
        tk.Button(top,text='Повторить ошибки последнего Run',command=self.retry_failed_last_run,bg='#7c2d12',fg='white',font=('Segoe UI',7),relief='flat').pack(side='left',padx=6)
        rows=self.db.rows('''SELECT q.run_id,q.task_uid,q.step_order,q.title,q.status,q.attempts,q.progress,q.started_at,q.finished_at,substr(coalesce(q.error,''),1,120) err
                             FROM pipeline_task_queue q ORDER BY q.run_id DESC, q.step_order LIMIT 500''')
        self.table(['Run','Task ID','№','Этап','Статус','Попытки','Прогресс','Старт','Финиш','Ошибка'],
                   [(r['run_id'],r['task_uid'],r['step_order'],r['title'],r['status'],r['attempts'],r['progress'],r['started_at'] or '',r['finished_at'] or '',r['err']) for r in rows])

    def retry_failed_last_run(self):
        try:
            last=self.db.one('SELECT id FROM pipeline_runs ORDER BY id DESC LIMIT 1')
            if not last:
                self.status.config(text='Нет запусков для повтора')
                return
            result=PipelineRunManager(Database()).retry_failed_tasks(last['id'])
            self.status.config(text=f"Повторено задач: {result.get('retried',0)}")
            self.show('Менеджер задач')
        except Exception as e:
            self.status.config(text=f'Ошибка повтора: {e}')

    def assets(self):
        rows=self.db.rows('SELECT filename,media_type,category,emotion,quality,duplicate_of FROM assets ORDER BY media_type, filename LIMIT 500')
        self.table(['Файл','Тип','Категория','Эмоция','Качество','Дубликат'], [(r['filename'],r['media_type'],r['category'],r['emotion'],r['quality'],r['duplicate_of'] or '') for r in rows])


    def visual_analysis(self):
        rows=self.db.rows("""SELECT a.filename,a.media_type,v.plan_type,v.palette,v.style_score,v.profile_json FROM visual_profiles v JOIN assets a ON a.id=v.asset_id ORDER BY v.style_score DESC LIMIT 500""")
        self.table(['Файл','Тип','План','Палитра','Стиль','Профиль'], [(r['filename'],r['media_type'],r['plan_type'],r['palette'],r['style_score'],r['profile_json']) for r in rows])

    def api_runs(self):
        rows=self.db.rows('SELECT service,mode,status,response_json,created_at FROM integration_runs ORDER BY id DESC LIMIT 300')
        self.table(['Сервис','Режим','Статус','Ответ','Время'], [(r['service'],r['mode'],r['status'],r['response_json'],r['created_at']) for r in rows])

    def shots(self):
        rows=self.db.rows('''SELECT s.idx,s.start_sec,s.end_sec,s.block,s.visual_need,s.status,a.filename asset FROM shots s LEFT JOIN assets a ON s.assigned_asset_id=a.id ORDER BY s.idx LIMIT 500''')
        self.table(['№','Начало','Конец','Блок','Потребность','Статус','Материал'], [(r['idx'],r['start_sec'],r['end_sec'],r['block'],r['visual_need'],r['status'],r['asset'] or '') for r in rows])

    def decisions(self):
        if self.db.one('SELECT name FROM sqlite_master WHERE type="table" AND name="director_decision_matrix"'):
            rows=self.db.rows('SELECT scene_id,shot_id,asset_id,decision,score,reason,action FROM director_decision_matrix WHERE project_id=? ORDER BY id DESC LIMIT 500', ('franklin',))
            self.table(['Сцена','Шот','Ассет','Решение','Оценка','Причина','Действие'], [(r['scene_id'],r['shot_id'],r['asset_id'],r['decision'],r['score'],r['reason'],r['action']) for r in rows])
        else:
            rows=self.db.rows('SELECT shot_id,score,reason,alternatives FROM director_decisions ORDER BY id LIMIT 500')
            self.table(['Шот','Оценка','Причина','Альтернативы'], [(r['shot_id'],r['score'],r['reason'],r['alternatives']) for r in rows])

    def director_ai_2_4(self):
        try:
            from az_enterprise.core.director_ai_runtime import DirectorAIRuntime
            report = DirectorAIRuntime(self.db).analyze()
            q=report['quality']; s=report['summary']
            rows=[
                ('Общее качество', str(q['overall'])+'%'),
                ('Покрытие', str(q['coverage'])+'%'),
                ('Разнообразие', str(q['diversity'])+'%'),
                ('CV качество', str(q['cv_quality'])+'%'),
                ('Повторы', str(q['repetition'])+'%'),
                ('API готовность', str(q['api'])+'%'),
                ('Проблем', s['issues']),
                ('Задач создано', s['tasks']),
                ('Блокирующих', s['blocking']),
                ('High', s['high']),
                ('Medium', s['medium']),
                ('HTML', str(EXPORTS/'franklin'/'director_ai_2_4.html')),
                ('Задачи CSV', str(EXPORTS/'franklin'/'director_tasks.csv')),
            ]
            rows += [('Следующее действие', a) for a in report.get('next_actions', [])]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def integrations(self):
        rows=self.db.rows('SELECT service,status,env_key,capabilities,last_check FROM integration_profiles ORDER BY service')
        self.table(['Сервис','Статус','ENV','Возможности','Проверка'], [(r['service'],r['status'],r['env_key'],r['capabilities'],r['last_check']) for r in rows])

    def api_jobs(self):
        rows=self.db.rows('SELECT service,job_type,status,payload,created_at FROM api_jobs ORDER BY id DESC LIMIT 300')
        self.table(['Сервис','Тип','Статус','Задание','Время'], [(r['service'],r['job_type'],r['status'],r['payload'],r['created_at']) for r in rows])


    def preflight(self):
        try:
            from az_enterprise.core.preflight import PreflightCenter
            report = PreflightCenter(self.db).run()
            rows = [('Итоговая оценка', str(report['score'])+'%'), ('Локальная готовность', 'Да' if report['local_ready'] else 'Нет'), ('Автономная готовность', 'Да' if report['autonomous_ready'] else 'Нет')]
            rows += [(c['title'], ('Да' if c['passed'] else 'Нет') + ' · ' + c['detail']) for c in report['checks']]
            rows += [('Следующее действие', a) for a in report['next_actions']]
            self.table(['Проверка','Результат'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])


    def operator_console(self):
        try:
            from az_enterprise.core.operator_console import OperatorConsole
            report = OperatorConsole(self.db).build_operator_plan()
            tasks = self.db.rows('SELECT priority,title,status,details FROM operator_tasks ORDER BY priority,id LIMIT 200')
            header=[('Операторская готовность','Да' if report['operator_ready'] else 'Нет'),('Задач','%s' % report['tasks']),('Недостающих шотов','%s' % report['missing']),('API-ключей найдено','%s' % report['api_credentials_found'])]
            rows=header + [(f"P{t['priority']} · {t['title']}", t['details']) for t in tasks]
            self.table(['Пункт','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])


    def working_state(self):
        try:
            from az_enterprise.core.working_state_auditor import WorkingStateAuditor
            report = WorkingStateAuditor(self.db).audit()
            rows=[
                ('Локальная production-готовность', 'Да' if report['local_production_ready'] else 'Нет'),
                ('Полная автономная готовность', 'Да' if report['full_autonomous_ready'] else 'Нет'),
                ('Материалы', report['assets']), ('Шоты', report['shots']),
                ('Назначено', report['assigned_shots']), ('Покрытие', str(report['coverage_pct'])+'%'),
                ('Live API', 'Да' if report['live_api_ready'] else 'Нет'),
                ('Экспертный статус', report['expert_status'])
            ]
            rows += [('Следующее действие', a) for a in report['next_actions']]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def live_api(self):
        try:
            from az_enterprise.core.live_api_layer import LiveApiLayer
            report = LiveApiLayer(self.db).inspect()
            rows=[('Live enabled', 'Да' if report['live_enabled'] else 'Нет'), ('Ключей найдено', report['credentials_present']), ('Сервисов', report['services'])]
            rows += [(r['service'], r['status'] + ' · ' + r['env_key']) for r in report['rows']]
            self.table(['Сервис','Статус'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def operator_timeline(self):
        try:
            from az_enterprise.core.final_timeline_viewer import FinalTimelineViewer
            report = FinalTimelineViewer(self.db).build()
            self.table(['Показатель','Значение'], [('Шотов', report['shots']), ('HTML', report['html']), ('JSON', report['json']), ('Действие', 'Откройте timeline_operator_view.html из папки exports/franklin')])
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])



    def montage_workbench(self):
        try:
            from az_enterprise.core.montage_workbench import MontageWorkbench
            report = MontageWorkbench(self.db).build()
            rows=[('Шотов', report['shots']), ('Назначено', report['assigned']), ('Нужно создать', report['missing']), ('Покрытие', str(report['coverage_pct'])+'%'), ('HTML', report['workbench_html']), ('CSV', report['operator_csv'])]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def local_autopilot(self):
        try:
            from az_enterprise.core.local_autopilot import LocalAutopilot
            report = LocalAutopilot(self.db).build()
            rows=[('Можно локально довести Franklin до черновика', 'Да' if report['local_finishable'] else 'Нет'), ('Покрытие', str(report['coverage_pct'])+'%'), ('Шотов', report['shots']), ('Назначено', report['assigned']), ('Нужно создать', report['missing']), ('Статус', report['expert_status'])]
            rows += [(f"Действие {i+1}", a) for i,a in enumerate(report['next_30_minutes'])]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])


    def native_timeline(self):
        try:
            from az_enterprise.core.native_timeline import NativeTimelineModel
            report = NativeTimelineModel(self.db).build()
            rows=[('Длительность', str(report['duration_sec'])+' сек'), ('Шотов', report['shots']), ('Нужно создать', report['missing']), ('JSON', report['json']), ('HTML', report['html']), ('Покрытие', str(report['stats'].get('coverage_pct'))+'%')]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])


    def cv_model(self):
        try:
            from az_enterprise.core.cv_model import CVModel
            report = CVModel(self.db).analyze()
            rows=[
                ('Движок', report['engine']),
                ('OpenCV', 'Да' if report.get('opencv_ready') else 'Нет'),
                ('Pillow fallback', 'Да' if report.get('pillow_ready') else 'Нет'),
                ('OCR', 'Да' if report.get('ocr_ready') else 'Нет'),
                ('Изображений', report['images']),
                ('Видео', report.get('videos',0)),
                ('Материалов проанализировано', report.get('assets_analyzed',0)),
                ('Сцен-кандидатов', report.get('scene_candidates',0)),
                ('Похожие пары', report['duplicate_pairs']),
                ('Кадров с лицами', report.get('assets_with_faces',0)),
                ('Проблемных материалов', report.get('bad_assets',0)),
                ('Размытых', report.get('blur_assets',0)),
                ('Тёмных', report.get('dark_assets',0)),
                ('Пересвет', report.get('overexposed_assets',0)),
                ('Средний cinematic grade', report['avg_cinematic_grade']),
                ('JSON', str(EXPORTS/'franklin'/'cv_model_report.json')),
                ('CSV', str(EXPORTS/'franklin'/'cv_asset_metadata.csv')),
                ('HTML', str(EXPORTS/'franklin'/'cv_runtime_report.html')),
            ]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def live_connectors(self):
        try:
            from az_enterprise.core.live_connectors import LiveConnectorHub
            report = LiveConnectorHub(self.db).export_report()
            rows=[('Validated/reachable', report['summary']['validated_or_reachable']), ('Credentials + live enabled', report['summary']['credential_live_enabled']), ('Paid allowed', 'Да' if report['summary']['paid_allowed'] else 'Нет'), ('JSON', report['json']), ('Guide', report['guide'])]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def native_viewer_rc(self):
        try:
            from az_enterprise.core.native_viewer_rc import NativeViewerRC
            report = NativeViewerRC(self.db).build_model()
            rows=[('Клипов', report['clips']), ('QC-маркеров', report['qc_markers']), ('Модель', report['model']), ('HTML', report['html']), ('CSV', report['csv']), ('Нативный просмотр', 'Запустите start_timeline_viewer.bat')]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])


    def live_api_test(self):
        try:
            from az_enterprise.core.live_api_test_suite import LiveApiTestSuite
            report = LiveApiTestSuite(self.db).run()
            rows=[('Режим', report['mode']), ('Сконфигурировано', f"{report['configured']}/{report['services_total']}"), ('Reachable', report['reachable']), ('Платные вызовы', 'Да' if report['paid_calls_allowed'] else 'Нет'), ('Готово к live-generation', 'Да' if report['ready_for_live_generation'] else 'Нет')]
            rows += [(r['service'], r['status'] + ' · ' + r.get('detail','')) for r in report['rows']]
            self.table(['Пункт','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def cv_review_board(self):
        try:
            from az_enterprise.core.cv_review_board import CVReviewBoard
            report = CVReviewBoard(self.db).build()
            rows=[('Материалов', report['items']), ('Флаги', report['flagged']), ('CSV', report['csv']), ('HTML', report['html'])]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def timeline_viewer_2(self):
        try:
            from az_enterprise.core.timeline_viewer_2 import TimelineViewer2
            report = TimelineViewer2(self.db).build()
            rows=[('Шотов', report['shots']), ('Длительность', str(report['duration_sec'])+' сек'), ('QC-маркеров', report['qc_markers']), ('JSON', report['json']), ('HTML', report['html'])]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])


    def test_center(self):
        try:
            from az_enterprise.core.test_center import TestCenter
            report = TestCenter(self.db).run()
            rows=[('Локальная готовность к тесту','Да' if report['local_ready_for_testing'] else 'Нет'),('Полная автономная готовность','Да' if report['full_autonomous_ready'] else 'Нет'),('Тестов',report['cases_total']),('Пройдено',report['passed']),('Провалено',report['failed']),('QC',str(report['qc_readiness'])+'%'),('Покрытие',str(report['coverage_pct'])+'%')]
            rows += [(c['suite']+' · '+c['title'], c['status']+' · '+str(c['actual'])) for c in report['cases']]
            self.table(['Проверка','Результат'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def final_assembly_pack(self):
        try:
            from az_enterprise.core.final_assembly_pack import FinalAssemblyPack
            report = FinalAssemblyPack(self.db).build()
            rows=[('Шотов', report['shots']), ('Назначено', report['assigned']), ('Нужно создать', report['missing']), ('Покрытие', str(report['coverage_pct'])+'%'), ('Папка', report['pack_dir']), ('Локальный черновик', 'Да' if report['ready_for_local_rough_cut'] else 'Нет')]
            rows += [('Блокер', b) for b in report['blockers']]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def capcut_bridge(self):
        try:
            from az_enterprise.core.capcut_bridge import CapCutBridge
            report = CapCutBridge(self.db).build()
            rows=[('Шотов', report['shots']), ('Назначено', report['assigned']), ('Нужно создать', report['missing']), ('HTML', report['html']), ('CSV', report['cut_list']), ('Bins', report['bins'])]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def rc1_plan(self):
        try:
            from az_enterprise.core.rc1_completion_planner import RC1CompletionPlanner
            report = RC1CompletionPlanner(self.db).plan()
            rows=[('Задач', report['tasks']), ('Missing', report['missing']), ('QC', str(report['qc'])+'%'), ('HTML', report['html']), ('CSV', report['csv'])]
            self.table(['Показатель','Значение'], rows)
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def readiness(self):
        self.project_brain()

    def events(self):
        rows=self.db.rows('SELECT type,payload,created_at FROM events ORDER BY id DESC LIMIT 300')
        self.table(['Событие','Данные','Время'], [(r['type'],r['payload'],r['created_at']) for r in rows])


    def production_state(self):
        try:
            from az_enterprise.core.production_state import ProductionState
            ps = ProductionState(self.db).summarize()
            rows = [
                ('Материалы', ps['assets']), ('Шоты', ps['shots']), ('Назначено', ps['assigned']),
                ('Нужно создать', ps['missing']), ('Покрытие', str(ps['coverage_pct'])+'%'),
                ('QC', str(ps['qc_readiness'])+'%'), ('API заданий', ps['api_jobs_ready']),
                ('Полная готовность', 'Да' if ps['full_work_ready'] else 'Нет')
            ]
            self.table(['Показатель','Значение'], rows + [('Блокер: '+b['title'], b['comment']) for b in ps.get('blockers', [])])
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])


    def franklin_acceptance(self):
        try:
            from az_enterprise.core.acceptance_center import AcceptanceCenter
            report = AcceptanceCenter(self.db).evaluate_franklin_working_state()
            rows = [(c['criterion'], 'Да' if c['passed'] else 'Нет') for c in report['checks']]
            rows = [('Итоговая готовность', str(report['score'])+'%'), ('Статус', 'Готов к локальной работе' if report['franklin_local_working_ready'] else 'Не готов')] + rows
            self.table(['Критерий','Значение'], rows + [('Следующее действие', a) for a in report['next_actions']])
        except Exception as e:
            self.table(['Ошибка'], [(str(e),)])

    def exports(self):
        exp=EXPORTS/'franklin'
        files=sorted(exp.glob('*')) if exp.exists() else []
        self.table(['Файл','Путь'], [(f.name,str(f)) for f in files])

    def live_run_console(self):
        # Rebuild a live console. If a run is active it will continue receiving updates.
        panel = tk.Frame(self.main, bg=CARD, highlightbackground='#334155', highlightthickness=1)
        panel.pack(fill='x', padx=16, pady=8)
        self.run_status_label = tk.Label(panel, text='Конвейер не запущен', bg=CARD, fg=TEXT, font=('Segoe UI',9,'bold'))
        self.run_status_label.pack(anchor='w', padx=10, pady=(8,4))
        self.run_progress = ttk.Progressbar(panel, orient='horizontal', mode='determinate', maximum=100)
        self.run_progress.pack(fill='x', padx=10, pady=(0,8))
        btnrow = tk.Frame(panel,bg=CARD); btnrow.pack(fill='x', padx=10, pady=(0,8))
        tk.Button(btnrow,text='Запустить полный конвейер',command=self.run_pipeline,bg='#075985',fg='white',font=('Segoe UI',8),relief='flat').pack(side='left',padx=(0,8))
        tk.Button(btnrow,text='Открыть экспорт',command=self.open_exports,bg='#334155',fg='white',font=('Segoe UI',8),relief='flat').pack(side='left')
        self.run_log_text = tk.Text(self.main,bg='#020617',fg=TEXT,insertbackground=TEXT,font=('Consolas',7),height=24,relief='flat')
        self.run_log_text.pack(fill='both',expand=True,padx=16,pady=8)
        self.run_log_text.insert('end','Live Run Console готов. Нажмите «Запустить полный конвейер».\n')
        # show recent logs if present
        try:
            last = self.db.one('SELECT id,status,progress FROM pipeline_runs ORDER BY id DESC LIMIT 1')
            if last:
                self.run_log_text.insert('end', f"Последний запуск: #{last['id']} / {last['status']} / {last['progress']}%\n")
                logs=self.db.rows('SELECT level,message,created_at FROM pipeline_logs WHERE run_id=? ORDER BY id DESC LIMIT 25',(last['id'],))
                for r in reversed(logs):
                    self.run_log_text.insert('end', f"{r['created_at']} [{r['level']}] {r['message']}\n")
        except Exception:
            pass

    def run_pipeline(self):
        if self.pipeline_running:
            self.status.config(text='Конвейер уже выполняется')
            return
        self.show('Live Run Console')
        self.pipeline_running = True
        self.status.config(text='Конвейер запущен...')
        if hasattr(self, 'run_status_label'):
            self.run_status_label.config(text='Конвейер выполняется...')
        if hasattr(self, 'run_progress'):
            self.run_progress['value']=0
        if hasattr(self, 'run_log_text'):
            self.run_log_text.insert('end','\n=== Новый запуск конвейера ===\n')
            self.run_log_text.see('end')

        def cb(event):
            self.pipeline_queue.put(event)

        def worker():
            try:
                PipelineRunManager(Database()).run(cb=cb)
            except Exception as e:
                self.pipeline_queue.put({'type':'error','message':str(e)})

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self._poll_pipeline_queue)

    def _poll_pipeline_queue(self):
        try:
            while True:
                ev = self.pipeline_queue.get_nowait()
                typ = ev.get('type')
                if typ == 'run_started':
                    if hasattr(self,'run_log_text'):
                        self.run_log_text.insert('end', f"{ev.get('time','')} [RUN] {ev.get('message','')}\n"); self.run_log_text.see('end')
                elif typ in ('step_start','step_done'):
                    pct = float(ev.get('progress',0))
                    if hasattr(self,'run_progress'): self.run_progress['value']=pct
                    if hasattr(self,'run_status_label'): self.run_status_label.config(text=f"{pct:.1f}% — {ev.get('title','')}")
                    if hasattr(self,'run_log_text'):
                        marker = '▶' if typ=='step_start' else '✓'
                        self.run_log_text.insert('end', f"{marker} {ev.get('title','')} — {pct:.1f}%\n")
                        self.run_log_text.see('end')
                elif typ == 'task_progress':
                    pct = float(ev.get('progress',0))
                    if hasattr(self,'run_progress'): self.run_progress['value']=pct
                    if hasattr(self,'run_status_label'): self.run_status_label.config(text=f"{pct:.1f}% — {ev.get('message','')}")
                    if hasattr(self,'run_log_text'):
                        self.run_log_text.insert('end', f"{ev.get('time','')} [PROGRESS] {ev.get('message','')} — {pct:.1f}%\n")
                        self.run_log_text.see('end')
                elif typ == 'task_started':
                    if hasattr(self,'run_log_text'):
                        self.run_log_text.insert('end', f"{ev.get('time','')} [TASK] ▶ {ev.get('message','')}\n")
                        self.run_log_text.see('end')
                elif typ == 'task_failed':
                    if hasattr(self,'run_log_text'):
                        self.run_log_text.insert('end', f"{ev.get('time','')} [FAILED] {ev.get('message','')}\n"); self.run_log_text.see('end')
                elif typ == 'task_completed':
                    if hasattr(self,'run_log_text'):
                        self.run_log_text.insert('end', f"{ev.get('time','')} [TASK] ✓ {ev.get('message','')}\n")
                        self.run_log_text.see('end')
                elif typ == 'log':
                    if hasattr(self,'run_log_text'):
                        self.run_log_text.insert('end', f"{ev.get('time','')} [{ev.get('level','')}] {ev.get('message','')}\n")
                        self.run_log_text.see('end')
                elif typ == 'finished':
                    self.pipeline_running = False
                    if hasattr(self,'run_progress'): self.run_progress['value']=100
                    if hasattr(self,'run_status_label'): self.run_status_label.config(text='100% — конвейер завершён')
                    self.status.config(text='Конвейер завершён. Отчёты сохранены в 06_Export / workspace/exports/franklin.')
                    self._refresh_dashboard_after_run()
                    return
                elif typ == 'error':
                    self.pipeline_running = False
                    msg = ev.get('message','Ошибка')
                    if hasattr(self,'run_status_label'): self.run_status_label.config(text=f'Ошибка: {msg}')
                    if hasattr(self,'run_log_text'):
                        self.run_log_text.insert('end', f"ERROR: {msg}\n{ev.get('traceback','')}\n")
                        self.run_log_text.see('end')
                    self.status.config(text='Ошибка конвейера')
                    return
        except queue.Empty:
            pass
        if self.pipeline_running:
            self.after(150, self._poll_pipeline_queue)

    def _refresh_dashboard_after_run(self):
        try:
            self.db = Database(); self.db.init()
        except Exception:
            pass

    def open_exports(self):
        exp=EXPORTS/'franklin'; exp.mkdir(parents=True,exist_ok=True)
        webbrowser.open(str(exp))

if __name__ == '__main__':
    App().mainloop()
