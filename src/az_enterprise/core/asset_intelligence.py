from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path
from .database import Database
from .paths import FRANKLIN, MEDIA_DIRS
from .events import EventBus

IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.heic'}
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm', '.mts', '.m2ts'}
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
    def __init__(
        self,
        db: Database,
        project_id: str = "franklin",
        root: Path = FRANKLIN,
        direct_root_scan: bool = False,
    ):
        self.db = db
        self.project_id = project_id
        self.root = Path(root)
        self.direct_root_scan = direct_root_scan
        self.bus = EventBus(db, project_id)

    def _unique_destination(self, destination: Path) -> Path:
        """Return an unused destination path without overwriting a file."""
        if not destination.exists():
            return destination

        counter = 1
        while True:
            candidate = (
                destination.parent
                / f"{destination.stem}_{counter}{destination.suffix}"
            )
            if not candidate.exists():
                return candidate
            counter += 1

    def _move_videos_from_images(self) -> list[dict[str, str]]:
        """
        Move video files from 02_Images to 03_Video before indexing.

        Existing media type recognition is reused. Relative subfolders are
        preserved, existing files are never overwritten, and external sources
        remain read-only.
        """
        if self.direct_root_scan:
            return []

        images_dir = self.root / MEDIA_DIRS["image"]
        videos_dir = self.root / MEDIA_DIRS["video"]

        if not images_dir.exists():
            return []

        moved: list[dict[str, str]] = []
        video_files = sorted(
            (
                path
                for path in images_dir.rglob("*")
                if path.is_file() and media_type(path) == "video"
            ),
            key=lambda path: str(path).lower(),
        )

        for source in video_files:
            relative_path = source.relative_to(images_dir)
            destination = videos_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination = self._unique_destination(destination)

            try:
                shutil.move(str(source), str(destination))
            except OSError as error:
                print(
                    f"[ASSETS][AUTO-SORT][ERROR] "
                    f"file={source.name} error={error}"
                )
                continue

            moved.append(
                {
                    "source": str(source),
                    "destination": str(destination),
                }
            )
            print(
                f"[ASSETS][AUTO-SORT] video={source.name} "
                f"destination={destination}"
            )

        if moved:
            print(
                f"[ASSETS][AUTO-SORT] moved_videos={len(moved)} "
                f"from={images_dir} to={videos_dir}"
            )

        return moved

    def _media_folders(self) -> list[Path]:
        if self.direct_root_scan:
            return [self.root]

        return [
            self.root / rel
            for rel in MEDIA_DIRS.values()
        ]

    def scan(self) -> dict:
        self.db.execute(
            """
            INSERT OR IGNORE INTO projects(
                id,
                title,
                duration_sec
            )
            VALUES(?,?,?)
            """,
            (
                self.project_id,
                self.project_id,
                0,
            ),
        )
        # Reuse existing media type recognition to move videos that were
        # accidentally copied into 02_Images.
        moved_videos = self._move_videos_from_images()

        # Alpha 2.0.2: rebuild asset catalog on every scan to avoid stale paths after
        # Windows-safe filename shortening or moving the project folder.
        try:
            self.db.execute("DELETE FROM assets WHERE project_id=?", (self.project_id,))
        except Exception:
            pass
        found = []
        seen_hashes: dict[str,str] = {}
        scanned_bytes = 0
        scanned_files = 0

        for folder in self._media_folders():
            if not folder.exists():
                continue

            for p in folder.rglob("*"):
                if not p.is_file():
                    continue
                mt = media_type(p)
                if mt == 'document' and p.suffix.lower() not in {'.txt','.md','.pdf','.docx','.csv','.json'}:
                    continue
                digest = sha256(p)
                category, tags, emotion, quality = infer_tags(p.name)

                # Asset IDs must remain unique across projects.
                project_digest = hashlib.sha256(
                    f"{self.project_id}:{digest}".encode("utf-8")
                ).hexdigest()
                asset_id = project_digest[:24]

                scanned_files += 1
                try:
                    scanned_bytes += p.stat().st_size
                except OSError:
                    pass

                if (
                    scanned_files == 1
                    or scanned_files % 10 == 0
                ):
                    print(
                        f"[ASSETS] indexed={scanned_files} "
                        f"size_gb={scanned_bytes / 1024**3:.3f} "
                        f"file={p.name}"
                    )
                duplicate_of = seen_hashes.get(digest)
                if not duplicate_of:
                    seen_hashes[digest] = asset_id
                self.db.execute(
                    """
                    INSERT INTO assets(
                        id,
                        project_id,
                        path,
                        filename,
                        media_type,
                        sha256,
                        category,
                        tags,
                        emotion,
                        quality,
                        duplicate_of
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        project_id=excluded.project_id,
                        path=excluded.path,
                        filename=excluded.filename,
                        media_type=excluded.media_type,
                        sha256=excluded.sha256,
                        category=excluded.category,
                        tags=excluded.tags,
                        emotion=excluded.emotion,
                        quality=excluded.quality,
                        duplicate_of=excluded.duplicate_of
                    """,
                    (
                        asset_id,
                        self.project_id,
                        str(p),
                        p.name,
                        mt,
                        digest,
                        category,
                        json.dumps(
                            tags,
                            ensure_ascii=False,
                        ),
                        emotion,
                        quality,
                        duplicate_of,
                    ),
                )
                found.append(asset_id)
        duplicate_count = int(
            self.db.one(
                """
                SELECT COUNT(*) AS count
                FROM assets
                WHERE project_id=?
                  AND duplicate_of IS NOT NULL
                """,
                (self.project_id,),
            )["count"]
        )

        result = {
            "assets": len(found),
            "duplicates": duplicate_count,
            "source_dir": str(self.root),
            "direct_root_scan": self.direct_root_scan,
            "scanned_bytes": scanned_bytes,
            "source_files_modified": bool(moved_videos),
            "moved_videos": len(moved_videos),
            "moved_video_files": moved_videos,
        }

        self.bus.emit("ASSETS_SCANNED", result)
        return result

    def stats(self) -> dict:
        rows = self.db.rows("SELECT media_type, COUNT(*) c FROM assets WHERE project_id=? GROUP BY media_type", (self.project_id,))
        return {r['media_type']: r['c'] for r in rows}
