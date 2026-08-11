from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "workspace"
    / "projects"
    / "hogueras"
    / "script"
    / "voice_script.json"
)
AUDIO_DIR = (
    ROOT
    / "workspace"
    / "projects"
    / "hogueras"
    / "01_Audio"
)
SCENE_DIR = AUDIO_DIR / "scenes"
OUTPUT_PATH = AUDIO_DIR / "voice_master_timeline.wav"
REPORT_PATH = AUDIO_DIR / "voice_master_timeline_report.json"


def probe_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
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
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return float(result.stdout.strip() or 0.0)


def main() -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")

    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg or ffprobe was not found in PATH")

    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(SCRIPT_PATH)

    payload = json.loads(
        SCRIPT_PATH.read_text(encoding="utf-8-sig")
    )

    total_duration = float(payload["duration_sec"])
    voice_scenes = [
        scene
        for scene in payload["scenes"]
        if str(scene.get("scene_id", "")).startswith("VO")
    ]

    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-t",
        f"{total_duration:.3f}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
    ]

    rows: list[dict[str, object]] = []

    for scene in voice_scenes:
        scene_id = str(scene["scene_id"])
        path = SCENE_DIR / f"{scene_id}.wav"

        if not path.exists():
            raise FileNotFoundError(path)

        command.extend(["-i", str(path)])

        actual_duration = probe_duration(ffprobe, path)
        start_sec = float(scene["start_sec"])
        approved_end_sec = float(scene["end_sec"])
        actual_end_sec = start_sec + actual_duration

        rows.append(
            {
                "scene_id": scene_id,
                "start_sec": round(start_sec, 3),
                "approved_end_sec": round(approved_end_sec, 3),
                "actual_duration_sec": round(actual_duration, 3),
                "actual_end_sec": round(actual_end_sec, 3),
                "fits_scene": (
                    actual_end_sec <= approved_end_sec + 0.05
                ),
            }
        )

    filters = [
        (
            f"[0:a]atrim=duration={total_duration:.3f},"
            "asetpts=PTS-STARTPTS[base]"
        )
    ]
    mix_inputs = ["[base]"]

    for input_index, scene in enumerate(
        voice_scenes,
        start=1,
    ):
        delay_ms = round(float(scene["start_sec"]) * 1000)
        label = f"vo{input_index:02d}"

        filters.append(
            f"[{input_index}:a]"
            f"adelay={delay_ms}|{delay_ms},"
            "aresample=48000,"
            "aformat=channel_layouts=stereo"
            f"[{label}]"
        )
        mix_inputs.append(f"[{label}]")

    filters.append(
        "".join(mix_inputs)
        + f"amix=inputs={len(mix_inputs)}:"
          "duration=first:"
          "dropout_transition=0:"
          "normalize=0,"
          f"atrim=duration={total_duration:.3f}"
          "[master]"
    )

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[master]",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(OUTPUT_PATH),
        ]
    )

    print("Building timeline-aligned voice master...")
    subprocess.run(command, check=True)

    final_duration = probe_duration(
        ffprobe,
        OUTPUT_PATH,
    )

    outside = [
        row
        for row in rows
        if not bool(row["fits_scene"])
    ]

    report = {
        "state": "VOICE_MASTER_TIMELINE_READY",
        "output": str(OUTPUT_PATH),
        "duration_sec": round(final_duration, 3),
        "target_duration_sec": round(total_duration, 3),
        "voice_scenes": rows,
        "scenes_outside_approved_windows": outside,
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 72)
    print("STATE:", report["state"])
    print("OUTPUT:", OUTPUT_PATH)
    print("DURATION:", round(final_duration, 3))
    print("OUTSIDE WINDOWS:", len(outside))
    print("REPORT:", REPORT_PATH)
    print("=" * 72)


if __name__ == "__main__":
    main()
