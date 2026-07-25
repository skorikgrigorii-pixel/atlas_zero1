from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .project_config_rc2 import ProjectConfigRC2


class VoiceProductionEngineRC2:
    """Create scene voice tracks and a canonical master narration."""

    def __init__(
        self,
        config: ProjectConfigRC2,
        *,
        voice_name: str = "Microsoft Irina Desktop",
        speech_rate: int = 0,
    ) -> None:
        self.config = config
        self.voice_name = voice_name
        self.speech_rate = max(
            -10,
            min(10, int(speech_rate)),
        )

    def run(self) -> dict[str, Any]:
        script_path = (
            self._discover_production_script()
        )

        production_script = self._read_json(
            script_path
        )

        scenes = list(
            production_script.get(
                "scenes",
                [],
            )
        )

        if not scenes:
            raise ValueError(
                "Production script contains no scenes"
            )

        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        powershell = (
            shutil.which("powershell")
            or shutil.which("pwsh")
        )

        if not ffmpeg:
            raise FileNotFoundError(
                "ffmpeg was not found"
            )

        if not ffprobe:
            raise FileNotFoundError(
                "ffprobe was not found"
            )

        if not powershell:
            raise FileNotFoundError(
                "PowerShell was not found"
            )

        audio_dir = (
            self.config.project_dir
            / "01_Audio"
        )

        scene_dir = (
            audio_dir
            / "scenes"
        )

        temp_dir = (
            audio_dir
            / "_voice_temp"
        )

        scene_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        scene_results = []

        for scene in scenes:
            scene_result = self._render_scene(
                scene=scene,
                powershell=powershell,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                scene_dir=scene_dir,
                temp_dir=temp_dir,
            )

            scene_results.append(
                scene_result
            )

        master_path = (
            audio_dir
            / "voice_master.wav"
        )

        concat_path = (
            temp_dir
            / "voice_concat.txt"
        )

        concat_path.write_text(
            "\n".join(
                (
                    "file '"
                    + str(
                        Path(row["output_path"])
                        .resolve()
                    ).replace(
                        "'",
                        "'\\''",
                    )
                    + "'"
                )
                for row in scene_results
            ),
            encoding="utf-8",
        )

        command = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(master_path),
        ]

        self._run_command(
            command,
            "Failed to concatenate voice master",
        )

        master_duration = self._probe_duration(
            ffprobe,
            master_path,
        )

        target_duration = float(
            production_script.get(
                "duration_sec",
                sum(
                    float(
                        scene.get(
                            "duration_sec",
                            0.0,
                        )
                    )
                    for scene in scenes
                ),
            )
        )

        report = {
            "state": "VOICE_READY",
            "project_id":
                self.config.project_id,
            "provider":
                "windows_system_speech",
            "voice_name":
                self.voice_name,
            "speech_rate":
                self.speech_rate,
            "scenes":
                len(scene_results),
            "target_duration_sec":
                round(target_duration, 3),
            "master_duration_sec":
                round(master_duration, 3),
            "duration_delta_sec":
                round(
                    master_duration
                    - target_duration,
                    3,
                ),
            "production_script_path":
                str(script_path),
            "master_audio_path":
                str(master_path),
            "scene_audio_dir":
                str(scene_dir),
            "scene_results":
                scene_results,
            "authority":
                "VoiceProductionEngineRC2",
        }

        report_path = (
            audio_dir
            / "voice_report.json"
        )

        manifest_path = (
            audio_dir
            / "voice_manifest.json"
        )

        report_path.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        manifest_path.write_text(
            json.dumps(
                {
                    "project_id":
                        self.config.project_id,
                    "master":
                        str(master_path),
                    "scenes":
                        scene_results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        report["report_path"] = str(
            report_path
        )
        report["manifest_path"] = str(
            manifest_path
        )

        return report

    def _render_scene(
        self,
        *,
        scene: dict[str, Any],
        powershell: str,
        ffmpeg: str,
        ffprobe: str,
        scene_dir: Path,
        temp_dir: Path,
    ) -> dict[str, Any]:
        scene_id = str(
            scene.get(
                "scene_id",
                "",
            )
        ).strip()

        if not scene_id:
            raise ValueError(
                "Scene ID is required"
            )

        voiceover = dict(
            scene.get(
                "voiceover",
                {},
            )
        )

        text = str(
            voiceover.get(
                "text",
                "",
            )
        ).strip()

        if not text:
            raise ValueError(
                f"Empty voice-over in {scene_id}"
            )

        target_duration = float(
            scene.get(
                "duration_sec",
                0.0,
            )
        )

        if target_duration <= 0:
            raise ValueError(
                f"Invalid duration in {scene_id}"
            )

        text_path = (
            temp_dir
            / f"{scene_id}.txt"
        )

        raw_path = (
            temp_dir
            / f"{scene_id}_raw.wav"
        )

        output_path = (
            scene_dir
            / f"{scene_id}.wav"
        )

        text_path.write_text(
            text,
            encoding="utf-8",
        )

        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object "
            "System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SelectVoice('{self.voice_name}'); "
            f"$s.Rate = {self.speech_rate}; "
            f"$text = Get-Content -Raw -Encoding UTF8 "
            f"'{str(text_path.resolve())}'; "
            f"$s.SetOutputToWaveFile("
            f"'{str(raw_path.resolve())}'); "
            "$s.Speak($text); "
            "$s.Dispose();"
        )

        self._run_command(
            [
                powershell,
                "-NoProfile",
                "-Command",
                ps_script,
            ],
            f"Speech synthesis failed for {scene_id}",
        )

        raw_duration = self._probe_duration(
            ffprobe,
            raw_path,
        )

        tempo_factor = 1.0

        if raw_duration > (
            target_duration + 0.25
        ):
            tempo_factor = (
                raw_duration
                / target_duration
            )

            if tempo_factor > 1.35:
                raise ValueError(
                    f"{scene_id} narration requires excessive "
                    f"tempo adjustment: {tempo_factor:.3f}x. "
                    f"Raw={raw_duration:.3f}s, "
                    f"target={target_duration:.3f}s"
                )

        audio_filter_parts = []

        if tempo_factor > 1.001:
            audio_filter_parts.append(
                f"atempo={tempo_factor:.6f}"
            )

        audio_filter_parts.extend([
            (
                "apad=pad_dur="
                f"{target_duration:.3f}"
            ),
            (
                "atrim=duration="
                f"{target_duration:.3f}"
            ),
        ])

        command = [
            ffmpeg,
            "-y",
            "-i",
            str(raw_path),
            "-af",
            ",".join(
                audio_filter_parts
            ),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]

        self._run_command(
            command,
            f"Audio padding failed for {scene_id}",
        )

        final_duration = self._probe_duration(
            ffprobe,
            output_path,
        )

        return {
            "scene_id": scene_id,
            "scene_title": scene.get(
                "title",
                scene_id,
            ),
            "target_duration_sec":
                round(target_duration, 3),
            "speech_duration_sec":
                round(raw_duration, 3),
            "tempo_factor":
                round(tempo_factor, 4),
            "tempo_adjusted":
                tempo_factor > 1.001,
            "final_duration_sec":
                round(final_duration, 3),
            "silence_duration_sec":
                round(
                    max(
                        0.0,
                        target_duration
                        - raw_duration,
                    ),
                    3,
                ),
            "output_path":
                str(output_path),
            "status": "ready",
        }

    def _discover_production_script(
        self,
    ) -> Path:
        candidates = [
            (
                self.config.project_dir
                / "script"
                / "production_script.json"
            ),
            (
                self.config.project_dir
                / "production_script.json"
            ),
            (
                self.config.export_dir
                / "production_script.json"
            ),
        ]

        for path in candidates:
            if (
                path.exists()
                and path.is_file()
            ):
                return path

        raise FileNotFoundError(
            "Production script JSON was not found"
        )

    @staticmethod
    def _read_json(
        path: Path,
    ) -> dict[str, Any]:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "Production script root "
                "must be an object"
            )

        return payload

    @staticmethod
    def _probe_duration(
        ffprobe: str,
        path: Path,
    ) -> float:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:"
                "nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        return float(
            result.stdout.strip()
            or 0.0
        )

    @staticmethod
    def _run_command(
        command: list[str],
        error_message: str,
    ) -> None:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            raise RuntimeError(
                error_message
                + "\n"
                + result.stderr[-2000:]
            )
