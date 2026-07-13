from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path.cwd()

TEMP_ROOT = Path.home() / "AppData" / "Local" / "Temp"

AUDIO = (
    ROOT
    / "workspace"
    / "projects"
    / "franklin"
    / "01_Audio"
    / "voice_master.m4a"
)

OUTPUT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / "franklin"
    / "render_rc1"
)

OUTPUT = (
    OUTPUT_DIR
    / "franklin_multimedia_v3_40_assets_fixed.mp4"
)

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

if not FFMPEG:
    raise RuntimeError("ffmpeg не найден.")

if not FFPROBE:
    raise RuntimeError("ffprobe не найден.")

temp_dirs = sorted(
    [
        path
        for path in TEMP_ROOT.glob("atlas_zero_franklin_*")
        if path.is_dir()
    ],
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)

if not temp_dirs:
    raise RuntimeError(
        "Временная папка рендера не найдена."
    )

temp_dir = temp_dirs[0]

segments = sorted(
    temp_dir.glob("segment_*.mp4")
)

print("=" * 72)
print("ATLAS ZERO — RECOVER FINAL MP4")
print("=" * 72)
print("TEMP DIR =", temp_dir)
print("SEGMENTS =", len(segments))
print("AUDIO    =", AUDIO)
print("OUTPUT   =", OUTPUT)

if len(segments) != 149:
    raise RuntimeError(
        f"Ожидалось 149 сегментов, найдено {len(segments)}."
    )

if not AUDIO.exists():
    raise FileNotFoundError(
        f"Мастер-аудио не найдено: {AUDIO}"
    )

# Проверяем первый и последний сегменты.
for segment in (segments[0], segments[-1]):
    check = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(segment),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if check.returncode != 0:
        raise RuntimeError(
            f"Повреждён сегмент: {segment}\n"
            + check.stderr
        )

    print(
        "VALID SEGMENT =",
        segment.name,
        "duration =",
        check.stdout.strip(),
    )

concat_file = temp_dir / "concat_recovery.txt"

concat_file.write_text(
    "\n".join(
        f"file '{segment.resolve().as_posix()}'"
        for segment in segments
    ),
    encoding="utf-8",
)

video_only = temp_dir / "render_no_audio_recovered.mp4"

print()
print("1. Склеиваю 149 сегментов...")

concat_process = subprocess.run(
    [
        FFMPEG,
        "-nostdin",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-movflags",
        "+faststart",
        str(video_only),
    ],
    stdin=subprocess.DEVNULL,
    capture_output=True,
    text=True,
    check=False,
)

if concat_process.returncode != 0:
    raise RuntimeError(
        "Ошибка склейки сегментов:\n"
        + "\n".join(
            concat_process.stderr.splitlines()[-30:]
        )
    )

print("VIDEO ONLY =", video_only)

print()
print("2. Добавляю мастер-озвучку...")

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

mux_process = subprocess.run(
    [
        FFMPEG,
        "-nostdin",
        "-y",
        "-i",
        str(video_only),
        "-i",
        str(AUDIO),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(OUTPUT),
    ],
    stdin=subprocess.DEVNULL,
    capture_output=True,
    text=True,
    check=False,
)

if mux_process.returncode != 0:
    raise RuntimeError(
        "Ошибка добавления звука:\n"
        + "\n".join(
            mux_process.stderr.splitlines()[-30:]
        )
    )

print()
print("3. Проверяю итоговый MP4...")

probe = subprocess.run(
    [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate",
        "-of",
        "json",
        str(OUTPUT),
    ],
    capture_output=True,
    text=True,
    check=False,
)

if probe.returncode != 0:
    raise RuntimeError(
        "Итоговый файл не прошёл проверку:\n"
        + probe.stderr
    )

print()
print("=" * 72)
print("RECOVERY COMPLETED")
print("=" * 72)
print(probe.stdout)
print("OUTPUT =", OUTPUT)
