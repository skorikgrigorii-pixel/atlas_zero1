from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ElevenLabsVoiceSettingsRC2:
    """Per-request ElevenLabs voice settings."""

    stability: float = 0.50
    similarity_boost: float = 0.75
    style: float = 0.15
    use_speaker_boost: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "stability": self._bounded(self.stability),
            "similarity_boost": self._bounded(
                self.similarity_boost
            ),
            "style": self._bounded(self.style),
            "use_speaker_boost":
                bool(self.use_speaker_boost),
        }

    @staticmethod
    def _bounded(value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class ElevenLabsVoiceProviderRC2:
    """Generate narration audio through the ElevenLabs REST API."""

    API_URL = (
        "https://api.elevenlabs.io/v1/"
        "text-to-speech/{voice_id}"
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "mp3_44100_128",
        voice_settings:
            ElevenLabsVoiceSettingsRC2 | None = None,
        request_timeout_sec: float = 120.0,
        maximum_attempts: int = 3,
        retry_delay_sec: float = 2.0,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("ELEVENLABS_API_KEY", "")
        ).strip()

        self.voice_id = (
            voice_id
            or os.environ.get("ELEVENLABS_VOICE_ID", "")
        ).strip()

        self.model_id = str(model_id).strip()
        self.output_format = str(output_format).strip()
        self.voice_settings = (
            voice_settings
            or ElevenLabsVoiceSettingsRC2()
        )
        self.request_timeout_sec = max(
            10.0,
            float(request_timeout_sec),
        )
        self.maximum_attempts = max(
            1,
            int(maximum_attempts),
        )
        self.retry_delay_sec = max(
            0.0,
            float(retry_delay_sec),
        )

        self._validate_configuration()

    def synthesize(
        self,
        *,
        text: str,
        output_path: Path,
        language_code: str | None = None,
        seed: int | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
    ) -> dict[str, Any]:

        # ---------------------------------------------------------
        # PAID API SAFETY GATE
        #
        # ElevenLabs synthesis is a billable operation.
        # Both explicit permissions are required.
        # ---------------------------------------------------------

        live_api_enabled = (
            os.environ.get(
                "AZ_ENABLE_LIVE_API",
                "",
            ).strip()
            == "1"
        )

        paid_calls_allowed = (
            os.environ.get(
                "AZ_ALLOW_PAID_CALLS",
                "",
            ).strip()
            == "1"
        )

        if not (
            live_api_enabled
            and paid_calls_allowed
        ):
            raise PermissionError(
                "ELEVENLABS_PAID_CALL_BLOCKED: "
                "Set both AZ_ENABLE_LIVE_API=1 "
                "and AZ_ALLOW_PAID_CALLS=1 "
                "to authorize paid speech synthesis."
            )

        normalized_text = str(text).strip()

        if not normalized_text:
            raise ValueError(
                "ElevenLabs narration text is empty"
            )

        destination = Path(output_path)

        if destination.suffix.lower() != ".mp3":
            raise ValueError(
                "ElevenLabs RC2 output path must use .mp3"
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload: dict[str, Any] = {
            "text": normalized_text,
            "model_id": self.model_id,
            "voice_settings":
                self.voice_settings.to_payload(),
        }

        if language_code:
            payload["language_code"] = (
                str(language_code).strip()
            )

        if seed is not None:
            payload["seed"] = int(seed)

        if previous_text:
            payload["previous_text"] = (
                str(previous_text).strip()
            )

        if next_text:
            payload["next_text"] = (
                str(next_text).strip()
            )

        request_url = self._request_url()
        request_body = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        last_error: Exception | None = None

        for attempt in range(
            1,
            self.maximum_attempts + 1,
        ):
            try:
                audio_bytes = self._post(
                    url=request_url,
                    body=request_body,
                )

                if not audio_bytes:
                    raise RuntimeError(
                        "ElevenLabs returned empty audio"
                    )

                temporary_path = destination.with_name(
                    destination.stem
                    + ".partial"
                    + destination.suffix
                )

                temporary_path.write_bytes(
                    audio_bytes
                )

                try:
                    audio_signal_qc = (
                        self.validate_audio_signal(
                            temporary_path
                        )
                    )

                except Exception:
                    temporary_path.unlink(
                        missing_ok=True
                    )
                    raise

                temporary_path.replace(
                    destination
                )

                return {
                    "provider": "elevenlabs",
                    "voice_id": self.voice_id,
                    "model_id": self.model_id,
                    "output_format": self.output_format,
                    "characters": len(normalized_text),
                    "bytes": len(audio_bytes),
                    "output_path": str(destination),
                    "attempt": attempt,

                    # Historical compatibility:
                    # status=ready still means a valid
                    # audio artifact exists.
                    #
                    # It does NOT yet mean speech content
                    # was verified.
                    "status": "ready",

                    "audio_signal_qc":
                        audio_signal_qc,

                    "readiness_scope":
                        "AUDIO_SIGNAL_ONLY",

                    "speech_content_status":
                        "UNKNOWN",
                }

            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                RuntimeError,
            ) as exc:
                last_error = exc

                if (
                    attempt >= self.maximum_attempts
                    or not self._is_retryable(exc)
                ):
                    break

                time.sleep(
                    self.retry_delay_sec * attempt
                )

        raise RuntimeError(
            "ElevenLabs speech synthesis failed: "
            + self._format_error(last_error)
        ) from last_error

    def validate_audio_signal(
        self,
        audio_path: Path,
        *,
        minimum_duration_sec: float = 0.25,
        minimum_peak_db: float = -50.0,
        minimum_mean_db: float = -60.0,
        minimum_significant_ratio: float = 0.001,
    ) -> dict[str, Any]:
        """
        Validate that an ElevenLabs output is a real,
        decodable audio signal.

        IMPORTANT:
        This validates AUDIO SIGNAL only.

        It does NOT prove that the signal contains
        intelligible human speech. Speech-content QC
        is a separate higher-level gate.
        """

        path = Path(audio_path)

        if not path.exists():
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "audio file does not exist"
            )

        if path.stat().st_size <= 0:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "audio file is empty"
            )

        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")

        if not ffmpeg:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "ffmpeg is not available"
            )

        if not ffprobe:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "ffprobe is not available"
            )

        # -------------------------------------------------------------
        # 1. CONTAINER / DURATION VALIDATION
        # -------------------------------------------------------------

        probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if probe.returncode != 0:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "audio container cannot be decoded by ffprobe: "
                + probe.stderr[-1000:]
            )

        try:
            duration_sec = float(
                probe.stdout.strip()
            )
        except Exception as exc:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "unable to determine audio duration"
            ) from exc

        if duration_sec < float(
            minimum_duration_sec
        ):
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                f"duration too short: {duration_sec:.3f}s"
            )

        # -------------------------------------------------------------
        # 2. FULL DECODE VALIDATION
        # -------------------------------------------------------------

        decode = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-v",
                "error",
                "-i",
                str(path),
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if decode.returncode != 0:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "ffmpeg decode failed: "
                + decode.stderr[-1000:]
            )

        # -------------------------------------------------------------
        # 3. VOLUME VALIDATION
        # -------------------------------------------------------------

        volume = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-i",
                str(path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        volume_text = (
            volume.stdout
            + "\n"
            + volume.stderr
        )

        mean_match = re.search(
            r"mean_volume:\s*([-\d.]+)\s*dB",
            volume_text,
        )

        peak_match = re.search(
            r"max_volume:\s*([-\d.]+)\s*dB",
            volume_text,
        )

        if not mean_match or not peak_match:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "unable to measure audio volume"
            )

        mean_volume_db = float(
            mean_match.group(1)
        )

        peak_volume_db = float(
            peak_match.group(1)
        )

        if peak_volume_db < float(
            minimum_peak_db
        ):
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                f"peak level is effectively silent: "
                f"{peak_volume_db:.1f} dB"
            )

        if mean_volume_db < float(
            minimum_mean_db
        ):
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                f"mean level is effectively silent: "
                f"{mean_volume_db:.1f} dB"
            )

        # -------------------------------------------------------------
        # 4. RAW PCM SIGNAL VALIDATION
        # -------------------------------------------------------------

        pcm = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-v",
                "error",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                "-",
            ],
            capture_output=True,
        )

        if pcm.returncode != 0:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "PCM extraction failed"
            )

        pcm_bytes = pcm.stdout

        if not pcm_bytes:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "decoded PCM stream is empty"
            )

        sample_count = (
            len(pcm_bytes) // 2
        )

        if sample_count <= 0:
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                "decoded PCM contains no samples"
            )

        significant_samples = 0

        for offset in range(
            0,
            len(pcm_bytes) - 1,
            2,
        ):
            sample = struct.unpack_from(
                "<h",
                pcm_bytes,
                offset,
            )[0]

            if abs(sample) >= 64:
                significant_samples += 1

        significant_ratio = (
            significant_samples
            / sample_count
        )

        if significant_ratio < float(
            minimum_significant_ratio
        ):
            raise RuntimeError(
                "ELEVENLABS_AUDIO_SIGNAL_QC_FAILED: "
                f"meaningful PCM signal ratio too low: "
                f"{significant_ratio:.6f}"
            )

        return {
            "state":
                "AUDIO_SIGNAL_VALID",

            "scope":
                "SIGNAL_ONLY",

            "speech_content_status":
                "UNKNOWN",

            "duration_sec":
                round(
                    duration_sec,
                    3,
                ),

            "mean_volume_db":
                round(
                    mean_volume_db,
                    3,
                ),

            "peak_volume_db":
                round(
                    peak_volume_db,
                    3,
                ),

            "pcm_sample_count":
                sample_count,

            "pcm_significant_samples":
                significant_samples,

            "pcm_significant_ratio":
                round(
                    significant_ratio,
                    6,
                ),

            "thresholds":
                {
                    "minimum_duration_sec":
                        minimum_duration_sec,

                    "minimum_peak_db":
                        minimum_peak_db,

                    "minimum_mean_db":
                        minimum_mean_db,

                    "minimum_significant_ratio":
                        minimum_significant_ratio,
                },
        }


    def _post(
        self,
        *,
        url: str,
        body: bytes,
    ) -> bytes:
        request = urllib.request.Request(
            url=url,
            data=body,
            method="POST",
            headers={
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key,
                "User-Agent":
                    "ATLAS-ZERO-RC2/VoiceProduction",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.request_timeout_sec,
            ) as response:
                content_type = str(
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                ).lower()

                response_body = response.read()

                if (
                    "application/json" in content_type
                    and response_body
                ):
                    raise RuntimeError(
                        "ElevenLabs returned JSON instead "
                        "of audio: "
                        + response_body.decode(
                            "utf-8",
                            errors="replace",
                        )[:1000]
                    )

                return response_body

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise ElevenLabsHTTPErrorRC2(
                status_code=int(exc.code),
                reason=str(exc.reason),
                response_body=detail,
            ) from exc

    def _request_url(self) -> str:
        encoded_voice_id = urllib.parse.quote(
            self.voice_id,
            safe="",
        )

        query = urllib.parse.urlencode(
            {
                "output_format":
                    self.output_format,
            }
        )

        return (
            self.API_URL.format(
                voice_id=encoded_voice_id
            )
            + "?"
            + query
        )

    def _validate_configuration(self) -> None:
        if not self.api_key:
            raise EnvironmentError(
                "ELEVENLABS_API_KEY is not configured"
            )

        if not self.voice_id:
            raise EnvironmentError(
                "ELEVENLABS_VOICE_ID is not configured"
            )

        if not self.model_id:
            raise ValueError(
                "ElevenLabs model_id is required"
            )

        if not self.output_format:
            raise ValueError(
                "ElevenLabs output_format is required"
            )

    @staticmethod
    def _is_retryable(
        error: Exception,
    ) -> bool:
        if isinstance(
            error,
            ElevenLabsHTTPErrorRC2,
        ):
            return (
                error.status_code == 429
                or error.status_code >= 500
            )

        return isinstance(
            error,
            (
                urllib.error.URLError,
                TimeoutError,
            ),
        )

    @staticmethod
    def _format_error(
        error: Exception | None,
    ) -> str:
        if error is None:
            return "unknown error"

        return str(error)


class ElevenLabsHTTPErrorRC2(
    urllib.error.HTTPError
):
    """HTTP error preserving ElevenLabs response details."""

    def __init__(
        self,
        *,
        status_code: int,
        reason: str,
        response_body: str,
    ) -> None:
        self.status_code = int(status_code)
        self.response_body = str(
            response_body
        ).strip()

        message = (
            f"HTTP {self.status_code}: {reason}"
        )

        if self.response_body:
            message += (
                " | "
                + self.response_body[:1500]
            )

        Exception.__init__(self, message)

    def __str__(self) -> str:
        return str(self.args[0])
