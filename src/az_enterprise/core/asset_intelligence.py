from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .database import Database
from .events import EventBus
from .paths import FRANKLIN, MEDIA_DIRS


IMAGE_EXT = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
}
VIDEO_EXT = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".m4v",
    ".webm",
    ".mts",
    ".m2ts",
}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac"}

KEYWORDS = {
    "ice": [
        "ice",
        "лед",
        "arctic",
        "снег",
        "snow",
        "frozen",
        "pressure",
        "closeic",
    ],
    "ship": [
        "ship",
        "erebus",
        "terror",
        "кораб",
        "hull",
        "bow",
        "deck",
        "mast",
    ],
    "crew": [
        "crew",
        "captain",
        "commander",
        "sailor",
        "franklin",
        "экипаж",
    ],
    "rigging": ["rigging", "rope", "sail", "такелаж"],
    "map": ["map", "карта", "route"],
    "archive": [
        "archive",
        "document",
        "paper",
        "note",
        "записка",
        "paper",
    ],
    "lab": ["lab", "dna", "ct", "микроскоп", "лаборат"],
    "audio": ["audio", "озвуч", "voice", "elevenlabs"],
    "video": ["hailuo", "video", "motion"],
}

EMOTIONS = {
    "threat": ["pressure", "ice", "storm", "dark", "bones", "skeleton"],
    "isolation": ["wide", "aerial", "drone", "arctic", "fog"],
    "investigation": ["document", "map", "lab", "archive", "note"],
    "human": ["crew", "captain", "commander", "portrait"],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def media_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return "document"


def infer_tags(name: str) -> tuple[str, list[str], str, float]:
    normalized_name = name.lower()
    tags: list[str] = []
    category = "general"

    for candidate_category, keys in KEYWORDS.items():
        if any(key in normalized_name for key in keys):
            tags.append(candidate_category)
            if category == "general":
                category = candidate_category

    emotion = "neutral"
    for candidate_emotion, keys in EMOTIONS.items():
        if any(key in normalized_name for key in keys):
            emotion = candidate_emotion
            break

    quality = 0.55 + min(len(tags) * 0.08, 0.35)
    if (
        "master" in normalized_name
        or "wide" in normalized_name
        or "hailuo" in normalized_name
    ):
        quality += 0.08

    return (
        category,
        sorted(set(tags)),
        emotion,
        round(min(quality, 0.98), 3),
    )


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
                    "[ASSETS][AUTO-SORT][ERROR] "
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

        return [self.root / rel for rel in MEDIA_DIRS.values()]

    @staticmethod
    def _probe_video(path: Path) -> dict[str, Any]:
        """
        Read only lightweight technical video metadata.

        This deliberately does not invoke CVModel, scene detection, OCR,
        similarity analysis or frame sampling.
        """
        fallback = {
            "width": 0,
            "height": 0,
            "duration_sec": 0.0,
        }

        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            print(
                "[ASSETS][METADATA][WARNING] "
                f"ffprobe_not_found file={path.name}"
            )
            return fallback

        command = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(path),
        ]

        try:
            raw = subprocess.check_output(
                command,
                stderr=subprocess.STDOUT,
                timeout=20,
            )
            payload = json.loads(
                raw.decode("utf-8", errors="replace")
            )
            streams = payload.get("streams") or []
            stream = streams[0] if streams else {}
            format_data = payload.get("format") or {}

            return {
                "width": int(stream.get("width") or 0),
                "height": int(stream.get("height") or 0),
                "duration_sec": round(
                    float(format_data.get("duration") or 0.0),
                    3,
                ),
            }
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            print(
                "[ASSETS][METADATA][WARNING] "
                f"file={path.name} error={error}"
            )
            return fallback

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

        moved_videos = self._move_videos_from_images()

        # Rebuild the asset catalog on every scan so paths never become stale.
        try:
            self.db.execute(
                "DELETE FROM assets WHERE project_id=?",
                (self.project_id,),
            )
        except Exception:
            pass

        found: list[str] = []
        seen_hashes: dict[str, str] = {}
        scanned_bytes = 0
        scanned_files = 0
        videos_probed = 0
        videos_with_duration = 0
        video_metadata_failures = 0

        for folder in self._media_folders():
            if not folder.exists():
                continue

            for path in folder.rglob("*"):
                if not path.is_file():
                    continue

                asset_media_type = media_type(path)
                if (
                    asset_media_type == "document"
                    and path.suffix.lower()
                    not in {
                        ".txt",
                        ".md",
                        ".pdf",
                        ".docx",
                        ".csv",
                        ".json",
                    }
                ):
                    continue

                digest = sha256(path)
                category, tags, emotion, quality = infer_tags(path.name)

                project_digest = hashlib.sha256(
                    f"{self.project_id}:{digest}".encode("utf-8")
                ).hexdigest()
                asset_id = project_digest[:24]

                scanned_files += 1
                try:
                    scanned_bytes += path.stat().st_size
                except OSError:
                    pass

                if scanned_files == 1 or scanned_files % 10 == 0:
                    print(
                        f"[ASSETS] indexed={scanned_files} "
                        f"size_gb={scanned_bytes / 1024**3:.3f} "
                        f"file={path.name}"
                    )

                duplicate_of = seen_hashes.get(digest)
                if not duplicate_of:
                    seen_hashes[digest] = asset_id

                width = 0
                height = 0
                duration_sec = 0.0

                if asset_media_type == "video":
                    metadata = self._probe_video(path)
                    width = int(metadata["width"])
                    height = int(metadata["height"])
                    duration_sec = float(metadata["duration_sec"])
                    videos_probed += 1

                    if duration_sec > 0.0:
                        videos_with_duration += 1
                    else:
                        video_metadata_failures += 1

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
                        duplicate_of,
                        width,
                        height,
                        duration_sec
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                        duplicate_of=excluded.duplicate_of,
                        width=excluded.width,
                        height=excluded.height,
                        duration_sec=excluded.duration_sec
                    """,
                    (
                        asset_id,
                        self.project_id,
                        str(path),
                        path.name,
                        asset_media_type,
                        digest,
                        category,
                        json.dumps(tags, ensure_ascii=False),
                        emotion,
                        quality,
                        duplicate_of,
                        width,
                        height,
                        duration_sec,
                    ),
                )
                found.append(asset_id)

        duplicate_row = self.db.one(
            """
            SELECT COUNT(*) AS count
            FROM assets
            WHERE project_id=?
              AND duplicate_of IS NOT NULL
            """,
            (self.project_id,),
        )
        duplicate_count = int(
            duplicate_row["count"] if duplicate_row else 0
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
            "videos_probed": videos_probed,
            "videos_with_duration": videos_with_duration,
            "video_metadata_failures": video_metadata_failures,
        }

        self.bus.emit("ASSETS_SCANNED", result)
        return result

    def stats(self) -> dict:
        rows = self.db.rows(
            """
            SELECT media_type, COUNT(*) c
            FROM assets
            WHERE project_id=?
            GROUP BY media_type
            """,
            (self.project_id,),
        )
        return {
            row["media_type"]: row["c"]
            for row in rows
        }
