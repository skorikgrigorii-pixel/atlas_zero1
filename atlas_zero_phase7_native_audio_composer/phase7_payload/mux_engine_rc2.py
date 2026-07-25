from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class MuxEngineRC2:
    def __init__(self, *, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            raise RuntimeError("ffmpeg and ffprobe must be available in PATH")
        self.output_movie = self.output_dir / "final_movie_rc2.mp4"
        self.report_path = self.output_dir / "mux_report_rc2.json"

    def run(self, *, visual_path: Path, audio_path: Path) -> dict[str, Any]:
        visual_path = Path(visual_path)
        audio_path = Path(audio_path)
        if not visual_path.exists():
            raise FileNotFoundError(f"Visual master is missing: {visual_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio master is missing: {audio_path}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.output_movie.with_suffix(".partial.mp4")
        temporary.unlink(missing_ok=True)

        process = subprocess.run(
            [
                self.ffmpeg, "-y", "-nostdin",
                "-i", str(visual_path),
                "-i", str(audio_path),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "320k",
                "-shortest",
                "-movflags", "+faststart",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            tail = "\n".join(process.stderr.splitlines()[-40:])
            raise RuntimeError(f"Native mux failed:\n{tail}")

        os.replace(temporary, self.output_movie)
        self._verify(self.output_movie)

        report = {
            "state": "FINAL_MOVIE_RENDERED",
            "schema": "atlas_zero.mux.rc2.v1",
            "migration_phase": "PHASE_7_NATIVE_AUDIO_COMPOSER",
            "visual_master": str(visual_path),
            "audio_master": str(audio_path),
            "output_movie": str(self.output_movie),
            "output_exists": self.output_movie.exists(),
            "output_size_bytes": self.output_movie.stat().st_size,
            "video_mode": "stream_copy",
            "audio_codec": "aac",
        }
        self.report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report

    def _verify(self, path: Path) -> None:
        process = subprocess.run(
            [
                self.ffprobe, "-v", "error",
                "-show_entries", "stream=codec_type",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip())
        payload = json.loads(process.stdout or "{}")
        kinds = {row.get("codec_type") for row in payload.get("streams", [])}
        if not {"video", "audio"}.issubset(kinds):
            raise RuntimeError(f"Final movie does not contain both video and audio: {path}")
