# -*- coding: utf-8 -*-

from pathlib import Path
import json
import os
import shutil
import sys
import traceback

ROOT = Path.cwd()

PROJECT_ID = "film_08_ai_companions"
SCENE_ID = "SC07"

VOICE_ID = "gJEfHTTiifXEDmO687lC"
VOICE_NAME = "PRINCE_NUR"

PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID

PRODUCTION = (
    PROJECT
    / "script"
    / "production_script.json"
)

EDITORIAL_PAYLOAD = (
    PROJECT
    / "voice"
    / "tts_payloads_v2"
    / f"{SCENE_ID}.txt"
)

PROVIDER_PAYLOAD = (
    PROJECT
    / "voice"
    / "tts_provider_payloads_v2"
    / f"{SCENE_ID}.txt"
)

OUTPUT_DIR = (
    PROJECT
    / "voice"
    / "controlled_tests"
    / "SC07_PRINCE_NUR_V2_1"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_MP3 = (
    OUTPUT_DIR
    / "FILM_08_SC07_PRINCE_NUR_V2_1.mp3"
)

REPORT = (
    OUTPUT_DIR
    / "FILM_08_SC07_PRINCE_NUR_V2_1_REPORT.json"
)


def banner(text):
    print()
    print("=" * 124)
    print(text)
    print("=" * 124)


def fail(message):
    raise RuntimeError(message)


def word_count(text):
    return len(
        [
            x for x
            in text.split()
            if x
        ]
    )


banner(
    "ATLAS ZERO - FILM 08 / SC07 / "
    "PRINCE NUR CONTROLLED TTS V2.1"
)

print("PROJECT        :", PROJECT_ID)
print("SCENE          :", SCENE_ID)
print("VOICE          :", "Принц Нур")
print("VOICE ID       :", VOICE_ID)
print("LIVE API       :", os.getenv("AZ_ENABLE_LIVE_API"))
print("PAID CALLS     :", os.getenv("AZ_ALLOW_PAID_CALLS"))

if os.getenv("AZ_ENABLE_LIVE_API") != "1":
    fail("LIVE API gate is not authorized")

if os.getenv("AZ_ALLOW_PAID_CALLS") != "1":
    fail("PAID CALL gate is not authorized")

for path in (
    PRODUCTION,
    EDITORIAL_PAYLOAD,
    PROVIDER_PAYLOAD,
):
    if not path.is_file():
        fail(f"Missing required artifact: {path}")


editorial = EDITORIAL_PAYLOAD.read_text(
    encoding="utf-8"
).strip()

provider_text = PROVIDER_PAYLOAD.read_text(
    encoding="utf-8"
).strip()


if not editorial:
    fail("SC07 editorial text is empty")

if not provider_text:
    fail("SC07 provider TTS text is empty")


print()
print("EDITORIAL WORDS :", word_count(editorial))
print("PROVIDER WORDS  :", word_count(provider_text))

if word_count(editorial) < 300:
    fail(
        "SC07 is unexpectedly short; "
        "refusing paid synthesis"
    )


# ------------------------------------------------------------
# Verify expected pronunciation processing.
# ------------------------------------------------------------

expected_tts_fragments = [
    "Рэ́плика",
    "Сари́на",
    "Сари́ну",
]

missing = [
    item
    for item in expected_tts_fragments
    if item not in provider_text
]

if missing:
    fail(
        "Pronunciation layer missing expected fragments: "
        + repr(missing)
    )


# Editorial text MUST NOT contain TTS stress layer.
for item in expected_tts_fragments:
    if item in editorial:
        fail(
            "TTS pronunciation leaked into editorial text: "
            + item
        )


print("PRONUNCIATION   : PASS")
print("EDITORIAL/TTS   : SEPARATE")


# ------------------------------------------------------------
# Show exact provider input BEFORE paid call.
# ------------------------------------------------------------

print()
print("-" * 124)
print("EXACT ELEVENLABS INPUT — SC07")
print("-" * 124)
print(provider_text)
print("-" * 124)


# ------------------------------------------------------------
# Import canonical provider.
# ------------------------------------------------------------

from az_enterprise.core.elevenlabs_voice_provider_rc2 import (
    ElevenLabsVoiceProviderRC2,
    ElevenLabsVoiceSettingsRC2,
)


settings = ElevenLabsVoiceSettingsRC2(
    stability=0.48,
    similarity_boost=0.78,
    style=0.22,
    use_speaker_boost=True,
)


provider = ElevenLabsVoiceProviderRC2(
    voice_id=VOICE_ID,
    model_id="eleven_multilingual_v2",
    voice_settings=settings,
)


# ------------------------------------------------------------
# EXACTLY ONE synthesis request.
# ------------------------------------------------------------

if OUTPUT_MP3.exists():
    backup = OUTPUT_MP3.with_suffix(
        ".mp3.before_controlled_test"
    )

    shutil.copy2(
        OUTPUT_MP3,
        backup,
    )

    OUTPUT_MP3.unlink()


print()
print("ELEVENLABS      : START — ONE AUTHORIZED SC07 CALL")


try:

    result = provider.synthesize(
        text=provider_text,
        output_path=OUTPUT_MP3,
    )

except TypeError:

    # Compatibility with provider signature where output path
    # is positional.
    result = provider.synthesize(
        provider_text,
        OUTPUT_MP3,
    )


if not OUTPUT_MP3.is_file():
    fail(
        "Provider returned without creating SC07 MP3"
    )

if OUTPUT_MP3.stat().st_size < 10000:
    fail(
        "SC07 MP3 is unexpectedly small"
    )


print("ELEVENLABS      : RETURNED")
print("OUTPUT          :", OUTPUT_MP3)
print("SIZE            :", OUTPUT_MP3.stat().st_size)


# ------------------------------------------------------------
# Canonical offline QC:
# audio signal + local ASR against EDITORIAL text.
# ------------------------------------------------------------

from az_enterprise.core.voice_production_engine_rc2 import (
    VoiceProductionEngineRC2,
)


engine = VoiceProductionEngineRC2(
    project_id=PROJECT_ID,
)


audio_qc = None
speech_qc = None


# Audio signal gate.
if hasattr(
    provider,
    "validate_audio_signal",
):

    audio_qc = provider.validate_audio_signal(
        OUTPUT_MP3
    )

else:

    print(
        "AUDIO SIGNAL QC : provider method not directly exposed; "
        "canonical synthesis gate already applied"
    )


# Speech content gate.
speech_methods = [
    "_validate_speech_content",
    "_validate_expected_speech",
    "_speech_content_qc",
]

speech_method = None

for name in speech_methods:

    candidate = getattr(
        engine,
        name,
        None,
    )

    if callable(candidate):
        speech_method = candidate
        print("SPEECH QC METHOD:", name)
        break


if speech_method is None:
    fail(
        "Canonical Speech Content QC method not found"
    )


try:

    speech_qc = speech_method(
        audio_path=OUTPUT_MP3,
        expected_text=editorial,
        language="ru",
    )

except TypeError:

    try:

        speech_qc = speech_method(
            OUTPUT_MP3,
            editorial,
            "ru",
        )

    except TypeError:

        speech_qc = speech_method(
            OUTPUT_MP3,
            editorial,
        )


# ------------------------------------------------------------
# Duration using ffprobe.
# ------------------------------------------------------------

import subprocess

proc = subprocess.run(
    [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(OUTPUT_MP3),
    ],
    capture_output=True,
    text=True,
    encoding="utf-8",
)

if proc.returncode != 0:
    fail(
        "ffprobe failed: "
        + proc.stderr
    )

duration = float(
    proc.stdout.strip()
)

natural_wpm = (
    word_count(editorial)
    / duration
    * 60.0
)


report = {
    "project_id": PROJECT_ID,
    "scene_id": SCENE_ID,

    "voice": {
        "name": "Принц Нур",
        "voice_id": VOICE_ID,
        "model": "eleven_multilingual_v2",
        "settings": {
            "stability": 0.48,
            "similarity_boost": 0.78,
            "style": 0.22,
            "use_speaker_boost": True,
        },
    },

    "text": {
        "editorial_words": word_count(editorial),
        "provider_words": word_count(provider_text),
        "pronunciation_layer": "PASS",
        "editorial_tts_separation": "PASS",
    },

    "audio": {
        "path": str(OUTPUT_MP3),
        "bytes": OUTPUT_MP3.stat().st_size,
        "duration_sec": duration,
        "natural_wpm": natural_wpm,
    },

    "quality": {
        "audio_signal": audio_qc,
        "speech_content": speech_qc,
    },

    "status": "GENERATED_PENDING_HUMAN_REVIEW",
}


REPORT.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    + "\n",
    encoding="utf-8",
)


banner(
    "FILM 08 / SC07 / PRINCE NUR CONTROLLED FIXTURE READY"
)

print("VOICE           : Принц Нур")
print("SCENE           : SC07")
print("WORDS           :", word_count(editorial))
print("DURATION        :", round(duration, 3), "sec")
print("NATURAL WPM     :", round(natural_wpm, 2))
print()
print("PRONUNCIATION   : PASS")
print("EDITORIAL/TTS   : PASS")
print("AUDIO FILE      :", OUTPUT_MP3)
print("REPORT          :", REPORT)
print()
print("PAID GENERATION : SC07 ONLY")
print("OTHER 10 SCENES : NOT GENERATED")
print()
print(
    "STATUS : GENERATED — HUMAN REVIEW REQUIRED "
    "BEFORE REMAINING 10"
)
print("=" * 124)
