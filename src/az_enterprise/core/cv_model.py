from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .database import Database
from .events import EventBus
from .paths import EXPORTS

try:
    import cv2
    import numpy as np
    CV_READY = True
except Exception:
    cv2 = None
    np = None
    CV_READY = False

try:
    from PIL import Image, ImageStat, ImageFilter
    PIL_READY = True
except Exception:
    Image = None
    ImageStat = None
    ImageFilter = None
    PIL_READY = False

import os
try:
    import pytesseract  # type: ignore
    OCR_READY = os.getenv('AZ_ENABLE_OCR') == '1'
except Exception:
    pytesseract = None
    OCR_READY = False


IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}


class CVModel:
    """ATLAS ZERO CV Runtime 2.2.

    Реальный локальный runtime: читает изображения и видео, извлекает технические
    параметры, считает яркость/контраст/резкость/edge density, строит pHash,
    ищет лица через OpenCV Haar Cascade, формирует scene candidates для видео,
    делает безопасный OCR при наличии pytesseract и сохраняет результат в SQLite
    и в экспортные JSON/CSV.
    """

    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.db.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cv_asset_metadata(
              asset_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              filename TEXT,
              media_type TEXT,
              engine TEXT,
              width INTEGER,
              height INTEGER,
              duration_sec REAL,
              fps REAL,
              frame_count INTEGER,
              brightness REAL,
              contrast REAL,
              blur_score REAL,
              edge_density REAL,
              face_count INTEGER DEFAULT 0,
              text_detected INTEGER DEFAULT 0,
              object_hints TEXT,
              scene_count INTEGER DEFAULT 0,
              cinematic_grade REAL,
              phash TEXT,
              metadata_json TEXT,
              quality_flags TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cv_scene_candidates(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              project_id TEXT NOT NULL,
              asset_id TEXT NOT NULL,
              scene_index INTEGER NOT NULL,
              time_sec REAL,
              confidence REAL,
              reason TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        for table, coldef in [
            ('cv_asset_metadata', 'quality_flags TEXT'),
        ]:
            try:
                self.db.conn.execute(f'ALTER TABLE {table} ADD COLUMN {coldef}')
            except Exception:
                pass
        self.db.conn.commit()

    # ---------------------------- IMAGE ANALYSIS ----------------------------
    def _analyze_image_opencv(self, path: Path) -> dict[str, Any]:
        img = cv2.imread(str(path))
        if img is None:
            return self._analyze_image_pillow(path)
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        contrast = float(gray.std())
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        edges = cv2.Canny(gray, 80, 160)
        edge_density = float((edges > 0).mean())
        mean_rgb = rgb.reshape(-1, 3).mean(axis=0).round(2).tolist()
        hist = []
        for ch in range(3):
            hst = cv2.calcHist([rgb], [ch], None, [8], [0, 256]).flatten()
            hst = (hst / max(float(hst.sum()), 1.0)).round(4).tolist()
            hist.append(hst)
        face_count, face_boxes = self._detect_faces(gray)
        text_result = self._ocr_image(path)
        object_hints = self._object_hints(path.name, w, h, brightness, edge_density, mean_rgb, face_count)
        aspect = w / max(h, 1)
        shot_type = self._shot_type(aspect, edge_density, blur_score, face_count, object_hints)
        grade = self._cinematic_grade(brightness, contrast, blur_score, edge_density, mean_rgb, face_count)
        phash = self._phash_opencv(gray)
        return {
            'engine': 'opencv_cv_runtime_2_2',
            'width': w, 'height': h, 'aspect': round(aspect, 3),
            'brightness': round(brightness, 2), 'contrast': round(contrast, 2),
            'blur_laplacian': round(blur_score, 2), 'edge_density': round(edge_density, 4),
            'mean_rgb': mean_rgb, 'hist8_rgb': hist, 'shot_type_cv': shot_type,
            'face_count': face_count, 'face_boxes': face_boxes,
            'ocr_ready': OCR_READY, 'text_detected': bool(text_result.get('text')),
            'ocr_text_preview': text_result.get('text', '')[:160],
            'object_hints': object_hints,
            'cinematic_grade': grade, 'phash': phash,
        }

    def _analyze_image_pillow(self, path: Path) -> dict[str, Any]:
        if not PIL_READY:
            return {'engine': 'cv_runtime_unavailable', 'error': 'Install opencv-python or Pillow'}
        im = Image.open(path).convert('RGB')
        w, h = im.size
        gray = im.convert('L')
        stat = ImageStat.Stat(gray)
        brightness = float(stat.mean[0])
        contrast = float(stat.stddev[0])
        edges = gray.filter(ImageFilter.FIND_EDGES)
        e_stat = ImageStat.Stat(edges)
        edge_density = min(1.0, float(e_stat.mean[0]) / 255.0)
        mean_rgb = [round(x, 2) for x in im.resize((1, 1)).getpixel((0, 0))]
        aspect = w / max(h, 1)
        object_hints = self._object_hints(path.name, w, h, brightness, edge_density, mean_rgb, 0)
        shot_type = self._shot_type(aspect, edge_density, 0, 0, object_hints)
        grade = self._cinematic_grade(brightness, contrast, 100, edge_density, mean_rgb, 0)
        ah = gray.resize((8, 8))
        pix = list(ah.getdata())
        avg = sum(pix) / max(len(pix), 1)
        phash = ''.join('1' if v > avg else '0' for v in pix)
        text_result = self._ocr_image(path)
        return {
            'engine': 'pillow_cv_runtime_2_2',
            'width': w, 'height': h, 'aspect': round(aspect, 3),
            'brightness': round(brightness, 2), 'contrast': round(contrast, 2),
            'blur_laplacian': None, 'edge_density': round(edge_density, 4),
            'mean_rgb': mean_rgb, 'hist8_rgb': None, 'shot_type_cv': shot_type,
            'face_count': 0, 'face_boxes': [],
            'ocr_ready': OCR_READY, 'text_detected': bool(text_result.get('text')),
            'ocr_text_preview': text_result.get('text', '')[:160],
            'object_hints': object_hints,
            'cinematic_grade': grade, 'phash': phash,
        }

    def _detect_faces(self, gray) -> tuple[int, list[dict[str, int]]]:
        if not CV_READY:
            return 0, []
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            cascade = cv2.CascadeClassifier(cascade_path)
            if cascade.empty():
                return 0, []
            faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(28, 28))
            boxes = [{'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)} for (x, y, w, h) in faces[:20]]
            return len(faces), boxes
        except Exception:
            return 0, []

    def _ocr_image(self, path: Path) -> dict[str, Any]:
        if not OCR_READY:
            return {'ocr_ready': False, 'text': ''}
        try:
            text = pytesseract.image_to_string(str(path), lang='eng+rus')
            text = ' '.join(text.split())
            return {'ocr_ready': True, 'text': text}
        except Exception as e:
            return {'ocr_ready': True, 'error': str(e), 'text': ''}

    # ---------------------------- VIDEO ANALYSIS ----------------------------
    def _analyze_video(self, path: Path) -> dict[str, Any]:
        if not CV_READY:
            return self._analyze_video_ffprobe(path)
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return self._analyze_video_ffprobe(path) | {'error': 'opencv_cannot_open_video'}
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = round(frame_count / max(fps, 1.0), 2) if frame_count else 0.0
        sample_count = min(24, max(5, int(duration // 2) if duration else 5))
        if frame_count <= 0:
            indexes = []
        else:
            indexes = sorted(set(int(i * max(frame_count - 1, 1) / max(sample_count - 1, 1)) for i in range(sample_count)))
        prev_hist = None
        scene_candidates: list[dict[str, Any]] = []
        brightness_values: list[float] = []
        edge_values: list[float] = []
        blur_values: list[float] = []
        face_total = 0
        for n, idx in enumerate(indexes):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = float(gray.mean())
            blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            edges = cv2.Canny(gray, 80, 160)
            edge_density = float((edges > 0).mean())
            brightness_values.append(brightness)
            blur_values.append(blur)
            edge_values.append(edge_density)
            face_count, _ = self._detect_faces(gray)
            face_total += face_count
            hist = cv2.calcHist([gray], [0], None, [48], [0, 256]).flatten()
            hist = hist / max(float(hist.sum()), 1.0)
            if prev_hist is not None:
                diff = float(cv2.compareHist(prev_hist.astype('float32'), hist.astype('float32'), cv2.HISTCMP_BHATTACHARYYA))
                if diff > 0.34:
                    scene_candidates.append({'scene_index': len(scene_candidates) + 1, 'time_sec': round(idx / max(fps, 1.0), 2), 'confidence': round(min(0.99, diff), 3), 'reason': f'histogram_diff={diff:.3f}'})
            prev_hist = hist
        cap.release()
        avg_brightness = self._avg(brightness_values)
        avg_edges = self._avg(edge_values)
        avg_blur = self._avg(blur_values)
        object_hints = self._object_hints(path.name, width, height, avg_brightness, avg_edges, [80, 120, 150], face_total)
        grade = self._cinematic_grade(avg_brightness, self._std(brightness_values), avg_blur, avg_edges, [80, 120, 150], face_total)
        return {
            'engine': 'opencv_video_cv_runtime_2_2', 'width': width, 'height': height,
            'fps': round(fps, 2), 'frame_count': frame_count, 'duration_sec': duration,
            'sampled_frames': len(indexes), 'scene_candidates': scene_candidates,
            'scene_count': max(1, len(scene_candidates) + 1) if frame_count else 0,
            'brightness': round(avg_brightness, 2), 'contrast': round(self._std(brightness_values), 2),
            'edge_density': round(avg_edges, 4), 'blur_laplacian': round(avg_blur, 2),
            'face_count': face_total, 'object_hints': object_hints,
            'text_detected': False, 'cinematic_grade': grade,
        }

    def _analyze_video_ffprobe(self, path: Path) -> dict[str, Any]:
        info = {'engine': 'ffprobe_video_metadata_2_0', 'width': 0, 'height': 0, 'fps': 0.0, 'frame_count': 0, 'duration_sec': 0.0, 'scene_candidates': [], 'scene_count': 0, 'face_count': 0, 'object_hints': self._object_hints(path.name, 0, 0, 0, 0, [0, 0, 0], 0), 'cinematic_grade': 0.5}
        exe = shutil.which('ffprobe')
        if not exe:
            info['warning'] = 'ffprobe_missing_and_opencv_unavailable'
            return info
        try:
            cmd = [exe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,avg_frame_rate,nb_frames:format=duration', '-of', 'json', str(path)]
            raw = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=8)
            data = json.loads(raw.decode('utf-8', errors='ignore'))
            stream = (data.get('streams') or [{}])[0]
            fmt = data.get('format') or {}
            fps_raw = stream.get('avg_frame_rate') or '0/1'
            num, den = [float(x) for x in fps_raw.split('/')] if '/' in fps_raw else (0.0, 1.0)
            fps = num / max(den, 1.0)
            duration = float(fmt.get('duration') or 0)
            info.update({'width': int(stream.get('width') or 0), 'height': int(stream.get('height') or 0), 'fps': round(fps, 2), 'frame_count': int(stream.get('nb_frames') or 0), 'duration_sec': round(duration, 2), 'scene_count': 1 if duration else 0})
            return info
        except Exception as e:
            info['error'] = str(e)
            return info

    # ---------------------------- MODEL HELPERS ----------------------------
    def _object_hints(self, filename: str, w: int, h: int, brightness: float, edge_density: float, mean_rgb: list[float], face_count: int) -> list[str]:
        name = filename.lower()
        hints: set[str] = set()
        for key, label in [
            ('ship', 'корабль'), ('erebus', 'корабль'), ('terror', 'корабль'), ('hull', 'корпус корабля'), ('bow', 'нос корабля'),
            ('ice', 'лёд'), ('arctic', 'арктика'), ('snow', 'снег'), ('crew', 'экипаж'), ('commander', 'капитан'),
            ('map', 'карта'), ('archive', 'архив'), ('rigging', 'такелаж'), ('deck', 'палуба'), ('drone', 'общий план')
        ]:
            if key in name:
                hints.add(label)
        if mean_rgb and len(mean_rgb) == 3 and mean_rgb[2] >= mean_rgb[0] + 6:
            hints.add('холодная палитра')
        if brightness > 175 and edge_density < 0.08:
            hints.add('туман/снег')
        if edge_density > 0.11:
            hints.add('детальная фактура')
        if face_count:
            hints.add('люди/лица')
        if not hints:
            hints.add('нейтральный визуальный материал')
        return sorted(hints)

    def _shot_type(self, aspect: float, edge_density: float, blur_score: float | None, face_count: int, object_hints: list[str]) -> str:
        if 'общий план' in object_hints or aspect > 1.9:
            return 'широкий / establishing'
        if face_count >= 2:
            return 'группа / экипаж'
        if face_count == 1:
            return 'портрет / персонаж'
        if edge_density > 0.12 and (blur_score or 100) > 120:
            return 'деталь / фактура'
        if 'карта' in object_hints or 'архив' in object_hints:
            return 'документ / архив'
        return 'общий кинематографический план'

    def _cinematic_grade(self, brightness: float, contrast: float, blur_score: float | None, edge_density: float, mean_rgb: list[float], face_count: int) -> float:
        grade = 0.52
        if 35 < brightness < 210: grade += 0.12
        if 16 < contrast < 82: grade += 0.12
        if (blur_score or 100) > 80: grade += 0.10
        if edge_density > 0.025: grade += 0.08
        if mean_rgb and len(mean_rgb) == 3 and mean_rgb[2] >= mean_rgb[0]: grade += 0.05
        if face_count: grade += 0.03
        if brightness > 235 or brightness < 15: grade -= 0.12
        return round(max(0.0, min(0.98, grade)), 3)

    def _phash_opencv(self, gray) -> str:
        small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
        dct = cv2.dct(np.float32(small))[:8, :8]
        med = np.median(dct[1:, :])
        return ''.join('1' if v > med else '0' for v in dct.flatten())

    def _avg(self, values: list[float]) -> float:
        return sum(values) / max(len(values), 1)

    def _std(self, values: list[float]) -> float:
        if not values:
            return 0.0
        avg = self._avg(values)
        return math.sqrt(sum((x - avg) ** 2 for x in values) / len(values))


    def _quality_flags(self, item: dict[str, Any]) -> list[str]:
        flags: list[str] = []
        b = float(item.get('brightness') or 0)
        c = float(item.get('contrast') or 0)
        blur = item.get('blur_laplacian')
        blur_v = float(blur or 0)
        edges = float(item.get('edge_density') or 0)
        grade = float(item.get('cinematic_grade') or 0)
        if b < 22:
            flags.append('слишком тёмный кадр')
        if b > 232:
            flags.append('пересвет')
        if blur is not None and blur_v < 45:
            flags.append('размытый кадр')
        if c < 8:
            flags.append('низкий контраст')
        if edges < 0.01:
            flags.append('мало деталей')
        if grade < 0.55:
            flags.append('низкая кинематографическая оценка')
        if not flags:
            flags.append('ok')
        return flags

    def _cv_summary_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        bad = 0; blur = 0; dark = 0; over = 0; ocr = 0; face_assets = 0
        for r in rows:
            flags = r.get('quality_flags') or []
            if flags != ['ok']:
                bad += 1
            if 'размытый кадр' in flags:
                blur += 1
            if 'слишком тёмный кадр' in flags:
                dark += 1
            if 'пересвет' in flags:
                over += 1
            if r.get('text_detected'):
                ocr += 1
            if int(r.get('face_count') or 0) > 0:
                face_assets += 1
        return {'bad_assets': bad, 'blur_assets': blur, 'dark_assets': dark, 'overexposed_assets': over, 'ocr_assets': ocr, 'assets_with_faces': face_assets}

    # ---------------------------- STORAGE / EXPORT ----------------------------
    def analyze(self) -> dict[str, Any]:
        rows = self.db.rows("SELECT id,path,filename,media_type FROM assets WHERE project_id=? AND media_type IN ('image','video')", (self.project_id,))
        image_results: list[dict[str, Any]] = []
        video_results: list[dict[str, Any]] = []
        self.db.execute('DELETE FROM cv_scene_candidates WHERE project_id=?', (self.project_id,))
        self.db.execute('DELETE FROM asset_similarity WHERE project_id=? AND reason LIKE ?', (self.project_id, 'CVModel%'))
        for r in rows:
            path = Path(r['path'])
            if r['media_type'] == 'video' or path.suffix.lower() in VIDEO_EXTS:
                data = self._analyze_video(path)
                item = {'asset_id': r['id'], 'filename': r['filename'], 'media_type': 'video', **data}
                video_results.append(item)
            else:
                data = self._analyze_image_opencv(path) if CV_READY else self._analyze_image_pillow(path)
                item = {'asset_id': r['id'], 'filename': r['filename'], 'media_type': 'image', **data}
                image_results.append(item)
            item['quality_flags'] = self._quality_flags(item)
            self._store_metadata(r, item)
            self._sync_asset_metadata(r, item)
            self._merge_visual_profile(r, item)
        duplicate_pairs = self._similar_from_phash(image_results)
        all_items = image_results + video_results
        avg_grade = round(sum(float(x.get('cinematic_grade') or 0) for x in all_items) / max(len(all_items), 1), 3)
        scene_total = sum(int(x.get('scene_count') or 0) for x in video_results)
        quality_summary = self._cv_summary_rows(all_items)
        report = {
            'engine': 'opencv_cv_runtime_2_2' if CV_READY else ('pillow_cv_runtime_2_2' if PIL_READY else 'cv_runtime_unavailable'),
            'opencv_ready': CV_READY, 'pillow_ready': PIL_READY, 'ocr_ready': OCR_READY,
            'images': len(image_results), 'videos': len(video_results), 'assets_analyzed': len(all_items),
            'scene_candidates': scene_total, 'duplicate_pairs': duplicate_pairs,
            'avg_cinematic_grade': avg_grade, **quality_summary,
        }
        payload = {'summary': report, 'items': image_results, 'videos': video_results}
        (self.export_dir / 'cv_model_report.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self._export_csv(all_items)
        self._export_scene_csv()
        self._export_html(report, all_items)
        (self.export_dir / 'cv_runtime_2_2_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.bus.emit('CV_MODEL_2_2_COMPLETED', report)
        return report

    def _store_metadata(self, asset_row, item: dict[str, Any]) -> None:
        metadata = json.dumps(item, ensure_ascii=False)
        self.db.execute(
            """INSERT OR REPLACE INTO cv_asset_metadata(
               asset_id,project_id,filename,media_type,engine,width,height,duration_sec,fps,frame_count,brightness,contrast,blur_score,edge_density,face_count,text_detected,object_hints,scene_count,cinematic_grade,phash,metadata_json,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (
                asset_row['id'], self.project_id, asset_row['filename'], asset_row['media_type'], item.get('engine'),
                int(item.get('width') or 0), int(item.get('height') or 0), float(item.get('duration_sec') or 0), float(item.get('fps') or 0), int(item.get('frame_count') or 0),
                float(item.get('brightness') or 0), float(item.get('contrast') or 0), float(item.get('blur_laplacian') or 0), float(item.get('edge_density') or 0),
                int(item.get('face_count') or 0), 1 if item.get('text_detected') else 0, json.dumps(item.get('object_hints') or [], ensure_ascii=False),
                int(item.get('scene_count') or 0), float(item.get('cinematic_grade') or 0), item.get('phash'), metadata,
            ),
        )
        self.db.execute('UPDATE cv_asset_metadata SET quality_flags=? WHERE asset_id=?', (json.dumps(item.get('quality_flags') or [], ensure_ascii=False), asset_row['id']))
        for sc in item.get('scene_candidates') or []:
            self.db.execute(
                'INSERT INTO cv_scene_candidates(project_id,asset_id,scene_index,time_sec,confidence,reason) VALUES(?,?,?,?,?,?)',
                (self.project_id, asset_row['id'], int(sc.get('scene_index') or 0), float(sc.get('time_sec') or 0), float(sc.get('confidence') or 0), sc.get('reason') or ''),
            )

    def _sync_asset_metadata(
        self,
        asset_row,
        item: dict[str, Any],
    ) -> None:
        """
        Synchronize technical media metadata with the canonical assets table.

        AssignmentPolicyRC2, TimelineEngineRC2 and RenderEngineRC2 read
        duration, width and height from assets.
        """
        self.db.execute(
            """
            UPDATE assets
            SET
                width=?,
                height=?,
                duration_sec=?
            WHERE id=?
              AND project_id=?
            """,
            (
                int(item.get("width") or 0),
                int(item.get("height") or 0),
                float(item.get("duration_sec") or 0.0),
                asset_row["id"],
                self.project_id,
            ),
        )

    def _merge_visual_profile(self, asset_row, item: dict[str, Any]) -> None:
        old = self.db.one('SELECT profile_json FROM visual_profiles WHERE asset_id=?', (asset_row['id'],))
        profile: dict[str, Any] = {}
        if old:
            try:
                profile = json.loads(old['profile_json'])
            except Exception:
                profile = {}
        profile['cv_runtime_2_2'] = item
        palette = 'холодная/сине-серая' if 'холодная палитра' in (item.get('object_hints') or []) else profile.get('palette') or 'нейтральная'
        plan = item.get('shot_type_cv') or profile.get('visual_plan') or 'универсальный'
        self.db.execute(
            '''INSERT OR REPLACE INTO visual_profiles(asset_id,project_id,profile_json,style_score,plan_type,palette,created_at)
               VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)''',
            (asset_row['id'], self.project_id, json.dumps(profile, ensure_ascii=False), float(item.get('cinematic_grade') or 0), plan, palette),
        )

    def _similar_from_phash(self, rows: list[dict[str, Any]]) -> int:
        def dist(a, b):
            return sum(x != y for x, y in zip(a, b)) if a and b and len(a) == len(b) else 99
        count = 0
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                d = dist(a.get('phash'), b.get('phash'))
                if d <= 8:
                    score = round(1 - d / 64, 3)
                    self.db.execute('INSERT INTO asset_similarity(project_id,asset_id_a,asset_id_b,score,reason) VALUES(?,?,?,?,?)', (self.project_id, a['asset_id'], b['asset_id'], score, f'CVModel 2.2 phash distance={d}'))
                    count += 1
        return count

    def _export_csv(self, rows: list[dict[str, Any]]) -> None:
        path = self.export_dir / 'cv_asset_metadata.csv'
        fields = ['asset_id', 'filename', 'media_type', 'engine', 'width', 'height', 'duration_sec', 'fps', 'frame_count', 'brightness', 'contrast', 'blur_laplacian', 'edge_density', 'face_count', 'text_detected', 'object_hints', 'scene_count', 'cinematic_grade', 'quality_flags']
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader()
            for r in rows:
                rr = dict(r)
                rr['object_hints'] = ', '.join(rr.get('object_hints') or [])
                rr['quality_flags'] = ', '.join(rr.get('quality_flags') or [])
                w.writerow(rr)

    def _export_scene_csv(self) -> None:
        rows = self.db.rows('SELECT asset_id,scene_index,time_sec,confidence,reason FROM cv_scene_candidates WHERE project_id=? ORDER BY asset_id, scene_index', (self.project_id,))
        path = self.export_dir / 'cv_scene_candidates.csv'
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(['asset_id', 'scene_index', 'time_sec', 'confidence', 'reason'])
            for r in rows:
                w.writerow([r['asset_id'], r['scene_index'], r['time_sec'], r['confidence'], r['reason']])

    def _export_html(self, report: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        trs = ''
        for r in rows:
            hints = ', '.join(r.get('object_hints') or [])
            trs += f"<tr><td>{r.get('filename')}</td><td>{r.get('media_type')}</td><td>{r.get('engine')}</td><td>{r.get('width')}×{r.get('height')}</td><td>{r.get('brightness')}</td><td>{r.get('contrast')}</td><td>{r.get('edge_density')}</td><td>{r.get('face_count')}</td><td>{hints}</td><td>{r.get('cinematic_grade')}</td><td>{', '.join(r.get('quality_flags') or [])}</td></tr>"
        html = f"""<!doctype html><meta charset='utf-8'><title>ATLAS ZERO CV Runtime 2.2</title>
<style>body{{font-family:Segoe UI,Arial;background:#0b1220;color:#e5edf8;margin:24px;font-size:13px}}.cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}.card{{background:#101b2d;border:1px solid #26364d;border-radius:14px;padding:14px}}.v{{font-size:28px;font-weight:800;color:#7dd3fc}}table{{border-collapse:collapse;width:100%;margin-top:18px}}td,th{{border-bottom:1px solid #26364d;padding:8px;text-align:left}}th{{color:#93c5fd}}</style>
<h1>ATLAS ZERO — CV Runtime 2.2</h1><div class='cards'><div class='card'>Engine<div class='v'>{report['engine']}</div></div><div class='card'>Images<div class='v'>{report['images']}</div></div><div class='card'>Videos<div class='v'>{report['videos']}</div></div><div class='card'>Scenes<div class='v'>{report['scene_candidates']}</div></div><div class='card'>Grade<div class='v'>{report['avg_cinematic_grade']}</div></div><div class='card'>Warnings<div class='v'>{report.get('bad_assets',0)}</div></div></div><table><tr><th>Файл</th><th>Тип</th><th>Engine</th><th>Размер</th><th>Яркость</th><th>Контраст</th><th>Edges</th><th>Лица</th><th>Объекты</th><th>Grade</th><th>Качество</th></tr>{trs}</table>"""
        (self.export_dir / 'cv_runtime_report.html').write_text(html, encoding='utf-8')
