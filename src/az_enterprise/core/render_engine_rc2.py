from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from .project_config_rc2 import ProjectConfigRC2
from .render_engine_rc1 import RenderEngineRC1


ProgressCallback = Callable[[dict[str, Any]], None]


class RenderEngineRC2:
    """Atomic render wrapper with mandatory ffprobe verification."""

    def __init__(
        self,
        config: ProjectConfigRC2,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.progress = progress or (lambda payload: None)
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffprobe:
            raise RuntimeError("ffprobe is not available in PATH")

    def _emit(self, stage: str, **details: Any) -> None:
        self.progress({"stage": stage, **details})

    def probe(self, path: Path) -> dict[str, Any]:
        proc = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,size,format_name",
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,r_frame_rate",
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "ffprobe failed")
        payload = json.loads(proc.stdout)
        streams = payload.get("streams", [])
        if not any(row.get("codec_type") == "video" for row in streams):
            raise RuntimeError("Rendered artifact has no video stream")
        if not any(row.get("codec_type") == "audio" for row in streams):
            raise RuntimeError("Rendered artifact has no audio stream")
        return payload

    def run(self) -> dict[str, Any]:
        self._emit("RENDER_START")
        legacy = RenderEngineRC1(project_id=self.config.project_id)
        report = legacy.run()
        if report.get("state") != "RENDERED":
            raise RuntimeError(str(report.get("error") or report))

        source = Path(str(report.get("output_mp4") or ""))
        if not source.exists() and self.config.project_id == "franklin":
            source = self.config.franklin_legacy_render_path
        if not source.exists():
            raise FileNotFoundError(f"Legacy renderer output missing: {source}")

        self._emit("VERIFY_SOURCE", path=str(source))
        source_probe = self.probe(source)

        destination = self.config.canonical_render_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".partial")
        partial.unlink(missing_ok=True)
        shutil.copy2(source, partial)
        self._emit("VERIFY_COPY", path=str(partial))
        final_probe = self.probe(partial)
        os.replace(partial, destination)
        self._emit("RENDER_COMPLETE", path=str(destination))

        return {
            "state": "RENDERED_VERIFIED",
            "output": str(destination),
            "source": str(source),
            "source_probe": source_probe,
            "media_probe": final_probe,
            "legacy_report": report,
        }
