from __future__ import annotations
import csv, json, html
from pathlib import Path
from .database import Database
from .paths import EXPORTS

class CapCutBridge:
    """Operator-grade bridge for building the Franklin timeline in CapCut.

    This module does not pretend to control CapCut's private desktop UI. It creates a
    deterministic handoff: ordered cut list, media bins, missing-generation batch and
    an HTML operator screen. This is the first fully usable bridge for the current
    Franklin project while live integrations are still gated.
    """
    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _tc(sec: float) -> str:
        sec = max(0, float(sec or 0))
        h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
        return f"{h:02d}:{m:02d}:{s:05.2f}"

    def build(self) -> dict:
        shots = self.db.rows('''SELECT s.id,s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,
                    s.emotion,s.status,s.transition,s.camera_motion,a.filename,a.path,a.media_type,a.category
                    FROM shots s LEFT JOIN assets a ON s.assigned_asset_id=a.id
                    WHERE s.project_id=? ORDER BY s.idx''', (self.project_id,))
        assets = self.db.rows('SELECT filename,path,media_type,category,emotion,quality FROM assets WHERE project_id=? ORDER BY media_type,category,filename', (self.project_id,))

        cut_csv = self.export_dir / 'capcut_manual_build_order.csv'
        with cut_csv.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['№','Таймкод IN','Таймкод OUT','Длительность','Блок','Действие в CapCut','Материал','Тип','Камера','Переход','Смысл','Статус'])
            for r in shots:
                dur = float(r['end_sec']) - float(r['start_sec'])
                if r['filename']:
                    action = 'Положить материал на видеодорожку V1; применить указанное движение камеры'
                    material = r['filename']
                else:
                    action = 'Оставить placeholder; материал нужно создать по prompt pack'
                    material = 'MISSING_' + str(r['idx']).zfill(3)
                w.writerow([r['idx'], self._tc(r['start_sec']), self._tc(r['end_sec']), f'{dur:.2f}', r['block'], action, material, r['media_type'] or 'placeholder', r['camera_motion'], r['transition'], r['story_goal'], r['status']])

        bins_csv = self.export_dir / 'capcut_bins.csv'
        with bins_csv.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['Bin','Файл','Тип','Категория','Эмоция','Качество','Путь'])
            for a in assets:
                bin_name = f"{a['media_type'] or 'media'} / {a['category'] or 'uncategorized'}"
                w.writerow([bin_name, a['filename'], a['media_type'], a['category'], a['emotion'], a['quality'], a['path']])

        missing = [r for r in shots if not r['filename']]
        missing_md = self.export_dir / 'capcut_missing_generation_batch.md'
        lines = ['# ATLAS ZERO — пакет недостающих материалов для Franklin', '', 'Использовать для пакетной генерации. После генерации положить файлы в `02_Images` или `03_Video`, затем заново запустить конвейер.', '']
        for r in missing[:80]:
            lines.append(f"## MISSING_{int(r['idx']):03d} · {r['block']} · {self._tc(r['start_sec'])}–{self._tc(r['end_sec'])}")
            lines.append(f"Смысл: {r['story_goal']}")
            lines.append(f"Нужно: {r['visual_need']}")
            lines.append(f"Эмоция: {r['emotion']}")
            lines.append('Prompt:')
            lines.append('```text')
            lines.append(f"Ultra photorealistic historical documentary frame for ATLAS ZERO Franklin Expedition film. Scene: {r['story_goal']}. Visual: {r['visual_need']}. Emotion: {r['emotion']}. Cold Arctic documentary realism, BBC / Netflix quality, no fantasy, no modern objects, cinematic, 16:9.")
            lines.append('```')
            lines.append('')
        missing_md.write_text('\n'.join(lines), encoding='utf-8')

        html_path = self.export_dir / 'capcut_operator_bridge.html'
        rows = []
        for r in shots[:220]:
            material = r['filename'] or f"<span class='missing'>MISSING_{int(r['idx']):03d}</span>"
            status = 'ok' if r['filename'] else 'missing'
            rows.append(f"<tr class='{status}'><td>{r['idx']}</td><td>{self._tc(r['start_sec'])}</td><td>{self._tc(r['end_sec'])}</td><td>{html.escape(r['block'] or '')}</td><td>{material}</td><td>{html.escape(r['camera_motion'] or '')}</td><td>{html.escape(r['transition'] or '')}</td><td>{html.escape(r['story_goal'] or '')}</td></tr>")
        html_path.write_text(f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>CapCut Bridge — Franklin</title>
<style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e5e7eb;font-size:13px;margin:22px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #334155;padding:6px;vertical-align:top}}th{{background:#111827;position:sticky;top:0}}.ok{{background:#0b1220}}.missing{{color:#f97316;font-weight:700}}tr.missing{{background:#2a1808}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:14px;margin:12px 0}}a{{color:#38bdf8}}</style>
<h1>ATLAS ZERO — CapCut Operator Bridge</h1>
<div class='card'><b>Назначение:</b> этот экран позволяет собрать Franklin в CapCut по готовому порядку без догадок.<br>
<b>Шоты:</b> {len(shots)} · <b>Назначено:</b> {len(shots)-len(missing)} · <b>Нужно создать:</b> {len(missing)}<br>
<b>Файлы:</b> capcut_manual_build_order.csv, capcut_bins.csv, capcut_missing_generation_batch.md</div>
<table><tr><th>№</th><th>IN</th><th>OUT</th><th>Блок</th><th>Материал</th><th>Камера</th><th>Переход</th><th>Смысл</th></tr>{''.join(rows)}</table></html>""", encoding='utf-8')

        return {
            'shots': len(shots),
            'assigned': len(shots) - len(missing),
            'missing': len(missing),
            'cut_list': str(cut_csv),
            'bins': str(bins_csv),
            'missing_batch': str(missing_md),
            'html': str(html_path),
        }
