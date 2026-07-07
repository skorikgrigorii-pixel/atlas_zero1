from __future__ import annotations
import json, csv, html
from .paths import EXPORTS
from .cv_model import CVModel

class CVReviewBoard:
    def __init__(self, db, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.export_dir=EXPORTS/project_id; self.export_dir.mkdir(parents=True,exist_ok=True)
    def build(self):
        # Reuse existing CV metadata when available; a full CV pass is expensive and
        # already runs in the pipeline before this board.
        existing = self.db.one('SELECT COUNT(*) c FROM cv_asset_metadata WHERE project_id=?', (self.project_id,))
        if not existing or not existing['c']:
            CVModel(self.db,self.project_id).analyze()
        rows=self.db.rows('''SELECT a.filename,a.path,a.media_type,v.style_score,v.plan_type,v.palette,v.profile_json FROM visual_profiles v JOIN assets a ON a.id=v.asset_id WHERE v.project_id=? ORDER BY v.style_score ASC''',(self.project_id,))
        reviewed=[]
        for r in rows:
            profile=json.loads(r['profile_json']) if r['profile_json'] else {}
            flags=[]
            if profile.get('blur_score',100) < 20: flags.append('возможный blur')
            if profile.get('contrast',100) < 18: flags.append('низкий контраст')
            if r['style_score'] < 55: flags.append('низкий cinematic grade')
            reviewed.append({**dict(r),'flags':', '.join(flags) or 'ok'})
        csv_path=self.export_dir/'cv_review_board.csv'
        with csv_path.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f); w.writerow(['Файл','Тип','План','Палитра','Оценка','Флаги'])
            for r in reviewed: w.writerow([r['filename'],r['media_type'],r['plan_type'],r['palette'],r['style_score'],r['flags']])
        cards=''
        for r in reviewed[:160]:
            src = html.escape(str(r['path']))
            name=html.escape(r['filename'])
            flags=html.escape(r['flags'])
            cards += f"<div class='card'><img src='file:///{src}'><b>{name}</b><small>{r['plan_type']} · {r['palette']} · score {r['style_score']}</small><em>{flags}</em></div>"
        html_doc=f"""<!doctype html><meta charset='utf-8'><title>CV Review Board</title><style>body{{background:#0f172a;color:#e5e7eb;font-family:Segoe UI,Arial;font-size:12px}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}}.card{{background:#111827;border:1px solid #334155;border-radius:10px;padding:8px}}img{{width:100%;height:120px;object-fit:cover;border-radius:8px;background:#020617}}small,em{{display:block;color:#9ca3af;margin-top:4px}}</style><h1>CV Review Board</h1><p>Кадры отсортированы от слабых к сильным. Сначала проверяйте первые карточки.</p><div class='grid'>{cards}</div>"""
        html_path=self.export_dir/'cv_review_board.html'; html_path.write_text(html_doc,encoding='utf-8')
        return {'items':len(reviewed),'flagged':sum(1 for r in reviewed if r['flags']!='ok'),'csv':str(csv_path),'html':str(html_path)}
