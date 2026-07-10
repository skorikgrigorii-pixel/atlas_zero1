from __future__ import annotations

import json
import shutil
from pathlib import Path

from az_enterprise.core.render_engine_rc1 import RenderEngineRC1


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00"
    b"\x03\x01\x01\x00\x18\xdd\x8d\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _prepare_workspace(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path
    timeline_dir = project_root / "workspace" / "exports" / "franklin" / "movie_runtime_rc1"
    timeline_dir.mkdir(parents=True, exist_ok=True)

    image_path = project_root / "workspace" / "projects" / "franklin" / "02_Images" / "frame.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(PNG_1X1)

    timeline = [
        {
            "shot_id": "shot_0001",
            "shot_index": 1,
            "duration_sec": 0.4,
            "status": "assigned",
            "asset_name": "frame.png",
            "asset_path": str(image_path),
            "media_type": "image",
        },
        {
            "shot_id": "shot_0002",
            "shot_index": 2,
            "duration_sec": 0.4,
            "status": "missing",
            "asset_name": "НУЖНО СОЗДАТЬ",
            "asset_path": "",
            "media_type": "missing",
        },
    ]

    timeline_path = timeline_dir / "timeline.json"
    timeline_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    return project_root, timeline_path


def test_render_engine_rc1_renders_or_reports_ffmpeg_missing(tmp_path: Path) -> None:
    project_root, timeline_path = _prepare_workspace(tmp_path)

    engine = RenderEngineRC1(project_id="franklin", root_dir=project_root)
    result = engine.run()

    out_dir = project_root / "workspace" / "exports" / "franklin" / "render_rc1"
    report_path = out_dir / "render_report.json"
    manifest_path = out_dir / "render_manifest.json"
    skipped_path = out_dir / "skipped_missing_assets.json"
    output_mp4 = out_dir / "franklin_render_rc1.mp4"

    assert timeline_path.exists()
    assert report_path.exists()
    assert manifest_path.exists()
    assert skipped_path.exists()

    skipped = json.loads(skipped_path.read_text(encoding="utf-8"))
    assert any(item.get("shot_id") == "shot_0002" for item in skipped)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["state"] in {"RENDERED", "FFMPEG_MISSING"}

    ffmpeg_available = bool(shutil.which("ffmpeg"))
    assert (output_mp4.exists() and result["state"] == "RENDERED") or (not ffmpeg_available)
