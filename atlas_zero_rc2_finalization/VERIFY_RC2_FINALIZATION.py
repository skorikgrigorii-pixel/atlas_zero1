from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ARCHIVED_TESTS = [
    "test_movie_runtime_rc1.py",
    "test_movie_runtime_rc1_assets.py",
    "test_render_engine_rc1.py",
]

ARCHIVED_TOOLS = [
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


def main() -> int:
    repo = find_repo_root()
    failures: list[str] = []

    release_gate = repo / "src" / "az_enterprise" / "core" / "release_gate.py"
    pipeline = repo / "src" / "az_enterprise" / "core" / "pipeline_runtime.py"

    gate_text = release_gate.read_text(encoding="utf-8-sig")
    pipeline_text = pipeline.read_text(encoding="utf-8-sig")

    if "def evaluate_release(self)" not in gate_text:
        failures.append("ReleaseGate.evaluate_release() is missing")
    if "RELEASE_GATE_EVALUATED" not in gate_text:
        failures.append("Neutral release event is missing")
    if ".evaluate_rc1()" in pipeline_text:
        failures.append("pipeline_runtime.py still calls evaluate_rc1()")
    if ".evaluate_release()" not in pipeline_text:
        failures.append("pipeline_runtime.py does not call evaluate_release()")

    for name in ARCHIVED_TESTS:
        if (repo / "tests" / name).exists():
            failures.append(f"Active legacy test still exists: tests/{name}")
        if not (repo / "tests" / "legacy_rc1" / name).exists():
            failures.append(f"Archived legacy test is missing: tests/legacy_rc1/{name}")

    for name in ARCHIVED_TOOLS:
        if (repo / "tools" / name).exists():
            failures.append(f"Active legacy tool still exists: tools/{name}")
        if not (repo / "tools" / "legacy_rc1" / name).exists():
            failures.append(f"Archived legacy tool is missing: tools/legacy_rc1/{name}")

    compile_targets = [
        release_gate,
        pipeline,
        repo / "atlas_zero_rc2_production_audit" / "RC2_PRODUCTION_AUDIT.py",
    ]
    for target in compile_targets:
        if not target.exists():
            continue
        process = subprocess.run(
            [sys.executable, "-m", "py_compile", str(target)],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            failures.append(f"Compile failed: {target}\n{process.stderr}")

    smoke = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from az_enterprise.core.release_gate import ReleaseGate;"
                "from az_enterprise.core.control_layer_rc2 import RC2ControlLayer;"
                "from az_enterprise.core.render_engine_rc2 import RenderEngineRC2;"
                "from az_enterprise.core.timeline_engine_rc2 import TimelineEngineRC2;"
                "print('RC2_FINALIZATION_SMOKE_OK')"
            ),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if smoke.returncode != 0:
        failures.append("Import smoke failed:\n" + smoke.stderr)

    print("=" * 76)
    print("ATLAS ZERO — VERIFY RC2 FINALIZATION")
    print("=" * 76)

    if failures:
        print("FAIL")
        for item in failures:
            print("-", item)
        return 2

    print("PASS")
    print(smoke.stdout.strip())
    print()
    print("Run the production audit:")
    print(r"python .\atlas_zero_rc2_production_audit\RUN_RC2_PRODUCTION_AUDIT.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
