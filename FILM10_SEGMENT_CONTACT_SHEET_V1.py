from pathlib import Path
import json
import subprocess
import html
import shutil

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

SEGMENT_JSON = (
    PROJECT
    / "00_Production"
    / "human_curated_corpus_v2"
    / "FILM10_VIDEO_SEGMENT_INVENTORY_V1.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "editorial_segment_review_v1"
)

FRAMES = OUT_DIR / "frames"
HTML = OUT_DIR / "FILM10_SEGMENT_CONTACT_SHEET_V1.html"
REPORT = OUT_DIR / "FILM10_SEGMENT_CONTACT_SHEET_V1.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)
FRAMES.mkdir(parents=True, exist_ok=True)

print("=" * 120)
print("ATLAS ZERO — FILM10 HUMAN-CURATED SEGMENT CONTACT SHEET V1")
print("=" * 120)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("CLIP       : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

if not SEGMENT_JSON.exists():
    raise FileNotFoundError(SEGMENT_JSON)

ffmpeg = shutil.which("ffmpeg")

if not ffmpeg:
    raise RuntimeError("ffmpeg not found in PATH")

payload = json.loads(
    SEGMENT_JSON.read_text(
        encoding="utf-8"
    )
)

segments = payload.get(
    "segment_inventory",
    []
)

if len(segments) != 181:
    raise RuntimeError(
        f"Expected 181 segments, got {len(segments)}"
    )

# ------------------------------------------------------------------
# EXTRACT ONE REPRESENTATIVE FRAME FROM EACH TEMPORAL SEGMENT
# ------------------------------------------------------------------

results = []

print()
print("=" * 120)
print("EXTRACTING REPRESENTATIVE FRAMES")
print("=" * 120)

for n, seg in enumerate(segments, 1):

    source = Path(seg["path"])

    if not source.exists():
        raise FileNotFoundError(source)

    start = float(seg["source_start"])
    end = float(seg["source_end"])

    midpoint = start + ((end - start) / 2.0)

    frame_name = (
        f"{n:03d}_"
        f"{seg['segment_id']}_"
        f"{start:07.3f}-"
        f"{end:07.3f}.jpg"
    )

    frame_path = FRAMES / frame_name

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{midpoint:.3f}",
        "-i", str(source),
        "-frames:v", "1",
        "-vf",
        "scale=480:-2:force_original_aspect_ratio=decrease",
        "-q:v", "3",
        str(frame_path),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    ok = (
        proc.returncode == 0
        and frame_path.exists()
        and frame_path.stat().st_size > 0
    )

    print(
        f"{n:03d}/181 | "
        f"{'OK' if ok else 'FAIL':<4} | "
        f"{start:7.3f}-{end:7.3f} | "
        f"{seg['filename']}"
    )

    results.append({
        **seg,
        "review_number": n,
        "midpoint": round(midpoint, 3),
        "frame": str(frame_path),
        "frame_ok": ok,
        "ffmpeg_error": (
            None
            if ok
            else proc.stderr[-2000:]
        ),
    })

failures = [
    row
    for row in results
    if not row["frame_ok"]
]

# ------------------------------------------------------------------
# BUILD HTML CONTACT SHEET
# ------------------------------------------------------------------

cards = []

for row in results:

    frame_path = Path(row["frame"])

    try:
        relative_frame = frame_path.relative_to(
            OUT_DIR
        ).as_posix()
    except ValueError:
        relative_frame = frame_path.as_uri()

    filename = html.escape(
        row["filename"]
    )

    segment_id = html.escape(
        row["segment_id"]
    )

    image_html = (
        f'<img src="{relative_frame}" loading="lazy">'
        if row["frame_ok"]
        else '<div class="failed">FRAME FAILED</div>'
    )

    card = f"""
    <div class="card">
        <div class="number">
            #{row["review_number"]:03d}
        </div>

        {image_html}

        <div class="meta">
            <div class="time">
                {row["source_start"]:.3f}
                →
                {row["source_end"]:.3f}
            </div>

            <div class="file">
                {filename}
            </div>

            <div class="id">
                {segment_id}
            </div>
        </div>
    </div>
    """

    cards.append(card)

document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Film10 Segment Contact Sheet V1</title>

<style>
body {{
    margin: 20px;
    font-family: Arial, sans-serif;
    background: #111;
    color: #eee;
}}

h1 {{
    margin-bottom: 4px;
}}

.summary {{
    color: #aaa;
    margin-bottom: 24px;
}}

.grid {{
    display: grid;
    grid-template-columns:
        repeat(auto-fill, minmax(360px, 1fr));
    gap: 16px;
}}

.card {{
    background: #1d1d1d;
    border: 1px solid #444;
    border-radius: 8px;
    overflow: hidden;
}}

.card img {{
    display: block;
    width: 100%;
    height: 240px;
    object-fit: contain;
    background: #000;
}}

.number {{
    font-size: 22px;
    font-weight: bold;
    padding: 10px 12px;
    background: #292929;
}}

.meta {{
    padding: 12px;
}}

.time {{
    font-size: 17px;
    font-weight: bold;
    margin-bottom: 8px;
}}

.file {{
    font-size: 13px;
    word-break: break-all;
    margin-bottom: 8px;
}}

.id {{
    color: #888;
    font-size: 11px;
}}

.failed {{
    height: 240px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #300;
    font-weight: bold;
}}
</style>
</head>

<body>

<h1>ATLAS ZERO — FILM10</h1>

<div class="summary">
Human-curated video segment contact sheet<br>
Segments: {len(results)}<br>
Frame failures: {len(failures)}
</div>

<div class="grid">
{''.join(cards)}
</div>

</body>
</html>
"""

HTML.write_text(
    document,
    encoding="utf-8"
)

REPORT.write_text(
    json.dumps(
        {
            "schema":
                "atlas_zero.film10.segment_contact_sheet.v1",

            "project_id":
                PROJECT_ID,

            "segments":
                len(results),

            "frames_ok":
                len(results) - len(failures),

            "frames_failed":
                len(failures),

            "html":
                str(HTML),

            "segments_review":
                results,

            "db_writes":
                False,

            "assignment":
                False,

            "render":
                False,

            "clip":
                False,

            "paid_calls":
                False,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8"
)

print()
print("=" * 120)
print("CONTACT SHEET SUMMARY")
print("=" * 120)

print("SEGMENTS      :", len(results))
print("FRAMES OK     :", len(results) - len(failures))
print("FRAMES FAILED :", len(failures))
print("HTML          :", HTML)
print("REPORT        :", REPORT)

if failures:

    print()
    print("FAILED SEGMENTS:")

    for row in failures:
        print(
            row["review_number"],
            row["segment_id"],
            row["filename"]
        )

print()
print("=" * 120)
print("CONTACT SHEET V1: COMPLETE")
print("=" * 120)

print("Opening contact sheet...")

subprocess.Popen(
    ["cmd", "/c", "start", "", str(HTML)],
    shell=False,
)

print("No DB writes.")
print("No semantic analysis.")
print("No assignment.")
print("No render.")
print("No paid API calls.")
