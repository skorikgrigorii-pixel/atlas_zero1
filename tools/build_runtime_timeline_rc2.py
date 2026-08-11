from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
PROJECT_ID = "hogueras"

RC2_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "rc2"
)

RENDER_MODEL_PATH = (
    RC2_DIR
    / "render"
    / "render_model_rc2.json"
)

EDITOR_OVERRIDES_PATH = (
    RC2_DIR
    / "editor_overrides_rc2.json"
)

OUTPUT_PATH = (
    RC2_DIR
    / "runtime_timeline_rc2.json"
)


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def merge_ranges(
    ranges: list[dict[str, float]],
) -> list[dict[str, float]]:
    normalized = []

    for item in ranges:
        start = as_float(item.get("start_sec"))
        end = as_float(item.get("end_sec"))

        if end <= start:
            continue

        normalized.append({
            "start_sec": round(start, 6),
            "end_sec": round(end, 6),
        })

    normalized.sort(
        key=lambda item: (
            item["start_sec"],
            item["end_sec"],
        )
    )

    merged: list[dict[str, float]] = []

    for item in normalized:
        if not merged:
            merged.append(dict(item))
            continue

        previous = merged[-1]

        if item["start_sec"] <= previous["end_sec"] + 0.001:
            previous["end_sec"] = round(
                max(
                    previous["end_sec"],
                    item["end_sec"],
                ),
                6,
            )
        else:
            merged.append(dict(item))

    for item in merged:
        item["duration_sec"] = round(
            item["end_sec"] - item["start_sec"],
            6,
        )

    return merged


if not RENDER_MODEL_PATH.exists():
    raise FileNotFoundError(
        f"Render model was not found: {RENDER_MODEL_PATH}"
    )

render_model = load_json(RENDER_MODEL_PATH)
source_clips = list(render_model.get("clips") or [])

if not source_clips:
    raise RuntimeError(
        "render_model_rc2.json contains no clips"
    )

clips = []

for index, source in enumerate(source_clips, start=1):
    start_sec = as_float(source.get("start_sec"))
    end_sec = as_float(source.get("end_sec"))
    duration_sec = as_float(source.get("duration_sec"))

    if end_sec <= start_sec and duration_sec > 0:
        end_sec = start_sec + duration_sec

    if end_sec <= start_sec:
        raise ValueError(
            f"Invalid clip timing at index {index}: "
            f"{start_sec}–{end_sec}"
        )

    clip = {
        "timeline_index": index,
        "shot_id": str(
            source.get("shot_id")
            or f"clip_{index:04d}"
        ),
        "start_sec": round(start_sec, 6),
        "end_sec": round(end_sec, 6),
        "duration_sec": round(
            end_sec - start_sec,
            6,
        ),
        "block": source.get("block"),
        "asset_name": source.get("asset_name"),
        "asset_path": source.get("asset_path"),
        "media_type": source.get("media_type"),
        "source_in_sec": source.get("source_in_sec"),
        "source_out_sec": source.get("source_out_sec"),
        "natural_sound_enabled": bool(
            source.get("natural_sound_enabled")
        ),
        "natural_sound_windows": (
            source.get("natural_sound_windows")
            or []
        ),
        "music_path": source.get("music_path"),
        "voice_path": source.get("voice_path"),
        "transition": source.get("transition"),
        "transition_duration_sec": source.get(
            "transition_duration_sec"
        ),
        "story_goal": source.get("story_goal"),
        "visual_need": source.get("visual_need"),
        "emotion": source.get("emotion"),
    }

    clips.append(clip)


clips.sort(
    key=lambda item: (
        item["start_sec"],
        item["end_sec"],
        item["timeline_index"],
    )
)

film_duration_sec = round(
    max(item["end_sec"] for item in clips),
    6,
)

natural_ranges: list[dict[str, float]] = []

for clip in clips:
    if clip["natural_sound_enabled"]:
        natural_ranges.append({
            "start_sec": clip["start_sec"],
            "end_sec": clip["end_sec"],
        })

    for window in clip["natural_sound_windows"]:
        if not isinstance(window, dict):
            continue

        relative_start = as_float(
            window.get("start_sec")
        )
        relative_end = as_float(
            window.get("end_sec")
        )

        # Внутренние окна клипа переводим
        # в абсолютное время фильма.
        absolute_start = (
            clip["start_sec"] + relative_start
        )
        absolute_end = (
            clip["start_sec"] + relative_end
        )

        natural_ranges.append({
            "start_sec": absolute_start,
            "end_sec": min(
                absolute_end,
                clip["end_sec"],
            ),
        })


if EDITOR_OVERRIDES_PATH.exists():
    overrides = load_json(EDITOR_OVERRIDES_PATH)

    for item in (
        overrides.get("natural_sound_enable")
        or []
    ):
        if isinstance(item, dict):
            natural_ranges.append({
                "start_sec": as_float(
                    item.get("start_sec")
                ),
                "end_sec": as_float(
                    item.get("end_sec")
                ),
            })


merged_natural_ranges = merge_ranges(
    natural_ranges
)

natural_sound_duration_sec = round(
    sum(
        item["duration_sec"]
        for item in merged_natural_ranges
    ),
    6,
)

payload = {
    "schema": "atlas_zero.runtime_timeline.rc2.v1",
    "state": "RUNTIME_TIMELINE_READY",
    "project_id": PROJECT_ID,
    "authority": "RenderEngineRC2",
    "timing_authority": str(
        RENDER_MODEL_PATH.resolve()
    ),
    "generated_at": datetime.now(
        timezone.utc
    ).isoformat(),
    "film_duration_sec": film_duration_sec,
    "clip_count": len(clips),
    "natural_sound_duration_sec": (
        natural_sound_duration_sec
    ),
    "available_narration_duration_sec": round(
        film_duration_sec
        - natural_sound_duration_sec,
        6,
    ),
    "source": {
        "render_model": str(
            RENDER_MODEL_PATH.resolve()
        ),
        "render_model_sha256": file_sha256(
            RENDER_MODEL_PATH
        ),
        "editor_overrides": (
            str(EDITOR_OVERRIDES_PATH.resolve())
            if EDITOR_OVERRIDES_PATH.exists()
            else None
        ),
    },
    "clips": clips,
    "protected_natural_sound_ranges": (
        merged_natural_ranges
    ),
}

OUTPUT_PATH.write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    ) + "\n",
    encoding="utf-8",
)

print("RUNTIME TIMELINE CREATED")
print("Output:", OUTPUT_PATH)
print("Authority:", payload["authority"])
print(
    "Film duration:",
    payload["film_duration_sec"],
)
print("Clips:", payload["clip_count"])
print(
    "Protected natural sound:",
    payload["natural_sound_duration_sec"],
)
print(
    "Available narration:",
    payload[
        "available_narration_duration_sec"
    ],
)
print("")
print(
    "No OpenAI or ElevenLabs request was started."
)
