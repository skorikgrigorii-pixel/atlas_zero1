from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path.cwd()

SEARCH_ROOTS = [
    ROOT / "src",
    ROOT / "tools",
]

TEXT_EXTENSIONS = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
}

SEARCH_GROUPS = {
    "PHASE4_OUTPUT": [
        r"phase4_av_master_rc2",
        r"phase4",
        r"av_master_rc2",
    ],
    "SILENCE_GENERATION": [
        r"anullsrc",
        r"aevalsrc",
        r"lavfi",
        r"silent",
        r"silence",
        r"audio_ready",
        r"voice_ready",
    ],
    "AUDIO_PROCESSING": [
        r"source_audio",
        r"original_audio",
        r"natural_sound",
        r"ambient",
        r"audio_mode",
        r"audio_gain",
        r"audio_stream",
        r"-map",
        r"amix",
        r"volume=",
        r"acrossfade",
        r"afade",
    ],
    "EVENT_CATEGORIES": [
        r"orchestra",
        r"band",
        r"music_performance",
        r"mascleta",
        r"masclet[aà]",
        r"fireworks",
        r"pyrotechnic",
        r"fuegos",
        r"petard",
    ],
    "ASSIGNMENT_TIMELINE": [
        r"assignment",
        r"timeline",
        r"selected_asset",
        r"asset_id",
        r"source_path",
        r"used_assets",
        r"used_asset",
        r"allow_reuse",
        r"reuse",
        r"duplicate",
        r"dedup",
        r"unique",
    ],
}


def iter_files():
    seen: set[Path] = set()

    for search_root in SEARCH_ROOTS:
        if not search_root.exists():
            continue

        for path in search_root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue

            if any(part in {".venv", "__pycache__", ".git"} for part in path.parts):
                continue

            resolved = path.resolve()
            if resolved in seen:
                continue

            seen.add(resolved)
            yield path


def read_text(path: Path) -> str | None:
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def print_matches(files: list[tuple[Path, str]]) -> None:
    for group_name, patterns in SEARCH_GROUPS.items():
        print()
        print("=" * 100)
        print(group_name)
        print("=" * 100)

        group_results: list[tuple[Path, int, str]] = []

        compiled = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in patterns
        ]

        for path, text in files:
            for line_number, line in enumerate(text.splitlines(), start=1):
                if any(pattern.search(line) for pattern in compiled):
                    group_results.append(
                        (
                            path,
                            line_number,
                            line.strip(),
                        )
                    )

        if not group_results:
            print("NO MATCHES")
            continue

        for path, line_number, line in group_results[:400]:
            try:
                relative = path.relative_to(ROOT)
            except ValueError:
                relative = path

            print(f"{relative}:{line_number}: {line}")

        if len(group_results) > 400:
            print(f"... TRUNCATED: {len(group_results) - 400} more matches")


def inspect_python_structure(files: list[tuple[Path, str]]) -> None:
    keywords = (
        "timeline",
        "assignment",
        "render",
        "audio",
        "phase4",
        "director",
    )

    print()
    print("=" * 100)
    print("RELEVANT PYTHON CLASSES AND FUNCTIONS")
    print("=" * 100)

    for path, text in files:
        if path.suffix.lower() != ".py":
            continue

        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        entries: list[tuple[int, str, str]] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                name = node.name
                kind = "CLASS"
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                kind = "FUNCTION"
            else:
                continue

            lowered = name.lower()
            if any(keyword in lowered for keyword in keywords):
                entries.append((node.lineno, kind, name))

        if not entries:
            continue

        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            relative = path

        print()
        print(relative)

        for line_number, kind, name in sorted(entries):
            print(f"  {line_number:5d} | {kind:8s} | {name}")


def inspect_ffmpeg_commands(files: list[tuple[Path, str]]) -> None:
    print()
    print("=" * 100)
    print("FILES CONTAINING FFMPEG OR SUBPROCESS")
    print("=" * 100)

    for path, text in files:
        lowered = text.lower()

        if "ffmpeg" not in lowered and "subprocess" not in lowered:
            continue

        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            relative = path

        lines = text.splitlines()
        interesting: list[tuple[int, str]] = []

        for line_number, line in enumerate(lines, start=1):
            line_lower = line.lower()

            if (
                "ffmpeg" in line_lower
                or "subprocess.run" in line_lower
                or "subprocess.popen" in line_lower
                or "anullsrc" in line_lower
                or "amix" in line_lower
                or "phase4_av_master" in line_lower
            ):
                interesting.append((line_number, line.strip()))

        if not interesting:
            continue

        print()
        print(relative)

        for line_number, line in interesting[:100]:
            print(f"  {line_number:5d} | {line}")


files: list[tuple[Path, str]] = []

for path in iter_files():
    text = read_text(path)
    if text is not None:
        files.append((path, text))

print("=" * 100)
print("ATLAS ZERO RC2 — TIMELINE AND SOURCE-AUDIO CODE AUDIT")
print("=" * 100)
print(f"root={ROOT}")
print(f"files_scanned={len(files)}")

print_matches(files)
inspect_python_structure(files)
inspect_ffmpeg_commands(files)

print()
print("=" * 100)
print("AUDIT COMPLETE")
print("=" * 100)
