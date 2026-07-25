from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    for candidate in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("Repository root was not found")


def main() -> None:
    root = repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    scripts = [
        Path(__file__).with_name("RC2_DEPENDENCY_AUDIT.py"),
        Path(__file__).with_name("RC2_E2E_INTEGRATION_TEST.py"),
    ]
    for script in scripts:
        print()
        print("=" * 72)
        print(f"RUNNING: {script.name}")
        print("=" * 72)
        process = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            env=env,
            check=False,
        )
        if process.returncode != 0:
            raise SystemExit(process.returncode)
    print()
    print("RC2 FINAL AUDIT AND E2E COMPLETE")
    print("NEXT STEP: HOGUERAS BENCHMARK")


if __name__ == "__main__":
    main()
