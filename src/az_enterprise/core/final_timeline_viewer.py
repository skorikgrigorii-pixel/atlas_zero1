from __future__ import annotations
import html, json
from .database import Database
from .paths import EXPORTS
from .events import EventBus

class FinalTimelineViewer:
    """Creates a practical review viewer for Franklin timeline.

    It is not a native NLE timeline yet, but it is a usable operator viewer with filters,
    shot details, asset assignments, missing flags and director reasons.
    """
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.export_dir=EXPORTS/project_id; self.bus=EventBus(db,project_id)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def build(self) -> dict:
        rows=self.db.rows('''SELECT s.id,s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,s.emotion,s.status,s.camera_motion,s.transition,
               a.filename asset,a.media_type,a.category,a.quality,d.score decision_score,d.reason decision_reason
          FROM shots s
          LEFT JOIN assets a ON a.id=s.assigned_asset_id
          LEFT JOIN director_decisions d ON d.shot_id=s.id AND d.project_id=s.project_id
         WHERE s.project_id=? ORDER BY s.idx''', (self.project_id,))
        blocks={}
        for r in rows: blocks.setdefault(r['block'] or 'Без блока', []).append(dict(r))
        data={'shots':[dict(r) for r in rows], 'blocks': blocks}
        json_path=self.export_dir/'timeline_operator_view.json'
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        html_path=self.export_dir/'timeline_operator_view.html'
        html_path.write_text(self._html(data), encoding='utf-8')
        self.bus.emit('FINAL_TIMELINE_VIEWER_BUILT', {'shots': len(rows), 'html': str(html_path)})
        return {'shots': len(rows), 'html': str(html_path), 'json': str(json_path)}

    def _html(self, data: dict) -> str:
        shots=data['shots']; blocks=data['blocks']
        total=max([s['end_sec'] for s in shots], default=1)
        block_bars=[]
        colors=['#2563eb','#059669','#7c3aed','#d97706','#dc2626','#0891b2']
        for i,(b,items) in enumerate(blocks.items()):
            start=items[0]['start_sec']; end=items[-1]['end_sec']; left=start/total*100; width=max((end-start)/total*100,1)
            block_bars.append(f"<div class='bar' title='{html.escape(str(b))}' style='left:{left:.2f}%;width:{width:.2f}%;background:{colors[i%len(colors)]}'>{html.escape(str(b))}</div>")
        rows=[]
        for s in shots:
            cls='missing' if s['status']!='assigned' else 'ok'
            rows.append(f"""<tr class='{cls}' data-status='{html.escape(str(s['status']))}' data-block='{html.escape(str(s['block']))}'>
<td>{s['idx']}</td><td>{s['start_sec']:.1f}</td><td>{s['end_sec']:.1f}</td><td>{html.escape(str(s['block']))}</td>
<td>{html.escape(str(s['visual_need']))}</td><td>{html.escape(str(s['emotion']))}</td>
<td>{html.escape(str(s['asset'] or 'НУЖНО СОЗДАТЬ'))}</td><td>{html.escape(str(s['camera_motion']))}</td><td>{html.escape(str(s['transition']))}</td>
<td>{html.escape(str(round(s['decision_score'] or 0,2)))}</td><td>{html.escape(str(s['decision_reason'] or ''))}</td></tr>""")
        return f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>ATLAS ZERO · Timeline Operator View</title>
<style>
body{{margin:0;background:#0b1220;color:#dbeafe;font-family:Segoe UI,Arial,sans-serif;font-size:12px}}header{{padding:14px 18px;background:#020617;border-bottom:1px solid #1e293b}}h1{{margin:0;font-size:18px}}.sub{{color:#94a3b8;margin-top:4px}}
.controls{{display:flex;gap:8px;padding:12px 18px;background:#0f172a;position:sticky;top:0;z-index:4}}button,input,select{{background:#111827;color:#e5e7eb;border:1px solid #334155;border-radius:6px;padding:6px 8px;font-size:12px}}
.timeline{{position:relative;height:36px;margin:14px 18px;background:#111827;border:1px solid #334155;border-radius:8px;overflow:hidden}}.bar{{position:absolute;top:0;height:100%;font-size:10px;display:flex;align-items:center;justify-content:center;color:white;white-space:nowrap;overflow:hidden}}
table{{border-collapse:collapse;width:calc(100% - 36px);margin:14px 18px 40px;background:#0f172a}}th{{position:sticky;top:45px;background:#111827;color:#93c5fd;z-index:3}}td,th{{border-bottom:1px solid #1e293b;padding:6px 7px;text-align:left;vertical-align:top}}tr.ok td:first-child{{border-left:3px solid #22c55e}}tr.missing td:first-child{{border-left:3px solid #f97316}}tr:hover{{background:#172554}}
.badge{{display:inline-block;padding:2px 6px;border-radius:999px;background:#1e293b;color:#bfdbfe;margin-left:6px}}
</style></head><body><header><h1>ATLAS ZERO Enterprise · Операторский таймлайн</h1><div class='sub'>Шотов: {len(shots)} · Длительность: {total:.1f} сек · Franklin production handoff</div></header>
<div class='controls'><input id='q' placeholder='поиск: лед, корабль, карта...' oninput='filter()'><select id='status' onchange='filter()'><option value=''>Все статусы</option><option value='assigned'>Назначено</option><option value='missing'>Нужно создать</option></select><button onclick='showMissing()'>Показать дефицит</button><button onclick='resetF()'>Сброс</button><span class='badge' id='count'></span></div>
<div class='timeline'>{''.join(block_bars)}</div><table id='tbl'><thead><tr><th>№</th><th>Старт</th><th>Финиш</th><th>Блок</th><th>Визуальная задача</th><th>Эмоция</th><th>Материал</th><th>Камера</th><th>Переход</th><th>Оценка</th><th>Решение ИИ</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<script>
function filter(){{let q=document.getElementById('q').value.toLowerCase();let st=document.getElementById('status').value;let n=0;document.querySelectorAll('#tbl tbody tr').forEach(r=>{{let txt=r.innerText.toLowerCase();let ok=(!q||txt.includes(q))&&(!st||r.dataset.status==st);r.style.display=ok?'':'none';if(ok)n++;}});document.getElementById('count').innerText='показано '+n;}}
function showMissing(){{document.getElementById('status').value='missing';filter();}}
function resetF(){{document.getElementById('q').value='';document.getElementById('status').value='';filter();}}
filter();
</script></body></html>"""
