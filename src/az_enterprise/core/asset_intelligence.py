from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from .database import Database
from .paths import FRANKLIN, MEDIA_DIRS
from .events import EventBus

IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.avi'}
AUDIO_EXT = {'.mp3', '.wav', '.m4a', '.aac'}

KEYWORDS = {
    'ice': ['ice','лед','arctic','снег','snow','frozen','pressure','closeic'],
    'ship': ['ship','erebus','terror','кораб','hull','bow','deck','mast'],
    'crew': ['crew','captain','commander','sailor','franklin','экипаж'],
    'rigging': ['rigging','rope','sail','такелаж'],
    'map': ['map','карта','route'],
    'archive': ['archive','document','paper','note','записка','paper'],
    'lab': ['lab','dna','ct','микроскоп','лаборат'],
    'audio': ['audio','озвуч','voice','elevenlabs'],
    'video': ['hailuo','video','motion'],
}

EMOTIONS = {
    'threat': ['pressure','ice','storm','dark','bones','skeleton'],
    'isolation': ['wide','aerial','drone','arctic','fog'],
    'investigation': ['document','map','lab','archive','note'],
    'human': ['crew','captain','commander','portrait'],
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def media_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT: return 'image'
    if ext in VIDEO_EXT: return 'video'
    if ext in AUDIO_EXT: return 'audio'
    return 'document'

def infer_tags(name: str) -> tuple[str, list[str], str, float]:
    n = name.lower()
    tags = []
    category = 'general'
    for cat, keys in KEYWORDS.items():
        if any(k in n for k in keys):
            tags.append(cat)
            if category == 'general':
                category = cat
    emotion = 'neutral'
    for emo, keys in EMOTIONS.items():
        if any(k in n for k in keys):
            emotion = emo
            break
    quality = 0.55 + min(len(tags)*0.08, 0.35)
    if 'master' in n or 'wide' in n or 'hailuo' in n:
        quality += 0.08
    return category, sorted(set(tags)), emotion, round(min(quality, .98), 3)

class AssetIntelligence:
    def __init__(self, db: Database, project_id='franklin', root: Path = FRANKLIN):
        self.db = db
        self.project_id = project_id
        self.root = root
        self.bus = EventBus(db, project_id)

    def scan(self) -> dict:
        self.db.execute("INSERT OR IGNORE INTO projects(id,title,duration_sec) VALUES(?,?,?)", (self.project_id, 'Franklin', 960))
        # Alpha 2.0.2: rebuild asset catalog on every scan to avoid stale paths after
        # Windows-safe filename shortening or moving the project folder.
        try:
            self.db.execute("DELETE FROM assets WHERE project_id=?", (self.project_id,))
        except Exception:
            pass
        found = []
        seen_hashes: dict[str,str] = {}
        for rel in MEDIA_DIRS.values():
            folder = self.root / rel
            if not folder.exists():
                continue
            for p in folder.rglob('*'):
                if not p.is_file():
                    continue
                mt = media_type(p)
                if mt == 'document' and p.suffix.lower() not in {'.txt','.md','.pdf','.docx','.csv','.json'}:
                    continue
                digest = sha256(p)
                category, tags, emotion, quality = infer_tags(p.name)
                asset_id = digest[:16]
                duplicate_of = seen_hashes.get(digest)
                if not duplicate_of:
                    seen_hashes[digest] = asset_id
                self.db.execute("""
                    INSERT OR REPLACE INTO assets(id,project_id,path,filename,media_type,sha256,category,tags,emotion,quality,duplicate_of)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """, (asset_id, self.project_id, str(p), p.name, mt, digest, category, json.dumps(tags, ensure_ascii=False), emotion, quality, duplicate_of))
                found.append(asset_id)
        self.bus.emit('ASSETS_SCANNED', {'count': len(found)})
        return {'assets': len(found), 'duplicates': len([x for x in found if self.db.one('SELECT duplicate_of FROM assets WHERE id=?',(x,))['duplicate_of']])}

    def stats(self) -> dict:
        rows = self.db.rows("SELECT media_type, COUNT(*) c FROM assets WHERE project_id=? GROUP BY media_type", (self.project_id,))
        return {r['media_type']: r['c'] for r in rows}
