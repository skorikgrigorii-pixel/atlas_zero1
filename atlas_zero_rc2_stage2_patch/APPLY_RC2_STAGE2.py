from __future__ import annotations

import hashlib
import json
import py_compile
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
PATCH = Path(__file__).resolve().parent
FILES = [
    "src/az_enterprise/core/runtime_governance_rc2.py",
    "src/az_enterprise/core/project_config_rc2.py",
    "src/az_enterprise/core/production_state_rc2.py",
    "src/az_enterprise/core/quality_gate_rc2.py",
    "src/az_enterprise/core/director_core_rc2.py",
    "src/az_enterprise/core/rc2_cli.py",
    "tests/test_rc2_stage2_unified_runtime.py",
    "docs/RC2_STAGE_2_UNIFIED_RUNTIME.md",
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(cmd: list[str]) -> None:
    print("[RUN]", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    if not (ROOT / "src/az_enterprise").exists():
        raise RuntimeError("Run from atlas_zero1 repository root")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "workspace/backups" / f"rc2_stage2_{stamp}"
    changed = []
    try:
        for rel in FILES:
            source = PATCH / rel
            destination = ROOT / rel
            if not source.exists():
                raise FileNotFoundError(source)
            if destination.exists() and digest(source) == digest(destination):
                print("[ALREADY CURRENT]", rel)
                continue
            if destination.exists():
                target_backup = backup / rel
                target_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, target_backup)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            changed.append(rel)
            print("[INSTALLED]", rel)

        for rel in FILES:
            if rel.endswith(".py"):
                py_compile.compile(str(ROOT / rel), doraise=True)
                print("[COMPILE OK]", rel)

        env = dict(__import__("os").environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_rc2_foundation.py", "tests/test_rc2_stage2_unified_runtime.py"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "az_enterprise.core.rc2_cli", "governance"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        report_path = ROOT / "workspace/exports/_system/rc2_stage2/install_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "state": "APPLIED_AND_VERIFIED",
            "stage": "RC2_STAGE_2_UNIFIED_RUNTIME",
            "changed": changed,
            "backup": str(backup),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("=" * 72)
        print("ATLAS ZERO RC2 STAGE 2 APPLIED AND VERIFIED")
        print("Backup:", backup)
        print("Report:", report_path)
        print("Next safe command:")
        print(f'{sys.executable} -m az_enterprise.core.rc2_cli plan franklin')
    except Exception:
        for rel in reversed(changed):
            destination = ROOT / rel
            saved = backup / rel
            if saved.exists():
                shutil.copy2(saved, destination)
            else:
                destination.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
