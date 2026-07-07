from __future__ import annotations
import json, html
from .paths import EXPORTS
from .native_timeline import NativeTimelineModel

class TimelineViewer2:
    def __init__(self, db, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.export_dir=EXPORTS/project_id; self.export_dir.mkdir(parents=True,exist_ok=True)
    def build(self):
        NativeTimelineModel(self.db,self.project_id).build()
        shots=self.db.rows('''SELECT s.idx,s.start_sec,s.end_sec,s.block,s.visual_need,s.status,s.camera_motion,s.transition,a.filename asset FROM shots s LEFT JOIN assets a ON a.id=s.assigned_asset_id WHERE s.project_id=? ORDER BY s.idx''',(self.project_id,))
        duration=max([r['end_sec'] for r in shots], default=960)
        model={'duration_sec':duration,'tracks':{'video':[],'voice':[],'text':[],'qc':[]}}
        lanes=''
        for r in shots:
            left=(r['start_sec']/duration)*100 if duration else 0; width=max(((r['end_sec']-r['start_sec'])/duration)*100,0.3)
            color='#0ea5e9' if r['status']=='assigned' else '#f59e0b'
            title=html.escape(f"#{r['idx']} {r['block']} {r['asset'] or 'missing'}")
            lanes += f"<div class='clip' title='{title}' style='left:{left:.3f}%;width:{width:.3f}%;background:{color}'>{r['idx']}</div>"
            model['tracks']['video'].append(dict(r))
            if r['status']!='assigned': model['tracks']['qc'].append({'idx':r['idx'],'start_sec':r['start_sec'],'type':'missing_asset','message':'Нужно создать материал'})
        json_path=self.export_dir/'timeline_viewer_2_model.json'; json_path.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
        html_doc=f"""<!doctype html><meta charset='utf-8'><title>ATLAS Timeline Viewer 2</title><style>body{{background:#0b1220;color:#e5e7eb;font-family:Segoe UI,Arial;font-size:12px;margin:20px}}.timeline{{position:relative;height:88px;background:#111827;border:1px solid #334155;border-radius:12px;overflow:hidden}}.clip{{position:absolute;top:18px;height:52px;border-radius:6px;overflow:hidden;white-space:nowrap;font-size:10px;color:#001018;text-align:center}}.legend span{{display:inline-block;margin-right:18px}}.blue{{color:#0ea5e9}}.yellow{{color:#f59e0b}}</style><h1>Нативная модель Timeline Viewer 2</h1><div class='legend'><span class='blue'>■ назначено</span><span class='yellow'>■ нужно создать</span><span>Длительность: {duration:.1f} сек · Шотов: {len(shots)}</span></div><div class='timeline'>{lanes}</div><h2>QC-маркеры</h2><pre>{html.escape(json.dumps(model['tracks']['qc'][:80], ensure_ascii=False, indent=2))}</pre>"""
        html_path=self.export_dir/'timeline_viewer_2.html'; html_path.write_text(html_doc,encoding='utf-8')
        return {'shots':len(shots),'duration_sec':duration,'qc_markers':len(model['tracks']['qc']),'json':str(json_path),'html':str(html_path)}
