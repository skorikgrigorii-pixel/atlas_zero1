from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PAYLOAD = SCRIPT_DIR / "phase7_payload"


def find_repo_root() -> Path:
    candidates = [Path.cwd(), SCRIPT_DIR, SCRIPT_DIR.parent]
    candidates.extend(Path.cwd().parents)
    candidates.extend(SCRIPT_DIR.parents)
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


def patch_render_engine(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "PHASE_6_NATIVE_TRANSITION_ENGINE",
        "PHASE_7_NATIVE_AUDIO_COMPOSER",
    )

    import_line = "from .audio_composer_rc2 import NativeAudioComposerRC2\n"
    if import_line not in text:
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from .") or line.startswith("import "):
                insert_at = i + 1
        lines.insert(insert_at, import_line.rstrip())
        text = "\n".join(lines) + "\n"

    path.write_text(text, encoding="utf-8")


def main() -> None:
    root = find_repo_root()
    core = root / "src" / "az_enterprise" / "core"

    required = [
        core / "camera_motion_rc2.py",
        core / "transition_engine_rc2.py",
        core / "visual_renderer_rc2.py",
        core / "render_engine_rc2.py",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Required Phase 6 files are missing:\n- " + "\n- ".join(missing))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "workspace" / "backups" / f"phase7_native_audio_{timestamp}"
    backup.mkdir(parents=True, exist_ok=True)

    payload_files = [
        "audio_timeline_rc2.py",
        "ducking_engine_rc2.py",
        "loudness_engine_rc2.py",
        "audio_renderer_rc2.py",
        "mux_engine_rc2.py",
        "audio_composer_rc2.py",
    ]
    targets = [core / name for name in payload_files] + [core / "render_engine_rc2.py"]

    for target in targets:
        if target.exists():
            shutil.copy2(target, backup / target.name)

    for name in payload_files:
        shutil.copy2(PAYLOAD / name, core / name)

    patch_render_engine(core / "render_engine_rc2.py")

    compiled = [core / name for name in payload_files] + [core / "render_engine_rc2.py"]
    for path in compiled:
        py_compile.compile(str(path), doraise=True)

    print("PHASE 7 INSTALLED")
    print(f"Repository: {root}")
    print(f"Backup: {backup}")
    for path in compiled:
        print(f"Compiled: {path}")


if __name__ == "__main__":
    main()
