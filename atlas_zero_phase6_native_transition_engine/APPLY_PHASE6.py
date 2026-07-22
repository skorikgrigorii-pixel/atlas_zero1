from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PAYLOAD = SCRIPT_DIR / "phase6_payload"


def find_repo_root() -> Path:
    candidates = [Path.cwd(), SCRIPT_DIR, SCRIPT_DIR.parent]
    candidates.extend(Path.cwd().parents)
    candidates.extend(SCRIPT_DIR.parents)
    seen: set[Path] = set()

    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        core = candidate / "src" / "az_enterprise" / "core"
        if core.is_dir():
            return candidate

    raise FileNotFoundError(
        "ATLAS ZERO repository root was not found. "
        "Run this installer from the repository or keep the extracted folder inside it."
    )


def patch_render_engine(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "PHASE_5_NATIVE_CAMERA_MOTION",
        "PHASE_6_NATIVE_TRANSITION_ENGINE",
    )

    # Extend strict transition vocabulary only when a recognizable set exists.
    marker = '            "crossfade",\n'
    additions = (
        '            "dissolve",\n'
        '            "fade_black",\n'
        '            "fade_white",\n'
        '            "dip_to_black",\n'
        '            "dip_to_white",\n'
        '            "wipe_left",\n'
        '            "wipe_right",\n'
        '            "wipe_up",\n'
        '            "wipe_down",\n'
        '            "slide_left",\n'
        '            "slide_right",\n'
        '            "slide_up",\n'
        '            "slide_down",\n'
        '            "push_left",\n'
        '            "push_right",\n'
        '            "push_up",\n'
        '            "push_down",\n'
        '            "circle_open",\n'
        '            "circle_close",\n'
        '            "pixelize",\n'
        '            "radial",\n'
        '            "smooth_left",\n'
        '            "smooth_right",\n'
        '            "smooth_up",\n'
        '            "smooth_down",\n'
        '            "zoom_in",\n'
        '            "zoom_out",\n'
        '            "custom",\n'
    )
    if marker in text and '"dip_to_black"' not in text:
        text = text.replace(marker, marker + additions, 1)

    path.write_text(text, encoding="utf-8")


def main() -> None:
    root = find_repo_root()
    core = root / "src" / "az_enterprise" / "core"

    required = [
        core / "camera_motion_rc2.py",
        core / "visual_renderer_rc2.py",
        core / "render_engine_rc2.py",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Phase 5 files are missing:\n- " + "\n- ".join(missing)
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "workspace" / "backups" / f"phase6_transition_engine_{timestamp}"
    backup.mkdir(parents=True, exist_ok=True)

    targets = [
        core / "transition_engine_rc2.py",
        core / "visual_renderer_rc2.py",
        core / "render_engine_rc2.py",
    ]
    for target in targets:
        if target.exists():
            shutil.copy2(target, backup / target.name)

    shutil.copy2(PAYLOAD / "transition_engine_rc2.py", core / "transition_engine_rc2.py")
    shutil.copy2(PAYLOAD / "visual_renderer_rc2.py", core / "visual_renderer_rc2.py")
    patch_render_engine(core / "render_engine_rc2.py")

    compiled = [
        core / "camera_motion_rc2.py",
        core / "transition_engine_rc2.py",
        core / "visual_renderer_rc2.py",
        core / "render_engine_rc2.py",
    ]
    for path in compiled:
        py_compile.compile(str(path), doraise=True)

    print("PHASE 6 INSTALLED")
    print(f"Repository: {root}")
    print(f"Backup: {backup}")
    for path in compiled:
        print(f"Compiled: {path}")


if __name__ == "__main__":
    main()
