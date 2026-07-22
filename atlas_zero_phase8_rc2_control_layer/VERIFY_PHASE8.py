from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

repo = Path.cwd().resolve()
package = Path(__file__).resolve().parent
target = repo / "tests" / "test_phase8_control_layer_rc2.py"
shutil.copy2(package / "tests" / "test_phase8_control_layer_rc2.py", target)

env = os.environ.copy()
env["PYTHONPATH"] = str(repo / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

commands = [
    [sys.executable, "-m", "pytest", str(target), "-q"],
    [sys.executable, "-c",
     "from az_enterprise.core.control_layer_rc2 import RC2ControlLayer, RC2ReadinessPlanner;"
     "from az_enterprise.core.render_engine_rc2 import RenderEngineRC2;"
     "print('PHASE8_IMPORT_SMOKE_OK')"],
]
for command in commands:
    process = subprocess.run(command, cwd=repo, env=env, check=False)
    if process.returncode:
        raise SystemExit(process.returncode)

print("PHASE 8 VERIFIED")
