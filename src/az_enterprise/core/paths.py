from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = ROOT / "workspace"
PROJECTS = WORKSPACE / "projects"
EXPORTS = WORKSPACE / "exports"
DB_PATH = WORKSPACE / "atlas_zero_enterprise.sqlite3"
FRANKLIN = PROJECTS / "franklin"

MEDIA_DIRS = {
    "audio": "01_Audio",
    "image": "02_Images",
    "video": "03_Video",
    "capcut": "04_CapCut",
    "music": "05_Music",
    "export": "06_Export",
}

for p in [WORKSPACE, PROJECTS, EXPORTS, FRANKLIN]:
    p.mkdir(parents=True, exist_ok=True)
