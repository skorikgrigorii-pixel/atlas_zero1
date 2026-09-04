# -*- coding: utf-8 -*-

from pathlib import Path
import json
import os
import subprocess
import sys
import traceback
import inspect
from datetime import datetime

ROOT = Path.cwd()

PROJECT_ID = "film_08_ai_companions"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

VOICE_ID = "gJEfHTTiifXEDmO687lC"
VOICE_NAME = "Принц Нур"
MODEL_ID = "eleven_multilingual_v2"

# ----------------------------------------------------------------
# CANONICAL NEW-SCENE SET
#
# SC07 is deliberately absent.
# These are the remaining ten V2.1 scenes.
# ----------------------------------------------------------------

SCENES = [
    "SC08",
    "SC10",
    "SC13",
    "SC15",
    "SC16",
    "SC18",
    "SC20",
    "SC21",
    "SC22",
    "SC23",
]

APPROVED_SC07 = "SC07"

EDITORIAL_DIR = (
    PROJECT
    / "voice"
    / "tts_payloads_v2"
)

PROVIDER_DIR = (
    PROJECT
    / "voice"
    / "tts_provider_payloads_v2"
)

OUTPUT_DIR = (
    PROJECT
    / "voice"
    / "production_v2_1"
    / "PRINCE_NUR"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

REPORT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "rc2"
    / "voice_production_v2_1"
)

REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

REPORT = (
    REPORT_DIR
    / "FILM_08_PRINCE_NUR_REMAINING_BATCH.json"
)


def banner(text):
    print()
    print("=" * 126)
    print(text)
    print("=" * 126)


def fail(message):
    raise RuntimeError(message)


def wc(text):
    return len([
        x
        for x in text.split()
        if x
    ])


def ffprobe_duration(path):

    proc = subprocess.run(
        [
            "ffprobe",
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
    )

    if proc.returncode != 0:
        raise RuntimeError(
            "ffprobe failed: "
            + proc.stderr
        )

    return float(
        proc.stdout.strip()
    )


banner(
    "ATLAS ZERO - FILM 08 / PRINCE NUR "
    "/ REMAINING 10-SCENE PRODUCTION"
)

print("PROJECT        :", PROJECT_ID)
print("VOICE          :", VOICE_NAME)
print("VOICE ID       :", VOICE_ID)
print("MODEL          :", MODEL_ID)
print("LIVE API       :", os.getenv("AZ_ENABLE_LIVE_API"))
print("PAID CALLS     :", os.getenv("AZ_ALLOW_PAID_CALLS"))
print("SCENES         :", SCENES)
print("SC07           : HARD EXCLUDED")


# ================================================================
# SAFETY PREFLIGHT
# ================================================================

if os.getenv("AZ_ENABLE_LIVE_API") != "1":
    fail("LIVE API is not authorized")

if os.getenv("AZ_ALLOW_PAID_CALLS") != "1":
    fail("PAID calls are not authorized")

if APPROVED_SC07 in SCENES:
    fail(
        "FATAL SAFETY ERROR: SC07 present in paid batch"
    )

if len(SCENES) != 10:
    fail(
        f"Expected exactly 10 scenes, got {len(SCENES)}"
    )

if len(set(SCENES)) != len(SCENES):
    fail("Duplicate scene IDs in paid batch")


# ================================================================
# PREFLIGHT ALL PAYLOADS BEFORE FIRST PAID CALL
# ================================================================

payloads = {}

banner("GLOBAL PAYLOAD PREFLIGHT")

for scene_id in SCENES:

    editorial_path = (
        EDITORIAL_DIR
        / f"{scene_id}.txt"
    )

    provider_path = (
        PROVIDER_DIR
        / f"{scene_id}.txt"
    )

    if not editorial_path.is_file():
        fail(
            f"{scene_id}: missing editorial payload: "
            f"{editorial_path}"
        )

    if not provider_path.is_file():
        fail(
            f"{scene_id}: missing provider payload: "
            f"{provider_path}"
        )

    editorial = editorial_path.read_text(
        encoding="utf-8"
    ).strip()

    provider_text = provider_path.read_text(
        encoding="utf-8"
    ).strip()

    if not editorial:
        fail(
            f"{scene_id}: empty editorial payload"
        )

    if not provider_text:
        fail(
            f"{scene_id}: empty provider payload"
        )

    # Strong protection against accidental technical-text leakage.
    forbidden = [
        "VOICE DIRECTION",
        "VISUAL DIRECTION",
        "AUDIO DIRECTION",
        "EDITORIAL NOTE",
        "SOURCE:",
        "SOURCES:",
        "http://",
        "https://",
        "\\workspace\\",
        "/workspace/",
        "SCENE ID",
        "SHOT LIST",
        "TECHNICAL",
    ]

    leaked = [
        marker
        for marker in forbidden
        if marker.lower() in provider_text.lower()
    ]

    if leaked:
        fail(
            f"{scene_id}: technical text detected "
            f"in provider payload: {leaked}"
        )

    payloads[scene_id] = {
        "editorial": editorial,
        "provider": provider_text,
        "editorial_path": editorial_path,
        "provider_path": provider_path,
    }

    print(
        f"{scene_id:<6} "
        f"EDITORIAL={wc(editorial):>4} "
        f"TTS={wc(provider_text):>4} "
        f"TECH=PASS"
    )


print()
print("GLOBAL PREFLIGHT : PASS")
print("PAID CALLS SO FAR: 0")


# ================================================================
# PROVIDER — SAME CONFIGURATION APPROVED ON SC07
# ================================================================

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
    model_id=MODEL_ID,
    voice_settings=settings,
)

print()
print("PROVIDER        : READY")
print("SETTINGS        : 0.48 / 0.78 / 0.22 / boost=True")


# ================================================================
# LOAD SPEECH QC WITHOUT ASSUMING ENGINE CONSTRUCTOR
#
# We inspect the class and construct it only with parameters
# actually supported by the installed RC2.
# ================================================================

from az_enterprise.core.voice_production_engine_rc2 import (
    VoiceProductionEngineRC2,
)

sig = inspect.signature(
    VoiceProductionEngineRC2
)

print("ENGINE SIGNATURE:", sig)

# First try parameterless construction if supported.
engine = None

try:
    engine = VoiceProductionEngineRC2()
except Exception:
    pass

# If construction requires project configuration, inspect existing
# constructor rather than inventing keyword arguments.
if engine is None:

    init_sig = inspect.signature(
        VoiceProductionEngineRC2.__init__
    )

    required = [
        p
        for name, p in init_sig.parameters.items()
        if name != "self"
        and p.default is inspect.Parameter.empty
        and p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]

    fail(
        "Cannot safely instantiate canonical engine "
        "for batch QC without its required runtime objects. "
        "Required constructor parameters: "
        + repr([p.name for p in required])
        + ". NO PAID CALLS HAVE BEEN MADE."
    )


qc_method = getattr(
    engine,
    "validate_speech_content",
    None,
)

if not callable(qc_method):
    fail(
        "Canonical validate_speech_content() unavailable. "
        "NO PAID CALLS HAVE BEEN MADE."
    )

print("SPEECH QC       : validate_speech_content READY")


# ================================================================
# PRODUCTION
# ================================================================

results = []

banner("PAID PRODUCTION START")

for index, scene_id in enumerate(
    SCENES,
    start=1,
):

    data = payloads[scene_id]

    editorial = data["editorial"]
    provider_text = data["provider"]

    output_mp3 = (
        OUTPUT_DIR
        / f"FILM_08_{scene_id}_PRINCE_NUR_V2_1.mp3"
    )

    scene_report = (
        OUTPUT_DIR
        / f"FILM_08_{scene_id}_PRINCE_NUR_V2_1.json"
    )

    print()
    print("-" * 126)
    print(
        f"{index}/10 — {scene_id}"
    )
    print("-" * 126)

    # ------------------------------------------------------------
    # NEVER overwrite/re-pay an already completed scene.
    # ------------------------------------------------------------

    if output_mp3.exists():

        print("AUDIO EXISTS     :", output_mp3)
        print("ACTION           : SKIP — NO PAID CALL")

        results.append({
            "scene_id": scene_id,
            "status": "SKIPPED_EXISTING_AUDIO",
            "audio": str(output_mp3),
        })

        continue

    print("EDITORIAL WORDS  :", wc(editorial))
    print("TTS WORDS        :", wc(provider_text))
    print("ELEVENLABS       : START")

    # ------------------------------------------------------------
    # ONE synthesis call for this scene.
    # ------------------------------------------------------------

    try:

        provider.synthesize(
            text=provider_text,
            output_path=output_mp3,
        )

    except TypeError:

        provider.synthesize(
            provider_text,
            output_mp3,
        )

    if not output_mp3.is_file():
        fail(
            f"{scene_id}: provider returned "
            "without output MP3"
        )

    size = output_mp3.stat().st_size

    if size < 10000:
        fail(
            f"{scene_id}: output unexpectedly small "
            f"({size} bytes)"
        )

    print("ELEVENLABS       : RETURNED")
    print("SIZE             :", size)

    # ------------------------------------------------------------
    # Duration
    # ------------------------------------------------------------

    duration = ffprobe_duration(
        output_mp3
    )

    wpm = (
        wc(editorial)
        / duration
        * 60.0
    )

    print("DURATION         :", round(duration, 3))
    print("NATURAL WPM      :", round(wpm, 2))

    # ------------------------------------------------------------
    # Canonical local Speech Content QC.
    # IMPORTANT: compares ASR against editorial text,
    # not stressed/provider text.
    # ------------------------------------------------------------

    print("SPEECH QC        : START")

    try:

        qc = qc_method(
            output_mp3,
            editorial,
            language_code="ru",
        )

    except TypeError:

        try:

            qc = qc_method(
                output_mp3,
                editorial,
                language="ru",
            )

        except TypeError:

            qc = qc_method(
                output_mp3,
                editorial,
            )

    if not isinstance(qc, dict):
        fail(
            f"{scene_id}: unexpected QC result type "
            f"{type(qc).__name__}"
        )

    state = (
        qc.get("state")
        or qc.get("status")
    )

    print("QC STATE         :", state)

    if state != "EXPECTED_SPEECH_CONFIRMED":

        scene_report.write_text(
            json.dumps(
                {
                    "scene_id": scene_id,
                    "status": "QC_FAILED",
                    "audio": str(output_mp3),
                    "duration_sec": duration,
                    "natural_wpm": wpm,
                    "speech_content_qc": qc,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ) + "\n",
            encoding="utf-8",
        )

        fail(
            f"{scene_id}: SPEECH CONTENT QC FAILED. "
            "BATCH STOPPED BEFORE NEXT PAID CALL."
        )

    print("SPEECH CONTENT   : PASS")

    item = {
        "scene_id": scene_id,
        "status": "VOICE_SCENE_READY",
        "voice": VOICE_NAME,
        "voice_id": VOICE_ID,
        "editorial_words": wc(editorial),
        "tts_words": wc(provider_text),
        "audio": str(output_mp3),
        "bytes": size,
        "duration_sec": duration,
        "natural_wpm": wpm,
        "speech_content_qc": qc,
    }

    scene_report.write_text(
        json.dumps(
            item,
            ensure_ascii=False,
            indent=2,
            default=str,
        ) + "\n",
        encoding="utf-8",
    )

    results.append(item)

    print("SCENE            : READY")


# ================================================================
# FINAL REPORT
# ================================================================

generated = [
    x
    for x in results
    if x["status"] == "VOICE_SCENE_READY"
]

skipped = [
    x
    for x in results
    if x["status"] == "SKIPPED_EXISTING_AUDIO"
]

total_duration = sum(
    x.get("duration_sec", 0.0)
    for x in generated
)

final = {
    "project_id": PROJECT_ID,
    "voice": {
        "name": VOICE_NAME,
        "voice_id": VOICE_ID,
        "model": MODEL_ID,
        "settings": {
            "stability": 0.48,
            "similarity_boost": 0.78,
            "style": 0.22,
            "use_speaker_boost": True,
        },
    },
    "approved_existing_scene": "SC07",
    "requested_remaining_scenes": SCENES,
    "generated_count": len(generated),
    "skipped_existing_count": len(skipped),
    "generated_duration_sec": total_duration,
    "scenes": results,
    "status": "PASS",
    "generated_at": datetime.now().isoformat(),
}

REPORT.write_text(
    json.dumps(
        final,
        ensure_ascii=False,
        indent=2,
        default=str,
    ) + "\n",
    encoding="utf-8",
)


banner(
    "ATLAS ZERO - FILM 08 / PRINCE NUR "
    "/ REMAINING BATCH COMPLETE"
)

print("SC07              : PRESERVED / NOT GENERATED")
print("REQUESTED         :", len(SCENES))
print("GENERATED         :", len(generated))
print("SKIPPED EXISTING  :", len(skipped))
print(
    "NEW AUDIO TOTAL   :",
    round(total_duration, 3),
    "sec",
)
print()
print("REPORT            :", REPORT)
print()
print("STATUS : PASS")
print("=" * 126)
