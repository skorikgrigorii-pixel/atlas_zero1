from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def find_repo_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


root = find_repo_root()
script = root / "atlas_zero_rc2_production_audit" / "RC2_PRODUCTION_AUDIT.py"
raise SystemExit(subprocess.call([sys.executable, str(script)], cwd=root))
