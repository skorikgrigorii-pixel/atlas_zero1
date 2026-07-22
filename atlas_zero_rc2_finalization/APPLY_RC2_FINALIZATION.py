from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


TESTS_TO_ARCHIVE = [
    "test_movie_runtime_rc1.py",
    "test_movie_runtime_rc1_assets.py",
    "test_render_engine_rc1.py",
]

TOOLS_TO_ARCHIVE = [
    "franklin_autopilot.py",
    "media_factory_rc1.py",
    "render_franklin_roughcut.py",
    "repair_semantic_asset_ids.py",
    "semantic_director_v1.py",
    "semantic_director_v1_1_multimedia.py",
    "semantic_director_v1_2_temporal.py",
    "visual_intelligence_v1.py",
]


def find_repo_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


def backup_file(src: Path, backup_root: Path, repo: Path) -> None:
    if not src.exists():
        return
    target = backup_root / src.relative_to(repo)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)


def replace_exact(path: Path, old: str, new: str, required: bool = True) -> bool:
    text = path.read_text(encoding="utf-8-sig")
    if old not in text:
        if required:
            raise RuntimeError(f"Expected text not found in {path}:\n{old}")
        return False
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True


def main() -> int:
    repo = find_repo_root()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = repo / "workspace" / "backups" / f"rc2_finalization_{stamp}"
    backup_root.mkdir(parents=True, exist_ok=True)

    release_gate = repo / "src" / "az_enterprise" / "core" / "release_gate.py"
    pipeline_runtime = repo / "src" / "az_enterprise" / "core" / "pipeline_runtime.py"
    audit_file = repo / "atlas_zero_rc2_production_audit" / "RC2_PRODUCTION_AUDIT.py"

    for path in [release_gate, pipeline_runtime, audit_file]:
        backup_file(path, backup_root, repo)

    # 1. ReleaseGate: neutral RC2 method and event.
    replace_exact(
        release_gate,
        "    def evaluate_rc1(self) -> dict:\n",
        "    def evaluate_release(self) -> dict:\n",
    )
    replace_exact(
        release_gate,
        "        self.bus.emit('RC1_RELEASE_GATE_EVALUATED', {'score':score,'ready':ready})",
        "        self.bus.emit('RELEASE_GATE_EVALUATED', {'score':score,'ready':ready})",
    )

    # Compatibility alias for old external callers. It does not import or execute RC1.
    text = release_gate.read_text(encoding="utf-8")
    marker = "        return {'ready':ready,'score':score,'checks':[{'criterion':c[0],'passed':c[1],'score':round(c[2],1)} for c in checks], 'blocking':['live_api' if not live_api_ok else None]}\n"
    if marker not in text:
        raise RuntimeError("ReleaseGate return marker was not found")
    alias = marker + "\n    def evaluate_rc1(self) -> dict:\n        \"\"\"Deprecated compatibility alias. Use evaluate_release().\"\"\"\n        return self.evaluate_release()\n"
    release_gate.write_text(text.replace(marker, alias), encoding="utf-8")

    # 2. Active production runtime uses the new method.
    replace_exact(
        pipeline_runtime,
        "ReleaseGate(self.db, self.project_id).evaluate_rc1()",
        "ReleaseGate(self.db, self.project_id).evaluate_release()",
    )

    # 3. Archive obsolete RC1 tests.
    tests_archive = repo / "tests" / "legacy_rc1"
    tests_archive.mkdir(parents=True, exist_ok=True)
    for name in TESTS_TO_ARCHIVE:
        src = repo / "tests" / name
        if src.exists():
            backup_file(src, backup_root, repo)
            dst = tests_archive / name
            if dst.exists():
                dst.unlink()
            shutil.move(str(src), str(dst))

    # 4. Archive legacy tools that directly import MovieRuntimeRC1/RenderEngineRC1.
    tools_archive = repo / "tools" / "legacy_rc1"
    tools_archive.mkdir(parents=True, exist_ok=True)
    for name in TOOLS_TO_ARCHIVE:
        src = repo / "tools" / name
        if src.exists():
            backup_file(src, backup_root, repo)
            dst = tools_archive / name
            if dst.exists():
                dst.unlink()
            shutil.move(str(src), str(dst))

    archive_readme = tools_archive / "README.md"
    archive_readme.write_text(
        "# Legacy RC1 tools\n\n"
        "These utilities directly depend on MovieRuntimeRC1 or RenderEngineRC1.\n"
        "They were removed from the active tools surface during RC2 finalization.\n"
        "Do not restore them without migrating them to public RC2 APIs.\n",
        encoding="utf-8",
    )

    # 5. Teach the production audit that archived tools are not active production code.
    if audit_file.exists():
        audit_text = audit_file.read_text(encoding="utf-8-sig")
        needle = '    "tests/legacy_rc1",\n'
        addition = '    "tests/legacy_rc1",\n    "tools/legacy_rc1",\n'
        if '"tools/legacy_rc1"' not in audit_text:
            if needle not in audit_text:
                raise RuntimeError("Could not patch RC2 audit legacy hints")
            audit_file.write_text(audit_text.replace(needle, addition), encoding="utf-8")

    report = {
        "operation": "ATLAS ZERO RC2 finalization",
        "backup": str(backup_root),
        "release_gate_method": "evaluate_release",
        "archived_tests": TESTS_TO_ARCHIVE,
        "archived_tools": TOOLS_TO_ARCHIVE,
    }
    report_path = repo / "workspace" / "audits" / "rc2_finalization_apply.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print("ATLAS ZERO — RC2 FINALIZATION APPLIED")
    print("=" * 76)
    print("Backup:", backup_root)
    print("Report:", report_path)
    print()
    print("Next:")
    print(r"$env:PYTHONPATH = ""$PWD\src""")
    print(r"python .\atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
