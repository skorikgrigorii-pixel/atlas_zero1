from __future__ import annotations
import json
from pathlib import Path
from .database import Database
from .paths import EXPORTS

class NativeTimelineModel:
    """Builds a richer, track-based timeline model for operator use.

    This is not a video editor yet; it is the first native timeline data layer:
    tracks, clips, gaps, missing media, subtitles, notes and QC markers.
    It is designed so the same data can later feed a Qt timeline widget,
    CapCut bridge, Resolve/Premiere exporters and the Director AI.
    """
    def __init__(self, db: Database, project_id='franklin'):
        self.db = db
        self.project_id = project_id
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def build(self) -> dict:
        shots = self.db.rows('''SELECT s.id,s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,s.emotion,s.status,
                                       a.filename,a.path,a.media_type,a.category,a.quality
                                FROM shots s LEFT JOIN assets a ON a.id=s.assigned_asset_id
                                WHERE s.project_id=? ORDER BY s.idx''', (self.project_id,))
        clips_video, clips_text, clips_qc, clips_audio = [], [], [], []
        missing = []
        for r in shots:
            dur = max(0, float(r['end_sec']) - float(r['start_sec']))
            asset_name = r['filename'] or 'НУЖНО СОЗДАТЬ'
            media_type = r['media_type'] or 'missing'
            clip = {
                'shot_id': r['id'], 'idx': r['idx'], 'start': round(float(r['start_sec']), 2),
                'end': round(float(r['end_sec']), 2), 'duration': round(dur, 2),
                'block': r['block'], 'asset': asset_name, 'asset_path': r['path'] or '',
                'media_type': media_type, 'visual_need': r['visual_need'], 'emotion': r['emotion'],
                'camera': self._camera_for(r), 'transition': self._transition_for(r),
                'status': r['status'], 'quality': r['quality'] or 0
            }
            clips_video.append(clip)
            clips_text.append({
                'start': clip['start'], 'end': clip['end'], 'text': r['story_goal'],
                'role': 'narration_reference', 'shot_idx': r['idx']
            })
            clips_qc.append({
                'start': clip['start'], 'end': clip['end'], 'severity': self._severity(r),
                'message': self._qc_message(r), 'shot_idx': r['idx']
            })
            if r['status'] == 'missing':
                missing.append(clip)
        # placeholder audio master, because user already has combined VO in CapCut.
        total = shots[-1]['end_sec'] if shots else 0
        clips_audio.append({'start': 0, 'end': round(float(total),2), 'duration': round(float(total),2), 'asset': 'Единая дорожка озвучки 1–6 блоков в CapCut', 'media_type': 'audio_reference'})
        model = {
            'project_id': self.project_id,
            'version': 'RC1 Alpha 1.4',
            'duration_sec': round(float(total),2),
            'tracks': [
                {'name': 'V1 Основной видеоряд', 'type': 'video', 'clips': clips_video},
                {'name': 'A1 Озвучка', 'type': 'audio', 'clips': clips_audio},
                {'name': 'T1 Текст диктора / смысл', 'type': 'text', 'clips': clips_text},
                {'name': 'QC Контроль', 'type': 'markers', 'clips': clips_qc},
            ],
            'missing_count': len(missing),
            'missing': missing[:200],
            'stats': self._stats(clips_video)
        }
        p = self.export_dir / 'native_timeline_model.json'
        p.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding='utf-8')
        html_path = self._write_html(model)
        return {'duration_sec': model['duration_sec'], 'shots': len(clips_video), 'missing': len(missing), 'json': str(p), 'html': str(html_path), 'stats': model['stats']}

    def _camera_for(self, r):
        need=(r['visual_need'] or '').lower()
        if 'close' in need or 'detail' in need or 'ice' in need: return 'Slow push-in 100→108%'
        if 'map' in need or 'document' in need: return 'Static + subtle parallax'
        if 'drone' in need or 'wide' in need or 'arctic' in need: return 'Slow aerial drift / Ken Burns'
        return 'Slow cinematic motion'

    def _transition_for(self, r):
        if r['idx'] % 12 == 0: return 'Fade to black 8f'
        if r['idx'] % 5 == 0: return 'Cross dissolve 6f'
        return 'Cut / short dissolve'

    def _severity(self, r):
        if r['status'] == 'missing': return 'high'
        if (r['quality'] or 0) and r['quality'] < 55: return 'medium'
        return 'ok'

    def _qc_message(self, r):
        if r['status'] == 'missing': return 'Не найден подходящий материал. Требуется генерация или замена.'
        if (r['quality'] or 0) and r['quality'] < 55: return 'Материал назначен, но качество ниже желаемого.'
        return 'Материал назначен.'

    def _stats(self, clips):
        total=len(clips); missing=sum(1 for c in clips if c['status']=='missing')
        video=sum(1 for c in clips if c['media_type']=='video')
        image=sum(1 for c in clips if c['media_type']=='image')
        return {'total_shots': total, 'assigned': total-missing, 'missing': missing, 'video_clips': video, 'image_clips': image, 'coverage_pct': round((total-missing)/total*100,2) if total else 0}

    def _write_html(self, model: dict) -> Path:
        max_dur=max(1, model['duration_sec'])
        rows=[]
        for track in model['tracks']:
            items=[]
            for c in track['clips']:
                left=(c['start']/max_dur)*100
                width=max(0.3, ((c['end']-c['start'])/max_dur)*100)
                status=c.get('status','')
                cls='missing' if status=='missing' else ('marker' if track['type']=='markers' else 'clip')
                label=(str(c.get('idx',''))+' · '+str(c.get('asset') or c.get('text') or c.get('message','')))[:72]
                title=json.dumps(c, ensure_ascii=False)
                items.append(f"<div class='{cls}' style='left:{left:.3f}%;width:{width:.3f}%' title='{title}'>{label}</div>")
            rows.append(f"<div class='track'><div class='trackname'>{track['name']}</div><div class='lane'>{''.join(items)}</div></div>")
        html=f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>ATLAS ZERO Native Timeline</title>
<style>
body{{margin:0;background:#0b1220;color:#e5e7eb;font-family:Segoe UI,Arial;font-size:12px}}
header{{padding:14px 18px;background:#020617;border-bottom:1px solid #334155;position:sticky;top:0;z-index:5}}
.stat{{display:inline-block;background:#111827;border:1px solid #334155;border-radius:10px;padding:8px 12px;margin-right:8px}}
.timeline{{padding:18px;min-width:1200px}}.track{{display:grid;grid-template-columns:190px 1fr;margin-bottom:8px;align-items:center}}
.trackname{{color:#93c5fd;padding-right:12px;text-align:right}}.lane{{height:42px;background:#111827;border:1px solid #334155;border-radius:8px;position:relative;overflow:hidden}}
.clip,.missing,.marker{{position:absolute;top:5px;height:30px;border-radius:6px;padding:6px;box-sizing:border-box;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px}}
.clip{{background:#075985;color:white}}.missing{{background:#7f1d1d;color:#fecaca}}.marker{{background:#374151;color:#fde68a}}
.legend{{padding:0 18px 18px;color:#9ca3af}}
</style>
<header><h2>ATLAS ZERO Enterprise RC1 Alpha 1.4 — Native Timeline Model</h2>
<div class='stat'>Длительность: {model['duration_sec']} сек</div><div class='stat'>Шотов: {model['stats']['total_shots']}</div><div class='stat'>Покрытие: {model['stats']['coverage_pct']}%</div><div class='stat'>Нужно создать: {model['missing_count']}</div></header>
<div class='timeline'>{''.join(rows)}</div><div class='legend'>Синий — назначенный материал. Красный — отсутствующий материал. Серый — QC/текстовые маркеры. Этот файл является операторской моделью будущего нативного timeline/viewer.</div></html>"""
        p=self.export_dir/'native_timeline_view.html'
        p.write_text(html, encoding='utf-8')
        return p
