from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


MODEL_PATH = Path(
    r"workspace\exports\hogueras\rc2\render\render_model_rc2.json"
)

model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))

ffprobe = shutil.which("ffprobe")
if not ffprobe:
    raise RuntimeError("ffprobe is not available in PATH")


EVENT_KEYWORDS = {
    "music_band": (
        "music_band",
        "music band",
        "marching band",
        "brass band",
        "orchestra",
        "оркестр",
        "музыкальн",
        "band playing",
        "musicians",
    ),
    "mascleta": (
        "mascleta",
        "mascletà",
        "pyrotechnic explosions",
        "daytime pyrotechnic",
        "petard",
        "петард",
        "масклет",
    ),
    "fireworks": (
        "fireworks",
        "firework",
        "fuegos artificiales",
        "pyrotechnic display",
        "night pyrotechnic",
        "фейерверк",
        "салют",
    ),
}


def event_category(clip: dict) -> str | None:
    searchable = " ".join(
        str(clip.get(field) or "")
        for field in (
            "scene_id",
            "scene_title",
            "block",
            "story_goal",
            "visual_need",
            "emotion",
            "asset_name",
            "source_mode",
        )
    ).casefold()

    for category, keywords in EVENT_KEYWORDS.items():
        if any(keyword.casefold() in searchable for keyword in keywords):
            return category

    return None


def probe_duration(path: Path) -> float | None:
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )

    if process.returncode != 0:
        return None

    text = process.stdout.strip()
    try:
        return float(text)
    except ValueError:
        return None


eligible = []

for clip in model.get("clips", []):
    if clip.get("media_type") != "video":
        continue

    if clip.get("natural_sound_enabled") is not True:
        continue

    category = event_category(clip)
    if category is None:
        continue

    source_path = Path(str(clip.get("asset_path") or ""))

    if not source_path.exists():
        continue

    eligible.append((clip, category, source_path))


selected = []

if eligible:
    target_count = max(
        1,
        min(
            len(eligible),
            round(len(eligible) * 0.35),
        ),
    )

    if target_count >= len(eligible):
        selected = eligible

    elif target_count == 1:
        selected = [eligible[len(eligible) // 2]]

    else:
        selected_indexes = []

        for position in range(target_count):
            index = round(
                position
                * (len(eligible) - 1)
                / (target_count - 1)
            )

            if index not in selected_indexes:
                selected_indexes.append(index)

        if len(selected_indexes) < target_count:
            for index in range(len(eligible)):
                if index in selected_indexes:
                    continue

                selected_indexes.append(index)

                if len(selected_indexes) >= target_count:
                    break

        selected = [
            eligible[index]
            for index in sorted(
                selected_indexes[:target_count]
            )
        ]


print("=" * 100)
print("ATLAS ZERO RC2 — SELECTED NATURAL AUDIO SOURCE RANGE AUDIT")
print("=" * 100)
print(f"Eligible clips: {len(eligible)}")
print(f"Selected clips: {len(selected)}")
print()

problems = 0

for clip, category, source_path in selected:
    source_duration = probe_duration(source_path)

    source_in = float(clip.get("source_in_sec") or 0.0)
    source_out_raw = clip.get("source_out_sec")
    source_out = (
        float(source_out_raw)
        if source_out_raw is not None
        else None
    )

    clip_duration = float(clip.get("duration_sec") or 0.0)

    windows = clip.get("natural_sound_windows") or [
        {
            "start_sec": 0.0,
            "end_sec": clip_duration,
        }
    ]

    print("-" * 100)
    print(
        f"shot={clip.get('shot_index')} | "
        f"category={category} | "
        f"asset={clip.get('asset_name')}"
    )
    print(f"path={source_path}")
    print(f"source_duration={source_duration}")
    print(f"source_in_sec={source_in}")
    print(f"source_out_sec={source_out}")
    print(f"clip_duration_sec={clip_duration}")
    print(f"timeline_start_sec={clip.get('start_sec')}")
    print(f"windows={windows}")

    for window_index, window in enumerate(windows, start=1):
        window_start = float(
            window.get("start_sec", window.get("start", 0.0))
        )
        window_end = float(
            window.get("end_sec", window.get("end", clip_duration))
        )

        trim_start = source_in + window_start
        trim_duration = window_end - window_start
        trim_end = trim_start + trim_duration

        valid = (
            source_duration is not None
            and trim_duration > 0.05
            and trim_start < source_duration
            and trim_end <= source_duration + 0.10
        )

        status = "OK" if valid else "INVALID"
        if not valid:
            problems += 1

        print(
            f"  window#{window_index}: "
            f"trim_start={trim_start:.3f} | "
            f"trim_duration={trim_duration:.3f} | "
            f"trim_end={trim_end:.3f} | "
            f"status={status}"
        )

print()
print("=" * 100)
print(f"Invalid source ranges: {problems}")
print("=" * 100)
