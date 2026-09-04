from pathlib import Path
import json
import subprocess
import re
import hashlib
import html

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID

PROBE = (
    PROJECT
    / "00_Production"
    / "editorial_fragmenter_v1"
    / "FILM10_SCENE_THRESHOLD_PROBE_V1.json"
)

OUT = (
    PROJECT
    / "00_Production"
    / "editorial_fragmenter_v2"
)

PREVIEWS = OUT / "previews"

OUT.mkdir(parents=True, exist_ok=True)
PREVIEWS.mkdir(parents=True, exist_ok=True)

REPORT = OUT / "FILM10_EDITORIAL_FRAGMENTS_V2.json"
HTML = OUT / "FILM10_EDITORIAL_FRAGMENTS_V2.html"

THRESHOLD = 0.40

# Editorial rules
MIN_FRAGMENT = 4.0
TARGET_MAX = 14.0
HARD_MAX = 20.0

print("=" * 120)
print("ATLAS ZERO — FILM10 EDITORIAL FRAGMENT BUILDER V2")
print("=" * 120)
print("PROJECT       :", PROJECT_ID)
print("SCENE THRESH :", THRESHOLD)
print("MIN FRAGMENT :", MIN_FRAGMENT)
print("TARGET MAX   :", TARGET_MAX)
print("HARD MAX     :", HARD_MAX)
print("LIVE API     : 0")
print("PAID CALLS   : 0")
print("DB WRITES    : NO")
print("SOURCE CUT   : NO")
print("RENDER       : NO")

if not PROBE.exists():
    raise FileNotFoundError(PROBE)

probe = json.loads(PROBE.read_text(encoding="utf-8"))

videos = probe.get("videos") or []

if not videos:
    raise RuntimeError("No videos in scene threshold probe.")

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def make_id(path, start, end):
    raw = f"{path}|{start:.3f}|{end:.3f}"
    return "frag_" + hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]


def clean_boundaries(boundaries, duration):
    values = [0.0]

    for x in boundaries:
        try:
            t = float(x)
        except Exception:
            continue

        if 0.05 < t < duration - 0.05:
            values.append(t)

    values.append(duration)

    values = sorted(set(round(x, 3) for x in values))

    return values


def base_fragments(boundaries):
    result = []

    for i in range(len(boundaries) - 1):
        a = boundaries[i]
        b = boundaries[i + 1]

        if b > a:
            result.append([a, b])

    return result


def merge_micro_fragments(frags):
    """
    Merge <4 sec fragments into nearest neighbour.
    Never deletes source time.
    """

    frags = [list(x) for x in frags]

    changed = True

    while changed and len(frags) > 1:

        changed = False

        for i, (a, b) in enumerate(frags):

            dur = b - a

            if dur >= MIN_FRAGMENT:
                continue

            # First fragment -> merge right.
            if i == 0:
                frags[1][0] = a
                del frags[0]
                changed = True
                break

            # Last fragment -> merge left.
            if i == len(frags) - 1:
                frags[i - 1][1] = b
                del frags[i]
                changed = True
                break

            left_duration = frags[i - 1][1] - frags[i - 1][0]
            right_duration = frags[i + 1][1] - frags[i + 1][0]

            # Prefer neighbour producing less oversized result.
            left_total = left_duration + dur
            right_total = right_duration + dur

            if left_total <= right_total:
                frags[i - 1][1] = b
                del frags[i]
            else:
                frags[i + 1][0] = a
                del frags[i]

            changed = True
            break

    return frags


def split_long_fragment(a, b):
    """
    Continuous shots can still be too long for documentary editing.
    Split them into editorial windows without altering source.
    """

    duration = b - a

    if duration <= HARD_MAX:
        return [[a, b]]

    # Determine reasonable number of pieces around TARGET_MAX.
    pieces = max(
        2,
        round(duration / TARGET_MAX)
    )

    piece_duration = duration / pieces

    # If rounding still creates > HARD_MAX, increase pieces.
    while piece_duration > HARD_MAX:
        pieces += 1
        piece_duration = duration / pieces

    result = []

    cursor = a

    for i in range(pieces):

        if i == pieces - 1:
            end = b
        else:
            end = a + piece_duration * (i + 1)

        result.append([
            round(cursor, 3),
            round(end, 3)
        ])

        cursor = end

    return result


def create_preview(source, start, end, output):
    mid = start + ((end - start) / 2)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{mid:.3f}",
        "-i", str(source),
        "-frames:v", "1",
        "-vf",
        "scale=640:-2:force_original_aspect_ratio=decrease",
        "-q:v", "3",
        str(output),
    ]

    r = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace"
    )

    return r.returncode == 0 and output.exists()


def tc(seconds):
    seconds = max(0, float(seconds))

    m = int(seconds // 60)
    s = seconds - m * 60

    return f"{m:02d}:{s:06.3f}"


# -------------------------------------------------------------------------
# Build editorial fragments
# -------------------------------------------------------------------------

all_fragments = []

video_summaries = []

for vi, row in enumerate(videos, 1):

    source = Path(row["path"])
    duration = float(row["duration_sec"])

    threshold_data = (
        row.get("thresholds", {})
        .get(str(THRESHOLD))
    )

    # JSON may serialize key as "0.4".
    if threshold_data is None:
        threshold_data = (
            row.get("thresholds", {})
            .get("0.4")
        )

    if threshold_data is None:
        raise RuntimeError(
            f"No threshold {THRESHOLD} data for {source.name}"
        )

    boundaries = threshold_data.get(
        "boundaries_sec",
        []
    )

    points = clean_boundaries(
        boundaries,
        duration
    )

    raw = base_fragments(points)

    merged = merge_micro_fragments(raw)

    editorial = []

    for a, b in merged:
        editorial.extend(
            split_long_fragment(a, b)
        )

    print()
    print(
        f"{vi:02d}/{len(videos):02d} | "
        f"{duration:8.3f}s | "
        f"scene={len(raw):3d} | "
        f"merged={len(merged):3d} | "
        f"editorial={len(editorial):3d} | "
        f"{source.name}"
    )

    summary = {
        "source_path": str(source),
        "filename": source.name,
        "duration_sec": duration,
        "scene_fragments": len(raw),
        "after_micro_merge": len(merged),
        "editorial_fragments": len(editorial),
    }

    video_summaries.append(summary)

    for a, b in editorial:

        fragment_id = make_id(
            source,
            a,
            b
        )

        preview = PREVIEWS / f"{fragment_id}.jpg"

        preview_ok = create_preview(
            source,
            a,
            b,
            preview
        )

        item = {
            "fragment_id": fragment_id,
            "source_path": str(source),
            "filename": source.name,
            "source_start": round(a, 3),
            "source_end": round(b, 3),
            "duration_sec": round(b - a, 3),
            "source_start_tc": tc(a),
            "source_end_tc": tc(b),
            "preview_path":
                str(preview) if preview_ok else None,
            "scene_threshold": THRESHOLD,
            "human_curated_source": True,
            "production_eligible": None,
            "editorial_label": None,
            "editorial_notes": None,
        }

        all_fragments.append(item)

# -------------------------------------------------------------------------
# Validation
# -------------------------------------------------------------------------

too_short = [
    x for x in all_fragments
    if x["duration_sec"] < MIN_FRAGMENT - 0.01
]

too_long = [
    x for x in all_fragments
    if x["duration_sec"] > HARD_MAX + 0.01
]

missing_previews = [
    x for x in all_fragments
    if not x["preview_path"]
]

total_source_time = sum(
    float(x["duration_sec"])
    for x in videos
)

total_fragment_time = sum(
    x["duration_sec"]
    for x in all_fragments
)

print()
print("=" * 120)
print("EDITORIAL FRAGMENT SUMMARY")
print("=" * 120)
print("SOURCE VIDEOS       :", len(videos))
print("EDITORIAL FRAGMENTS :", len(all_fragments))
print("SOURCE TIME         :", f"{total_source_time:.3f}s")
print("FRAGMENT TIME       :", f"{total_fragment_time:.3f}s")
print("TIME DELTA          :", f"{total_fragment_time-total_source_time:+.3f}s")
print("UNDER 4 SEC         :", len(too_short))
print("OVER 20 SEC         :", len(too_long))
print("MISSING PREVIEWS    :", len(missing_previews))

# -------------------------------------------------------------------------
# JSON
# -------------------------------------------------------------------------

payload = {
    "schema":
        "atlas_zero.film10.editorial_fragments.v2",

    "project_id":
        PROJECT_ID,

    "scene_threshold":
        THRESHOLD,

    "rules": {
        "min_fragment_sec": MIN_FRAGMENT,
        "target_max_sec": TARGET_MAX,
        "hard_max_sec": HARD_MAX,
        "micro_fragments_merged": True,
        "long_continuous_scenes_windowed": True,
        "source_files_modified": False,
    },

    "summary": {
        "source_videos": len(videos),
        "editorial_fragments": len(all_fragments),
        "source_time_sec": round(total_source_time, 3),
        "fragment_time_sec": round(total_fragment_time, 3),
        "time_delta_sec":
            round(total_fragment_time-total_source_time, 3),
        "under_min": len(too_short),
        "over_max": len(too_long),
        "missing_previews": len(missing_previews),
    },

    "videos":
        video_summaries,

    "fragments":
        all_fragments,

    "db_writes":
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
    encoding="utf-8"
)

# -------------------------------------------------------------------------
# HTML contact sheet
# -------------------------------------------------------------------------

cards = []

for idx, item in enumerate(all_fragments, 1):

    preview_path = item.get("preview_path")

    if preview_path:
        try:
            rel = Path(preview_path).relative_to(
                HTML.parent
            ).as_posix()
        except Exception:
            rel = Path(preview_path).as_uri()
    else:
        rel = ""

    image_html = (
        f'<img src="{html.escape(rel)}">'
        if rel
        else '<div class="missing">NO PREVIEW</div>'
    )

    cards.append(
        f"""
        <div class="card">
            <div class="head">
                #{idx:03d}
            </div>

            {image_html}

            <div class="body">
                <div class="time">
                    {item["source_start_tc"]}
                    →
                    {item["source_end_tc"]}
                </div>

                <div class="duration">
                    {item["duration_sec"]:.3f} sec
                </div>

                <div class="file">
                    {html.escape(item["filename"])}
                </div>

                <div class="id">
                    {item["fragment_id"]}
                </div>
            </div>
        </div>
        """
    )

html_doc = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Film10 Editorial Fragments V2</title>

<style>

body {{
    margin: 0;
    padding: 24px;
    background: #111;
    color: #eee;
    font-family: Arial, sans-serif;
}}

h1 {{
    margin-top: 0;
}}

.summary {{
    margin-bottom: 24px;
    padding: 16px;
    background: #1c1c1c;
    border-radius: 8px;
}}

.grid {{
    display: grid;
    grid-template-columns:
        repeat(3, minmax(0, 1fr));
    gap: 18px;
}}

.card {{
    background: #1b1b1b;
    border: 1px solid #444;
    border-radius: 8px;
    overflow: hidden;
}}

.head {{
    font-size: 25px;
    font-weight: bold;
    padding: 12px;
}}

.card img {{
    display: block;
    width: 100%;
    height: 260px;
    object-fit: contain;
    background: black;
}}

.body {{
    padding: 14px;
}}

.time {{
    font-size: 20px;
    font-weight: bold;
}}

.duration {{
    margin-top: 5px;
    color: #ccc;
}}

.file {{
    margin-top: 10px;
    word-break: break-word;
}}

.id {{
    margin-top: 10px;
    color: #888;
    font-size: 12px;
}}

.missing {{
    height: 260px;
    display:flex;
    align-items:center;
    justify-content:center;
    background:#300;
}}

</style>
</head>

<body>

<h1>FILM10 — Editorial Fragments V2</h1>

<div class="summary">
    <b>Scene threshold:</b> {THRESHOLD}<br>
    <b>Source videos:</b> {len(videos)}<br>
    <b>Editorial fragments:</b> {len(all_fragments)}<br>
    <b>Source time:</b> {total_source_time:.3f}s<br>
    <b>Fragment time:</b> {total_fragment_time:.3f}s<br>
    <b>Under 4 sec:</b> {len(too_short)}<br>
    <b>Over 20 sec:</b> {len(too_long)}<br>
</div>

<div class="grid">
{''.join(cards)}
</div>

</body>
</html>
"""

HTML.write_text(
    html_doc,
    encoding="utf-8"
)

print()
print("=" * 120)
print("OUTPUT")
print("=" * 120)
print("JSON :", REPORT)
print("HTML :", HTML)

print()
print("=" * 120)

if (
    not too_short
    and not too_long
    and not missing_previews
    and abs(total_fragment_time-total_source_time) < 0.2
):
    print("FILM10 EDITORIAL FRAGMENT BUILDER V2: PASS")
else:
    print("FILM10 EDITORIAL FRAGMENT BUILDER V2: REVIEW")

print("=" * 120)
print("Original source videos were NOT modified.")
print("No DB writes.")
print("No render.")
print("No paid API calls.")

# Open catalogue automatically.
subprocess.Popen(
    ["cmd", "/c", "start", "", str(HTML)],
    shell=False
)
