from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


TARGET = Path("src/az_enterprise/core/timeline_engine_rc2.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly 1 matching block, found {count}"
        )
    return text.replace(old, new, 1)


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(
            f"Target file not found: {TARGET.resolve()}"
        )

    original = TARGET.read_text(encoding="utf-8")

    required_markers = (
        "class TimelineEngineRC2:",
        "def _load_rows(self)",
        '"media_type": row["media_type"],',
        '"natural_sound_window",',
        "def run(self)",
    )

    missing = [marker for marker in required_markers if marker not in original]
    if missing:
        raise RuntimeError(
            "Unexpected timeline_engine_rc2.py structure. "
            f"Missing markers: {missing}"
        )

    already_patched = (
        '"natural_sound_enabled": natural_sound_enabled' in original
        and '"natural_sound_windows": natural_sound_windows' in original
        and '"source_mode": "canonical_database"' in original
    )

    if already_patched:
        compile(original, str(TARGET), "exec")
        print("status=ALREADY_PATCHED")
        print("syntax=OK")
        print(f"target={TARGET}")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(
        f"{TARGET.name}.backup_before_canonical_natural_sound_{timestamp}"
    )
    shutil.copy2(TARGET, backup)

    patched = original

    old_before_append = '''        for row in rows:
            start_sec = float(row["start_sec"] or 0.0)
            end_sec = float(row["end_sec"] or start_sec)

            timeline_rows.append(
'''

    new_before_append = '''        for row in rows:
            start_sec = float(row["start_sec"] or 0.0)
            end_sec = float(row["end_sec"] or start_sec)
            duration_sec = round(
                max(0.0, end_sec - start_sec),
                3,
            )

            media_type = str(
                row["media_type"] or ""
            ).strip().lower()

            asset_path = str(
                row["asset_path"] or ""
            ).strip()

            status = str(
                row["status"] or ""
            ).strip().lower()

            natural_sound_enabled = bool(
                media_type == "video"
                and asset_path
                and status == "assigned"
                and duration_sec > 0.0
            )

            natural_sound_windows = (
                [[0.0, duration_sec]]
                if natural_sound_enabled
                else []
            )

            timeline_rows.append(
'''

    patched = replace_once(
        patched,
        old_before_append,
        new_before_append,
        "insert canonical natural-sound calculation",
    )

    old_duration = '''                    "duration_sec": round(
                        max(0.0, end_sec - start_sec),
                        3,
                    ),
'''

    new_duration = '''                    "duration_sec": duration_sec,
'''

    patched = replace_once(
        patched,
        old_duration,
        new_duration,
        "reuse canonical duration",
    )

    old_fields = '''                    "asset_path": row["asset_path"],
                    "media_type": row["media_type"],
                }
'''

    new_fields = '''                    "asset_path": row["asset_path"],
                    "media_type": row["media_type"],
                    "natural_sound_enabled": natural_sound_enabled,
                    "natural_sound_window": natural_sound_enabled,
                    "natural_sound_windows": natural_sound_windows,
                    "natural_sound_reason": (
                        "embedded_source_audio_candidate"
                        if natural_sound_enabled
                        else ""
                    ),
                    "natural_sound_priority": (
                        50
                        if natural_sound_enabled
                        else 0
                    ),
                    "source_mode": "canonical_database",
                }
'''

    patched = replace_once(
        patched,
        old_fields,
        new_fields,
        "export canonical natural-sound metadata",
    )

    old_csv_header = '''                    "natural_sound_window",
                    "source_mode",
'''

    new_csv_header = '''                    "natural_sound_window",
                    "natural_sound_enabled",
                    "natural_sound_windows",
                    "natural_sound_reason",
                    "natural_sound_priority",
                    "source_mode",
'''

    patched = replace_once(
        patched,
        old_csv_header,
        new_csv_header,
        "extend CSV headers",
    )

    old_csv_values = '''                        row.get("natural_sound_window"),
                        row.get("source_mode"),
'''

    new_csv_values = '''                        row.get("natural_sound_window"),
                        row.get("natural_sound_enabled"),
                        json.dumps(
                            row.get("natural_sound_windows", []),
                            ensure_ascii=False,
                        ),
                        row.get("natural_sound_reason"),
                        row.get("natural_sound_priority"),
                        row.get("source_mode"),
'''

    patched = replace_once(
        patched,
        old_csv_values,
        new_csv_values,
        "extend CSV values",
    )

    try:
        compile(patched, str(TARGET), "exec")
    except Exception:
        shutil.copy2(backup, TARGET)
        raise

    TARGET.write_text(patched, encoding="utf-8")

    verification = TARGET.read_text(encoding="utf-8")
    compile(verification, str(TARGET), "exec")

    required_after = (
        '"natural_sound_enabled": natural_sound_enabled',
        '"natural_sound_windows": natural_sound_windows',
        '"natural_sound_reason": (',
        '"source_mode": "canonical_database"',
    )

    missing_after = [marker for marker in required_after if marker not in verification]
    if missing_after:
        shutil.copy2(backup, TARGET)
        raise RuntimeError(
            f"Post-patch verification failed: {missing_after}"
        )

    print("status=PATCH_APPLIED")
    print("syntax=OK")
    print("timeline_authority=canonical_database")
    print("video_candidates=ALL_ASSIGNED_VIDEO_SHOTS")
    print("window_mode=FULL_TIMELINE_CLIP")
    print("physical_audio_probe=RENDER_ENGINE")
    print(f"target={TARGET}")
    print(f"backup={backup}")


if __name__ == "__main__":
    main()
