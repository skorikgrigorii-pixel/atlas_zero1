from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "workspace" / "projects" / "hogueras" / "script" / "voice_script.json"
AUDIO_DIR = ROOT / "workspace" / "projects" / "hogueras" / "01_Audio"
BACKUP_DIR = ROOT / "workspace" / "backups"

NEW_TEXT = """Но главный финал происходит не в небе.

В полночь 24 июня с замка Санта-Барбара запускают световую пальму. Она даёт сигнал к началу Кремы — сожжению хогер.

Сначала загорается монумент у здания мэрии, затем огонь появляется в других районах города.

Фигуры, которые создавали несколько месяцев, исчезают за считаные минуты. Пожарные контролируют пламя и поливают водой конструкции и зрителей.

Утром от огромных фигур останутся мокрый асфальт, пепел и фотографии. Но совсем скоро комиссии начнут готовить следующий праздник — новые идеи, новых персонажей и новые хогеры. Чтобы через год Аликанте снова построил город из огня и снова сжёг его в ночь Святого Хуана."""


def count_cyrillic(text: str) -> int:
    return sum(
        0x0400 <= ord(ch) <= 0x04FF or 0x0500 <= ord(ch) <= 0x052F
        for ch in text
    )


def count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-'][A-Za-zА-Яа-яЁё0-9]+)?", text))


def main() -> None:
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(SCRIPT_PATH)

    payload = json.loads(SCRIPT_PATH.read_text(encoding="utf-8-sig"))
    scenes = payload.get("scenes", [])

    scene = next(
        (item for item in scenes if str(item.get("scene_id", "")).strip() == "VO20"),
        None,
    )
    if scene is None:
        raise RuntimeError("VO20 was not found")

    if count_cyrillic(NEW_TEXT) < 100 or "?" in NEW_TEXT:
        raise RuntimeError("New VO20 text failed UTF-8 validation")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = BACKUP_DIR / f"hogueras_vo20_before_shorten_{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    shutil.copy2(SCRIPT_PATH, backup_root / "voice_script.json")

    voiceover = scene.get("voiceover")
    if not isinstance(voiceover, dict):
        raise RuntimeError("VO20 voiceover is not an object")

    old_text = str(voiceover.get("text", ""))
    voiceover["text"] = NEW_TEXT
    voiceover["target_words"] = count_words(NEW_TEXT)

    payload["full_voiceover"] = "\n\n".join(
        str(item.get("voiceover", {}).get("text", "")).strip()
        for item in scenes
        if str(item.get("voiceover", {}).get("text", "")).strip()
    )

    SCRIPT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8-sig",
    )

    # Remove only VO20 cache and single-scene reports.
    for path in (
        AUDIO_DIR / "voice_blocks" / "voice_block_26.mp3",
        AUDIO_DIR / "scenes" / "VO20.wav",
        AUDIO_DIR / "voice_report_VO20.json",
        AUDIO_DIR / "voice_manifest_VO20.json",
    ):
        path.unlink(missing_ok=True)

    print("=" * 78)
    print("VO20 TEXT UPDATED")
    print("=" * 78)
    print("Backup:", backup_root)
    print("Old words:", count_words(old_text))
    print("New words:", count_words(NEW_TEXT))
    print("Cyrillic:", count_cyrillic(NEW_TEXT))
    print("Question marks:", NEW_TEXT.count("?"))
    print("VO20 cache removed")
    print()
    print("Next command:")
    print(r".\.venv\Scripts\python.exe -m az_enterprise.cli voice-rc2 hogueras --scene-id VO20")


if __name__ == "__main__":
    main()
