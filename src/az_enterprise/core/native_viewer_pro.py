from __future__ import annotations
import json, csv, html
from pathlib import Path
from typing import Any
from .database import Database
from .paths import EXPORTS

class NativeViewerPro:
    """Native Viewer 2.2 — HTML viewer with timeline, shot table and CV metadata."""
    def __init__(self, db: Database, project_id: str='franklin'):
        self.db=db; self.project_id=project_id; self.export_dir=EXPORTS/project_id; self.export_dir.mkdir(parents=True,exist_ok=True)

    def build(self)->dict[str,Any]:
        shots=[dict(r) for r in self.db.rows('''SELECT s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,s.status,s.camera_motion,a.filename,a.path,a.media_type,a.id asset_id
             FROM shots s LEFT JOIN assets a ON a.id=s.assigned_asset_id WHERE s.project_id=? ORDER BY s.idx''',(self.project_id,))]
        cv={r['asset_id']:dict(r) for r in self.db.rows('SELECT * FROM cv_asset_metadata WHERE project_id=?',(self.project_id,))}
        rows=[]
        for s in shots:
            c=cv.get(s.get('asset_id')) or {}
            rows.append({**s,'cv_grade':c.get('cinematic_grade'),'faces':c.get('face_count'),'scenes':c.get('scene_count'),'objects':c.get('object_hints')})
        model={'project_id':self.project_id,'shots':len(rows),'assigned':sum(1 for r in rows if r.get('asset_id')),'missing':sum(1 for r in rows if not r.get('asset_id')),'rows':rows}
        (self.export_dir/'native_viewer_pro.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
        self._csv(rows)
        html_path=self._html(model)
        return {'shots':model['shots'],'assigned':model['assigned'],'missing':model['missing'],'html':str(html_path),'json':str(self.export_dir/'native_viewer_pro.json')}

    def _csv(self, rows):
        with (self.export_dir/'native_viewer_pro.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f, fieldnames=['idx','start_sec','end_sec','block','visual_need','status','filename','media_type','cv_grade','faces','scenes','objects'])
            w.writeheader()
            for r in rows: w.writerow({k:r.get(k,'') for k in w.fieldnames})

    def _asset_rel(self, path):
        if not path: return ''
        try:
            p=Path(path)
            return p.as_uri()
        except Exception:
            return ''

    def _html(self, model):
        row_html=[]
        for r in model['rows']:
            cls='missing' if not r.get('asset_id') else 'ready'
            media=''
            uri=self._asset_rel(r.get('path'))
            if uri and (r.get('media_type')=='image'):
                media=f"<img src='{uri}' loading='lazy'>"
            elif uri and (r.get('media_type')=='video'):
                media=f"<video src='{uri}' controls preload='metadata'></video>"
            else:
                media='<span class="gen">GENERATE</span>'
            obj=html.escape(str(r.get('objects') or ''))[:180]
            row_html.append(f"""<tr class='{cls}' data-block='{html.escape(str(r.get('block') or ''))}' data-need='{html.escape(str(r.get('visual_need') or ''))}'><td>{r['idx']:04d}</td><td>{self._tc(r['start_sec'])}–{self._tc(r['end_sec'])}</td><td>{html.escape(str(r.get('block') or ''))}</td><td>{html.escape(str(r.get('visual_need') or ''))}</td><td>{media}<div>{html.escape(str(r.get('filename') or 'НУЖНО СОЗДАТЬ'))}</div></td><td>grade {r.get('cv_grade') or '—'}<br>faces {r.get('faces') or 0}<br>scenes {r.get('scenes') or 0}<br>{obj}</td><td>{html.escape(str(r.get('camera_motion') or ''))}</td></tr>""")
        html_doc=f"""<!doctype html><meta charset='utf-8'><title>ATLAS ZERO Native Viewer Pro</title>
<style>body{{font-family:Segoe UI,Arial;background:#08111f;color:#eaf2ff;margin:0;font-size:13px}}header{{position:sticky;top:0;background:#020617;padding:18px 24px;border-bottom:1px solid #26364d;z-index:2}}.kpi{{display:flex;gap:10px;margin-top:10px}}.kpi span{{background:#101b2d;border:1px solid #334155;border-radius:12px;padding:8px 12px}}table{{width:100%;border-collapse:collapse}}th{{position:sticky;top:112px;background:#14243a;text-align:left;padding:10px}}td{{border-bottom:1px solid #24364e;padding:10px;vertical-align:top}}tr.ready{{background:#071a2a}}tr.missing{{background:#2a1015}}img,video{{width:240px;max-height:140px;border-radius:10px;object-fit:cover}}.gen{{color:#fbbf24;font-weight:800}}input{{background:#0b1424;color:#fff;border:1px solid #334155;border-radius:8px;padding:8px;width:360px}}</style>
<header><h1>ATLAS ZERO — Native Viewer Pro 2.2</h1><input id='q' placeholder='Поиск по блоку, категории, файлу...' oninput='filterRows()'><div class='kpi'><span>Шотов: <b>{model['shots']}</b></span><span>Назначено: <b>{model['assigned']}</b></span><span>Дефицит: <b>{model['missing']}</b></span></div></header>
<table><thead><tr><th>№</th><th>Время</th><th>Блок</th><th>Категория</th><th>Материал</th><th>CV</th><th>Движение</th></tr></thead><tbody>{''.join(row_html)}</tbody></table>
<script>function filterRows(){{let q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>{{r.style.display=r.innerText.toLowerCase().includes(q)?'':'none'}})}};</script>"""
        path=self.export_dir/'native_viewer_pro.html'
        path.write_text(html_doc,encoding='utf-8')
        return path

    def _tc(self, sec):
        sec=float(sec or 0); m=int(sec//60); s=sec-m*60; return f'{m:02d}:{s:05.2f}'
