from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from az_enterprise.core.finalization_runtime_rc2 import (
    FinalizationRuntimeRC2,
)


def _runtime(tmp_path: Path) -> FinalizationRuntimeRC2:
    runtime = object.__new__(FinalizationRuntimeRC2)
    runtime.config = SimpleNamespace(
        project_id="demo",
        rc2_dir=tmp_path,
        render_dir=tmp_path / "render",
        preview_render_path=tmp_path / "render" / "render_preview_rc2.mp4",
        canonical_render_path=tmp_path / "render" / "demo_RC2.mp4",
    )
    runtime.report_path = tmp_path / "render" / "finalization_report_rc2.json"
    runtime.lock_path = tmp_path / "finalization_runtime.lock"
    runtime.progress = lambda payload: None
    return runtime


def test_require_status_rejects_invalid_state(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with pytest.raises(RuntimeError, match="not allowed"):
        runtime._require_status("FAILED", {"PREVIEW_RENDERED"})


def test_atomic_copy_and_hash(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    source = tmp_path / "source.mp4"
    destination = tmp_path / "out" / "final.mp4"
    source.write_bytes(b"atlas-zero-rc2")

    runtime._copy_atomic(source, destination)

    assert destination.read_bytes() == source.read_bytes()
    assert runtime._sha256(destination) == runtime._sha256(source)
    assert not destination.with_suffix(".mp4.partial").exists()


def test_write_json_atomic(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    path = tmp_path / "report.json"

    runtime._write_json_atomic(path, {"state": "OK"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"state": "OK"}
    assert not path.with_suffix(".json.partial").exists()


def test_equivalent_media() -> None:
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "1110.000"},
    }

    assert FinalizationRuntimeRC2._equivalent_media(probe, probe)
