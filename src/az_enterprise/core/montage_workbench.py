from __future__ import annotations
import json, csv, html
from pathlib import Path
from .database import Database
from .paths import EXPORTS
from .events import EventBus

class MontageWorkbench:
    """Creates a practical local монтажный рабочий экран for Franklin.

    This is not a fake native NLE: it is a local operator workbench that turns
    the current Project Brain state into a usable assembly surface: tracks,
    search, filters, missing-shot prompts, and copy-ready CapCut steps.
    """
    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.bus = EventBus(db, project_id)

    def build(self) -> dict:
        shots = self.db.rows('''SELECT s.id,s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,
            s.emotion,s.status,s.transition,s.camera_motion,a.filename,a.path,a.media_type
            FROM shots s LEFT JOIN assets a ON a.id=s.assigned_asset_id
            WHERE s.project_id=? ORDER BY s.idx''', (self.project_id,))
        decisions = {r['shot_id']: dict(r) for r in self.db.rows('SELECT shot_id,score,reason,alternatives FROM director_decisions WHERE project_id=?', (self.project_id,))}
        missing = [dict(s) for s in shots if s['status'] != 'assigned']
        assigned = [dict(s) for s in shots if s['status'] == 'assigned']
        blocks = {}
        for s in shots:
            blocks.setdefault(s['block'] or 'B00', {'shots':0,'assigned':0,'missing':0,'duration':0})
            b = blocks[s['block'] or 'B00']
            b['shots'] += 1
            b['duration'] += max(0, float(s['end_sec']) - float(s['start_sec']))
            if s['status'] == 'assigned': b['assigned'] += 1
            else: b['missing'] += 1
        data = {
            'project': self.project_id,
            'shots': len(shots),
            'assigned': len(assigned),
            'missing': len(missing),
            'coverage_pct': round(len(assigned)/max(len(shots),1)*100, 1),
            'blocks': blocks,
            'workbench_html': str(self.export_dir/'montage_workbench.html'),
            'workbench_json': str(self.export_dir/'montage_workbench.json'),
            'operator_csv': str(self.export_dir/'operator_timeline_board.csv'),
        }
        (self.export_dir/'montage_workbench.json').write_text(json.dumps({'summary':data,'shots':[dict(x) for x in shots]}, ensure_ascii=False, indent=2), encoding='utf-8')
        self._write_csv(shots, decisions)
        self._write_html(shots, decisions, data)
        self.bus.emit('MONTAGE_WORKBENCH_BUILT', {'shots': len(shots), 'missing': len(missing), 'coverage': data['coverage_pct']})
        return data

    def _write_csv(self, shots, decisions):
        p = self.export_dir/'operator_timeline_board.csv'
        with p.open('w', newline='', encoding='utf-8-sig') as f:
            w=csv.writer(f)
            w.writerow(['№','Начало','Конец','Блок','Статус','Материал','Тип','Смысл','Визуальная задача','Камера','Переход','Решение ИИ'])
            for s in shots:
                d = decisions.get(s['id'], {})
                w.writerow([s['idx'], self._tc(s['start_sec']), self._tc(s['end_sec']), s['block'], s['status'], s['filename'] or 'СОЗДАТЬ', s['media_type'] or '', s['story_goal'], s['visual_need'], s['camera_motion'], s['transition'], d.get('reason','')])

    def _write_html(self, shots, decisions, summary):
        block_cards = ''.join(
            f"<div class='metric'><span>{html.escape(str(k))}</span><b>{v['assigned']}/{v['shots']}</b><small>{round(v['duration']/60,1)} мин · нужно {v['missing']}</small></div>"
            for k,v in sorted(summary['blocks'].items())
        )
        rows=[]
        for s in shots:
            d=decisions.get(s['id'], {})
            status_class='ok' if s['status']=='assigned' else 'miss'
            asset=html.escape(s['filename'] or 'СОЗДАТЬ')
            prompt = html.escape(self._prompt_for(s))
            rows.append(f"""
            <tr data-status='{status_class}' data-block='{html.escape(str(s['block']))}'>
              <td>{s['idx']}</td><td>{self._tc(s['start_sec'])}</td><td>{self._tc(s['end_sec'])}</td>
              <td>{html.escape(str(s['block']))}</td><td><span class='{status_class}'>{'готов' if s['status']=='assigned' else 'создать'}</span></td>
              <td>{asset}</td><td>{html.escape(str(s['visual_need']))}</td><td>{html.escape(str(s['emotion']))}</td>
              <td>{html.escape(str(s['camera_motion']))}</td><td>{html.escape(str(d.get('reason','')))}</td>
              <td><button onclick="copyText(`{prompt}`)">Промпт</button></td>
            </tr>""")
        page=f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>ATLAS ZERO · Монтажная мастерская</title>
        <style>
        :root{{--bg:#0b1220;--panel:#111827;--card:#1f2937;--line:#334155;--text:#e5e7eb;--muted:#9ca3af;--ok:#22c55e;--miss:#f97316;--accent:#38bdf8}}
        body{{margin:0;background:var(--bg);color:var(--text);font-family:Segoe UI,Arial;font-size:12px}}
        header{{position:sticky;top:0;z-index:5;background:#020617;border-bottom:1px solid var(--line);padding:12px 18px;display:flex;align-items:center;gap:18px}}
        h1{{font-size:18px;margin:0}} .sub{{color:var(--muted)}}
        .metrics{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;padding:14px 18px}}
        .metric{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;min-height:58px}}
        .metric span{{display:block;color:var(--muted)}} .metric b{{font-size:18px}} .metric small{{display:block;color:var(--muted)}}
        .tools{{display:flex;gap:8px;padding:0 18px 12px}} input,select{{background:#0f172a;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px}}
        table{{width:calc(100% - 36px);margin:0 18px 24px;border-collapse:collapse;background:var(--panel);border:1px solid var(--line)}}
        th{{position:sticky;top:54px;background:#111827;color:#cbd5e1;text-align:left;padding:8px;border-bottom:1px solid var(--line)}}
        td{{padding:7px;border-bottom:1px solid #1f2937;vertical-align:top}} tr:hover{{background:#172033}}
        .ok{{color:var(--ok);font-weight:700}} .miss{{color:var(--miss);font-weight:700}} button{{background:#075985;color:white;border:0;border-radius:7px;padding:5px 8px;font-size:11px;cursor:pointer}}
        .toast{{position:fixed;right:16px;bottom:16px;background:#064e3b;color:white;border-radius:8px;padding:10px 12px;display:none}}
        </style></head><body>
        <header><h1>ATLAS ZERO · Монтажная мастерская Franklin</h1><span class='sub'>локальный рабочий таймлайн · покрытие {summary['coverage_pct']}% · шотов {summary['shots']} · нужно создать {summary['missing']}</span></header>
        <section class='metrics'>
          <div class='metric'><span>Покрытие</span><b>{summary['coverage_pct']}%</b><small>назначенных материалов</small></div>
          <div class='metric'><span>Шотов</span><b>{summary['shots']}</b><small>в монтажной структуре</small></div>
          <div class='metric'><span>Назначено</span><b>{summary['assigned']}</b><small>можно класть в CapCut</small></div>
          <div class='metric'><span>Нужно создать</span><b>{summary['missing']}</b><small>пакет промптов доступен</small></div>
          {block_cards}
        </section>
        <div class='tools'><input id='q' placeholder='поиск: лед, корабль, B03...' oninput='filterRows()'><select id='status' onchange='filterRows()'><option value='all'>Все</option><option value='ok'>Готовые</option><option value='miss'>Нужно создать</option></select></div>
        <table id='tbl'><thead><tr><th>№</th><th>Начало</th><th>Конец</th><th>Блок</th><th>Статус</th><th>Материал</th><th>Визуальная задача</th><th>Эмоция</th><th>Камера</th><th>Решение ИИ</th><th></th></tr></thead><tbody>{''.join(rows)}</tbody></table>
        <div class='toast' id='toast'>Скопировано</div>
        <script>
        function filterRows(){{let q=document.getElementById('q').value.toLowerCase();let st=document.getElementById('status').value;document.querySelectorAll('#tbl tbody tr').forEach(r=>{{let txt=r.innerText.toLowerCase();let ok=(st==='all'||r.dataset.status===st)&&txt.includes(q);r.style.display=ok?'':'none';}})}}
        function copyText(t){{navigator.clipboard.writeText(t);let el=document.getElementById('toast');el.style.display='block';setTimeout(()=>el.style.display='none',1200)}}
        </script></body></html>"""
        (self.export_dir/'montage_workbench.html').write_text(page, encoding='utf-8')

    def _prompt_for(self, s) -> str:
        need = s['visual_need'] or 'historical documentary frame'
        emotion = s['emotion'] or 'cold investigation'
        return f"Ultra photorealistic historical documentary frame, Franklin Expedition, {need}. Emotion: {emotion}. Cold Arctic blue-gray palette, realistic 19th century details, BBC / Netflix documentary realism, no fantasy, no CGI look, no modern objects."

    def _tc(self, sec) -> str:
        sec=float(sec); m=int(sec//60); s=sec-m*60
        return f"{m:02d}:{s:05.2f}"
