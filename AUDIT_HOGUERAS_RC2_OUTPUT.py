from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
BASE = ROOT / "workspace" / "exports" / "hogueras" / "rc2"
TIMELINE = BASE / "timeline" / "timeline.json"
RENDER = BASE / "render"

FILES_TO_CHECK = [
    TIMELINE,
    RENDER / "render_model_rc2.json",
    RENDER / "render_preflight_rc2.json",
    RENDER / "render_validation_rc2.json",
    RENDER / "visual_render_report_rc2.json",
    RENDER / "render_manifest.json",
    RENDER / "visual_master_rc2.mp4",
    RENDER / "phase4_av_master_rc2.mp4",
    RENDER / "hogueras_review_720p.mp4",
]

PATH_KEYS = {
    "source",
    "source_path",
    "asset_path",
    "media_path",
    "file_path",
    "filepath",
    "path",
    "input",
    "input_path",
    "video_path",
    "clip_path",
    "asset",
    "filename",
    "file",
}


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def timeline_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]

    if isinstance(data, dict):
        for key in ("rows", "clips", "shots", "timeline", "items", "segments"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]

    return []


def find_media_path(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()

            if (
                key_lower in PATH_KEYS
                and isinstance(item, str)
                and item.lower().endswith(
                    (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".jpg", ".jpeg", ".png")
                )
            ):
                return item

        for item in value.values():
            result = find_media_path(item)
            if result:
                return result

    elif isinstance(value, list):
        for item in value:
            result = find_media_path(item)
            if result:
                return result

    return None


def find_text_matches(value: Any, words: tuple[str, ...], prefix: str = "") -> list[str]:
    matches: list[str] = []

    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            matches.extend(find_text_matches(item, words, location))

    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(find_text_matches(item, words, f"{prefix}[{index}]"))

    elif isinstance(value, str):
        text = value.lower()
        if any(word in text for word in words):
            matches.append(f"{prefix}: {value}")

    return matches


def ffprobe(path: Path) -> str:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,channels,sample_rate",
        "-of",
        "json",
        str(path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except FileNotFoundError:
        return "FFPROBE_NOT_FOUND"
    except subprocess.TimeoutExpired:
        return "FFPROBE_TIMEOUT"

    if result.returncode != 0:
        return f"FFPROBE_ERROR: {result.stderr.strip()[-500:]}"

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()

    duration = payload.get("format", {}).get("duration")
    streams = payload.get("streams", [])

    lines = [f"duration={duration}"]
    if not streams:
        lines.append("streams=NONE")

    for stream in streams:
        lines.append(
            "stream "
            f"index={stream.get('index')} "
            f"type={stream.get('codec_type')} "
            f"codec={stream.get('codec_name')} "
            f"channels={stream.get('channels')} "
            f"sample_rate={stream.get('sample_rate')}"
        )

    return "\n    ".join(lines)


print("=" * 80)
print("ATLAS ZERO RC2 — HOGUERAS OUTPUT AUDIT")
print("=" * 80)

print("\n[1] ARTIFACTS")
for path in FILES_TO_CHECK:
    if path.exists():
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"EXISTS | {format_size(stat.st_size):>10} | {modified} | "
            f"{path.relative_to(ROOT)}"
        )
    else:
        print(f"MISSING | {path.relative_to(ROOT)}")

print("\n[2] TIMELINE")
if not TIMELINE.exists():
    print(f"ERROR: timeline not found: {TIMELINE}")
else:
    timeline_data = load_json(TIMELINE)
    rows = timeline_rows(timeline_data)

    print(f"timeline_path={TIMELINE}")
    print(f"rows={len(rows)}")

    selected: list[tuple[int, str]] = []
    missing_source_rows: list[int] = []

    for index, row in enumerate(rows, start=1):
        source = find_media_path(row)
        if source:
            selected.append((index, source))
        else:
            missing_source_rows.append(index)

    normalized = [
        Path(source.replace("\\", "/")).name.lower()
        for _, source in selected
    ]
    counts = Counter(normalized)
    duplicates = {
        name: count
        for name, count in counts.items()
        if count > 1
    }

    print(f"rows_with_media={len(selected)}")
    print(f"rows_without_detected_media={len(missing_source_rows)}")
    print(f"unique_source_files={len(counts)}")
    print(f"duplicate_source_names={len(duplicates)}")
    print(f"repeated_timeline_positions={sum(count - 1 for count in counts.values())}")

    print("\nTOP DUPLICATES:")
    if not duplicates:
        print("  NONE")
    else:
        for name, count in sorted(
            duplicates.items(),
            key=lambda item: (-item[1], item[0]),
        )[:30]:
            positions = [
                str(index)
                for index, source in selected
                if Path(source.replace("\\", "/")).name.lower() == name
            ]
            print(f"  {count}x | rows={','.join(positions)} | {name}")

    print("\nFIRST 25 TIMELINE SOURCES:")
    for index, source in selected[:25]:
        print(f"  {index:03d} | {source}")

    print("\nEYE / ГЛАЗ REFERENCES:")
    eye_matches = find_text_matches(
        timeline_data,
        ("eye", "глаз", "oko", "occhio"),
    )
    if eye_matches:
        for match in eye_matches[:50]:
            print(f"  {match}")
    else:
        print("  No textual eye references found in timeline.")

print("\n[3] FINAL VIDEO STREAMS")
for filename in ("visual_master_rc2.mp4", "phase4_av_master_rc2.mp4"):
    path = RENDER / filename
    print(f"\n{filename}")
    if path.exists():
        print(f"    {ffprobe(path)}")
    else:
        print("    MISSING")

print("\n[4] REPORT AUDIO REFERENCES")
for filename in (
    "render_model_rc2.json",
    "visual_render_report_rc2.json",
    "render_manifest.json",
):
    path = RENDER / filename
    print(f"\n{filename}")

    if not path.exists():
        print("  MISSING")
        continue

    try:
        data = load_json(path)
    except Exception as exc:
        print(f"  READ_ERROR: {type(exc).__name__}: {exc}")
        continue

    matches = find_text_matches(
        data,
        (
            "audio",
            "ambient",
            "natural_sound",
            "source_audio",
            "sfx",
            "voice",
            "sound",
            "mute",
            "volume",
        ),
    )

    if not matches:
        print("  No audio-related fields found.")
    else:
        for match in matches[:80]:
            print(f"  {match}")

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
