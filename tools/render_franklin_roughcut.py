from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path

from az_enterprise.core.render_engine_rc1 import RenderEngineRC1


ROOT = Path.cwd()

TIMELINE = (
    ROOT
    / "workspace"
    / "exports"
    / "franklin"
    / "movie_runtime_rc1"
    / "timeline.json"
)

MASTER_AUDIO = (
    ROOT
    / "workspace"
    / "projects"
    / "franklin"
    / "01_Audio"
    / "voice_master.m4a"
)

OUTPUT = (
    ROOT
    / "workspace"
    / "exports"
    / "franklin"
    / "render_rc1"
    / "franklin_render_rc1.mp4"
)

if not TIMELINE.exists():
    raise FileNotFoundError(f"Timeline not found: {TIMELINE}")

if not MASTER_AUDIO.exists():
    raise FileNotFoundError(
        f"Master audio not found: {MASTER_AUDIO}"
    )

timeline = json.loads(
    TIMELINE.read_text(encoding="utf-8")
)

assigned = sum(
    1
    for item in timeline
    if item.get("status") == "assigned"
    and item.get("asset_path")
)

missing = len(timeline) - assigned

print("=" * 72)
print("ATLAS ZERO — FRANKLIN REAL RENDER")
print("=" * 72)
print("TIMELINE TOTAL    =", len(timeline))
print("TIMELINE ASSIGNED =", assigned)
print("TIMELINE MISSING  =", missing)
print("MASTER AUDIO      =", MASTER_AUDIO)

if len(timeline) != 149:
    raise RuntimeError(
        f"Expected 149 timeline items, found {len(timeline)}."
    )

if missing:
    raise RuntimeError(
        f"Render stopped: {missing} shots are not ready."
    )

engine = RenderEngineRC1(project_id="franklin")

engine.temp_dir = (
    Path(tempfile.gettempdir())
    / f"atlas_zero_franklin_{uuid.uuid4().hex[:12]}"
)

print("TEMP DIR          =", engine.temp_dir)
print("OUTPUT            =", OUTPUT)
print()
print("Rendering 149 segments. Do not close PowerShell.")

report = engine.run()

print()
print("=" * 72)
print("RENDER REPORT")
print("=" * 72)
print(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    )
)
print("=" * 72)

if report.get("state") != "RENDERED":
    print()
    print(
        "Temporary files were preserved for diagnostics:",
        engine.temp_dir,
    )
    raise RuntimeError(
        report.get("error")
        or f"Unexpected render state: {report.get('state')}"
    )

print()
print("Render completed successfully.")
print("OUTPUT =", report.get("output_mp4"))
