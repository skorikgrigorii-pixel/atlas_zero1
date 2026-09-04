from pathlib import Path
import json
import subprocess
import shutil

ROOT = Path.cwd()

PLAN = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_REMOUNT_V3.json"
AUDIO = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_AUDIO_V3.m4a"

REAL = ROOT / "workspace/projects/gardner/02_Visuals/real"

OUT = ROOT / "workspace/exports/gardner/rc2/ru_remount"
TMP = OUT / "_segments_v4"

VISUAL_OUT = OUT / "gardner_RU_VISUAL_V4.mp4"
FINAL = OUT / "gardner_RU_REMOUNT_V4.mp4"
V4_PLAN = OUT / "gardner_RU_REMOUNT_V4.json"

if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)

data = json.loads(PLAN.read_text(encoding="utf-8-sig"))
timeline = data["timeline"]
TARGET = float(data["target_duration_sec"])

# ------------------------------------------------------------
# V4 EDITORIAL REPLACEMENTS
#
# These timestamps point to visually repetitive portions
# observed in V3. The script resolves the actual shot ID.
# ------------------------------------------------------------

requests = [
    # repeated artwork around 04:30
    (270.0, REAL / "museum" / "G074_fenway_interior_19.jpg"),

    # repeated historic exterior around 06:30
    (390.0, REAL / "museum" / "G083_fenway_interior_10.jpg"),

    # repeated museum facade around 09:00
    (540.0, REAL / "museum" / "G075_fenway_interior_23.jpg"),

    # repeated evidence/poster feel around 09:30
    (570.0, REAL / "museum" / "G084_fenway_interior_11.jpg"),

    # repeated night reconstruction around 11:00
    (660.0, REAL / "museum" / "G085_fenway_interior_13.jpg"),

    # another evidence-heavy repeat around 11:30
    (690.0, REAL / "museum" / "G087_fenway_interior_15.jpg"),

    # repeated exterior around 14:00
    (840.0, REAL / "museum" / "G093_fenway_interior_24.jpg"),

    # repeated night-street/reconstruction around 19:00
    (1140.0, REAL / "museum" / "G082_fenway_interior_08.jpg"),
]

for _, p in requests:
    if not p.exists():
        raise FileNotFoundError(p)

# ------------------------------------------------------------
# FIND SHOTS AT REQUESTED V4 TIMESTAMPS
# ------------------------------------------------------------

replacement_by_shot = {}

for timestamp, image in requests:

    hit = None

    for row in timeline:
        a = float(row["new_start"])
        b = float(row["new_end"])

        if a <= timestamp < b:
            hit = row
            break

    if hit is None:
        raise RuntimeError(
            f"No V3 shot at {timestamp:.3f}s"
        )

    shot_id = str(hit["shot_id"])

    # Never replace one of our four newly animated assets.
    if str(hit.get("source_type")) == "ANIMATION":
        print(
            f"SKIP {timestamp:.1f}s -> {shot_id}: "
            f"already animation"
        )
        continue

    replacement_by_shot[shot_id] = image

    print(
        f"REPLACE {timestamp:7.1f}s | "
        f"{shot_id:20} | "
        f"{image.name}"
    )

print()
print(f"V4 replacements: {len(replacement_by_shot)}")

# ------------------------------------------------------------
# RENDER
# ------------------------------------------------------------

concat_lines = []

for idx, row in enumerate(timeline, 1):

    out = TMP / f"{idx:04d}.mp4"

    shot_id = str(row["shot_id"])
    duration = float(row["duration"])

    replacement = replacement_by_shot.get(shot_id)

    if replacement:

        # Slow documentary Ken Burns motion.
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

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-loop", "1",
            "-i", str(replacement),
            "-t", f"{duration:.6f}",
            "-an",
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            str(out)
        ]

    elif str(row.get("source_type")) == "ANIMATION":

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-stream_loop", "-1",
            "-i", str(row["source"]),
            "-t", f"{duration:.6f}",
            "-an",
            "-vf",
            (
                "scale=1920:1080:"
                "force_original_aspect_ratio=increase,"
                "crop=1920:1080,"
                "fps=30,"
                "format=yuv420p"
            ),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            str(out)
        ]

    else:

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-ss", f"{float(row['source_start']):.6f}",
            "-i", str(row["source"]),
            "-t", f"{duration:.6f}",
            "-an",
            "-vf", "fps=30,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            str(out)
        ]

    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    concat_lines.append(
        "file '" +
        str(out.resolve()).replace("\\", "/") +
        "'"
    )

    if idx % 25 == 0:
        print(f"Rendered {idx}/{len(timeline)}")

concat = TMP / "concat.txt"
concat.write_text(
    "\n".join(concat_lines),
    encoding="utf-8"
)

print()
print("Building Gardner RU V4 visual master...")

subprocess.run([
    "ffmpeg", "-y", "-nostdin",
    "-f", "concat",
    "-safe", "0",
    "-i", str(concat),
    "-an",
    "-c:v", "copy",
    "-movflags", "+faststart",
    str(VISUAL_OUT)
], check=True)

# ------------------------------------------------------------
# ENSURE VIDEO COVERS LOCKED AUDIO
# ------------------------------------------------------------

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

visual_duration = probe(VISUAL_OUT)

pad = max(0.0, TARGET - visual_duration + 0.05)

print()
print(f"Visual runtime : {visual_duration:.3f}")
print(f"Target         : {TARGET:.3f}")
print(f"Tail pad       : {pad:.3f}")

# ------------------------------------------------------------
# FINAL V4 + LOCKED V3 AUDIO
# ------------------------------------------------------------

subprocess.run([
    "ffmpeg", "-y", "-nostdin",
    "-i", str(VISUAL_OUT),
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
# SAVE V4 PLAN
# ------------------------------------------------------------

data["version"] = "RU_EDITORIAL_REMOUNT_V4"
data["v4_locked_audio"] = str(AUDIO)

data["v4_replacements"] = {
    shot: str(path)
    for shot, path in replacement_by_shot.items()
}

V4_PLAN.write_text(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print()
print("=" * 80)
print("GARDNER RU V4 READY")
print("=" * 80)
print("FILM :", FINAL)
print("PLAN :", V4_PLAN)
print(f"REPLACEMENTS : {len(replacement_by_shot)}")
print()

subprocess.run([
    "ffprobe",
    "-v", "error",
    "-show_entries",
    "stream=index,codec_type,duration,width,height,"
    "sample_rate,channels:format=duration",
    "-of", "default=noprint_wrappers=1",
    str(FINAL)
])

print("=" * 80)

