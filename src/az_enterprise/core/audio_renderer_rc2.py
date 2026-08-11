from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .audio_timeline_rc2 import AudioEventRC2, AudioTimelineValidatorRC2
from .ducking_engine_rc2 import DuckingEngineRC2, DuckingProfileRC2
from .loudness_engine_rc2 import LoudnessEngineRC2, LoudnessProfileRC2


class AudioRendererRC2:
    """Native FFmpeg audio compositor for voice, music, and SFX."""

    def __init__(
        self,
        *,
        project_id: str,
        output_dir: Path,
        sample_rate: int = 48000,
        channels: int = 2,
        ducking_profile: DuckingProfileRC2 | None = None,
        loudness_profile: LoudnessProfileRC2 | None = None,
    ) -> None:
        self.project_id = project_id
        self.output_dir = Path(output_dir)
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.ducking_profile = ducking_profile or DuckingProfileRC2()
        self.loudness_profile = loudness_profile or LoudnessProfileRC2()
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            raise RuntimeError("ffmpeg and ffprobe must be available in PATH")
        self.audio_master = self.output_dir / "audio_master_rc2.m4a"
        self.report_path = self.output_dir / "audio_report_rc2.json"

    def run(
        self,
        events: Iterable[AudioEventRC2],
        *,
        target_duration_sec: float,
        video_timeline_hash: str | None = None,
        rebind_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        events = AudioTimelineValidatorRC2.validate(events)
        if target_duration_sec <= 0:
            raise ValueError("Target duration must be positive")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        command, filter_graph, final_label = self._build_command(
            events,
            target_duration_sec=target_duration_sec,
        )
        self._run(command)
        self._verify(self.audio_master)

        report = {
            "state": "AUDIO_RENDERED",
            "schema": "atlas_zero.audio_render.rc2.v2",
            "migration_phase": "PHASE_7_NATIVE_AUDIO_COMPOSER",
            "project_id": self.project_id,
            "output_audio": str(self.audio_master),
            "output_exists": self.audio_master.exists(),
            "output_size_bytes": self.audio_master.stat().st_size,
            "target_duration_sec": target_duration_sec,
            "video_timeline_hash": video_timeline_hash,
            "audio_map_built_for_timeline_hash": video_timeline_hash,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "events_total": len(events),
            "voice_events": sum(1 for e in events if e.kind == "voice"),
            "music_events": sum(1 for e in events if e.kind == "music"),
            "sfx_events": sum(1 for e in events if e.kind == "sfx"),
            "synchronized_events": sum(
                1 for e in events if e.preserve_sync
            ),
            "rebound_events": sum(
                1 for e in events if e.rebind_status == "rebound"
            ),
            "unresolved_events": sum(
                1
                for e in events
                if e.preserve_sync
                and e.rebind_status not in {"rebound", "already_current"}
            ),
            "rebind_report": rebind_report or {},
            "ducking": self.ducking_profile.to_dict(),
            "loudness": self.loudness_profile.to_dict(),
            "final_filter_label": final_label,
            "filter_graph": filter_graph,
            "events": [e.to_dict() for e in events],
        }
        self._write_json(self.report_path, report)
        return report

    def _build_command(
        self,
        events: list[AudioEventRC2],
        *,
        target_duration_sec: float,
    ) -> tuple[list[str], str, str]:
        command = [self.ffmpeg, "-y", "-nostdin"]
        filters: list[str] = []

        if not events:
            command.extend([
                "-f", "lavfi",
                "-t", f"{target_duration_sec:.6f}",
                "-i", f"anullsrc=r={self.sample_rate}:cl=stereo",
            ])
            filters.append("[0:a]anull[a_silence]")
            input_labels = {"voice": [], "music": [], "sfx": ["[a_silence]"]}
        else:
            input_labels = {"voice": [], "music": [], "sfx": []}
            for idx, event in enumerate(events):
                if event.loop:
                    command.extend(["-stream_loop", "-1"])
                command.extend(["-i", event.asset_path])

                delay_ms = int(round(event.start_sec * 1000))
                trim_end = max(0.0, event.duration_sec)
                chain = (
                    f"[{idx}:a]"
                    f"atrim=0:{trim_end:.6f},"
                    f"asetpts=PTS-STARTPTS,"
                    f"aresample={self.sample_rate},"
                    f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"volume={event.gain_db}dB"
                )
                if event.fade_in_sec > 0:
                    chain += (
                        f",afade=t=in:st=0:d={event.fade_in_sec:.6f}"
                    )
                if event.fade_out_sec > 0:
                    fade_start = max(
                        0.0,
                        event.duration_sec - event.fade_out_sec,
                    )
                    chain += (
                        f",afade=t=out:st={fade_start:.6f}:"
                        f"d={event.fade_out_sec:.6f}"
                    )
                chain += f",adelay={delay_ms}|{delay_ms}[a{idx}]"
                filters.append(chain)
                input_labels[event.kind].append(f"[a{idx}]")

        mixed: dict[str, str | None] = {}
        for kind in ("voice", "music", "sfx"):
            labels = input_labels[kind]
            if not labels:
                mixed[kind] = None
            elif len(labels) == 1:
                mixed[kind] = labels[0]
            else:
                out = f"[mix_{kind}]"
                filters.append(
                    "".join(labels)
                    + f"amix=inputs={len(labels)}:"
                    + "duration=longest:dropout_transition=0"
                    + out
                )
                mixed[kind] = out

        voice = mixed["voice"]
        music = mixed["music"]
        sfx = mixed["sfx"]

        if music and voice:
            filters.append(
                DuckingEngineRC2.build_filter(
                    music_label=music,
                    voice_label=voice,
                    output_label="[music_ducked]",
                    profile=self.ducking_profile,
                )
            )
            music = "[music_ducked]"

        mix_labels = [label for label in (voice, music, sfx) if label]
        if not mix_labels:
            raise RuntimeError("No audio source was created")
        if len(mix_labels) == 1:
            filters.append(f"{mix_labels[0]}anull[mix_all]")
        else:
            filters.append(
                "".join(mix_labels)
                + f"amix=inputs={len(mix_labels)}:"
                + "duration=longest:dropout_transition=0[mix_all]"
            )

        filters.append(
            f"[mix_all]atrim=0:{target_duration_sec:.6f},"
            f"apad=pad_dur={target_duration_sec:.6f}[mix_padded]"
        )
        filters.append(
            LoudnessEngineRC2.build_filter(
                "[mix_padded]",
                "[audio_final]",
                self.loudness_profile,
            )
        )

        filter_graph = ";".join(filters)
        command.extend([
            "-filter_complex", filter_graph,
            "-map", "[audio_final]",
            "-t", f"{target_duration_sec:.6f}",
            "-c:a", "aac",
            "-b:a", "320k",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            str(self.audio_master),
        ])
        return command, filter_graph, "[audio_final]"

    def _run(self, command: list[str]) -> None:
        process = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            tail = "\n".join(process.stderr.splitlines()[-40:])
            raise RuntimeError(f"Native audio render failed:\n{tail}")

    def _verify(self, path: Path) -> None:
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Invalid audio output: {path}")
        process = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,size",
                "-show_entries",
                "stream=codec_type,sample_rate,channels",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip())
        payload = json.loads(process.stdout or "{}")
        if not any(
            stream.get("codec_type") == "audio"
            for stream in payload.get("streams", [])
        ):
            raise RuntimeError(f"No audio stream: {path}")

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
