from pathlib import Path
import json
import subprocess

ROOT = Path.cwd()

PLAN = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_REMOUNT_V4.json"
SEGDIR = ROOT / "workspace/exports/gardner/rc2/ru_remount/_segments_v4"
CONCAT = SEGDIR / "concat.txt"

IMAGE = (
    ROOT /
    "workspace/projects/gardner/02_Visuals/real/museum/"
    "G018_stolen_rembrandt_frames.jpg"
)

AUDIO = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_AUDIO_V3.m4a"

VISUAL = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_VISUAL_V4_1.mp4"
FINAL  = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_REMOUNT_V4_1.mp4"

TARGET = 1291.848
SHOT = "SC09_SHOT_014"

data = json.loads(
    PLAN.read_text(encoding="utf-8-sig")
)

timeline = data["timeline"]

index = None
row = None

for i, x in enumerate(timeline, 1):
    if str(x.get("shot_id")) == SHOT:
        index = i
        row = x
        break

if row is None:
    raise RuntimeError(f"{SHOT} not found")

duration = float(row["duration"])

segment = SEGDIR / f"{index:04d}.mp4"

print()
print("=" * 72)
print("GARDNER RU V4.1 — SC09_SHOT_014 PATCH")
print("=" * 72)
print("INDEX    :", index)
print("SHOT     :", SHOT)
print("DURATION :", duration)
print("OLD      :", row.get("source"))
print("NEW      :", IMAGE)
print("SEGMENT  :", segment)

if not IMAGE.exists():
    raise FileNotFoundError(IMAGE)

# ------------------------------------------------------------
# Replace ONLY this one segment.
# ------------------------------------------------------------

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
    str(segment)
], check=True)

print()
print("Patched one V4 segment.")

# ------------------------------------------------------------
# Rebuild visual master from existing 221 segments.
# No re-render of all shots.
# ------------------------------------------------------------

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

visual_duration = probe(VISUAL)
pad = max(0.0, TARGET - visual_duration + 0.05)

print()
print(f"VISUAL : {visual_duration:.3f}")
print(f"TARGET : {TARGET:.3f}")
print(f"PAD    : {pad:.3f}")

# ------------------------------------------------------------
# Locked Russian audio remains untouched.
# ------------------------------------------------------------

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

print()
print("=" * 72)
print("GARDNER RU V4.1 READY")
print("=" * 72)
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

print("=" * 72)

