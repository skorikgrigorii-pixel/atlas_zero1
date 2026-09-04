from __future__ import annotations

import ast
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "src" / "az_enterprise" / "core" / "director_core_rc2.py"

REPLACEMENTS = [
    ('    _PRODUCTION_STAGE_ORDER = (\n        "assets",\n        "story",\n        "assignment",\n        "timeline",\n        "render_prepare",\n    )\n', '    _PRODUCTION_STAGE_ORDER = (\n        "assets",\n        "story",\n        "assignment",\n        "timeline",\n        "render_prepare",\n        "render",\n    )\n', "production stage order"),
    ('            if not release and target in {"render", "quality"}:\n                raise ValueError(\n                    f"Stage {target!r} requires release=True or run_release()"\n                )\n', '            if not release and target == "quality":\n                raise ValueError(\n                    f"Stage {target!r} requires release=True or run_release()"\n                )\n', "target validation"),
    ('                else:\n                    preflight = results.get("render_prepare")\n                    if preflight is None:\n                        raise RuntimeError(\n                            "Production execution must include render_prepare"\n                        )\n\n                    ready = preflight.get("state") == "RENDER_PREFLIGHT_READY"\n                    state.status = "PREPARED" if ready else "REVIEW"\n                    state.quality = {}\n                    state.release_authorized = False\n                    result_state = (\n                        "PRODUCTION_PREPARED"\n                        if ready\n                        else "PRODUCTION_REWORK_REQUIRED"\n                    )\n', '                else:\n                    preflight = results.get("render_prepare")\n                    if preflight is None:\n                        raise RuntimeError(\n                            "Production execution must include render_prepare"\n                        )\n\n                    render = results.get("render")\n                    if render is None:\n                        raise RuntimeError(\n                            "Production execution must include render"\n                        )\n\n                    preflight_ready = (\n                        preflight.get("state") == "RENDER_PREFLIGHT_READY"\n                    )\n                    render_ready = render.get("state") in {\n                        "RENDER_PREVIEW_VERIFIED",\n                        "RENDERED_VERIFIED",\n                    }\n                    ready = preflight_ready and render_ready\n\n                    if ready:\n                        state.status = (\n                            "RENDERED"\n                            if render.get("state") == "RENDERED_VERIFIED"\n                            else "PREVIEW_RENDERED"\n                        )\n                    else:\n                        state.status = "REVIEW"\n\n                    state.quality = {}\n                    state.release_authorized = False\n                    result_state = (\n                        "PRODUCTION_RENDERED"\n                        if ready\n                        else "PRODUCTION_REWORK_REQUIRED"\n                    )\n', "production completion state"),
    ('    def run(self, *, resume: bool = True, force: bool = False) -> dict[str, Any]:\n        """Run the production build without requiring narration or release."""\n\n        del resume\n        result = self.run_targets(\n            targets=None,\n            force=force,\n            release=False,\n        )\n        if result["state"] != "PRODUCTION_PREPARED":\n            raise RuntimeError("RC2 production preflight blocked completion")\n        return result\n', '    def run(self, *, resume: bool = True, force: bool = False) -> dict[str, Any]:\n        """Run production and create a verified preview without narration."""\n\n        del resume\n        result = self.run_targets(\n            targets=None,\n            force=force,\n            release=False,\n        )\n        if result["state"] != "PRODUCTION_RENDERED":\n            raise RuntimeError("RC2 production render blocked completion")\n        return result\n', "run contract"),
]


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(f"Target file not found: {TARGET}")

    original = TARGET.read_text(encoding="utf-8-sig")
    updated = original

    for old, new, label in REPLACEMENTS:
        count = updated.count(old)
        if count != 1:
            raise RuntimeError(
                f"{label}: expected exactly one match, found {count}. "
                "No changes were written."
            )
        updated = updated.replace(old, new, 1)

    ast.parse(updated, filename=str(TARGET))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(
        f"{TARGET.name}.backup_before_preview_render_{timestamp}"
    )
    shutil.copy2(TARGET, backup)
    TARGET.write_text(updated, encoding="utf-8")

    print("ATLAS ZERO RC2 render integration applied successfully.")
    print(f"Updated: {TARGET}")
    print(f"Backup:  {backup}")
    print("Production stages: assets -> story -> assignment -> timeline -> render_prepare -> render")


if __name__ == "__main__":
    main()
