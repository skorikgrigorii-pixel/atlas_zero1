from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .elevenlabs_voice_provider_rc2 import (
    ElevenLabsVoiceProviderRC2,
    ElevenLabsVoiceSettingsRC2,
)
from .project_config_rc2 import ProjectConfigRC2


class VoiceProductionEngineRC2:
    """Create ElevenLabs scene tracks and canonical master narration."""

    def __init__(
        self,
        config: ProjectConfigRC2,
        *,
        voice_name: str = "Microsoft Irina Desktop",
        speech_rate: int = 0,
        voice_id: str | None = None,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "mp3_44100_128",
        language_code: str | None = None,
        stability: float = 0.50,
        similarity_boost: float = 0.75,
        style: float = 0.15,
        use_speaker_boost: bool = True,
        maximum_tempo_factor: float = 1.15,
        scene_id: str | None = None,
    ) -> None:
        self.config = config

        # Retained for backward compatibility with the former Windows
        # speech constructor and its existing tests. ElevenLabs does not
        # use either value.
        self.voice_name = str(voice_name)
        self.speech_rate = max(
            -10,
            min(10, int(speech_rate)),
        )

        self.voice_id = voice_id
        self.model_id = str(model_id).strip()
        self.output_format = str(
            output_format
        ).strip()
        self.language_code = (
            str(language_code).strip()
            if language_code
            else None
        )
        self.voice_settings = (
            ElevenLabsVoiceSettingsRC2(
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                use_speaker_boost=
                    use_speaker_boost,
            )
        )
        self.maximum_tempo_factor = max(
            1.0,
            float(maximum_tempo_factor),
        )
        self.scene_id = (
            str(scene_id).strip()
            if scene_id
            else None
        )

        self.runtime_timeline_path = (
            self.config.export_dir
            / "rc2"
            / "runtime_timeline_rc2.json"
        )
        self.runtime_timeline: dict[str, Any] | None = None
        self.runtime_scene_durations: dict[str, float] = {}

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

        self.runtime_timeline = self._load_runtime_timeline()
        self.runtime_scene_durations = (
            self._build_runtime_scene_durations(
                scenes,
                self.runtime_timeline,
            )
        )

        selected_scenes = scenes
        selected_scene_indexes = list(
            range(1, len(scenes) + 1)
        )

        if self.scene_id:
            matches = [
                (index, scene)
                for index, scene in enumerate(
                    scenes,
                    start=1,
                )
                if str(
                    scene.get("scene_id", "")
                ).strip() == self.scene_id
            ]

            if not matches:
                available = ", ".join(
                    str(scene.get("scene_id", ""))
                    for scene in scenes
                )
                raise ValueError(
                    f"Scene '{self.scene_id}' was not found. "
                    f"Available scenes: {available}"
                )

            selected_scene_indexes = [
                matches[0][0]
            ]
            selected_scenes = [
                matches[0][1]
            ]

        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")

        if not ffmpeg:
            raise FileNotFoundError(
                "ffmpeg was not found"
            )

        if not ffprobe:
            raise FileNotFoundError(
                "ffprobe was not found"
            )

        provider = ElevenLabsVoiceProviderRC2(
            voice_id=self.voice_id,
            model_id=self.model_id,
            output_format=self.output_format,
            voice_settings=self.voice_settings,
        )

        audio_dir = (
            self.config.project_dir
            / "01_Audio"
        )
        block_dir = (
            audio_dir
            / "voice_blocks"
        )
        scene_dir = (
            audio_dir
            / "scenes"
        )
        temp_dir = (
            audio_dir
            / "_voice_temp"
        )

        for path in (
            audio_dir,
            block_dir,
            scene_dir,
            temp_dir,
        ):
            path.mkdir(
                parents=True,
                exist_ok=True,
            )

        scene_results: list[
            dict[str, Any]
        ] = []

        narration_texts = [
            (
                ""
                if (
                    str(
                        dict(
                            scene.get(
                                "voiceover",
                                {},
                            )
                        ).get(
                            "mode",
                            "",
                        )
                    ).strip().lower()
                    == "silence"
                )
                else self._scene_text(scene)
            )
            for scene in scenes
        ]

        for original_index, scene in zip(
            selected_scene_indexes,
            selected_scenes,
        ):
            previous_text = (
                narration_texts[original_index - 2]
                if original_index > 1
                else None
            )
            next_text = (
                narration_texts[original_index]
                if original_index < len(scenes)
                else None
            )

            scene_result = self._render_scene(
                scene=scene,
                scene_index=original_index,
                target_duration_override=(
                    self.runtime_scene_durations.get(
                        str(scene.get("scene_id", "")).strip()
                    )
                ),
                provider=provider,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                block_dir=block_dir,
                scene_dir=scene_dir,
                previous_text=previous_text,
                next_text=next_text,
            )
            scene_results.append(
                scene_result
            )

        single_scene_mode = (
            self.scene_id is not None
        )

        if single_scene_mode:
            master_path = Path(
                scene_results[0]["output_path"]
            )
            master_duration = (
                self._probe_duration(
                    ffprobe,
                    master_path,
                )
            )
            selected_scene_id = str(
                selected_scenes[0].get("scene_id", "")
            ).strip()
            target_duration = float(
                self.runtime_scene_durations.get(
                    selected_scene_id,
                    selected_scenes[0].get(
                        "duration_sec",
                        0.0,
                    ),
                )
            )
        else:
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
                    self._concat_entry(
                        Path(row["output_path"])
                    )
                    for row in scene_results
                ),
                encoding="utf-8",
            )

            self._run_command(
                [
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
                ],
                "Failed to concatenate voice master",
            )

            master_duration = (
                self._probe_duration(
                    ffprobe,
                    master_path,
                )
            )
            if self.runtime_timeline:
                target_duration = float(
                    self.runtime_timeline.get(
                        "available_narration_duration_sec",
                        master_duration,
                    )
                )
            else:
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
            "state": (
                "VOICE_SCENE_READY"
                if single_scene_mode
                else "VOICE_READY"
            ),
            "project_id":
                self.config.project_id,
            "provider": "elevenlabs",
            "voice_id": provider.voice_id,
            "model_id": provider.model_id,
            "output_format":
                provider.output_format,
            "language_code":
                self.language_code,
            "scenes": len(scene_results),
            "selected_scene_id": self.scene_id,
            "single_scene_mode": single_scene_mode,
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
            "runtime_timeline_path": (
                str(self.runtime_timeline_path)
                if self.runtime_timeline
                else None
            ),
            "timing_authority": (
                "runtime_timeline_rc2"
                if self.runtime_timeline
                else "production_script"
            ),
            "runtime_film_duration_sec": (
                round(float(self.runtime_timeline.get(
                    "film_duration_sec", 0.0
                )), 3)
                if self.runtime_timeline
                else None
            ),
            "runtime_available_narration_duration_sec": (
                round(float(self.runtime_timeline.get(
                    "available_narration_duration_sec", 0.0
                )), 3)
                if self.runtime_timeline
                else None
            ),
            "master_audio_path":
                str(master_path),
            "voice_block_dir":
                str(block_dir),
            "scene_audio_dir":
                str(scene_dir),
            "scene_results":
                scene_results,
            "authority":
                "VoiceProductionEngineRC2",
        }

        if single_scene_mode:
            safe_scene_id = self.scene_id or "scene"
            report_path = (
                audio_dir
                / f"voice_report_{safe_scene_id}.json"
            )
            manifest_path = (
                audio_dir
                / f"voice_manifest_{safe_scene_id}.json"
            )
        else:
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
            encoding="utf-8-sig",
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "project_id":
                        self.config.project_id,
                    "provider":
                        "elevenlabs",
                    "voice_id":
                        provider.voice_id,
                    "model_id":
                        provider.model_id,
                    "master":
                        str(master_path),
                    "voice_blocks": [
                        row["source_audio_path"]
                        for row in scene_results
                    ],
                    "scenes":
                        scene_results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8-sig",
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
        scene_index: int,
        target_duration_override: float | None,
        provider: ElevenLabsVoiceProviderRC2,
        ffmpeg: str,
        ffprobe: str,
        block_dir: Path,
        scene_dir: Path,
        previous_text: str | None,
        next_text: str | None,
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
        is_silence = (
            str(
                voiceover.get(
                    "mode",
                    "",
                )
            ).strip().lower()
            == "silence"
        )

        if not text and not is_silence:
            raise ValueError(
                f"Empty voice-over in {scene_id}"
            )

        target_duration = float(
            target_duration_override
            if target_duration_override is not None
            else scene.get(
                "duration_sec",
                0.0,
            )
        )

        if target_duration <= 0:
            raise ValueError(
                f"Invalid duration in {scene_id}"
            )

        block_path = (
            block_dir
            / f"voice_block_{scene_index:02d}.mp3"
        )
        output_path = (
            scene_dir
            / f"{scene_id}.wav"
        )

        if is_silence:
            self._run_command(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    (
                        "anullsrc="
                        "channel_layout=stereo:"
                        "sample_rate=48000"
                    ),
                    "-t",
                    f"{target_duration:.3f}",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_s16le",
                    str(output_path),
                ],
                (
                    "Failed to create silence "
                    f"for {scene_id}"
                ),
            )

            final_duration = self._probe_duration(
                ffprobe,
                output_path,
            )

            return {
                "scene_id": scene_id,
                "scene_index": scene_index,
                "scene_title": scene.get(
                    "title",
                    scene_id,
                ),
                "provider": "silence",
                "voice_id": None,
                "model_id": None,
                "characters": 0,
                "target_duration_sec":
                    round(target_duration, 3),
                "speech_duration_sec": 0.0,
                "tempo_factor": 1.0,
                "tempo_adjusted": False,
                "final_duration_sec":
                    round(final_duration, 3),
                "silence_duration_sec":
                    round(target_duration, 3),
                "source_audio_path": None,
                "output_path": str(output_path),
                "status": "ready",
            }

        # ---------------------------------------------------------
        # RESUME / PAID-CALL PROTECTION
        #
        # A valid existing provider block is canonical reusable
        # production material. Never regenerate it automatically.
        # ---------------------------------------------------------

        existing_block = (
            block_path.is_file()
            and block_path.stat().st_size > 1000
        )

        if existing_block:

            provider_result = {
                "provider":
                    "elevenlabs",

                "voice_id":
                    provider.voice_id,

                "model_id":
                    provider.model_id,

                "output_format":
                    provider.output_format,

                "characters":
                    len(text),

                "bytes":
                    block_path.stat().st_size,

                "output_path":
                    str(block_path),

                "attempt":
                    0,

                "status":
                    "reused_existing",
            }

        else:

            provider_result = provider.synthesize(
                text=text,
                output_path=block_path,
                language_code=
                    self.language_code,
                previous_text=previous_text,
                next_text=next_text,
            )

        raw_duration = self._probe_duration(
            ffprobe,
            block_path,
        )
        tempo_factor = 1.0

        if raw_duration > (
            target_duration + 0.25
        ):
            tempo_factor = (
                raw_duration
                / target_duration
            )

            if (
                tempo_factor
                > self.maximum_tempo_factor
            ):
                raise ValueError(
                    f"{scene_id} ElevenLabs narration "
                    "does not fit the approved scene: "
                    f"{tempo_factor:.3f}x adjustment "
                    "would be required. "
                    f"Speech={raw_duration:.3f}s, "
                    f"target={target_duration:.3f}s. "
                    "Revise the narrator text or scene "
                    "duration; production voice will "
                    "not be excessively accelerated."
                )

        audio_filters: list[str] = []

        if tempo_factor > 1.001:
            audio_filters.append(
                f"atempo={tempo_factor:.6f}"
            )

        # Keep the provider's natural ending intact.
        # Do not pad narration to the scene duration and
        # do not trim quiet final phonemes.

        preparation_command = [
            ffmpeg,
            "-y",
            "-i",
            str(block_path),
        ]

        if audio_filters:
            preparation_command.extend([
                "-af",
                ",".join(audio_filters),
            ])

        preparation_command.extend([
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ])

        self._run_command(
            preparation_command,
            (
                "ElevenLabs audio preparation failed "
                f"for {scene_id}"
            ),
        )

        final_duration = self._probe_duration(
            ffprobe,
            output_path,
        )

        return {
            "scene_id": scene_id,
            "scene_index": scene_index,
            "scene_title": scene.get(
                "title",
                scene_id,
            ),
            "provider": "elevenlabs",
            "voice_id": provider.voice_id,
            "model_id": provider.model_id,
            "characters":
                provider_result["characters"],
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
                        final_duration
                        - raw_duration,
                    ),
                    3,
                ),
            "source_audio_path":
                str(block_path),
            "output_path":
                str(output_path),
            "status": "ready",
        }

    @staticmethod
    def _scene_text(
        scene: dict[str, Any],
    ) -> str:
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

        scene_id = str(
            scene.get(
                "scene_id",
                "UNKNOWN",
            )
        )

        if not text:
            raise ValueError(
                f"Empty voice-over in {scene_id}"
            )

        return text

    @staticmethod
    def _concat_entry(
        path: Path,
    ) -> str:
        escaped = str(
            path.resolve()
        ).replace(
            "'",
            "'\\''",
        )
        return f"file '{escaped}'"

    def _load_runtime_timeline(
        self,
    ) -> dict[str, Any] | None:
        path = self.runtime_timeline_path
        if not path.exists() or not path.is_file():
            return None

        payload = self._read_json(path)

        if str(payload.get("state") or "").strip() != "RUNTIME_TIMELINE_READY":
            raise ValueError(
                "runtime_timeline_rc2.json is present but is not ready"
            )

        film_duration = float(payload.get("film_duration_sec", 0.0))
        available = float(
            payload.get("available_narration_duration_sec", 0.0)
        )

        if film_duration <= 0:
            raise ValueError(
                "Runtime timeline has invalid film_duration_sec"
            )
        if available <= 0:
            raise ValueError(
                "Runtime timeline has no available narration duration"
            )
        if available > film_duration + 0.001:
            raise ValueError(
                "Runtime narration duration exceeds film duration"
            )

        return payload

    def _build_runtime_scene_durations(
        self,
        scenes: list[dict[str, Any]],
        runtime_timeline: dict[str, Any] | None,
    ) -> dict[str, float]:
        if not runtime_timeline:
            return {}

        available = float(
            runtime_timeline["available_narration_duration_sec"]
        )
        rows: list[tuple[str, int, bool]] = []

        for scene in scenes:
            scene_id = str(scene.get("scene_id", "")).strip()
            if not scene_id:
                raise ValueError("Scene ID is required")

            voiceover = dict(scene.get("voiceover", {}))
            is_silence = (
                str(voiceover.get("mode", "")).strip().lower()
                == "silence"
            )
            text = "" if is_silence else self._scene_text(scene)
            rows.append((scene_id, len(text.split()), is_silence))

        total_words = sum(
            words
            for _, words, is_silence in rows
            if not is_silence
        )
        if total_words <= 0:
            raise ValueError(
                "Runtime timing requires at least one narrated scene"
            )

        result: dict[str, float] = {}
        narrated_ids: list[str] = []

        for scene_id, words, is_silence in rows:
            if is_silence:
                result[scene_id] = 0.001
            else:
                narrated_ids.append(scene_id)
                result[scene_id] = max(
                    0.001,
                    available * (words / total_words),
                )

        drift = available - sum(result[x] for x in narrated_ids)
        if narrated_ids:
            result[narrated_ids[-1]] += drift

        return {
            key: round(value, 6)
            for key, value in result.items()
        }

    def _discover_production_script(
        self,
    ) -> Path:
        candidates = [
            (
                self.config.project_dir
                / "script"
                / "voice_script.json"
            ),
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
                encoding="utf-8-sig"
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
                (
                    "default=noprint_wrappers=1:"
                    "nokey=1"
                ),
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8-sig",
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
            encoding="utf-8-sig",
            errors="replace",
        )

        if result.returncode != 0:
            raise RuntimeError(
                error_message
                + "\n"
                + result.stderr[-2000:]
            )
