warning: in the working copy of 'src/az_enterprise/ui/app.py', LF will be replaced by CRLF the next time Git touches it
[1mdiff --git a/src/az_enterprise/ui/app.py b/src/az_enterprise/ui/app.py[m
[1mindex 0a4e5f4..ee6e0d8 100644[m
[1m--- a/src/az_enterprise/ui/app.py[m
[1m+++ b/src/az_enterprise/ui/app.py[m
[36m@@ -143,6 +143,7 @@[m [mclass App(tk.Tk):[m
         row2=tk.Frame(self.main,bg=BG); row2.pack(fill='x',padx=14,pady=6)[m
         self.card(row2,'CV Runtime', 'готов' if cv else 'нет данных', f"grade {round(cv['g'] or 0,2) if cv else 0} · faces {cv['faces'] or 0 if cv else 0} · scenes {cv['scenes'] or 0 if cv else 0}").pack(side='left',fill='x',expand=True,padx=4)[m
         self.card(row2,'Последний Run', str(last['id']) if last else '—', f"{last['progress'] if last else 0}% · {last['current_step'] if last else 'idle'}").pack(side='left',fill='x',expand=True,padx=4)[m
[32m+[m[32m        self.card(row2,'Director AI', self._director_ai_summary()[0], self._director_ai_summary()[1]).pack(side='left',fill='x',expand=True,padx=4)[m
         self.card(row2,'Live API', self._api_summary()[0], self._api_summary()[1]).pack(side='left',fill='x',expand=True,padx=4)[m
         graph=tk.Frame(self.main,bg=CARD,highlightbackground='#24364e',highlightthickness=1); graph.pack(fill='both',expand=True,padx=14,pady=8)[m
         tk.Label(graph,text='ГРАФ КОНВЕЙЕРА',bg=CARD,fg=TEXT,font=('Segoe UI',9,'bold')).pack(anchor='w',padx=10,pady=(8,4))[m
[36m@@ -157,6 +158,15 @@[m [mclass App(tk.Tk):[m
         except Exception:[m
             return ('—','нет данных')[m
 [m
[32m+[m[32m    def _director_ai_summary(self):[m
[32m+[m[32m        try:[m
[32m+[m[32m            missing=self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status='missing'", ('franklin',))['c'][m
[32m+[m[32m            tasks=self.db.one('SELECT COUNT(*) c FROM director_tasks WHERE project_id=?', ('franklin',))['c'][m
[32m+[m[32m            issues=self.db.one('SELECT COUNT(*) c FROM director_issues WHERE project_id=?', ('franklin',))['c'][m
[32m+[m[32m            return (f'{tasks} задач · {missing} missing', f'{issues} проблем для исправления')[m
[32m+[m[32m        except Exception:[m
[32m+[m[32m            return ('—','нет данных')[m
[32m+[m
     def _draw_pipeline_graph(self, parent, run_id=None, compact=False):[m
         """Render pipeline graph safely. This method is intentionally self-contained[m
         so the UI can never crash if graph data is missing or the DB is old."""[m
