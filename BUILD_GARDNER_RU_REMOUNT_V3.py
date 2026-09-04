from pathlib import Path
import json
import subprocess
import shutil
from collections import Counter, defaultdict

ROOT = Path.cwd()

TIMELINE = ROOT / "workspace/exports/gardner/rc2/timeline/timeline.json"
VISUAL_MASTER = ROOT / "workspace/exports/gardner/rc2/render/visual_master_rc2.mp4"

VOICE_DIR = ROOT / "workspace/projects/gardner/01_Audio/ru/scenes"
MUSIC = ROOT / "workspace/projects/gardner/01_Audio/ru/music/The_Empty_Frame.mp3"
ANIM_DIR = ROOT / "workspace/projects/gardner/02_Visuals/generated/ru_remount"

OUT_DIR = ROOT / "workspace/exports/gardner/rc2/ru_remount"
SEG_DIR = OUT_DIR / "_segments_v3"

OUT_DIR.mkdir(parents=True, exist_ok=True)

if SEG_DIR.exists():
    shutil.rmtree(SEG_DIR)

SEG_DIR.mkdir(parents=True)

VISUAL_OUT = OUT_DIR / "gardner_RU_VISUAL_V3.mp4"
AUDIO_OUT  = OUT_DIR / "gardner_RU_AUDIO_V3.m4a"
FINAL      = OUT_DIR / "gardner_RU_REMOUNT_V3.mp4"
PLAN       = OUT_DIR / "gardner_RU_REMOUNT_V3.json"

# ------------------------------------------------------------
# PROBE
# ------------------------------------------------------------

def duration(path):
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

for p in [TIMELINE, VISUAL_MASTER, MUSIC, *voices]:
    if not p.exists():
        raise FileNotFoundError(p)

VOICE_DUR = [duration(p) for p in voices]
MUSIC_TOTAL = duration(MUSIC)

TARGET = sum(VOICE_DUR) + MUSIC_TOTAL

# Artistic distribution of the SAME 60.029 sec.
# No music after VO10.
MUSIC_DUR = [
    6.000,  # before VO01
    6.000,  # before VO02
    8.000,  # before VO03
    8.000,  # before VO04
    8.000,  # before VO05
    5.526,  # before VO06
    6.000,  # before VO07
    7.819,  # before VO08
    4.684,  # before VO09
    0.000,  # VO10 starts directly
]

# Correct tiny difference from actual MP3 duration.
MUSIC_DUR[7] += MUSIC_TOTAL - sum(MUSIC_DUR)

print()
print("=" * 82)
print("GARDNER RU — REAL REMOUNT V3")
print("=" * 82)
print(f"RU VOICE : {sum(VOICE_DUR):.3f}")
print(f"MUSIC    : {sum(MUSIC_DUR):.3f}")
print(f"TARGET   : {TARGET:.3f}")
print("=" * 82)

# ------------------------------------------------------------
# TIMELINE
# ------------------------------------------------------------

timeline = json.loads(
    TIMELINE.read_text(encoding="utf-8-sig")
)

def sid(row):
    raw = str(row.get("scene_id", ""))
    digits = "".join(c for c in raw if c.isdigit())
    return f"SC{int(digits):02d}"

scenes = defaultdict(list)

for row in timeline:
    scenes[sid(row)].append(row)

def asset_key(row):
    return str(
        row.get("asset_path")
        or row.get("asset_name")
        or row.get("asset_id")
        or ""
    )

asset_counts = Counter(
    asset_key(x)
    for x in timeline
    if asset_key(x)
)

# ------------------------------------------------------------
# NEW ANIMATIONS
# ------------------------------------------------------------

ANIM = {
    i: ANIM_DIR / f"GARDNER_RU_ANIM_{i:02d}.mp4"
    for i in range(1, 5)
}

for p in ANIM.values():
    if not p.exists():
        raise FileNotFoundError(p)

# Three animated-photo replacements.
# Fourth animation is reserved for the missing SC10 runtime.
REPLACEMENTS = {
    "SC01_SHOT_018": ANIM[1],
    "SC02_SHOT_007": ANIM[2],
    "SC04_SHOT_007": ANIM[3],
}

PROTECTED = set(REPLACEMENTS.keys())

# ------------------------------------------------------------
# EDIT SCORE
# Higher score = better candidate for removal.
# ------------------------------------------------------------

def removal_score(row):

    shot_id = str(row.get("shot_id"))
    asset = asset_key(row)
    name = str(row.get("asset_name") or "").lower()
    source = str(row.get("source_mode") or "").lower()

    repeats = asset_counts.get(asset, 1)

    generated = (
        "seedream" in name
        or "hailuo" in name
        or "generated" in source
        or "\\generated\\" in asset.lower()
        or "/generated/" in asset.lower()
    )

    score = 0.0

    # Repetition is our strongest signal.
    if repeats >= 6:
        score += 8
    elif repeats >= 5:
        score += 7
    elif repeats >= 4:
        score += 5
    elif repeats >= 3:
        score += 3
    elif repeats == 2:
        score += 1

    # Prefer removing weaker synthetic reconstructions
    # before unique factual material.
    if generated:
        score += 4

    # Never remove our new replacement locations.
    if shot_id in PROTECTED:
        score -= 100

    return score

# ------------------------------------------------------------
# BUILD REAL EDIT PLAN
# ------------------------------------------------------------

edit_rows = []
decisions = []
cursor = 0.0

for scene_index in range(10):

    scene_id = f"SC{scene_index+1:02d}"
    rows = scenes[scene_id]

    original = sum(
        float(x.get("duration_sec") or 0)
        for x in rows
    )

    target = VOICE_DUR[scene_index] + MUSIC_DUR[scene_index]

    print()
    print("-" * 82)
    print(
        f"{scene_id}: ORIGINAL={original:.3f} "
        f"TARGET={target:.3f} "
        f"CHANGE={target-original:+.3f}"
    )

    # --------------------------------------------------------
    # SC10: keep all original material and ADD real new video.
    # --------------------------------------------------------

    if target > original + 0.01:

        for row in rows:

            d = float(row.get("duration_sec") or 0)

            edit_rows.append({
                "scene_id": scene_id,
                "shot_id": row.get("shot_id"),
                "source_type": "MASTER",
                "source": str(VISUAL_MASTER),
                "source_start": float(row.get("start_sec") or 0),
                "duration": d,
                "new_start": cursor,
                "new_end": cursor + d,
            })

            decisions.append({
                "scene": scene_id,
                "shot": row.get("shot_id"),
                "decision": "KEEP",
                "duration": d,
            })

            cursor += d

        extra = target - original

        edit_rows.append({
            "scene_id": scene_id,
            "shot_id": "SC10_RU_ANIM_EXTENSION",
            "source_type": "ANIMATION",
            "source": str(ANIM[4]),
            "source_start": 0.0,
            "duration": extra,
            "new_start": cursor,
            "new_end": cursor + extra,
        })

        decisions.append({
            "scene": scene_id,
            "shot": "SC10_RU_ANIM_EXTENSION",
            "decision": "ADD_NEW_VIDEO",
            "duration": extra,
            "source": str(ANIM[4]),
        })

        cursor += extra

        print(f"  ADD ANIM_04 : {extra:.3f}s")
        continue

    # --------------------------------------------------------
    # Scenes that need shortening.
    # --------------------------------------------------------

    cut_needed = original - target

    # Keep first and last shot unless absolutely necessary.
    candidates = []

    for idx, row in enumerate(rows):

        shot_id = str(row.get("shot_id"))

        if shot_id in PROTECTED:
            continue

        if idx == 0 or idx == len(rows) - 1:
            continue

        candidates.append({
            "row": row,
            "score": removal_score(row),
            "duration": float(row.get("duration_sec") or 0),
        })

    candidates.sort(
        key=lambda x: (
            x["score"],
            x["duration"]
        ),
        reverse=True
    )

    dropped = set()
    removed = 0.0

    # Remove WHOLE weak shots while that remains sensible.
    for item in candidates:

        remaining = cut_needed - removed

        if remaining <= 2.75:
            break

        d = item["duration"]

        # Avoid a large overshoot.
        if d <= remaining + 2.0:
            shot_id = str(item["row"].get("shot_id"))
            dropped.add(shot_id)
            removed += d

            decisions.append({
                "scene": scene_id,
                "shot": shot_id,
                "decision": "DROP",
                "duration": d,
                "score": item["score"],
                "asset": item["row"].get("asset_name"),
            })

            print(
                f"  DROP {shot_id:16} "
                f"{d:6.3f}s score={item['score']:.1f}"
            )

    trim_remaining = cut_needed - removed

    # Find ONE weakest retained shot for the final precision trim.
    trim_shot = None

    if trim_remaining > 0.01:

        retained_candidates = [
            x for x in candidates
            if str(x["row"].get("shot_id")) not in dropped
            and x["duration"] - trim_remaining >= 2.0
        ]

        if not retained_candidates:
            raise RuntimeError(
                f"{scene_id}: cannot trim final "
                f"{trim_remaining:.3f}s safely"
            )

        trim_shot = retained_candidates[0]["row"]

        print(
            f"  TRIM {trim_shot.get('shot_id')} "
            f"by {trim_remaining:.3f}s"
        )

    # --------------------------------------------------------
    # Emit retained shots in ORIGINAL ORDER.
    # --------------------------------------------------------

    for row in rows:

        shot_id = str(row.get("shot_id"))

        if shot_id in dropped:
            continue

        original_duration = float(
            row.get("duration_sec") or 0
        )

        d = original_duration

        if trim_shot is row:
            d -= trim_remaining

            decisions.append({
                "scene": scene_id,
                "shot": shot_id,
                "decision": "TRIM",
                "old_duration": original_duration,
                "new_duration": d,
                "trimmed": trim_remaining,
            })

        replacement = REPLACEMENTS.get(shot_id)

        if replacement:

            source_type = "ANIMATION"
            source = replacement
            source_start = 0.0

            decisions.append({
                "scene": scene_id,
                "shot": shot_id,
                "decision": "REPLACE_WITH_ANIMATION",
                "duration": d,
                "source": str(replacement),
            })

        else:

            source_type = "MASTER"
            source = VISUAL_MASTER
            source_start = float(
                row.get("start_sec") or 0
            )

            if not any(
                d0.get("scene") == scene_id
                and d0.get("shot") == shot_id
                for d0 in decisions
            ):
                decisions.append({
                    "scene": scene_id,
                    "shot": shot_id,
                    "decision": "KEEP",
                    "duration": d,
                })

        edit_rows.append({
            "scene_id": scene_id,
            "shot_id": shot_id,
            "source_type": source_type,
            "source": str(source),
            "source_start": source_start,
            "duration": d,
            "new_start": cursor,
            "new_end": cursor + d,
        })

        cursor += d

# ------------------------------------------------------------
# RUNTIME CHECK
# ------------------------------------------------------------

print()
print("=" * 82)
print(f"NEW VISUAL RUNTIME : {cursor:.3f}")
print(f"TARGET             : {TARGET:.3f}")
print("=" * 82)

if abs(cursor - TARGET) > 0.05:
    raise RuntimeError(
        f"Runtime mismatch: {cursor:.3f} != {TARGET:.3f}"
    )

# ------------------------------------------------------------
# RENDER SHOTS
# ------------------------------------------------------------

concat_path = SEG_DIR / "concat.txt"
concat_lines = []

print()
print(f"Rendering {len(edit_rows)} retained/new shots...")

for idx, item in enumerate(edit_rows, 1):

    out = SEG_DIR / f"{idx:04d}.mp4"

    if item["source_type"] == "MASTER":

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-ss", f"{item['source_start']:.6f}",
            "-i", item["source"],
            "-t", f"{item['duration']:.6f}",
            "-an",
            "-vf", "fps=30,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            str(out)
        ]

    else:

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-stream_loop", "-1",
            "-i", item["source"],
            "-t", f"{item['duration']:.6f}",
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
        print(f"  {idx}/{len(edit_rows)}")

concat_path.write_text(
    "\n".join(concat_lines),
    encoding="utf-8"
)

print("Building V3 visual master...")

subprocess.run([
    "ffmpeg", "-y", "-nostdin",
    "-f", "concat",
    "-safe", "0",
    "-i", str(concat_path),
    "-an",
    "-c:v", "copy",
    "-movflags", "+faststart",
    str(VISUAL_OUT)
], check=True)

# ------------------------------------------------------------
# BUILD AUDIO = MUSIC + RU VO
# ------------------------------------------------------------

print("Building V3 Russian soundtrack...")

cmd = [
    "ffmpeg", "-y", "-nostdin",
    "-stream_loop", "-1",
    "-i", str(MUSIC)
]

for voice in voices:
    cmd += ["-i", str(voice)]

filters = []
music_cursor = 0.0

for i, d in enumerate(MUSIC_DUR):

    if d <= 0.001:
        continue

    fade = min(0.5, d / 3)

    filters.append(
        f"[0:a]"
        f"atrim=start={music_cursor:.6f}:duration={d:.6f},"
        f"asetpts=PTS-STARTPTS,"
        f"aresample=48000,"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"afade=t=in:st=0:d={fade:.3f},"
        f"afade=t=out:st={max(0,d-fade):.6f}:d={fade:.3f}"
        f"[m{i}]"
    )

    music_cursor += d

for i in range(10):

    filters.append(
        f"[{i+1}:a]"
        f"aresample=48000,"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo"
        f"[v{i}]"
    )

order = []

for i in range(10):

    if MUSIC_DUR[i] > 0.001:
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
# FINAL MUX
# ------------------------------------------------------------

print("Muxing Gardner RU V3...")

subprocess.run([
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
], check=True)

# ------------------------------------------------------------
# SAVE EDIT DECISIONS
# ------------------------------------------------------------

PLAN.write_text(
    json.dumps(
        {
            "project": "gardner",
            "version": "RU_REAL_REMOUNT_V3",
            "rule": "Russian narrator + 60 sec music = total film runtime",
            "voice_duration_sec": sum(VOICE_DUR),
            "music_duration_sec": sum(MUSIC_DUR),
            "target_duration_sec": TARGET,
            "music_distribution": MUSIC_DUR,
            "original_shots": len(timeline),
            "final_shots": len(edit_rows),
            "replacements": {
                k: str(v)
                for k, v in REPLACEMENTS.items()
            },
            "sc10_extension": str(ANIM[4]),
            "decisions": decisions,
            "timeline": edit_rows,
        },
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print()
print("=" * 82)
print("GARDNER RU REAL REMOUNT V3 READY")
print("=" * 82)
print("VISUAL :", VISUAL_OUT)
print("AUDIO  :", AUDIO_OUT)
print("FILM   :", FINAL)
print("PLAN   :", PLAN)
print(f"SHOTS  : {len(timeline)} -> {len(edit_rows)}")

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

print("=" * 82)

