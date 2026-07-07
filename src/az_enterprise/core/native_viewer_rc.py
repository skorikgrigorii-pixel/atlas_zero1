from __future__ import annotations
import json, csv
from .database import Database
from .paths import EXPORTS
from .events import EventBus

class NativeViewerRC:
    """Data model for the native timeline/viewer.

    Alpha 1.8 does not depend on a heavy video engine. It builds a structured viewer model
    with tracks, clips, markers, inspector payloads and validation data. The UI can render
    this model in Tkinter now and a Qt viewer later without changing the pipeline.
    """
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.export_dir=EXPORTS/project_id; self.bus=EventBus(db, project_id)

    def build_model(self) -> dict:
        rows=self.db.rows('''SELECT s.id,s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,s.emotion,s.status,s.camera_motion,s.transition,a.filename,a.path,a.media_type
                             FROM shots s LEFT JOIN assets a ON a.id=s.assigned_asset_id WHERE s.project_id=? ORDER BY s.idx''', (self.project_id,))
        tracks={'Видео':[],'Озвучка':[],'Субтитры':[],'QC':[]}
        for r in rows:
            clip={'shot_id':r['id'],'idx':r['idx'],'start':r['start_sec'],'end':r['end_sec'],'duration':round(r['end_sec']-r['start_sec'],2),'block':r['block'],'label':r['filename'] or r['visual_need'],'status':r['status'],'media_type':r['media_type'] or 'missing','path':r['path'] or '', 'camera':r['camera_motion'], 'transition':r['transition']}
            tracks['Видео'].append(clip)
            tracks['Субтитры'].append({'start':r['start_sec'],'end':r['end_sec'],'text':r['story_goal']})
            if r['status'] != 'assigned': tracks['QC'].append({'time':r['start_sec'],'level':'warn','text':'Не найден материал: '+(r['visual_need'] or '')})
        tracks['Озвучка'].append({'start':0,'end':max((c['end'] for c in tracks['Видео']), default=0),'label':'Единая озвучка фильма'})
        model={'project_id':self.project_id,'version':'native_viewer_rc_1_5','tracks':tracks,'duration_sec':tracks['Озвучка'][0]['end'] if tracks['Озвучка'] else 0,'clip_count':len(tracks['Видео']),'qc_markers':len(tracks['QC'])}
        p=self.export_dir/'native_viewer_model_rc.json'
        p.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding='utf-8')
        self._write_html(model)
        self._write_csv(model)
        self.bus.emit('NATIVE_VIEWER_RC_BUILT', {'clips':model['clip_count'],'qc_markers':model['qc_markers']})
        return {'model':str(p),'html':str(self.export_dir/'native_viewer_rc.html'),'csv':str(self.export_dir/'native_viewer_tracks.csv'),'clips':model['clip_count'],'qc_markers':model['qc_markers']}

    def _write_csv(self, model):
        p=self.export_dir/'native_viewer_tracks.csv'
        with p.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f); w.writerow(['Трек','№','Старт','Конец','Длительность','Блок','Статус','Медиа','Название'])
            for c in model['tracks']['Видео']:
                w.writerow(['Видео',c['idx'],c['start'],c['end'],c['duration'],c['block'],c['status'],c['media_type'],c['label']])

    def _write_html(self, model):
        dur=max(model['duration_sec'],1)
        rows=[]
        for c in model['tracks']['Видео']:
            left=100*c['start']/dur; width=max(.4,100*c['duration']/dur)
            color='#22c55e' if c['status']=='assigned' else '#f59e0b'
            rows.append(f"<div class='clip' title='#{c['idx']} {c['label']}' style='left:{left:.3f}%;width:{width:.3f}%;background:{color}'><span>{c['idx']}</span></div>")
        markers=''.join(f"<li>{m['time']:.1f}s — {m['text']}</li>" for m in model['tracks']['QC'][:80])
        html=f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>Native Viewer RC 1.5</title>
<style>body{{margin:0;background:#0f172a;color:#e5e7eb;font:12px Segoe UI,Arial}}header{{padding:12px 16px;background:#020617}}.wrap{{padding:16px}}.lane{{position:relative;height:56px;background:#111827;border:1px solid #334155;border-radius:8px;margin:10px 0;overflow:hidden}}.clip{{position:absolute;top:8px;height:38px;border-radius:5px;overflow:hidden;color:#020617;font-weight:700;font-size:10px;display:flex;align-items:center;justify-content:center}}.grid{{display:grid;grid-template-columns:2fr 1fr;gap:16px}}.panel{{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px}}li{{margin:6px 0}}</style>
<header><b>ATLAS ZERO — Native Timeline / Viewer RC 1.5</b> · Franklin · clips {model['clip_count']} · duration {model['duration_sec']:.1f}s</header>
<div class='wrap'><div class='grid'><div class='panel'><h3>Видео-трек</h3><div class='lane'>{''.join(rows)}</div><p>Зелёный: материал назначен. Жёлтый: требуется генерация / замена.</p></div><div class='panel'><h3>QC-маркеры</h3><ul>{markers}</ul></div></div></div></html>"""
        (self.export_dir/'native_viewer_rc.html').write_text(html, encoding='utf-8')
