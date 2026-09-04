from pathlib import Path
import subprocess
import json

ROOT = Path.cwd()

SEGDIR = ROOT / "workspace/exports/gardner/rc2/ru_remount/_segments_v4"
PLAN = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_REMOUNT_V4.json"

IMAGE = (
    ROOT /
    "workspace/projects/gardner/02_Visuals/real/museum/"
    "G018_stolen_rembrandt_frames.jpg"
)

AUDIO = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_AUDIO_V3.m4a"

VISUAL = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_VISUAL_V4_2.mp4"
FINAL  = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_REMOUNT_V4_2.mp4"

CONCAT = SEGDIR / "concat.txt"

TARGET = 1291.848
BLACK_TIME = 1174.45

def probe(path):
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return float(r.stdout.strip())

data = json.loads(
    PLAN.read_text(encoding="utf-8-sig")
)

timeline = data["timeline"]

segments = sorted(
    SEGDIR.glob("*.mp4"),
    key=lambda p: int(p.stem)
)

if len(segments) != len(timeline):
    raise RuntimeError(
        f"Segment/timeline mismatch: "
        f"{len(segments)} vs {len(timeline)}"
    )

print()
print("=" * 78)
print("GARDNER RU V4.2 — ACTUAL BLACK SEGMENT RESOLUTION")
print("=" * 78)

cursor = 0.0
owner = None

for idx, seg in enumerate(segments):
    d = probe(seg)
    start = cursor
    end = start + d

    if start <= BLACK_TIME < end:
        owner = {
            "index": idx,
            "segment": seg,
            "start": start,
            "end": end,
            "duration": d,
            "row": timeline[idx],
        }
        break

    cursor = end

if owner is None:
    raise RuntimeError(
        f"No actual segment found at {BLACK_TIME}s"
    )

row = owner["row"]

print("BLACK TIME   :", BLACK_TIME)
print("SEGMENT      :", owner["segment"])
print("ACTUAL START :", f"{owner['start']:.6f}")
print("ACTUAL END   :", f"{owner['end']:.6f}")
print("DURATION     :", f"{owner['duration']:.6f}")
print("SCENE        :", row.get("scene_id"))
print("SHOT         :", row.get("shot_id"))
print("SOURCE TYPE  :", row.get("source_type"))
print("SOURCE       :", row.get("source"))
print("SOURCE START :", row.get("source_start"))
print()

if not IMAGE.exists():
    raise FileNotFoundError(IMAGE)

# ------------------------------------------------------------
# PATCH THE ACTUAL SEGMENT
# ------------------------------------------------------------

duration = owner["duration"]
frames = max(1, round(duration * 30))

vf = (
    "scale=2200:-2,"
    "zoompan="
    "z='min(zoom+0.00045,1.055)':"
    "x='iw/2-(iw/zoom/2)':"
    "y='ih/2-(ih/zoom/2)':"
    f"d={frames}:"
    "s=1920x1080:"
    "fps=30,"
    "format=yuv420p"
)

print("Replacing ACTUAL offending segment...")

subprocess.run([
    "ffmpeg", "-y", "-nostdin",
    "-loop", "1",
    "-i", str(IMAGE),
    "-t", f"{duration:.6f}",
    "-an",
    "-vf", vf,
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-crf", "20",
    str(owner["segment"])
], check=True)

# ------------------------------------------------------------
# REBUILD VISUAL
# ------------------------------------------------------------

print()
print("Rebuilding V4.2 visual master...")

subprocess.run([
    "ffmpeg", "-y", "-nostdin",
    "-f", "concat",
    "-safe", "0",
    "-i", str(CONCAT),
    "-an",
    "-c:v", "copy",
    "-movflags", "+faststart",
    str(VISUAL)
], check=True)

visual_duration = probe(VISUAL)
pad = max(0.0, TARGET - visual_duration + 0.05)

print()
print(f"VISUAL : {visual_duration:.6f}")
print(f"TARGET : {TARGET:.6f}")
print(f"PAD    : {pad:.6f}")

# ------------------------------------------------------------
# LOCKED AUDIO — NO CHANGES
# ------------------------------------------------------------

print()
print("Muxing V4.2 with locked RU audio...")

subprocess.run([
    "ffmpeg", "-y", "-nostdin",
    "-i", str(VISUAL),
    "-i", str(AUDIO),
    "-filter_complex",
    f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.6f}[v]",
    "-map", "[v]",
    "-map", "1:a:0",
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-crf", "20",
    "-c:a", "copy",
    "-t", f"{TARGET:.6f}",
    "-movflags", "+faststart",
    str(FINAL)
], check=True)

# ------------------------------------------------------------
# AUTOMATIC BLACK QC
# ------------------------------------------------------------

print()
print("=" * 78)
print("BLACKDETECT V4.2")
print("=" * 78)

qc = subprocess.run(
    [
        "ffmpeg", "-hide_banner",
        "-i", str(FINAL),
        "-vf", "blackdetect=d=0.50:pic_th=0.98:pix_th=0.10",
        "-an",
        "-f", "null", "-"
    ],
    capture_output=True,
    text=True
)

black_lines = [
    line.strip()
    for line in qc.stderr.splitlines()
    if "black_start:" in line
]

if black_lines:
    print("BLACK EVENTS FOUND:")
    for line in black_lines:
        print(line)
else:
    print("BLACK EVENTS: 0")

print()
print("=" * 78)
print("GARDNER RU V4.2 READY")
print("=" * 78)
print(FINAL)

subprocess.run([
    "ffprobe",
    "-v", "error",
    "-show_entries",
    "stream=index,codec_type,duration,width,height,"
    "sample_rate,channels:format=duration",
    "-of", "default=noprint_wrappers=1",
    str(FINAL)
])

print("=" * 78)

