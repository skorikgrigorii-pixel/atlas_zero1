from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path.cwd()

TARGETS = {
    "src/az_enterprise/core/timeline_engine_rc2.py": [
        (120, 190),
        (560, 630),
    ],
    "src/az_enterprise/core/render_engine_rc2.py": [
        (40, 90),
        (470, 550),
        (650, 710),
        (970, 1090),
        (1330, 1390),
    ],
    "src/az_enterprise/core/audio_timeline_rc2.py": [
        (1, 1000),
    ],
    "src/az_enterprise/core/audio_renderer_rc2.py": [
        (1, 240),
    ],
}

print("=" * 100)
print("ATLAS ZERO RC2 — TARGETED SOURCE AUDIO EXTRACTION")
print("=" * 100)

for relative_path, ranges in TARGETS.items():
    path = ROOT / relative_path

    print()
    print("=" * 100)
    print(relative_path)
    print("=" * 100)

    if not path.exists():
        print("MISSING")
        continue

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    for start, end in ranges:
        actual_end = min(end, len(lines))

        print()
        print(f"--- LINES {start}-{actual_end} ---")

        if start > len(lines):
            print("RANGE OUTSIDE FILE")
            continue

        for number in range(start, actual_end + 1):
            print(f"{number:05d}: {lines[number - 1]}")

print()
print("=" * 100)
print("EXTRACTION COMPLETE")
print("=" * 100)
