from __future__ import annotations
import json, math, os, struct, statistics, hashlib
from pathlib import Path
from .database import Database
from .events import EventBus

try:
    from PIL import Image, ImageStat, ImageOps, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


def _png_size(path: Path):
    try:
        with path.open('rb') as f:
            sig=f.read(24)
        if sig.startswith(b'\x89PNG\r\n\x1a\n'):
            return struct.unpack('>II', sig[16:24])
    except Exception:
        pass
    return None


def _jpeg_size(path: Path):
    try:
        with path.open('rb') as f:
            data=f.read(2)
            if data != b'\xff\xd8': return None
            while True:
                marker_prefix=f.read(1)
                if marker_prefix != b'\xff': return None
                marker=f.read(1)
                while marker == b'\xff': marker=f.read(1)
                if marker in [b'\xc0',b'\xc1',b'\xc2',b'\xc3',b'\xc5',b'\xc6',b'\xc7',b'\xc9',b'\xca',b'\xcb',b'\xcd',b'\xce',b'\xcf']:
                    f.read(3)
                    h,w=struct.unpack('>HH', f.read(4))
                    return w,h
                length=struct.unpack('>H', f.read(2))[0]
                f.seek(length-2, 1)
    except Exception:
        return None


def image_size(path: Path):
    return _png_size(path) or _jpeg_size(path)


def _safe_lower(name: str) -> str:
    return (name or '').lower().replace('_',' ').replace('-',' ')


def plan_from_name(filename: str, width: int|None=None, height: int|None=None) -> str:
    n=_safe_lower(filename)
    if any(k in n for k in ['close','detail','macro','icepressure','closeic','extreme']): return 'крупный план'
    if any(k in n for k in ['wide','aerial','drone','master','panorama']): return 'общий план'
    if any(k in n for k in ['medium','crew','commander','portrait']): return 'средний план'
    if width and height:
        ratio=width/max(height,1)
        if ratio > 1.9: return 'широкий общий план'
    return 'универсальный план'


def palette_from_name(filename: str) -> str:
    n=_safe_lower(filename)
    if any(k in n for k in ['arctic','ice','snow','cool','blue','frozen','polar']): return 'холодная сине-серая'
    if any(k in n for k in ['deck','hull','wood','bow','rigging']): return 'дерево / холодный металл'
    if any(k in n for k in ['lab','document','paper','map']): return 'нейтральная документальная'
    return 'не определена'


def hamming(a: str|None, b: str|None) -> int|None:
    if not a or not b or len(a) != len(b): return None
    return sum(ch1 != ch2 for ch1,ch2 in zip(a,b))


def _image_metrics(path: Path) -> dict:
    """Return explainable local CV metrics. Works without internet or paid APIs."""
    size = image_size(path)
    profile = {
        'width': size[0] if size else None,
        'height': size[1] if size else None,
        'avg_rgb': None,
        'brightness': None,
        'contrast': None,
        'saturation': None,
        'sharpness_proxy': None,
        'ahash': None,
        'dominant_palette': None,
        'cv_engine': 'headers_only'
    }
    if not PIL_AVAILABLE:
        return profile
    try:
        im = Image.open(path).convert('RGB')
        profile['width'], profile['height'] = im.size
        small = im.resize((64,64))
        stat = ImageStat.Stat(small)
        avg = tuple(round(x,1) for x in stat.mean)
        profile['avg_rgb'] = avg
        gray = ImageOps.grayscale(small)
        gstat = ImageStat.Stat(gray)
        profile['brightness'] = round(gstat.mean[0],2)
        profile['contrast'] = round(gstat.stddev[0],2)
        # saturation approximation: average RGB channel spread
        pixels = list(small.getdata())
        spreads = [max(p)-min(p) for p in pixels]
        profile['saturation'] = round(sum(spreads)/len(spreads),2) if spreads else 0
        # sharpness proxy: mean edge response
        edges = ImageOps.grayscale(im.resize((96,96))).filter(ImageFilter.FIND_EDGES) if False else None
        # avoid importing ImageFilter lazily if not needed; use neighbor-delta proxy instead
        gp = list(gray.resize((16,16)).getdata())
        deltas=[]
        for y in range(16):
            for x in range(15): deltas.append(abs(gp[y*16+x]-gp[y*16+x+1]))
        for y in range(15):
            for x in range(16): deltas.append(abs(gp[y*16+x]-gp[(y+1)*16+x]))
        profile['sharpness_proxy'] = round(sum(deltas)/len(deltas),2) if deltas else 0
        tiny = gray.resize((8,8))
        vals = list(tiny.getdata())
        mean = sum(vals)/len(vals)
        profile['ahash'] = ''.join('1' if v >= mean else '0' for v in vals)
        r,g,b = avg
        if b >= r + 10 and b >= g - 5:
            profile['dominant_palette'] = 'холодная синяя'
        elif r > b + 25 and g > b:
            profile['dominant_palette'] = 'тёплая/землистая'
        elif profile['saturation'] < 20:
            profile['dominant_palette'] = 'монохромная документальная'
        else:
            profile['dominant_palette'] = 'смешанная'
        profile['cv_engine'] = 'local_pillow_metrics'
    except Exception as e:
        profile['cv_error'] = str(e)
    return profile


class VisualIntelligence:
    """Local computer vision layer for RC1 Alpha 0.9.

    It is intentionally offline-safe: no credits, no API calls. It computes dimensions,
    color/brightness/contrast proxies, perceptual hashes, visual-plan labels and
    similarity clusters. Later this contract can be upgraded with CLIP/OpenAI Vision.
    """
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id; self.bus=EventBus(db, project_id)

    def analyze_assets(self) -> dict:
        rows=self.db.rows("SELECT id,path,filename,media_type,category,tags,emotion,quality FROM assets WHERE project_id=?", (self.project_id,))
        count=0; updated=0; hashes=[]; anomalies=0
        for r in rows:
            if r['media_type'] not in ('image','video'):
                continue
            p=Path(r['path'])
            metrics=_image_metrics(p) if r['media_type']=='image' else {}
            width,height=metrics.get('width'),metrics.get('height')
            visual_plan=plan_from_name(r['filename'], width, height)
            camera='ken burns / slow push-in' if r['media_type']=='image' else 'нативное движение видео'
            palette=metrics.get('dominant_palette') or palette_from_name(r['filename'])
            consistency=0.70
            if 'холод' in (palette or '') or 'син' in (palette or ''): consistency += 0.13
            if r['category'] in ('ship','ice','crew','rigging','video'): consistency += 0.06
            if r['quality']: consistency += min(float(r['quality']) * .08, .08)
            if metrics.get('contrast') is not None and metrics.get('contrast') < 8: consistency -= 0.08
            if metrics.get('brightness') is not None and (metrics['brightness'] < 20 or metrics['brightness'] > 235): consistency -= 0.06
            consistency=round(max(0.1,min(consistency, .98)),3)
            risk=[]
            if metrics.get('dominant_palette') == 'тёплая/землистая': risk.append('палитра может выбиваться из холодного арктического стиля')
            if metrics.get('contrast') is not None and metrics['contrast'] < 8: risk.append('низкая контрастность')
            if metrics.get('sharpness_proxy') is not None and metrics['sharpness_proxy'] < 4: risk.append('возможная мягкость/размытие')
            anomalies += 1 if risk else 0
            profile={
                'asset_id': r['id'], 'filename': r['filename'], 'media_type': r['media_type'],
                'width': width, 'height': height, 'visual_plan': visual_plan,
                'palette': palette, 'camera_suggestion': camera,
                'style_consistency': consistency,
                'historical_risk': 'низкий' if r['category'] in ('ship','ice','crew','rigging','video') else 'средний',
                'cv_metrics': metrics,
                'risks': risk,
                'notes': 'Локальный анализ RC1 Alpha 0.9: размер, палитра, яркость, контраст, ahash, схожесть.'
            }
            self.db.execute('''INSERT OR REPLACE INTO visual_profiles(asset_id,project_id,profile_json,style_score,plan_type,palette,created_at)
                               VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)''',
                            (r['id'], self.project_id, json.dumps(profile, ensure_ascii=False), consistency, visual_plan, palette))
            if width and height:
                self.db.execute('UPDATE assets SET width=?, height=? WHERE id=?', (width,height,r['id']))
                updated += 1
            if metrics.get('ahash'):
                hashes.append((r['id'], r['filename'], metrics['ahash']))
            count += 1
        sim = self._write_similarity(hashes)
        self._export_contact_sheet()
        self.bus.emit('VISUAL_INTELLIGENCE_COMPLETED', {'profiles': count, 'dimensions_updated': updated, 'similar_pairs': sim, 'anomalies': anomalies})
        return {'visual_profiles': count, 'dimensions_updated': updated, 'similar_pairs': sim, 'anomalies': anomalies, 'engine':'local_cv_0_9'}

    def _write_similarity(self, hashes: list[tuple[str,str,str]]) -> int:
        self.db.execute('DELETE FROM asset_similarity WHERE project_id=?', (self.project_id,))
        pairs=0
        for i in range(len(hashes)):
            a_id,a_name,a_hash=hashes[i]
            for j in range(i+1,len(hashes)):
                b_id,b_name,b_hash=hashes[j]
                dist=hamming(a_hash,b_hash)
                if dist is not None and dist <= 10:
                    score=round(1-(dist/64),3)
                    self.db.execute('INSERT INTO asset_similarity(project_id,asset_id_a,asset_id_b,score,reason) VALUES(?,?,?,?,?)',
                                    (self.project_id,a_id,b_id,score,f'Похожие визуальные хеши; hamming={dist}'))
                    pairs += 1
        return pairs

    def _export_contact_sheet(self):
        if not PIL_AVAILABLE:
            return
        from .paths import EXPORTS
        out_dir=EXPORTS/self.project_id
        out_dir.mkdir(parents=True, exist_ok=True)
        rows=self.db.rows("SELECT a.path,a.filename,v.style_score,v.plan_type,v.palette FROM assets a LEFT JOIN visual_profiles v ON v.asset_id=a.id WHERE a.project_id=? AND a.media_type='image' ORDER BY v.style_score DESC LIMIT 36", (self.project_id,))
        if not rows: return
        cell_w, cell_h = 260, 205
        sheet=Image.new('RGB',(cell_w*3, cell_h*math.ceil(len(rows)/3)),(15,23,42))
        draw=ImageDraw.Draw(sheet)
        for idx,r in enumerate(rows):
            x=(idx%3)*cell_w; y=(idx//3)*cell_h
            try:
                im=Image.open(r['path']).convert('RGB')
                im.thumbnail((cell_w-20, 140))
                sheet.paste(im,(x+10,y+10))
            except Exception:
                pass
            txt=f"{r['filename'][:34]}\n{r['plan_type'] or ''} | {r['palette'] or ''}\nscore {r['style_score'] or 0:.2f}"
            draw.text((x+10,y+150),txt,fill=(226,232,240))
        sheet.save(out_dir/'visual_contact_sheet.jpg',quality=88)

    def coverage(self) -> dict:
        plans=self.db.rows('SELECT plan_type, COUNT(*) c FROM visual_profiles WHERE project_id=? GROUP BY plan_type', (self.project_id,))
        palettes=self.db.rows('SELECT palette, COUNT(*) c FROM visual_profiles WHERE project_id=? GROUP BY palette', (self.project_id,))
        similar=self.db.one('SELECT COUNT(*) c FROM asset_similarity WHERE project_id=?', (self.project_id,))
        return {'plans': {r['plan_type']:r['c'] for r in plans}, 'palettes': {r['palette']:r['c'] for r in palettes}, 'similar_pairs': similar['c'] if similar else 0}
