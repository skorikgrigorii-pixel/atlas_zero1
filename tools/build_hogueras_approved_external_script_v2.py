from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
SCRIPT_DIR = ROOT / "workspace" / "projects" / "hogueras" / "script"
SOURCE = SCRIPT_DIR / "approved_external_script.json"
MAP_PATH = SCRIPT_DIR / "hogueras_master_narration_v2_scene_map.json"
OUTPUT = SCRIPT_DIR / "approved_external_script_v2.json"


def find_scene_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("scenes", "items", "segments"):
            candidate = value.get(key)
            if (
                isinstance(candidate, list)
                and candidate
                and all(isinstance(item, dict) for item in candidate)
            ):
                ids = {
                    str(item.get("scene_id") or item.get("id") or "")
                    for item in candidate
                }
                if any(scene_id.startswith("SC") for scene_id in ids):
                    return candidate
        for child in value.values():
            try:
                return find_scene_list(child)
            except LookupError:
                pass

    if isinstance(value, list):
        for child in value:
            try:
                return find_scene_list(child)
            except LookupError:
                pass

    raise LookupError("Scene list was not found in approved_external_script.json")


def set_text(scene: dict[str, Any], text: str) -> str:
    if isinstance(scene.get("voiceover"), dict):
        scene["voiceover"]["text"] = text
        return "voiceover.text"

    if isinstance(scene.get("voiceover"), str):
        scene["voiceover"] = text
        return "voiceover"

    for key in (
        "text",
        "narration",
        "narration_text",
        "script_text",
        "voice_text",
    ):
        if key in scene:
            scene[key] = text
            return key

    scene["text"] = text
    return "text(created)"


def main() -> int:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source script not found: {SOURCE}")
    if not MAP_PATH.exists():
        raise FileNotFoundError(f"Scene map not found: {MAP_PATH}")

    document = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    scene_map = json.loads(MAP_PATH.read_text(encoding="utf-8-sig"))
    scenes = find_scene_list(document)

    indexed: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        scene_id = str(scene.get("scene_id") or scene.get("id") or "")
        if scene_id:
            indexed[scene_id] = scene

    expected = [f"SC{i:02d}" for i in range(1, 21)]
    missing = [scene_id for scene_id in expected if scene_id not in indexed]
    extra = [scene_id for scene_id in scene_map if scene_id not in indexed]

    if missing:
        raise ValueError("Source script is missing scenes: " + ", ".join(missing))
    if extra:
        raise ValueError("Scene map contains unknown scenes: " + ", ".join(extra))

    fields: dict[str, str] = {}
    for scene_id in expected:
        fields[scene_id] = set_text(indexed[scene_id], scene_map[scene_id])

    if isinstance(document, dict):
        document["source_mode"] = "approved_external_master_narration_v2"
        document["revision"] = "2.0"

    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("APPROVED EXTERNAL SCRIPT V2 CREATED")
    print("Output:", OUTPUT)
    print("Scenes:", len(expected))
    print("Updated fields:")
    for scene_id in expected:
        print(f" - {scene_id}: {fields[scene_id]}")
    print("")
    print("No OpenAI or ElevenLabs request was started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
