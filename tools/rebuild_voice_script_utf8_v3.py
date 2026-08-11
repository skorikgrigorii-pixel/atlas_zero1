from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "workspace" / "projects" / "hogueras" / "script"

SOURCE_PATH = SCRIPT_DIR / "hogueras_narration_utf8.txt"
VOICE_SCRIPT_PATH = SCRIPT_DIR / "voice_script.json"
FIXED_PATH = SCRIPT_DIR / "voice_script_fixed.json"
REPORT_PATH = SCRIPT_DIR / "voice_script_utf8_rebuild_report.txt"
BACKUP_DIR = ROOT / "workspace" / "backups"


# Paragraph ranges are taken from the approved narration file.
# The text itself is never stored in this program: it is extracted verbatim
# from hogueras_narration_utf8.txt.
SCENE_PLAN = [
    ("VO01", "Вступление", [(1, 5)]),
    ("VO02", "Приход Огня", [(8, 9)]),
    ("SIL01", "Фейерверки без диктора", []),
    ("VO03", "История праздника", [(12, 16)]),
    ("VO04", "Строительство хогер", [(18, 22)]),
    ("VO05", "Истории и сатира", [(24, 29)]),
    ("VO06", "Искусство одного лета", [(31, 37)]),
    ("VO07", "Ночной город", [(39, 45)]),
    ("VO08", "Комиссии районов", [(47, 51)]),
    ("VO09", "Парад цветов", [(53, 57)]),
    ("VO10", "Семейная традиция", [(59, 64)]),
    ("VO11", "Музыка шествия", [(66, 67)]),
    ("SIL02", "Живой звук духового оркестра", []),
    ("VO12", "Город живёт на улице", [(70, 70), (72, 77)]),
    ("VO13", "Формирование традиции", [(79, 83)]),
    ("VO14", "Продолжение Парада цветов", [(85, 91)]),
    ("VO15", "Масклета", [(93, 98)]),
    ("SIL03", "Живой звук Масклеты", []),
    ("VO16", "Дневные Маслеты", [(101, 107)]),
    ("VO17", "Ночь Святого Хуана", [(109, 113), (115, 119)]),
    ("SIL04", "Живой звук пляжа", []),
    ("VO18", "Ночные пиротехнические показы", [(122, 123)]),
    ("SIL05", "Фейерверк без диктора", []),
    ("VO19", "Фейерверки над морем", [(125, 125), (127, 130)]),
    ("SIL06", "Сильная часть салюта", []),
    ("VO20", "Крема и финал", [(133, 137), (139, 142), (145, 151)]),
]


# Existing timing is valid through VO18. The final source section requires
# VO19 to run until 12:44, an 8-second silent climax, and VO20 from 12:52.
FINAL_TIMING_PATCH = {
    "VO19": (734.0, 764.0),   # 12:14–12:44
    "SIL06": (764.0, 772.0),  # 12:44–12:52
    "VO20": (772.0, 823.0),   # 12:52–13:43
}


def count_cyrillic(text: str) -> int:
    return sum(
        0x0400 <= ord(ch) <= 0x04FF or 0x0500 <= ord(ch) <= 0x052F
        for ch in text
    )


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-'][A-Za-zА-Яа-яЁё0-9]+)?", text)


def split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def collect(paragraphs: list[str], ranges: Iterable[tuple[int, int]]) -> str:
    selected: list[str] = []
    for start, end in ranges:
        if start < 0 or end >= len(paragraphs) or start > end:
            raise RuntimeError(f"Invalid narration paragraph range: {start}–{end}")
        selected.extend(paragraphs[start : end + 1])
    return "\n\n".join(selected)


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Missing narration source: {SOURCE_PATH}")
    if not VOICE_SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing voice script: {VOICE_SCRIPT_PATH}")

    source = SOURCE_PATH.read_text(encoding="utf-8-sig")
    if count_cyrillic(source) < 1000:
        raise RuntimeError("Narration source contains too little Cyrillic.")
    if source.count("?") != 0:
        raise RuntimeError("Narration source contains literal question marks.")

    paragraphs = split_paragraphs(source)
    if len(paragraphs) != 152:
        raise RuntimeError(
            f"Unexpected narration structure: expected 152 paragraphs, got {len(paragraphs)}. "
            "The approved source may have changed."
        )

    payload = json.loads(VOICE_SCRIPT_PATH.read_text(encoding="utf-8-sig"))
    scenes = payload.get("scenes")
    if not isinstance(scenes, list):
        raise RuntimeError("voice_script.json: scenes must be a list.")

    expected_ids = [item[0] for item in SCENE_PLAN]
    actual_ids = [scene.get("scene_id") for scene in scenes]
    if actual_ids != expected_ids:
        raise RuntimeError(
            "Scene order mismatch.\n"
            f"Expected: {expected_ids}\n"
            f"Actual:   {actual_ids}"
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = BACKUP_DIR / f"hogueras_voice_script_utf8_{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    shutil.copy2(VOICE_SCRIPT_PATH, backup_root / "voice_script.json")
    shutil.copy2(SOURCE_PATH, backup_root / "hogueras_narration_utf8.txt")

    plan_by_id = {
        scene_id: (title, ranges)
        for scene_id, title, ranges in SCENE_PLAN
    }

    report_lines = [
        "=" * 92,
        "ATLAS ZERO — HOGUERAS VOICE SCRIPT UTF-8 REBUILD REPORT",
        "=" * 92,
        f"Source: {SOURCE_PATH}",
        f"Backup: {backup_root}",
        "",
        f"{'SCENE':<7} {'START':>7} {'END':>7} {'DUR':>7} {'WORDS':>7} {'W/S':>7}  STATUS",
        "-" * 92,
    ]

    full_voice_parts: list[str] = []

    for scene in scenes:
        scene_id = scene["scene_id"]
        title, ranges = plan_by_id[scene_id]
        text = collect(paragraphs, ranges)

        scene["title"] = title

        voiceover = scene.get("voiceover")
        if not isinstance(voiceover, dict):
            raise RuntimeError(f"{scene_id}: voiceover must be an object.")

        voiceover["text"] = text
        voiceover["target_words"] = len(words(text))

        if scene_id in FINAL_TIMING_PATCH:
            start_sec, end_sec = FINAL_TIMING_PATCH[scene_id]
            scene["start_sec"] = start_sec
            scene["end_sec"] = end_sec
            scene["duration_sec"] = round(end_sec - start_sec, 3)

        start = float(scene["start_sec"])
        end = float(scene["end_sec"])
        duration = float(scene["duration_sec"])
        word_count = len(words(text))
        rate = word_count / duration if duration > 0 else 0.0

        if scene_id.startswith("SIL"):
            status = "SILENCE_OK" if not text else "ERROR"
        elif rate <= 2.6:
            status = "OK"
        elif rate <= 2.9:
            status = "FAST_REVIEW"
        else:
            status = "TOO_FAST"

        report_lines.append(
            f"{scene_id:<7} {start:7.1f} {end:7.1f} {duration:7.1f} "
            f"{word_count:7d} {rate:7.2f}  {status}"
        )

        if text:
            full_voice_parts.append(text)

    payload["duration_sec"] = 823.0
    payload["scene_count"] = len(scenes)
    payload["full_voiceover"] = "\n\n".join(full_voice_parts)

    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    FIXED_PATH.write_text(serialized, encoding="utf-8-sig")

    verified = json.loads(FIXED_PATH.read_text(encoding="utf-8-sig"))

    rebuilt_strings: list[str] = [str(verified.get("full_voiceover", ""))]
    for scene in verified["scenes"]:
        rebuilt_strings.append(str(scene.get("title", "")))
        rebuilt_strings.append(str(scene.get("voiceover", {}).get("text", "")))

    rebuilt_text = "\n".join(rebuilt_strings)
    cyrillic = count_cyrillic(rebuilt_text)
    questions = rebuilt_text.count("?")
    replacements = rebuilt_text.count("\ufffd")

    if cyrillic < 1000:
        raise RuntimeError(f"Validation failed: too little Cyrillic ({cyrillic}).")
    if questions != 0:
        raise RuntimeError(f"Validation failed: question marks found ({questions}).")
    if replacements != 0:
        raise RuntimeError(
            f"Validation failed: Unicode replacement characters found ({replacements})."
        )

    # Ensure every voiced paragraph comes verbatim from the approved source.
    for scene in verified["scenes"]:
        text = scene.get("voiceover", {}).get("text", "")
        if not text:
            continue
        for paragraph in text.split("\n\n"):
            if paragraph not in source:
                raise RuntimeError(
                    f"{scene['scene_id']}: generated paragraph is not verbatim in source:\n{paragraph}"
                )

    # Fail only for scenes that are objectively beyond the agreed safety ceiling.
    unsafe: list[str] = []
    for scene in verified["scenes"]:
        text = scene.get("voiceover", {}).get("text", "")
        if not text:
            continue
        duration = float(scene["duration_sec"])
        rate = len(words(text)) / duration
        if rate > 2.9:
            unsafe.append(f"{scene['scene_id']}={rate:.2f} words/sec")

    if unsafe:
        raise RuntimeError("Unsafe narration speed: " + ", ".join(unsafe))

    shutil.copy2(FIXED_PATH, VOICE_SCRIPT_PATH)

    report_lines.extend(
        [
            "-" * 92,
            f"Scenes: {len(verified['scenes'])}",
            f"Duration: {verified['duration_sec']:.1f} sec",
            f"Cyrillic in rebuilt narration fields: {cyrillic}",
            f"Question marks in rebuilt narration fields: {questions}",
            f"Unicode replacement characters: {replacements}",
            "",
            "Result: ACTIVE voice_script.json REPLACED SUCCESSFULLY",
            "No ElevenLabs generation was started.",
        ]
    )
    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8-sig")

    print("\n".join(report_lines))


if __name__ == "__main__":
    main()
