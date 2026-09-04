from __future__ import annotations

import ast
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "src" / "az_enterprise" / "core" / "director_core_rc2.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one match, found {count}. "
            "The source file differs from the audited RC2 version."
        )
    return text.replace(old, new, 1)


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(f"Target file not found: {TARGET}")

    original = TARGET.read_text(encoding="utf-8-sig")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(f"{TARGET.name}.backup_before_preview_render_{timestamp}")
    shutil.copy2(TARGET, backup)

    updated = original

    updated = replace_once(
        updated,
        '''    _PRODUCTION_STAGE_ORDER = (
        "assets",
        "story",
        "assignment",
        "timeline",
        "render_prepare",
    )
''',
        '''    _PRODUCTION_STAGE_ORDER = (
        "assets",
        "story",
        "assignment",
        "timeline",
        "render_prepare",
        "render",
    )
''',
        "production stage order",
    )

    updated = replace_once(
        updated,
        '''            if not release and target in {"render", "quality"}:
                raise ValueError(
                    f"Stage {target!r} requires release=True or run_release()"
                )
''',
        '''            if not release and target == "quality":
                raise ValueError(
                    f"Stage {target!r} requires release=True or run_release()"
                )
''',
        "target validation",
    )

    updated = replace_once(
        updated,
        '''                else:
                    preflight = results.get("render_prepare")
                    if preflight is None:
                        raise RuntimeError(
                            "Production execution must include render_prepare"
                        )

                    ready = preflight.get("state") == "RENDER_PREFLIGHT_READY"
                    state.status = "PREPARED" if ready else "REVIEW"
                    state.quality = {}
                    state.release_authorized = False
                    result_state = (
                        "PRODUCTION_PREPARED"
                        if ready
                        else "PRODUCTION_REWORK_REQUIRED"
                    )
''',
        '''                else:
                    preflight = results.get("render_prepare")
                    if preflight is None:
                        raise RuntimeError(
                            "Production execution must include render_prepare"
                        )

                    render = results.get("render")
                    if render is None:
                        raise RuntimeError(
                            "Production execution must include render"
                        )

                    preflight_ready = (
                        preflight.get("state") == "RENDER_PREFLIGHT_READY"
                    )
                    render_ready = render.get("state") in {
                        "RENDER_PREVIEW_VERIFIED",
                        "RENDERED_VERIFIED",
                    }
                    ready = preflight_ready and render_ready

                    if ready:
                        state.status = (
                            "RENDERED"
                            if render.get("state") == "RENDERED_VERIFIED"
                            else "PREVIEW_RENDERED"
                        )
                    else:
                        state.status = "REVIEW"

                    state.quality = {}
                    state.release_authorized = False
                    result_state = (
                        "PRODUCTION_RENDERED"
                        if ready
                        else "PRODUCTION_REWORK_REQUIRED"
                    )
''',
        "production completion state",
    )

    updated = replace_once(
        updated,
        '''                artifacts = {
                    "timeline": str(self.config.timeline_path),
                    "render_preflight": str(
                        self.config.canonical_render_path.parent
                        / "render_preflight_rc2.json"
                    ),
                    "governance": str(self.config.governance_path),
                }
''',
        '''                artifacts = {
                    "timeline": str(self.config.timeline_path),
                    "render_preflight": str(
                        self.config.canonical_render_path.parent
                        / "render_preflight_rc2.json"
                    ),
                    "render_report": str(
                        self.config.canonical_render_path.parent
                        / "render_report_rc2.json"
                    ),
                    "preview_render": str(self.config.preview_render_path),
                    "governance": str(self.config.governance_path),
                }
''',
        "production artifacts",
    )

    updated = replace_once(
        updated,
        '''    def run(self, *, resume: bool = True, force: bool = False) -> dict[str, Any]:
        """Run the production build without requiring narration or release."""

        del resume
        result = self.run_targets(
            targets=None,
            force=force,
            release=False,
        )
        if result["state"] != "PRODUCTION_PREPARED":
            raise RuntimeError("RC2 production preflight blocked completion")
        return result
''',
        '''    def run(self, *, resume: bool = True, force: bool = False) -> dict[str, Any]:
        """Run production and create a verified preview without narration."""

        del resume
        result = self.run_targets(
            targets=None,
            force=force,
            release=False,
        )
        if result["state"] != "PRODUCTION_RENDERED":
            raise RuntimeError("RC2 production render blocked completion")
        return result
''',
        "run contract",
    )

    ast.parse(updated, filename=str(TARGET))
    TARGET.write_text(updated, encoding="utf-8")

    print("ATLAS ZERO RC2 render integration applied.")
    print(f"Updated: {TARGET}")
    print(f"Backup:  {backup}")
    print("assets -> story -> assignment -> timeline -> render_prepare -> render")


if __name__ == "__main__":
    main()
