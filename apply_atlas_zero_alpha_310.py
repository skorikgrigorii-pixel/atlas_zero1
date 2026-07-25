from pathlib import Path
import shutil

ROOT = Path(__file__).parent
TARGET = ROOT / "src" / "az_enterprise" / "core" / "pipeline_runtime.py"

if not TARGET.exists():
    raise FileNotFoundError(TARGET)

backup = TARGET.with_suffix(".py.alpha310.bak")
shutil.copy2(TARGET, backup)

print("Backup created:", backup.name)
print("Pipeline file found:", TARGET.name)
print("Alpha 3.1 patch scaffold ready.")