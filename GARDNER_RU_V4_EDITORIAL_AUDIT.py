from pathlib import Path
import json
import subprocess
from collections import Counter, defaultdict

ROOT = Path.cwd()

PLAN = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_REMOUNT_V3.json"
VOICE_DIR = ROOT / "workspace/projects/gardner/01_Audio/ru/scenes"

OUT_DIR = ROOT / "workspace/exports/gardner/rc2/ru_remount/v4_editorial"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = OUT_DIR / "gardner_RU_V4_EDITORIAL_AUDIT.json"
OUT_MD   = OUT_DIR / "gardner_RU_V4_EDITORIAL_AUDIT.md"

if not PLAN.exists():
    raise FileNotFoundError(PLAN)

# ------------------------------------------------------------
# HELPERS
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

def fmt(sec):
    sec = max(0.0, float(sec))
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:06.3f}"

# ------------------------------------------------------------
# LOAD V3 EDIT PLAN
# ------------------------------------------------------------

data = json.loads(
    PLAN.read_text(encoding="utf-8-sig")
)

timeline = data.get("timeline", [])

if not timeline:
    raise RuntimeError("V3 timeline missing from plan")

music = data.get("music_distribution", [])

if len(music) != 10:
    raise RuntimeError(
        f"Expected 10 music blocks, got {len(music)}"
    )

# ------------------------------------------------------------
# REAL VOICE DURATIONS
# ------------------------------------------------------------

voices = []

for i in range(1, 11):
    p = VOICE_DIR / f"VOICE_{i:03d}_RU.mp3"

    if not p.exists():
        raise FileNotFoundError(p)

    voices.append({
        "index": i,
        "path": str(p),
        "duration": probe_duration(p)
    })

# ------------------------------------------------------------
# CALCULATE ACTUAL AUDIO WINDOWS
#
# V3 structure:
# music -> voice -> music -> voice ...
# ------------------------------------------------------------

audio_windows = []

cursor = 0.0

for i in range(10):

    music_start = cursor
    music_end = cursor + float(music[i])

    voice_start = music_end
    voice_end = voice_start + voices[i]["duration"]

    audio_windows.append({
        "scene": f"SC{i+1:02d}",
        "music_start": music_start,
        "music_end": music_end,
        "music_duration": float(music[i]),
        "voice_start": voice_start,
        "voice_end": voice_end,
        "voice_duration": voices[i]["duration"],
    })

    cursor = voice_end

# ------------------------------------------------------------
# ASSET / SOURCE NORMALIZATION
# ------------------------------------------------------------

def source_key(row):

    source_type = str(
        row.get("source_type") or ""
    )

    source = str(
        row.get("source") or ""
    )

    shot = str(
        row.get("shot_id") or ""
    )

    if source_type == "ANIMATION":
        return Path(source).name

    # MASTER shots no longer contain the original asset path
    # in V3 plan. Shot ID remains canonical identity.
    return shot

keys = [
    source_key(row)
    for row in timeline
]

usage = Counter(keys)

# ------------------------------------------------------------
# BUILD SCENE / VO MAP
# ------------------------------------------------------------

report = []

for window in audio_windows:

    scene_id = window["scene"]

    scene_rows = [
        x for x in timeline
        if str(x.get("scene_id")) == scene_id
    ]

    # Shots actually intersecting spoken narration.
    spoken_rows = []

    for row in timeline:

        a = float(row.get("new_start") or 0)
        b = float(row.get("new_end") or 0)

        overlap = max(
            0.0,
            min(b, window["voice_end"])
            - max(a, window["voice_start"])
        )

        if overlap > 0.01:

            spoken_rows.append({
                "shot_id": row.get("shot_id"),
                "source_type": row.get("source_type"),
                "source": row.get("source"),
                "start": a,
                "end": b,
                "duration": float(
                    row.get("duration") or (b-a)
                ),
                "voice_overlap": overlap,
                "usage_count": usage[
                    source_key(row)
                ],
                "key": source_key(row),
            })

    # Music-only visual material.
    music_rows = []

    if window["music_duration"] > 0:

        for row in timeline:

            a = float(row.get("new_start") or 0)
            b = float(row.get("new_end") or 0)

            overlap = max(
                0.0,
                min(b, window["music_end"])
                - max(a, window["music_start"])
            )

            if overlap > 0.01:

                music_rows.append({
                    "shot_id": row.get("shot_id"),
                    "start": a,
                    "end": b,
                    "overlap": overlap,
                    "source_type": row.get("source_type"),
                    "key": source_key(row),
                })

    animations = [
        x for x in spoken_rows
        if x["source_type"] == "ANIMATION"
    ]

    # Because MASTER references visual_master, detect
    # repetition additionally by repeated shot IDs / source keys.
    repeated = [
        x for x in spoken_rows
        if x["usage_count"] > 1
    ]

    report.append({
        **window,
        "scene_shots": len(scene_rows),
        "spoken_shots": spoken_rows,
        "music_shots": music_rows,
        "animations": animations,
        "repeated": repeated,
    })

# ------------------------------------------------------------
# GLOBAL REPETITION / ANIMATION MAP
# ------------------------------------------------------------

animations_global = [
    {
        "scene": x.get("scene_id"),
        "shot": x.get("shot_id"),
        "source": x.get("source"),
        "start": x.get("new_start"),
        "end": x.get("new_end"),
        "duration": x.get("duration"),
    }
    for x in timeline
    if x.get("source_type") == "ANIMATION"
]

# ------------------------------------------------------------
# SAVE JSON
# ------------------------------------------------------------

result = {
    "project": "gardner",
    "audit": "RU_V4_EDITORIAL",
    "source_plan": str(PLAN),
    "runtime": cursor,
    "voice_total": sum(
        x["duration"] for x in voices
    ),
    "music_total": sum(
        float(x) for x in music
    ),
    "audio_windows": audio_windows,
    "animations": animations_global,
    "scenes": report,
}

OUT_JSON.write_text(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

# ------------------------------------------------------------
# HUMAN-READABLE REPORT
# ------------------------------------------------------------

md = []

md.append("# ATLAS ZERO — GARDNER RU V4 EDITORIAL AUDIT")
md.append("")
md.append(
    f"Runtime: **{fmt(cursor)} / {cursor:.3f}s**"
)
md.append(
    f"Russian narration: **{sum(x['duration'] for x in voices):.3f}s**"
)
md.append(
    f"Music: **{sum(float(x) for x in music):.3f}s**"
)
md.append("")
md.append("---")
md.append("")

for scene in report:

    md.append(
        f"## {scene['scene']}"
    )
    md.append("")

    md.append(
        f"Music: `{fmt(scene['music_start'])} → "
        f"{fmt(scene['music_end'])}` "
        f"({scene['music_duration']:.3f}s)"
    )

    md.append(
        f"VOICE: `{fmt(scene['voice_start'])} → "
        f"{fmt(scene['voice_end'])}` "
        f"({scene['voice_duration']:.3f}s)"
    )

    md.append("")
    md.append(
        f"Shots under narration: **{len(scene['spoken_shots'])}**"
    )

    if scene["animations"]:
        md.append(
            f"New animations under narration: "
            f"**{len(scene['animations'])}**"
        )

    md.append("")
    md.append("| Time | Shot | Type | Dur | VO overlap |")
    md.append("|---|---|---|---:|---:|")

    for shot in scene["spoken_shots"]:

        md.append(
            f"| {fmt(shot['start'])}–{fmt(shot['end'])} "
            f"| {shot['shot_id']} "
            f"| {shot['source_type']} "
            f"| {shot['duration']:.3f} "
            f"| {shot['voice_overlap']:.3f} |"
        )

    md.append("")

    if scene["repeated"]:

        md.append("### Repetition candidates")
        md.append("")

        for shot in scene["repeated"]:
            md.append(
                f"- `{shot['shot_id']}` "
                f"{fmt(shot['start'])}–{fmt(shot['end'])} "
                f"usage={shot['usage_count']}"
            )

        md.append("")

    if scene["animations"]:

        md.append("### New generated material")
        md.append("")

        for shot in scene["animations"]:
            md.append(
                f"- `{shot['shot_id']}` — "
                f"`{Path(shot['source']).name}` — "
                f"{fmt(shot['start'])}–{fmt(shot['end'])}"
            )

        md.append("")

    md.append("---")
    md.append("")

OUT_MD.write_text(
    "\n".join(md),
    encoding="utf-8"
)

# ------------------------------------------------------------
# CONSOLE SUMMARY
# ------------------------------------------------------------

print()
print("=" * 78)
print("GARDNER RU V4 — EDITORIAL AUDIT COMPLETE")
print("=" * 78)
print(f"Runtime      : {cursor:.3f}")
print(f"Voice        : {sum(x['duration'] for x in voices):.3f}")
print(f"Music        : {sum(float(x) for x in music):.3f}")
print(f"V3 shots     : {len(timeline)}")
print(f"Animations   : {len(animations_global)}")
print()

for scene in report:

    print(
        f"{scene['scene']}  "
        f"VOICE {fmt(scene['voice_start'])} -> "
        f"{fmt(scene['voice_end'])}  "
        f"shots={len(scene['spoken_shots']):2d}  "
        f"animations={len(scene['animations'])}"
    )

print()
print("REPORT :", OUT_MD)
print("JSON   :", OUT_JSON)
print("=" * 78)

