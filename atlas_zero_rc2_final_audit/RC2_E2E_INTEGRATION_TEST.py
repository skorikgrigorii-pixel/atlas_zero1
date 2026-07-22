from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def repo_root() -> Path:
    for candidate in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("Repository root was not found")


def run(command: list[str], cwd: Path) -> None:
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise RuntimeError(process.stderr or process.stdout)


def main() -> None:
    root = repo_root()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must be available in PATH")

    from az_enterprise.core.audio_composer_rc2 import NativeAudioComposerRC2
    from az_enterprise.core.audio_timeline_rc2 import AudioEventRC2

    output = root / "workspace" / "integration_tests" / "rc2_e2e"
    output.mkdir(parents=True, exist_ok=True)

    visual = output / "visual_master_rc2.mp4"
    voice = output / "voice_test.wav"
    music = output / "music_test.wav"
    sfx = output / "sfx_test.wav"

    run([
        ffmpeg, "-y", "-f", "lavfi", "-i",
        "color=c=black:s=1280x720:r=25:d=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(visual)
    ], root)
    run([
        ffmpeg, "-y", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=48000:duration=2",
        "-c:a", "pcm_s16le", str(voice)
    ], root)
    run([
        ffmpeg, "-y", "-f", "lavfi", "-i",
        "sine=frequency=220:sample_rate=48000:duration=4",
        "-c:a", "pcm_s16le", str(music)
    ], root)
    run([
        ffmpeg, "-y", "-f", "lavfi", "-i",
        "sine=frequency=880:sample_rate=48000:duration=0.5",
        "-c:a", "pcm_s16le", str(sfx)
    ], root)

    events = [
        AudioEventRC2("voice_1", "voice", str(voice), 0.7, 2.0, gain_db=-3.0),
        AudioEventRC2("music_1", "music", str(music), 0.0, 4.0, gain_db=-16.0, fade_in_sec=0.2, fade_out_sec=0.4),
        AudioEventRC2("sfx_1", "sfx", str(sfx), 3.0, 0.5, gain_db=-8.0),
    ]

    composer = NativeAudioComposerRC2(project_id="rc2_e2e_smoke", output_dir=output)
    report = composer.run(
        visual_master=visual,
        audio_events=events,
        target_duration_sec=4.0,
    )

    final_movie = Path(report["mux_report"]["output_movie"])
    probe = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-show_entries", "stream=codec_type",
            "-of", "json", str(final_movie),
        ],
        capture_output=True, text=True, check=False,
    )
    if probe.returncode != 0:
        raise RuntimeError(probe.stderr)
    payload = json.loads(probe.stdout)
    kinds = {s.get("codec_type") for s in payload.get("streams", [])}
    if not {"audio", "video"}.issubset(kinds):
        raise RuntimeError("E2E output is missing audio or video")

    result = {
        "state": "RC2_E2E_PASS",
        "final_movie": str(final_movie),
        "probe": payload,
        "composer_report": report,
    }
    result_path = output / "rc2_e2e_report.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("RC2 E2E PASS")
    print(f"Final movie: {final_movie}")
    print(f"Report: {result_path}")


if __name__ == "__main__":
    main()
