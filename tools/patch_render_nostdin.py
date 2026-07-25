from pathlib import Path
import shutil
import subprocess
import sys

path = Path("src/az_enterprise/core/render_engine_rc1.py")

if not path.exists():
    raise FileNotFoundError(path)

source = path.read_text(encoding="utf-8")

old = '''    @staticmethod
    def _run_ffmpeg(cmd: list[str], step: str) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            stderr_tail = "\\n".join(proc.stderr.splitlines()[-10:])
            raise RuntimeError(f"ffmpeg failed during {step}: {stderr_tail}")
'''

new = '''    @staticmethod
    def _run_ffmpeg(cmd: list[str], step: str) -> None:
        # FFmpeg must never inherit the parent process stdin.
        # This is especially important when Python itself is started
        # through a PowerShell pipeline.
        if "-nostdin" not in cmd:
            cmd = [cmd[0], "-nostdin", *cmd[1:]]

        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            stderr_tail = "\\n".join(proc.stderr.splitlines()[-20:])
            raise RuntimeError(
                f"ffmpeg failed during {step}: {stderr_tail}"
            )
'''

if old in source:
    backup = path.with_suffix(
        path.suffix + ".backup_before_nostdin"
    )

    shutil.copy2(path, backup)
    path.write_text(
        source.replace(old, new, 1),
        encoding="utf-8",
    )

    print("RenderEngine исправлен.")
    print("Backup:", backup)

elif "stdin=subprocess.DEVNULL" in source:
    print("Исправление stdin уже установлено.")

else:
    raise RuntimeError(
        "Метод _run_ffmpeg имеет неожиданную структуру. "
        "Автоматическая замена остановлена."
    )

result = subprocess.run(
    [sys.executable, "-m", "py_compile", str(path)]
)

if result.returncode != 0:
    raise RuntimeError("Ошибка синтаксиса RenderEngine.")

print("Синтаксис RenderEngine корректен.")
