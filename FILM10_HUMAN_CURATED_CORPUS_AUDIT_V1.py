from pathlib import Path
import json
import subprocess

ROOT = Path.cwd().resolve()

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / "film_10_nepal_tibet_aftershock"
)

ROOTS = {
    "ARCHIVE":
        PROJECT / "02_Visuals" / "real" / "archive",

    "SOCIAL":
        PROJECT / "00_Research" / "visual_research" / "social_downloads",
}

VIDEO_EXT = {
    ".mp4", ".mov", ".mkv", ".webm",
    ".avi", ".m4v", ".mpeg", ".mpg"
}

IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".gif", ".tif", ".tiff"
}

print("=" * 110)
print("ATLAS ZERO — FILM10 POST-HUMAN-CLEANUP CORPUS AUDIT")
print("=" * 110)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")
print()

records = []

def duration(path: Path):

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            return None

        return float(result.stdout.strip())

    except Exception:
        return None


for source, folder in ROOTS.items():

    print("=" * 110)
    print(source)
    print("=" * 110)
    print(folder)

    files = [
        p
        for p in folder.rglob("*")
        if p.is_file()
        and p.suffix.lower() in (VIDEO_EXT | IMAGE_EXT)
    ]

    print("MEDIA FILES:", len(files))
    print()

    for path in files:

        ext = path.suffix.lower()

        if ext in VIDEO_EXT:
            media_type = "video"
            seconds = duration(path)
        else:
            media_type = "image"
            seconds = None

        records.append({
            "source": source,
            "path": str(path.resolve()),
            "relative_path": str(path.relative_to(PROJECT)),
            "filename": path.name,
            "media_type": media_type,
            "duration_sec": seconds,
            "size_bytes": path.stat().st_size,
        })


videos = [
    r for r in records
    if r["media_type"] == "video"
]

images = [
    r for r in records
    if r["media_type"] == "image"
]

known_video_seconds = sum(
    r["duration_sec"]
    for r in videos
    if r["duration_sec"] is not None
)

print()
print("=" * 110)
print("CURRENT CORPUS SUMMARY")
print("=" * 110)

print("TOTAL MEDIA :", len(records))
print("VIDEOS      :", len(videos))
print("IMAGES      :", len(images))

print(
    "VIDEO TIME  :",
    f"{known_video_seconds:.3f} sec"
)

minutes = int(
    known_video_seconds // 60
)

seconds = (
    known_video_seconds
    - minutes * 60
)

print(
    "VIDEO TC    :",
    f"{minutes:02d}:{seconds:06.3f}"
)

print()
print("=" * 110)
print("VIDEOS — LONGEST FIRST")
print("=" * 110)

for r in sorted(
    videos,
    key=lambda x: x["duration_sec"] or 0,
    reverse=True,
):

    d = r["duration_sec"]

    if d is None:
        tc = "UNKNOWN"
    else:
        m = int(d // 60)
        s = d - m * 60
        tc = f"{m:02d}:{s:06.3f}"

    print(
        f"{r['source']:<8} "
        f"{tc:>10} | "
        f"{r['relative_path']}"
    )


out_dir = (
    PROJECT
    / "00_Production"
    / "human_curated_corpus_v1"
)

out_dir.mkdir(
    parents=True,
    exist_ok=True,
)

report = (
    out_dir
    / "FILM10_HUMAN_CURATED_CORPUS_V1.json"
)

report.write_text(
    json.dumps(
        {
            "project_id":
                "film_10_nepal_tibet_aftershock",

            "human_curated":
                True,

            "total_media":
                len(records),

            "videos":
                len(videos),

            "images":
                len(images),

            "video_duration_sec":
                known_video_seconds,

            "assets":
                records,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("=" * 110)
print("REPORT")
print("=" * 110)
print(report)

print()
print("No DB changes.")
print("No semantic analysis.")
print("No assignment.")
print("No render.")
