from pathlib import Path
import subprocess
import json
import re
import statistics

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID

SEGMENT_REPORT = (
    PROJECT
    / "00_Production"
    / "human_curated_corpus_v2"
    / "FILM10_VIDEO_SEGMENT_INVENTORY_V1.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "editorial_fragmenter_v1"
)

OUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT = OUT_DIR / "FILM10_SCENE_THRESHOLD_PROBE_V1.json"

THRESHOLDS = [0.18, 0.25, 0.32, 0.40]

print("=" * 120)
print("ATLAS ZERO — FILM10 REAL SCENE BOUNDARY THRESHOLD PROBE V1")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("CUT FILES  : NO")
print("RENDER     : NO")

if not SEGMENT_REPORT.exists():
    raise FileNotFoundError(SEGMENT_REPORT)

ffmpeg = "ffmpeg"
ffprobe = "ffprobe"

# -----------------------------------------------------------------------------
# Load source video paths from inventory
# -----------------------------------------------------------------------------

data = json.loads(
    SEGMENT_REPORT.read_text(
        encoding="utf-8"
    )
)

def collect_paths(obj):
    found = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()

            if (
                isinstance(v, str)
                and lk in {
                    "path",
                    "source_path",
                    "asset_path",
                    "video_path",
                    "file",
                }
            ):
                p = Path(v)

                if not p.is_absolute():
                    p = ROOT / p

                if p.exists() and p.suffix.lower() in {
                    ".mp4", ".mov", ".mkv", ".webm",
                    ".avi", ".m4v", ".mpeg", ".mpg"
                }:
                    found.append(p.resolve())

            found.extend(collect_paths(v))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(collect_paths(item))

    return found

videos = collect_paths(data)

# Inventory schema fallback: filenames only.
if not videos:

    names = set()

    def collect_names(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                collect_names(v)

        elif isinstance(obj, list):
            for v in obj:
                collect_names(v)

        elif isinstance(obj, str):
            low = obj.lower()

            if low.endswith((
                ".mp4", ".mov", ".mkv", ".webm",
                ".avi", ".m4v", ".mpeg", ".mpg"
            )):
                names.add(Path(obj).name)

    collect_names(data)

    roots = [
        PROJECT / "00_Research" / "visual_research" / "social_downloads",
        PROJECT / "02_Visuals" / "real" / "archive",
    ]

    by_name = {}

    for base in roots:
        if not base.exists():
            continue

        for p in base.rglob("*"):
            if p.is_file():
                by_name.setdefault(
                    p.name,
                    []
                ).append(p.resolve())

    for name in sorted(names):
        candidates = by_name.get(name, [])

        if len(candidates) == 1:
            videos.append(candidates[0])

videos = list(dict.fromkeys(videos))

if not videos:
    raise RuntimeError(
        "No source videos resolved from segment inventory."
    )

print()
print("SOURCE VIDEOS:", len(videos))

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def duration(path):
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if r.returncode != 0:
        return None

    try:
        return float(r.stdout.strip())
    except Exception:
        return None


def detect(path, threshold):
    """
    Metadata-only scene-change detection.
    No frames written.
    """

    vf = (
        f"select='gt(scene,{threshold})',"
        f"metadata=print"
    )

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i", str(path),
        "-an",
        "-vf", vf,
        "-f", "null",
        "-"
    ]

    r = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )

    text = (r.stdout or "") + "\n" + (r.stderr or "")

    times = []

    # FFmpeg metadata filter normally prints:
    # frame:... pts:... pts_time:12.345
    for m in re.finditer(
        r"pts_time[:=]\s*([0-9]+(?:\.[0-9]+)?)",
        text
    ):
        try:
            times.append(float(m.group(1)))
        except Exception:
            pass

    # deduplicate timestamps
    cleaned = []

    for t in sorted(times):
        if not cleaned or abs(t - cleaned[-1]) > 0.05:
            cleaned.append(t)

    return cleaned


def fragment_lengths(boundaries, total):
    points = [0.0]

    for t in boundaries:
        if 0.05 < t < total - 0.05:
            points.append(t)

    points.append(total)

    points = sorted(set(points))

    return [
        points[i + 1] - points[i]
        for i in range(len(points) - 1)
        if points[i + 1] > points[i]
    ]


# -----------------------------------------------------------------------------
# Probe
# -----------------------------------------------------------------------------

rows = []

for idx, path in enumerate(videos, 1):

    dur = duration(path)

    print()
    print("=" * 120)
    print(
        f"{idx:02d}/{len(videos):02d} | "
        f"{dur if dur is not None else 0:.3f}s | "
        f"{path.name}"
    )
    print("=" * 120)

    video_row = {
        "path": str(path),
        "filename": path.name,
        "duration_sec": dur,
        "thresholds": {},
    }

    if dur is None or dur <= 0:
        video_row["error"] = "duration unavailable"
        rows.append(video_row)
        continue

    for threshold in THRESHOLDS:

        boundaries = detect(
            path,
            threshold
        )

        lengths = fragment_lengths(
            boundaries,
            dur
        )

        short_2 = sum(
            1 for x in lengths if x < 2.0
        )

        short_4 = sum(
            1 for x in lengths if x < 4.0
        )

        median_len = (
            statistics.median(lengths)
            if lengths else dur
        )

        result = {
            "threshold": threshold,
            "scene_changes": len(boundaries),
            "fragments": len(lengths),
            "median_fragment_sec": median_len,
            "under_2_sec": short_2,
            "under_4_sec": short_4,
            "boundaries_sec": boundaries,
        }

        video_row["thresholds"][
            str(threshold)
        ] = result

        print(
            f"threshold={threshold:.2f}"
            f" | changes={len(boundaries):4d}"
            f" | fragments={len(lengths):4d}"
            f" | median={median_len:7.3f}s"
            f" | <2s={short_2:3d}"
            f" | <4s={short_4:3d}"
        )

    rows.append(video_row)

# -----------------------------------------------------------------------------
# Corpus summary
# -----------------------------------------------------------------------------

print()
print("=" * 120)
print("CORPUS SUMMARY")
print("=" * 120)

summary = {}

for threshold in THRESHOLDS:

    changes = 0
    fragments = 0
    under_2 = 0
    under_4 = 0
    medians = []

    for row in rows:

        r = row.get(
            "thresholds",
            {}
        ).get(
            str(threshold)
        )

        if not r:
            continue

        changes += r["scene_changes"]
        fragments += r["fragments"]
        under_2 += r["under_2_sec"]
        under_4 += r["under_4_sec"]

        medians.append(
            r["median_fragment_sec"]
        )

    corpus_median = (
        statistics.median(medians)
        if medians else 0
    )

    summary[str(threshold)] = {
        "scene_changes": changes,
        "fragments": fragments,
        "median_video_fragment_sec": corpus_median,
        "under_2_sec": under_2,
        "under_4_sec": under_4,
    }

    print(
        f"{threshold:.2f}"
        f" | changes={changes:5d}"
        f" | fragments={fragments:5d}"
        f" | median={corpus_median:7.3f}s"
        f" | <2s={under_2:4d}"
        f" | <4s={under_4:4d}"
    )

# -----------------------------------------------------------------------------
# Recommendation heuristic
# -----------------------------------------------------------------------------

candidates = []

for threshold in THRESHOLDS:

    s = summary[str(threshold)]

    if not s["fragments"]:
        continue

    short_ratio = (
        s["under_4_sec"]
        / s["fragments"]
    )

    median = s[
        "median_video_fragment_sec"
    ]

    # Desired documentary source fragment range:
    # roughly 4–20 sec, without excessive micro-cuts.
    score = 0

    if 4 <= median <= 20:
        score += 3

    elif 2 <= median < 4:
        score += 1

    if short_ratio <= 0.25:
        score += 3

    elif short_ratio <= 0.40:
        score += 1

    # Prefer middle thresholds when otherwise equal.
    score -= abs(
        threshold - 0.32
    )

    candidates.append(
        (
            score,
            threshold,
            short_ratio,
            median,
        )
    )

if candidates:

    candidates.sort(
        reverse=True
    )

    best = candidates[0]

    recommendation = {
        "threshold": best[1],
        "score": best[0],
        "under_4_ratio": best[2],
        "median_fragment_sec": best[3],
    }

else:
    recommendation = None

print()
print("=" * 120)
print("PROVISIONAL RECOMMENDATION")
print("=" * 120)

if recommendation:

    print(
        "THRESHOLD:",
        recommendation["threshold"]
    )

    print(
        "MEDIAN:",
        f"{recommendation['median_fragment_sec']:.3f}s"
    )

    print(
        "UNDER 4 SEC:",
        f"{recommendation['under_4_ratio']:.2%}"
    )

else:
    print("NO RECOMMENDATION")

# -----------------------------------------------------------------------------
# Save
# -----------------------------------------------------------------------------

payload = {
    "schema":
        "atlas_zero.film10.scene_threshold_probe.v1",

    "project_id":
        PROJECT_ID,

    "source_video_count":
        len(videos),

    "thresholds":
        THRESHOLDS,

    "summary":
        summary,

    "recommendation":
        recommendation,

    "videos":
        rows,

    "db_writes":
        False,

    "cut_files":
        False,

    "render":
        False,

    "paid_calls":
        False,
}

REPORT.write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("=" * 120)
print("OUTPUT")
print("=" * 120)
print(REPORT)

print()
print("=" * 120)
print("SCENE THRESHOLD PROBE COMPLETE")
print("=" * 120)
print("No files cut.")
print("No DB writes.")
print("No render.")
print("No paid API calls.")
