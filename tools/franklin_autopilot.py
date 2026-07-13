from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from az_enterprise.core.database import Database
from az_enterprise.core.movie_runtime_rc1 import MovieRuntimeRC1


PROJECT_ID = "franklin"

PROJECT_DIR = ROOT / "workspace" / "projects" / PROJECT_ID
AUDIO_DIR = PROJECT_DIR / "01_Audio"
SCRIPT_DIR = PROJECT_DIR / "script"

INBOX_DIR = ROOT / "workspace" / "inbox" / PROJECT_ID
EXPORT_DIR = ROOT / "workspace" / "exports" / PROJECT_ID
RUNTIME_DIR = EXPORT_DIR / "movie_runtime_rc1"

SCRIPT_TXT = SCRIPT_DIR / "production_script.txt"
INPUT_MANIFEST = RUNTIME_DIR / "runtime_input_manifest.json"

AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
}

SCRIPT_EXTENSIONS = {
    ".docx",
    ".txt",
    ".md",
}

EXPECTED_AUDIO_BLOCKS = {1, 2, 3, 4, 5, 6}
AVERAGE_SHOT_DURATION_SEC = 6.5
MIN_SHOTS = 120
MAX_SHOTS = 180


def ensure_directories() -> None:
    for path in (
        PROJECT_DIR,
        AUDIO_DIR,
        SCRIPT_DIR,
        INBOX_DIR,
        EXPORT_DIR,
        RUNTIME_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def run_command(command: list[str]) -> str:
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if process.returncode != 0:
        raise RuntimeError(
            "Команда завершилась с ошибкой:\n"
            + " ".join(command)
            + "\n"
            + process.stderr
        )

    return process.stdout.strip()


def probe_duration(path: Path) -> float:
    output = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )

    return float(output)


def decode_unicode_filename(value: str) -> str:
    pattern = re.compile(r"#U([0-9A-Fa-f]{4})")

    def replace(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    return pattern.sub(replace, value)


def detect_block_number(path: Path) -> int | None:
    decoded = decode_unicode_filename(path.stem).lower()

    patterns = (
        r"(?:блок|block|voice[_\-\s]*block)[_\-\s]*0?([1-6])",
        r"(?:озвучка).*?0?([1-6])",
    )

    for pattern in patterns:
        match = re.search(pattern, decoded, re.IGNORECASE)

        if match:
            return int(match.group(1))

    return None


def audio_candidates() -> list[Path]:
    roots = (
        INBOX_DIR,
        AUDIO_DIR,
    )

    found: dict[str, Path] = {}

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue

            found[str(path.resolve()).lower()] = path

    return sorted(
        found.values(),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


def normalize_audio() -> dict[int, Path]:
    by_block: dict[int, Path] = {}

    for candidate in audio_candidates():
        block_number = detect_block_number(candidate)

        if block_number is None:
            continue

        if block_number not in by_block:
            by_block[block_number] = candidate

    missing = EXPECTED_AUDIO_BLOCKS - set(by_block)

    if missing:
        raise RuntimeError(
            "Не найдены аудиоблоки: "
            + ", ".join(str(number) for number in sorted(missing))
            + f"\nПоложите недостающие файлы в: {INBOX_DIR}"
        )

    normalized: dict[int, Path] = {}

    for block_number in sorted(by_block):
        source = by_block[block_number]
        target = AUDIO_DIR / (
            f"voice_block_{block_number:02d}"
            f"{source.suffix.lower()}"
        )

        if source.resolve() != target.resolve():
            shutil.copy2(source, target)

        normalized[block_number] = target

    return normalized


def find_script_source() -> Path:
    preferred_names = (
        "ATLAS_ZERO_Master_Production_Script_v1.0.docx",
        "production_script.docx",
        "production_script.txt",
        "final.txt",
    )

    roots = (
        INBOX_DIR,
        SCRIPT_DIR,
        PROJECT_DIR,
    )

    candidates: list[Path] = []

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in SCRIPT_EXTENSIONS:
                continue

            candidates.append(path)

    for preferred_name in preferred_names:
        for candidate in candidates:
            if candidate.name.lower() == preferred_name.lower():
                return candidate

    semantic_candidates = [
        candidate
        for candidate in candidates
        if re.search(
            r"production|script|сценар|atlas.*zero|franklin",
            candidate.name,
            re.IGNORECASE,
        )
    ]

    if semantic_candidates:
        return max(
            semantic_candidates,
            key=lambda item: (
                item.stat().st_size,
                item.stat().st_mtime,
            ),
        )

    raise RuntimeError(
        "Production Script не найден.\n"
        f"Положите DOCX, TXT или MD в папку:\n{INBOX_DIR}"
    )


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml_data = archive.read("word/document.xml")

    root = ElementTree.fromstring(xml_data)

    namespace = {
        "w": (
            "http://schemas.openxmlformats.org/"
            "wordprocessingml/2006/main"
        )
    }

    paragraphs: list[str] = []

    for paragraph in root.findall(".//w:p", namespace):
        text_parts = [
            node.text or ""
            for node in paragraph.findall(".//w:t", namespace)
        ]

        text = "".join(text_parts).strip()

        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs).strip()


def extract_script_text(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".docx":
        return extract_docx_text(path)

    return path.read_text(
        encoding="utf-8",
        errors="ignore",
    ).strip()


def prepare_script() -> tuple[Path, dict[str, int]]:
    source = find_script_source()
    text = extract_script_text(source)

    if not text:
        raise RuntimeError(
            f"Из сценария не удалось извлечь текст: {source}"
        )

    SCRIPT_TXT.write_text(
        text,
        encoding="utf-8",
    )

    non_empty_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    return source, {
        "line_count": len(non_empty_lines),
        "char_count": len(text),
    }


def build_audio_report(
    normalized_audio: dict[int, Path],
) -> tuple[list[dict[str, object]], float]:
    rows: list[dict[str, object]] = []
    total_duration = 0.0

    for block_number, path in sorted(normalized_audio.items()):
        duration = probe_duration(path)
        total_duration += duration

        rows.append(
            {
                "block": block_number,
                "filename": path.name,
                "path": str(path.resolve()),
                "duration_sec": round(duration, 3),
            }
        )

    return rows, round(total_duration, 3)


def run_pipeline(
    script_meta: dict[str, int],
    audio_duration_sec: float,
) -> dict[str, object]:
    database = Database()
    database.init()

    runtime = MovieRuntimeRC1(
        database,
        PROJECT_ID,
    )

    script = runtime._load_production_script()

    # Голос является источником точной длительности фильма.
    script["estimated_duration_sec"] = audio_duration_sec
    script["line_count"] = script_meta["line_count"]
    script["char_count"] = script_meta["char_count"]

    target_shots = round(
        audio_duration_sec / AVERAGE_SHOT_DURATION_SEC
    )

    target_shots = min(
        MAX_SHOTS,
        max(MIN_SHOTS, target_shots),
    )

    print()
    print("Пересоздание монтажной структуры...")
    print(f"Длительность: {audio_duration_sec:.3f} сек.")
    print(f"Целевое количество шотов: {target_shots}")

    structure = runtime._build_scene_and_shots(script)

    print("Назначение визуальных материалов...")
    assignment = runtime._execute_visual_generator()

    print("Построение timeline...")
    timeline_result = runtime._build_timeline()

    timeline_path = RUNTIME_DIR / "timeline.json"

    timeline = json.loads(
        timeline_path.read_text(encoding="utf-8")
    )

    statuses = Counter(
        item.get("status", "unknown")
        for item in timeline
    )

    assigned = statuses.get("assigned", 0)
    missing = statuses.get("missing", 0)

    timeline_duration = max(
        (
            float(item.get("end_sec", 0))
            for item in timeline
        ),
        default=0.0,
    )

    return {
        "structure": structure,
        "assignment": {
            "assigned": assignment.get("assigned", 0),
            "missing": assignment.get("missing", 0),
            "tasks_generated": assignment.get(
                "tasks_generated",
                0,
            ),
        },
        "timeline": {
            "path": str(timeline_path.resolve()),
            "items": len(timeline),
            "assigned": assigned,
            "missing": missing,
            "duration_sec": round(timeline_duration, 3),
        },
        "timeline_result": timeline_result,
    }


def write_manifest(
    script_source: Path,
    script_meta: dict[str, int],
    audio_rows: list[dict[str, object]],
    audio_duration_sec: float,
    pipeline_result: dict[str, object],
) -> None:
    payload = {
        "project_id": PROJECT_ID,
        "script": {
            "source": str(script_source.resolve()),
            "normalized": str(SCRIPT_TXT.resolve()),
            **script_meta,
        },
        "audio": {
            "blocks": audio_rows,
            "count": len(audio_rows),
            "total_duration_sec": audio_duration_sec,
        },
        "montage": {
            "average_shot_duration_sec": (
                AVERAGE_SHOT_DURATION_SEC
            ),
            "minimum_shots": MIN_SHOTS,
            "maximum_shots": MAX_SHOTS,
        },
        "pipeline": pipeline_result,
    }

    INPUT_MANIFEST.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    ensure_directories()

    print("=" * 68)
    print("ATLAS ZERO — FRANKLIN AUTO-INGEST")
    print("=" * 68)
    print(f"Входящая папка: {INBOX_DIR}")

    script_source, script_meta = prepare_script()

    print()
    print("Сценарий найден:")
    print(script_source)
    print(
        f"Строк: {script_meta['line_count']}, "
        f"символов: {script_meta['char_count']}"
    )

    normalized_audio = normalize_audio()
    audio_rows, audio_duration_sec = build_audio_report(
        normalized_audio
    )

    print()
    print("Озвучка:")

    for row in audio_rows:
        print(
            f"Блок {row['block']}: "
            f"{row['duration_sec']} сек. — "
            f"{row['filename']}"
        )

    minutes = int(audio_duration_sec // 60)
    seconds = audio_duration_sec % 60

    print(
        f"Общая длительность: "
        f"{minutes:02d}:{seconds:06.3f}"
    )

    pipeline_result = run_pipeline(
        script_meta=script_meta,
        audio_duration_sec=audio_duration_sec,
    )

    write_manifest(
        script_source=script_source,
        script_meta=script_meta,
        audio_rows=audio_rows,
        audio_duration_sec=audio_duration_sec,
        pipeline_result=pipeline_result,
    )

    timeline = pipeline_result["timeline"]

    print()
    print("=" * 68)
    print("РЕЗУЛЬТАТ")
    print("=" * 68)
    print(f"Шотов:       {timeline['items']}")
    print(f"Назначено:   {timeline['assigned']}")
    print(f"Отсутствует: {timeline['missing']}")
    print(
        f"Длительность timeline: "
        f"{timeline['duration_sec']} сек."
    )
    print(f"Manifest: {INPUT_MANIFEST}")
    print("=" * 68)

    if timeline["missing"] > 0:
        print()
        print(
            "Рендер не запущен: "
            "есть шоты без назначенного материала."
        )
        return 2

    print()
    print("Входящие материалы подготовлены.")
    print("Timeline прошёл проверку.")
    print("Рендер пока не запускался.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
