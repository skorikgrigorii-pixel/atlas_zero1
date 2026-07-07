from __future__ import annotations
import json, html
from .database import Database
from .paths import EXPORTS
from .events import EventBus

class TimelineStudio:
    """Enterprise timeline/viewer exporter for RC1 Alpha 0.5."""
    def __init__(self, db: Database, project_id: str='franklin'):
        self.db=db
        self.project_id=project_id
        self.bus=EventBus(db, project_id)
        self.export_dir=EXPORTS/project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def rows(self):
        return self.db.rows('''SELECT s.id,s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,s.emotion,
            s.status,s.transition,s.camera_motion,a.filename asset,a.path asset_path,a.media_type media_type,
            d.score,d.reason
            FROM shots s
            LEFT JOIN assets a ON a.id=s.assigned_asset_id
            LEFT JOIN director_decisions d ON d.shot_id=s.id
            WHERE s.project_id=? ORDER BY s.idx''', (self.project_id,))

    @staticmethod
    def tc(sec: float) -> str:
        sec=max(0,float(sec))
        h=int(sec//3600); m=int((sec%3600)//60); s=int(sec%60); ms=int((sec-int(sec))*1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    def export_timeline_package(self) -> dict:
        rows=self.rows(); files=[]
        data=[]
        for r in rows:
            data.append({
                'shot_id':r['id'],'idx':r['idx'],'start_sec':r['start_sec'],'end_sec':r['end_sec'],
                'duration_sec':round(r['end_sec']-r['start_sec'],3),'block':r['block'],'story_goal':r['story_goal'],
                'visual_need':r['visual_need'],'emotion':r['emotion'],'status':r['status'],
                'asset':r['asset'],'asset_path':r['asset_path'],'media_type':r['media_type'],
                'transition':r['transition'],'camera_motion':r['camera_motion'],'director_score':r['score'],'director_reason':r['reason']
            })
        out_json=self.export_dir/'timeline_enterprise.json'
        out_json.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        files.append(str(out_json))
        srt=[]
        for i,r in enumerate(rows,1):
            title=(r['story_goal'] or r['visual_need'] or 'Кадр').strip()
            srt.append(f"{i}\n{self.tc(r['start_sec'])} --> {self.tc(r['end_sec'])}\n{title}\n")
        out_srt=self.export_dir/'черновые_субтитры_по_шотам.srt'
        out_srt.write_text('\n'.join(srt),encoding='utf-8')
        files.append(str(out_srt))
        guide=self.export_dir/'capcut_guide_ru.md'
        lines=['# CapCut guide — ATLAS ZERO RC1 Alpha 0.5','', 'Импортируйте материалы в CapCut и укладывайте по этому порядку.','']
        for r in rows[:220]:
            asset=r['asset'] or 'СОЗДАТЬ/ЗАМЕНИТЬ МАТЕРИАЛ'
            lines.append(f"- {r['idx']:03d} | {r['start_sec']:.2f}–{r['end_sec']:.2f} | {asset} | {r['camera_motion']} | {r['transition']} | {r['visual_need']}")
        guide.write_text('\n'.join(lines),encoding='utf-8')
        files.append(str(guide))
        html_file=self.export_dir/'timeline_viewer.html'
        cards=[]
        for r in rows:
            status='ok' if r['status']=='assigned' else 'miss'
            cards.append(f"""<div class='shot {status}'>
                <div class='num'>#{r['idx']:03d}</div>
                <div class='time'>{r['start_sec']:.1f}–{r['end_sec']:.1f}</div>
                <div class='block'>{html.escape(r['block'] or '')}</div>
                <div class='asset'>{html.escape(r['asset'] or 'НУЖНО СОЗДАТЬ')}</div>
                <div class='need'>{html.escape(r['visual_need'] or '')}</div>
                <div class='reason'>{html.escape(r['reason'] or '')}</div>
            </div>""")
        html_file.write_text(f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>Timeline Viewer</title>
<style>
body{{margin:0;background:#0b1220;color:#dbeafe;font-family:Inter,Arial,sans-serif;font-size:12px}}header{{position:sticky;top:0;background:#111827;padding:12px 18px;border-bottom:1px solid #334155}}h1{{font-size:18px;margin:0}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:10px;padding:14px}}.shot{{border:1px solid #334155;border-radius:12px;padding:10px;background:#111827}}.shot.ok{{border-left:4px solid #22c55e}}.shot.miss{{border-left:4px solid #f59e0b}}.num{{font-weight:700;color:#93c5fd}}.time,.block{{color:#94a3b8}}.asset{{margin-top:6px;color:#fff}}.need{{margin-top:6px}}.reason{{margin-top:6px;color:#a7f3d0;font-size:11px}}</style>
<header><h1>ATLAS ZERO — Timeline Viewer RC1 Alpha 0.5</h1><div>Всего шотов: {len(rows)} | Назначено: {sum(1 for r in rows if r['status']=='assigned')} | Нужно создать: {sum(1 for r in rows if r['status']!='assigned')}</div></header>
<div class='grid'>{''.join(cards)}</div></html>""", encoding='utf-8')
        files.append(str(html_file))
        self.bus.emit('TIMELINE_PACKAGE_EXPORTED', {'files':files,'shots':len(rows)})
        return {'files':files,'shots':len(rows)}
