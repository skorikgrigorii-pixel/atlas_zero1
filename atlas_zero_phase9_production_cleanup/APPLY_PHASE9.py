from __future__ import annotations

import ast
import json
import py_compile
import shutil
from datetime import datetime
from pathlib import Path


EXCLUDED_TOP_LEVEL_PREFIXES = (
    "atlas_zero_rc2_1_patch",
    "atlas_zero_rc2_2_patch",
    "atlas_zero_rc2_stage2_patch",
    "atlas_zero_phase8_rc2_control_layer",
    "atlas_zero_phase9_production_cleanup",
    "atlas_zero_rc2_final_audit",
    "audit_rc2_production",
    "workspace",
    ".git",
    ".pytest_cache",
)

ARCHIVE_TESTS = (
    "tests/test_movie_runtime_rc1.py",
    "tests/test_movie_runtime_rc1_assets.py",
    "tests/test_render_engine_rc1.py",
)


def find_repo_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


def backup_file(repo: Path, backup: Path, path: Path) -> None:
    if not path.exists():
        return
    destination = backup / path.relative_to(repo)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def replace_text(path: Path, replacements: dict[str, str]) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig")
    changed = []
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new)
            changed.append(old)
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def remove_utf8_bom(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    data = path.read_bytes()
    bom = b"\xef\xbb\xbf"
    if data.startswith(bom):
        path.write_bytes(data[len(bom):])
        return True
    return False


def patch_auditor(path: Path) -> bool:
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8-sig")
    marker = "# PHASE9_PRODUCTION_SCOPE"
    if marker in text:
        return False

    helper = r