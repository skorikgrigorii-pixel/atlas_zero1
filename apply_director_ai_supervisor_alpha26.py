from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ROOT / "src" / "az_enterprise" / "core" / "director_core_rc2.py"
BACKUP = CORE.with_suffix(".py.backup_before_alpha26")
TEST = ROOT / "tests" / "test_director_ai_supervisor_alpha26.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    source = CORE.read_text(encoding="utf-8")

    if "_run_director_ai_analysis" in source:
        print("Alpha 2.6 integration is already present; no changes made.")
        return

    BACKUP.write_text(source, encoding="utf-8")

    source = replace_once(
        source,
        "from .database import Database\n",
        "from .database import Database\nfrom .director_ai_runtime import DirectorAIRuntime\n",
        "DirectorAIRuntime import",
    )

    anchor = "    @classmethod\n    def _recommended_targets_from_quality(\n"

    methods = '''    def _run_director_ai_analysis(self) -> dict[str, Any]:
        # Director AI is advisory. QualityGateRC2 remains release authority.
        try:
            report = DirectorAIRuntime(
                self.db,
                project_id=self.config.project_id,
            ).analyze()
        except Exception as exc:
            self.progress(
                {
                    "stage": "DIRECTOR_AI",
                    "status": "ADVISORY_FAILED",
                    "error": str(exc),
                }
            )
            return {
                "state": "DIRECTOR_AI_ADVISORY_FAILED",
                "project_id": self.config.project_id,
                "error": str(exc),
                "issues": [],
                "tasks": [],
                "next_actions": [],
            }

        enriched = dict(report)
        enriched.setdefault("state", "DIRECTOR_AI_ANALYSIS_READY")
        return enriched

    @classmethod
    def _recommended_targets_from_director_ai(
        cls,
        report: Mapping[str, Any],
    ) -> tuple[str, ...]:
        codes = cls._collect_issue_codes(report)
        task_types = {
            str(mapping.get("task_type") or "").strip().lower()
            for mapping in cls._walk_mappings(report)
            if mapping.get("task_type")
        }
        targets: list[str] = []

        if codes & {
            "FILM_TOO_LONG",
            "OPENING_HOOK_WEAK",
            "SCENE_LOW_COVERAGE",
        } or task_types & {
            "create_director_cut",
            "strengthen_opening",
            "generate_scene_coverage",
        }:
            targets.append("story")

        if codes & {
            "MISSING_VISUAL",
            "ASSET_OVERUSED",
            "ASSET_REUSED_TOO_SOON",
            "LOW_CV_QUALITY",
            "EXCLUDED_ASSET_USED",
        } or task_types & {
            "generate_asset",
            "replace_repeated_asset",
            "review_or_replace_asset",
            "replace_excluded_asset",
        }:
            targets.append("assignment")

        if codes & {
            "LOW_VISUAL_DIVERSITY",
            "LOW_VISUAL_DYNAMICS",
            "STATIC_IMAGE_TOO_LONG",
            "NATURAL_SOUND_MISSING",
        } or task_types & {
            "add_visual_variety",
            "shorten_static_shot",
            "add_natural_sound",
        }:
            targets.append("timeline")

        return tuple(dict.fromkeys(targets))

'''

    source = replace_once(
        source,
        anchor,
        methods + anchor,
        "Director AI methods insertion",
    )

    old_report = '''        quality = execution.get("results", {}).get("quality", {})
        passed = quality.get("state") == "PASSED"
        recommended_targets = () if passed else self._recommended_targets_from_quality(
            quality
        )

        return {
            "metrics": {"quality": 1.0 if passed else 0.5},
            "project_facts": {
                "quality_passed": passed,
                "project_id": self.config.project_id,
            },
            "recommended_targets": recommended_targets,
            "metadata": {
                "execution": dict(execution),
                "quality_state": quality.get("state"),
                "issue_codes": sorted(self._collect_issue_codes(quality)),
            },
        }
'''

    new_report = '''        quality = execution.get("results", {}).get("quality", {})
        passed = quality.get("state") == "PASSED"

        if passed:
            director_ai: dict[str, Any] = {
                "state": "SKIPPED_QUALITY_PASSED",
                "project_id": self.config.project_id,
                "issues": [],
                "tasks": [],
                "next_actions": [],
            }
            recommended_targets: tuple[str, ...] = ()
        else:
            director_ai = self._run_director_ai_analysis()
            recommended_targets = tuple(
                dict.fromkeys(
                    (
                        *self._recommended_targets_from_quality(quality),
                        *self._recommended_targets_from_director_ai(director_ai),
                    )
                )
            )

        quality_issue_codes = self._collect_issue_codes(quality)
        director_issue_codes = self._collect_issue_codes(director_ai)

        return {
            "metrics": {"quality": 1.0 if passed else 0.5},
            "project_facts": {
                "quality_passed": passed,
                "project_id": self.config.project_id,
                "director_ai_state": director_ai.get("state"),
            },
            "recommended_targets": recommended_targets,
            "metadata": {
                "execution": dict(execution),
                "quality_state": quality.get("state"),
                "issue_codes": sorted(
                    quality_issue_codes | director_issue_codes
                ),
                "quality_issue_codes": sorted(quality_issue_codes),
                "director_ai_issue_codes": sorted(director_issue_codes),
                "director_ai": director_ai,
            },
        }
'''

    source = replace_once(
        source,
        old_report,
        new_report,
        "Supervisor report integration",
    )

    ast.parse(source, filename=str(CORE))
    CORE.write_text(source, encoding="utf-8")

    TEST.write_text(
        '''from az_enterprise.core.director_core_rc2 import DirectorCoreRC2


def test_director_ai_targets_are_mapped_to_existing_rc2_stages():
    report = {
        "issues": [
            {"rule_code": "FILM_TOO_LONG"},
            {"rule_code": "ASSET_REUSED_TOO_SOON"},
            {"rule_code": "STATIC_IMAGE_TOO_LONG"},
        ]
    }

    assert DirectorCoreRC2._recommended_targets_from_director_ai(report) == (
        "story",
        "assignment",
        "timeline",
    )


def test_api_not_ready_does_not_trigger_media_rework():
    report = {
        "issues": [{"rule_code": "API_NOT_READY"}],
        "tasks": [{"task_type": "connect_api"}],
    }

    assert DirectorCoreRC2._recommended_targets_from_director_ai(report) == ()


def test_task_types_can_route_rework_without_rule_codes():
    report = {
        "tasks": [
            {"task_type": "strengthen_opening"},
            {"task_type": "replace_repeated_asset"},
            {"task_type": "add_visual_variety"},
        ]
    }

    assert DirectorCoreRC2._recommended_targets_from_director_ai(report) == (
        "story",
        "assignment",
        "timeline",
    )
''',
        encoding="utf-8",
    )

    print(f"Patched: {CORE}")
    print(f"Backup:  {BACKUP}")
    print(f"Tests:   {TEST}")
    print("Alpha 2.6 Director AI advisory integration applied successfully.")


if __name__ == "__main__":
    main()
