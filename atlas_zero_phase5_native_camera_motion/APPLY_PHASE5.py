from __future__ import annotations
import py_compile, shutil
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CORE=ROOT/"src"/"az_enterprise"/"core"
PAYLOAD=ROOT/"phase5_payload"

def main():
    if not CORE.exists(): raise FileNotFoundError(f"ATLAS ZERO core directory not found: {CORE}")
    backup=ROOT/"workspace"/"backups"/f"phase5_camera_motion_{datetime.now():%Y%m%d_%H%M%S}"
    backup.mkdir(parents=True,exist_ok=True)
    for name in ["camera_motion_rc2.py","visual_renderer_rc2.py","render_engine_rc2.py"]:
        target=CORE/name
        if target.exists(): shutil.copy2(target,backup/name)
    shutil.copy2(PAYLOAD/"camera_motion_rc2.py",CORE/"camera_motion_rc2.py")
    shutil.copy2(PAYLOAD/"visual_renderer_rc2.py",CORE/"visual_renderer_rc2.py")
    render=CORE/"render_engine_rc2.py"; text=render.read_text(encoding="utf-8")
    text=text.replace("PHASE_4_NATIVE_VISUAL_RENDERER","PHASE_5_NATIVE_CAMERA_MOTION")
    marker='            "ken_burns",\n'
    if marker in text and '            "slow_pull",\n' not in text:
        text=text.replace(marker,marker+'            "slow_pull",\n            "pan_up",\n            "pan_down",\n            "custom",\n',1)
    render.write_text(text,encoding="utf-8")
    for name in ["camera_motion_rc2.py","visual_renderer_rc2.py","render_engine_rc2.py"]:
        py_compile.compile(str(CORE/name),doraise=True)
    print("PHASE 5 INSTALLED")
    print(f"Backup: {backup}")

if __name__=="__main__": main()
