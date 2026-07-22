from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


CORE_FILES = [
    "src/az_enterprise/core/movie_runtime_rc1.py",
    "src/az_enterprise/core/rc1_completion_planner.py",
    "src/az_enterprise/core/render_engine_rc1.py",
]

ROOT_FILES = [
    "ATLAS_ZERO_RC1_ALPHA_3_1.patch",
    "paceexportsfranklinmovie_runtime_rc1manual_edit_package.md",
]

DIRECTORIES = [
    "tests/legacy_rc1",
    "tools/legacy_rc1",
]

NAME_MARKERS = (
    "movie_runtime_rc1",
    "render_engine_rc1",
    "rc1_completion",
)


def find_repo_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


def read_audit(repo: Path) -> dict:
    path = repo / "workspace" / "audits" / "rc2_production" / "rc2_production_audit.json"
    if not path.exists():
        raise RuntimeError(f"Production audit not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def move_to_backup(repo: Path, backup: Path, source: Path, moved: list[str]) -> None:
    if not source.exists():
        return
    relative = source.relative_to(repo)
    target = backup / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    shutil.move(str(source), str(target))
    moved.append(relative.as_posix())


def main() -> int:
    repo = find_repo_root()
    audit = read_audit(repo)

    if audit.get("score") != 100:
        raise RuntimeError(f"RC1 removal blocked: audit score is {audit.get('score')}, expected 100")
    if audit.get("status") != "RC2_PRODUCTION_READY":
        raise RuntimeError(f"RC1 removal blocked: status is {audit.get('status')}")
    if not audit.get("answers", {}).get("safe_to_remove_rc1"):
        raise RuntimeError("RC1 removal blocked: safe_to_remove_rc1 is false")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = repo / "workspace" / "backups" / f"removed_rc1_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []

    for rel in CORE_FILES + ROOT_FILES:
        move_to_backup(repo, backup, repo / rel, moved)

    for rel in DIRECTORIES:
        move_to_backup(repo, backup, repo / rel, moved)

    core = repo / "src" / "az_enterprise" / "core"
    for path in list(core.glob("*rc1*")):
        if path.is_file():
            move_to_backup(repo, backup, path, moved)

    # Remove compiled RC1 bytecode from active caches.
    removed_cache: list[str] = []
    for cache in repo.rglob("__pycache__"):
        try:
            cache.relative_to(repo / "workspace" / "backups")
            continue
        except ValueError:
            pass
        for file in cache.glob("*.pyc"):
            lower = file.name.lower()
            if any(marker in lower for marker in NAME_MARKERS):
                rel = file.relative_to(repo).as_posix()
                file.unlink()
                removed_cache.append(rel)

    manifest = {
        "operation": "REMOVE_RC1_FROM_ACTIVE_PROJECT",
        "audit_score_before": audit.get("score"),
        "audit_status_before": audit.get("status"),
        "backup": str(backup),
        "moved": moved,
        "removed_cache": removed_cache,
        "note": "Historical workspace exports were preserved.",
    }

    report = repo / "workspace" / "audits" / "rc1_removal_manifest.json"
    report.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print("ATLAS ZERO — RC1 REMOVED FROM ACTIVE PROJECT")
    print("=" * 76)
    print("Moved files/directories:", len(moved))
    print("Removed cache files:", len(removed_cache))
    print("Backup:", backup)
    print("Manifest:", report)
    print()
    print("Historical workspace exports were not deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
