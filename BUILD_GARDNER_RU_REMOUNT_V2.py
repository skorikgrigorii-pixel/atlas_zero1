from pathlib import Path
import json
import subprocess
import shutil

ROOT = Path.cwd()

TIMELINE = ROOT / "workspace/exports/gardner/rc2/timeline/timeline.json"
VISUAL_MASTER = ROOT / "workspace/exports/gardner/rc2/render/visual_master_rc2.mp4"
VOICE_DIR = ROOT / "workspace/projects/gardner/01_Audio/ru/scenes"
MUSIC = ROOT / "workspace/projects/gardner/01_Audio/ru/music/The_Empty_Frame.mp3"
ANIM_DIR = ROOT / "workspace/projects/gardner/02_Visuals/generated/ru_remount"

OUT_DIR = ROOT / "workspace/exports/gardner/rc2/ru_remount"
SEG_DIR = OUT_DIR / "_segments"

OUT_DIR.mkdir(parents=True, exist_ok=True)

if SEG_DIR.exists():
    shutil.rmtree(SEG_DIR)

SEG_DIR.mkdir(parents=True)

FINAL = OUT_DIR / "gardner_RU_REMOUNT_V2.mp4"
VISUAL_OUT = OUT_DIR / "gardner_RU_VISUAL_V2.mp4"
AUDIO_OUT = OUT_DIR / "gardner_RU_AUDIO_V2.m4a"
PLAN = OUT_DIR / "gardner_RU_REMOUNT_V2.json"

# ------------------------------------------------------------
# REAL AUDIO DURATIONS
# ------------------------------------------------------------

def probe_duration(path):
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

voices = [
    VOICE_DIR / f"VOICE_{i:03d}_RU.mp3"
    for i in range(1, 11)
]

for p in voices:
    if not p.exists():
        raise FileNotFoundError(p)

if not MUSIC.exists():
    raise FileNotFoundError(MUSIC)

VOICE_DUR = [probe_duration(p) for p in voices]
MUSIC_TOTAL = probe_duration(MUSIC)

TARGET = sum(VOICE_DUR) + MUSIC_TOTAL

print()
print("=" * 76)
print("GARDNER RU REMOUNT V2")
print("=" * 76)
print(f"RU VOICE TOTAL : {sum(VOICE_DUR):.3f} sec")
print(f"MUSIC TOTAL    : {MUSIC_TOTAL:.3f} sec")
print(f"FILM TARGET    : {TARGET:.3f} sec")
print("=" * 76)

# ------------------------------------------------------------
# LOAD CANONICAL TIMELINE
# ------------------------------------------------------------

timeline = json.loads(
    TIMELINE.read_text(encoding="utf-8-sig")
)

scenes = {}

for row in timeline:
    raw = str(row.get("scene_id", ""))
    digits = "".join(c for c in raw if c.isdigit())

    if not digits:
        continue

    sid = f"SC{int(digits):02d}"
    scenes.setdefault(sid, []).append(row)

ORIGINAL_DUR = []

for i in range(1, 11):
    sid = f"SC{i:02d}"

    d = sum(
        float(x.get("duration_sec") or 0)
        for x in scenes[sid]
    )

    ORIGINAL_DUR.append(d)

# ------------------------------------------------------------
# MUSIC DISTRIBUTION
# ------------------------------------------------------------

# Start with ~6 seconds at every chapter boundary.
# Music is one TOTAL budget, not ten mandatory pauses.

base_transition = MUSIC_TOTAL / 10.0
music_dur = [base_transition] * 10

# A scene may not become longer than its available canonical
# visual material. If necessary, reduce its music allocation.

saved = 0.0

for i in range(10):

    maximum_music = max(
        0.0,
        ORIGINAL_DUR[i] - VOICE_DUR[i]
    )

    if music_dur[i] > maximum_music:
        reduction = music_dur[i] - maximum_music
        music_dur[i] = maximum_music
        saved += reduction

# Redistribute saved music ONLY to scenes that have visual room.

while saved > 0.0005:

    candidates = []

    for i in range(10):
        room = (
            ORIGINAL_DUR[i]
            - VOICE_DUR[i]
            - music_dur[i]
        )

        if room > 0.001:
            candidates.append((room, i))

    if not candidates:
        break

    candidates.sort(reverse=True)

    room, i = candidates[0]
    add = min(room, saved)

    music_dur[i] += add
    saved -= add

if saved > 0.01:
    raise RuntimeError(
        f"Unable to place {saved:.3f}s of music "
        f"inside existing visual runtime."
    )

print()
print("===== FINAL MUSIC DISTRIBUTION =====")

for i in range(10):
    print(
        f"SC{i+1:02d}: "
        f"VOICE={VOICE_DUR[i]:8.3f}  "
        f"MUSIC={music_dur[i]:7.3f}  "
        f"WINDOW={VOICE_DUR[i]+music_dur[i]:8.3f}  "
        f"AVAILABLE={ORIGINAL_DUR[i]:8.3f}"
    )

print()
print(f"MUSIC CHECK: {sum(music_dur):.3f}")

# ------------------------------------------------------------
# NEW ANIMATIONS
# ------------------------------------------------------------

anims = [
    ANIM_DIR / f"GARDNER_RU_ANIM_{i:02d}.mp4"
    for i in range(1, 5)
]

for p in anims:
    if not p.exists():
        raise FileNotFoundError(p)

# Four new generated animations replace four old static shots.
REPLACEMENTS = {
    "SC01_SHOT_018": anims[0],
    "SC02_SHOT_007": anims[1],
    "SC04_SHOT_007": anims[2],
    "SC05_SHOT_009": anims[3],
}

# ------------------------------------------------------------
# BUILD NEW VISUAL TIMELINE
# ------------------------------------------------------------

selected = []
cursor = 0.0

for scene_index in range(10):

    sid = f"SC{scene_index+1:02d}"
    shots = scenes[sid]

    target = VOICE_DUR[scene_index] + music_dur[scene_index]
    original = ORIGINAL_DUR[scene_index]

    print()
    print(
        f"{sid}: original={original:.3f} "
        f"target={target:.3f} "
        f"trim={original-target:.3f}"
    )

    ratio = target / original

    rows = []

    for row in shots:

        original_shot_duration = float(
            row.get("duration_sec") or 0
        )

        duration = original_shot_duration * ratio

        rows.append({
            "source": row,
            "duration": duration
        })

    # Correct floating point rounding on final shot.
    actual = sum(x["duration"] for x in rows)
    correction = target - actual

    if rows:
        rows[-1]["duration"] += correction

    for item in rows:

        row = item["source"]
        duration = item["duration"]
        shot_id = str(row.get("shot_id"))

        selected.append({
            "scene_id": sid,
            "shot_id": shot_id,
            "old_start": float(row.get("start_sec") or 0),
            "old_end": float(row.get("end_sec") or 0),
            "old_duration": float(row.get("duration_sec") or 0),
            "new_start": cursor,
            "new_end": cursor + duration,
            "duration": duration,
            "replacement": (
                str(REPLACEMENTS[shot_id])
                if shot_id in REPLACEMENTS
                else None
            )
        })

        cursor += duration

print()
print("=" * 76)
print(f"NEW VISUAL RUNTIME: {cursor:.3f}")
print(f"TARGET             : {TARGET:.3f}")
print("=" * 76)

if abs(cursor - TARGET) > 0.05:
    raise RuntimeError(
        f"Timeline mismatch {cursor:.3f} / {TARGET:.3f}"
    )

# ------------------------------------------------------------
# RENDER VISUAL SEGMENTS
# ------------------------------------------------------------

concat_file = SEG_DIR / "concat.txt"
concat_lines = []

print()
print("Rendering visual remount...")

for idx, item in enumerate(selected, 1):

    segment = SEG_DIR / f"{idx:04d}.mp4"
    duration = item["duration"]

    if item["replacement"]:

        source = item["replacement"]

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-stream_loop", "-1",
            "-i", source,
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
            str(segment)
        ]

    else:

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-ss", f"{item['old_start']:.6f}",
            "-i", str(VISUAL_MASTER),
            "-t", f"{duration:.6f}",
            "-an",
            "-vf", "fps=30,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            str(segment)
        ]

    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    concat_lines.append(
        "file '" +
        str(segment.resolve()).replace("\\", "/") +
        "'"
    )

    if idx % 25 == 0:
        print(f"  {idx}/{len(selected)} shots")

concat_file.write_text(
    "\n".join(concat_lines),
    encoding="utf-8"
)

print("Building visual master...")

subprocess.run(
    [
        "ffmpeg", "-y", "-nostdin",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-an",
        "-c:v", "copy",
        "-movflags", "+faststart",
        str(VISUAL_OUT)
    ],
    check=True
)

# ------------------------------------------------------------
# BUILD AUDIO
# ------------------------------------------------------------

print("Building Russian soundtrack...")

cmd = [
    "ffmpeg", "-y", "-nostdin",
    "-stream_loop", "-1",
    "-i", str(MUSIC)
]

for voice in voices:
    cmd += ["-i", str(voice)]

filters = []

music_cursor = 0.0

for i, duration in enumerate(music_dur):

    start = music_cursor
    music_cursor += duration

    fade = min(0.5, duration / 3)

    chain = (
        f"[0:a]"
        f"atrim=start={start:.6f}:duration={duration:.6f},"
        f"asetpts=PTS-STARTPTS,"
        f"aresample=48000,"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo"
    )

    if duration > 0.2:
        chain += (
            f",afade=t=in:st=0:d={fade:.3f},"
            f"afade=t=out:"
            f"st={max(0,duration-fade):.6f}:"
            f"d={fade:.3f}"
        )

    chain += f"[m{i}]"
    filters.append(chain)

for i in range(10):

    filters.append(
        f"[{i+1}:a]"
        f"aresample=48000,"
        f"aformat=sample_fmts=fltp:"
        f"channel_layouts=stereo"
        f"[v{i}]"
    )

order = []

for i in range(10):
    order.append(f"[m{i}]")
    order.append(f"[v{i}]")

filters.append(
    "".join(order) +
    f"concat=n={len(order)}:v=0:a=1[audio]"
)

cmd += [
    "-filter_complex", ";".join(filters),
    "-map", "[audio]",
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-ac", "2",
    "-t", f"{TARGET:.6f}",
    str(AUDIO_OUT)
]

subprocess.run(cmd, check=True)

# ------------------------------------------------------------
# FINAL FILM
# ------------------------------------------------------------

print("Muxing final Gardner RU...")

subprocess.run(
    [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(VISUAL_OUT),
        "-i", str(AUDIO_OUT),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "copy",
        "-t", f"{TARGET:.6f}",
        "-movflags", "+faststart",
        str(FINAL)
    ],
    check=True
)

# ------------------------------------------------------------
# SAVE PLAN
# ------------------------------------------------------------

PLAN.write_text(
    json.dumps(
        {
            "project": "gardner",
            "version": "RU_REMOUNT_V2",
            "rule": "RU narrator + 1 music track = total film runtime",
            "voice_duration_sec": sum(VOICE_DUR),
            "music_duration_sec": MUSIC_TOTAL,
            "target_duration_sec": TARGET,
            "music_distribution": music_dur,
            "replacement_shots": {
                k: str(v)
                for k, v in REPLACEMENTS.items()
            },
            "timeline": selected
        },
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print()
print("=" * 76)
print("GARDNER RU REMOUNT V2 READY")
print("=" * 76)
print("VISUAL :", VISUAL_OUT)
print("AUDIO  :", AUDIO_OUT)
print("FILM   :", FINAL)
print("PLAN   :", PLAN)

print()
print("===== FINAL PROBE =====")

subprocess.run([
    "ffprobe",
    "-v", "error",
    "-show_entries",
    "stream=index,codec_type,codec_name,width,height,"
    "sample_rate,channels:format=duration",
    "-of", "default=noprint_wrappers=1",
    str(FINAL)
])

print("=" * 76)
