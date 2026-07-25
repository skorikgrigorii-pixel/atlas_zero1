from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from az_enterprise.core.database import Database


ROOT = Path.cwd()
PROJECT_ID = "franklin"

PROJECT_DIR = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

TIMELINE_PATH = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "movie_runtime_rc1"
    / "timeline.json"
)

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".bmp", ".tif", ".tiff", ".gif",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".webm",
    ".avi", ".m4v",
}


print("=" * 72)
print("ATLAS ZERO — MULTIMEDIA ASSET AUDIT")
print("=" * 72)

disk_images = []
disk_videos = []

for path in PROJECT_DIR.rglob("*"):
    if not path.is_file():
        continue

    suffix = path.suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        disk_images.append(path)

    elif suffix in VIDEO_EXTENSIONS:
        disk_videos.append(path)


print()
print("FILES ON DISK")
print("Images/animated images =", len(disk_images))
print("Videos                 =", len(disk_videos))

folder_counts = Counter()

for path in disk_images + disk_videos:
    try:
        relative = path.relative_to(PROJECT_DIR)
        folder = relative.parts[0] if relative.parts else "."
    except ValueError:
        folder = "outside_project"

    folder_counts[folder] += 1

print()
print("FILES BY PROJECT FOLDER")

for folder, count in sorted(folder_counts.items()):
    print(f"{count:4d}  {folder}")


db = Database()
db.init()

rows = [
    dict(row)
    for row in db.rows(
        """
        SELECT
            id,
            filename,
            path,
            media_type,
            duration_sec,
            duplicate_of
        FROM assets
        WHERE project_id=?
        ORDER BY media_type, filename
        """,
        (PROJECT_ID,),
    )
]

db_counts = Counter(
    row["media_type"]
    for row in rows
)

print()
print("DATABASE ASSETS")

for media_type, count in sorted(db_counts.items()):
    print(f"{count:4d}  {media_type}")

db_video_rows = [
    row
    for row in rows
    if row["media_type"] == "video"
]

print()
print("VIDEOS REGISTERED IN DATABASE =", len(db_video_rows))

for row in db_video_rows:
    print(
        f"- {row['filename']} | "
        f"duration={row['duration_sec']} | "
        f"duplicate_of={row['duplicate_of'] or '-'}"
    )


if not TIMELINE_PATH.exists():
    raise FileNotFoundError(
        f"Timeline not found: {TIMELINE_PATH}"
    )

timeline = json.loads(
    TIMELINE_PATH.read_text(encoding="utf-8")
)

timeline_media = Counter(
    str(row.get("media_type") or "missing")
    for row in timeline
)

timeline_paths = Counter(
    str(row.get("asset_path") or "")
    for row in timeline
    if row.get("asset_path")
)

timeline_videos = [
    row
    for row in timeline
    if row.get("media_type") == "video"
]

print()
print("TIMELINE MEDIA USAGE")

for media_type, count in sorted(timeline_media.items()):
    print(f"{count:4d}  {media_type}")

print()
print("Timeline unique assets =", len(timeline_paths))
print("Timeline video shots   =", len(timeline_videos))
print(
    "Timeline unique videos =",
    len({
        row.get("asset_path")
        for row in timeline_videos
        if row.get("asset_path")
    }),
)

if timeline_videos:
    print()
    print("VIDEOS USED IN TIMELINE")

    for path, count in Counter(
        row["asset_path"]
        for row in timeline_videos
        if row.get("asset_path")
    ).most_common():
        print(f"{count:3d}  {Path(path).name}")


print()
print("VIDEO FILES FOUND ON DISK")

for path in disk_videos:
    print("-", path.relative_to(PROJECT_DIR))

print()
print("=" * 72)
