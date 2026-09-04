from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path


model_path = Path(
    r"workspace\exports\hogueras\rc2\render\render_model_rc2.json"
)

model = json.loads(model_path.read_text(encoding="utf-8"))

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


def source_has_audio(path: Path) -> bool:
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )

    return process.returncode == 0 and bool(process.stdout.strip())


clips = model.get("clips", [])

natural_enabled = []
recognized = []
eligible = []
missing_source = []
without_audio = []

for clip in clips:
    if clip.get("media_type") != "video":
        continue

    if clip.get("natural_sound_enabled") is not True:
        continue

    natural_enabled.append(clip)

    category = event_category(clip)
    if category is None:
        continue

    row = {
        "shot_index": clip.get("shot_index"),
        "category": category,
        "asset_name": clip.get("asset_name"),
        "asset_path": clip.get("asset_path"),
        "start_sec": clip.get("start_sec"),
        "duration_sec": clip.get("duration_sec"),
        "visual_need": clip.get("visual_need"),
        "story_goal": clip.get("story_goal"),
    }
    recognized.append(row)

    source_path = Path(str(clip.get("asset_path") or ""))

    if not source_path.exists():
        missing_source.append(row)
        continue

    if not source_has_audio(source_path):
        without_audio.append(row)
        continue

    eligible.append(row)


if eligible:
    target_count = max(
        1,
        min(
            len(eligible),
            round(len(eligible) * 0.35),
        ),
    )
else:
    target_count = 0


print("=" * 78)
print("ATLAS ZERO RC2 — NATURAL SOUND FILTER DIAGNOSTIC")
print("=" * 78)
print(f"Render model clips:           {len(clips)}")
print(f"Natural sound enabled:        {len(natural_enabled)}")
print(f"Recognized by event keywords: {len(recognized)}")
print(f"Missing source files:         {len(missing_source)}")
print(f"Sources without audio:        {len(without_audio)}")
print(f"Actually eligible:            {len(eligible)}")
print(f"Selected by 35% rule:         {target_count}")
print()

print("RECOGNIZED CATEGORIES")
for name, count in sorted(
    Counter(row["category"] for row in recognized).items()
):
    print(f"- {name}: {count}")

print()
print("ACTUALLY ELIGIBLE CLIPS")

if not eligible:
    print("- NONE")
else:
    for row in eligible:
        print(
            f"- shot={row['shot_index']} | "
            f"category={row['category']} | "
            f"start={row['start_sec']} | "
            f"duration={row['duration_sec']} | "
            f"asset={row['asset_name']}"
        )

print()
print("UNRECOGNIZED VISUAL_NEED VALUES")

unrecognized_visual_needs = Counter()

for clip in natural_enabled:
    if event_category(clip) is None:
        value = str(clip.get("visual_need") or "<EMPTY>")
        unrecognized_visual_needs[value] += 1

for value, count in unrecognized_visual_needs.most_common():
    print(f"- {count:>3} | {value}")
