from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .project_config_rc2 import ProjectConfigRC2
from .render_engine_rc2 import RenderEngineRC2
from .postproduction_quality_rc2 import PostProductionQualityRC2


class QualityGateRC2:
    """Mandatory release gate based on verified artifacts and semantic constraints."""

    def __init__(self, config: ProjectConfigRC2) -> None:
        self.config = config

    @staticmethod
    def _read_json(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def run(self, *, release: bool = True) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add(
            code: str,
            passed: bool,
            details: dict[str, Any] | None = None,
            *,
            required: bool = True,
        ) -> None:
            checks.append(
                {
                    "code": code,
                    "passed": bool(passed),
                    "required": required,
                    "details": details or {},
                }
            )

        timeline_path = self.config.timeline_path
        add("TIMELINE_EXISTS", timeline_path.exists(), {"path": str(timeline_path)})
        if not timeline_path.exists():
            return self._finish(checks, {})

        rows = self._read_json(timeline_path)
        incomplete = [
            row
            for row in rows
            if row.get("status") != "assigned" or not row.get("asset_path")
        ]
        unique_assets = {str(row.get("asset_path")) for row in rows if row.get("asset_path")}
        media_usage = Counter(str(row.get("media_type") or "missing") for row in rows)
        average_reuse = len(rows) / max(len(unique_assets), 1)
        unique_ratio = len(unique_assets) / max(len(rows), 1)

        add("TIMELINE_NOT_EMPTY", len(rows) > 0, {"items": len(rows)})
        add("TIMELINE_COMPLETE", len(incomplete) == 0, {"incomplete": len(incomplete)})
        asset_counts = Counter(
            str(row.get("asset_path"))
            for row in rows
            if row.get("asset_path")
        )
        reused_assets = {
            asset_path: count
            for asset_path, count in asset_counts.items()
            if count > 1
        }
        repeated_uses_total = sum(
            count - 1 for count in reused_assets.values()
        )

        add(
            "SOURCE_TIMELINE_ASSET_DIVERSITY",
            len(unique_assets) > 0,
            {
                "unique_assets": len(unique_assets),
                "unique_ratio": round(unique_ratio, 4),
                "average_reuse": round(average_reuse, 3),
                "reused_assets_in_source_timeline": reused_assets,
                "repeated_uses_in_source_timeline": repeated_uses_total,
                "policy": "source repeats are removed during editor pass",
            },
            required=True,
        )
        add(
            "VIDEO_USAGE_PRESENT",
            media_usage.get("video", 0) >= self.config.minimum_video_shots,
            {"video_shots": media_usage.get("video", 0)},
            required=False,
        )

        editor_report_path = self.config.render_dir / "editor_pass_report_rc2.json"
        add(
            "EDITOR_PASS_REPORT_EXISTS",
            editor_report_path.exists(),
            {"path": str(editor_report_path)},
        )
        if editor_report_path.exists():
            editor_report = self._read_json(editor_report_path)
            duplicate_warnings = list(editor_report.get("duplicate_warnings") or [])
            replacement_blocked = list(editor_report.get("replacement_blocked") or [])
            duplicate_groups = list(editor_report.get("duplicate_groups") or [])
            remaining_duplicates = max(
                len(duplicate_warnings),
                len(replacement_blocked),
                len(duplicate_groups),
            )
            removed_repeated = list(editor_report.get("removed_repeated_clips") or [])
            add(
                "NO_ASSET_REUSE_IN_RENDER_MODEL",
                remaining_duplicates == 0,
                {
                    "duplicate_warnings": len(duplicate_warnings),
                    "replacement_blocked": len(replacement_blocked),
                    "duplicate_groups": len(duplicate_groups),
                    "repeated_clips_removed": len(removed_repeated),
                    "clips_input": editor_report.get("clips_input"),
                    "clips_output": editor_report.get("clips_output"),
                    "duration_output_sec": editor_report.get("duration_output_sec"),
                    "policy": editor_report.get("timeline_policy"),
                },
            )
            add(
                "COMPACT_TIMELINE_POLICY",
                str(editor_report.get("timeline_policy") or "")
                == "compact_after_removal_no_fixed_duration",
                {
                    "policy": editor_report.get("timeline_policy"),
                    "duration_input_sec": editor_report.get("duration_input_sec"),
                    "duration_output_sec": editor_report.get("duration_output_sec"),
                    "duration_removed_sec": editor_report.get("duration_removed_sec"),
                },
            )
            add(
                "NATURAL_SOUND_SCENE_POLICY",
                str(editor_report.get("natural_sound_selection_policy") or "")
                == "one_ranked_event_per_scene_with_strict_spacing",
                {
                    "policy": editor_report.get("natural_sound_selection_policy"),
                    "events_selected": editor_report.get("natural_sound_selected"),
                    "scenes_selected": editor_report.get("natural_sound_scenes_selected"),
                },
            )

        temporal_path = self.config.temporal_summary_path
        add("TEMPORAL_REPORT_EXISTS", temporal_path.exists(), {"path": str(temporal_path)})
        if temporal_path.exists():
            temporal = self._read_json(temporal_path)
            add(
                "TEMPORAL_VALIDATED",
                temporal.get("state") == "TEMPORALLY_VALIDATED",
                {"state": temporal.get("state")},
            )
            add(
                "NO_TEMPORAL_VIOLATIONS",
                int(temporal.get("temporal_violations", 0)) == 0,
                {"violations": temporal.get("temporal_violations", 0)},
            )
            add(
                "NO_MODERN_ASSETS_IN_HISTORY",
                int(temporal.get("modern_assets_in_historical", 0)) == 0,
                {"violations": temporal.get("modern_assets_in_historical", 0)},
            )

        if not release:
            preflight_path = self.config.render_preflight_report_path
            add("RENDER_PREFLIGHT_EXISTS", preflight_path.exists(), {"path": str(preflight_path)})
            if preflight_path.exists():
                preflight=self._read_json(preflight_path)
                add(
                    "RENDER_PREFLIGHT_READY",
                    preflight.get("state")=="RENDER_PREFLIGHT_READY",
                    {"state": preflight.get("state")},
                )
            context={
                "mode":"production",
                "timeline":{
                    "items":len(rows),
                    "incomplete":len(incomplete),
                    "unique_assets":len(unique_assets),
                    "media_usage":dict(media_usage),
                    "unique_ratio":round(unique_ratio,4),
                    "average_reuse":round(average_reuse,3),
                    "reused_assets": reused_assets,
                    "repeated_uses_total": repeated_uses_total,
                    "asset_uniqueness_policy": "absolute_one_use_per_film",
                }
            }
            return self._finish(checks, context)

        render_path = self.config.canonical_render_path
        add("RENDER_EXISTS", render_path.exists(), {"path": str(render_path)})
        media_probe = None
        if render_path.exists():
            try:
                media_probe = RenderEngineRC2(self.config).probe(render_path)
                add("RENDER_VALID", True, media_probe.get("format", {}))
            except Exception as exc:
                add("RENDER_VALID", False, {"error": str(exc)})

        postproduction = PostProductionQualityRC2(self.config).analyze()
        post_metrics = postproduction.get("metrics", {})

        add(
            "POSTPRODUCTION_ANALYZED",
            postproduction.get("state") == "ANALYZED",
            {"state": postproduction.get("state")},
        )
        add(
            "NO_EXCLUDED_ASSETS",
            int(post_metrics.get("excluded_assets_used", 0)) == 0,
            {"count": post_metrics.get("excluded_assets_used", 0)},
        )
        add(
            "FILM_DURATION_ACCEPTABLE",
            float(post_metrics.get("film_duration_sec", 0.0))
            <= float(post_metrics.get("maximum_film_duration_sec", 960.0)),
            {
                "duration_sec": post_metrics.get("film_duration_sec"),
                "maximum_sec": post_metrics.get("maximum_film_duration_sec"),
            },
        )
        add(
            "OPENING_HOOK_ACCEPTABLE",
            not bool(post_metrics.get("opening_hook_weak", False)),
            {
                "opening_items": post_metrics.get("opening_items"),
                "opening_unique_assets": post_metrics.get("opening_unique_assets"),
                "opening_video_items": post_metrics.get("opening_video_items"),
            },
            required=False,
        )
        add(
            "STATIC_IMAGE_DURATION_ACCEPTABLE",
            int(post_metrics.get("static_image_overruns", 0)) == 0,
            {"count": post_metrics.get("static_image_overruns", 0)},
            required=False,
        )

        context = {
            "timeline": {
                "items": len(rows),
                "incomplete": len(incomplete),
                "unique_assets": len(unique_assets),
                "media_usage": dict(media_usage),
                "unique_ratio": round(unique_ratio, 4),
                "average_reuse": round(average_reuse, 3),
            },
            "media_probe": media_probe,
            "postproduction": postproduction,
        }
        return self._finish(checks, context)

    def _finish(self, checks: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
        required_passed = all(row["passed"] for row in checks if row.get("required", True))
        warnings = [row for row in checks if not row["passed"] and not row.get("required", True)]
        mode=context.get("mode","release")
        result = {
            "state": (
                "PRODUCTION_READY" if (mode=="production" and required_passed)
                else "PASSED" if required_passed
                else "PRODUCTION_BLOCKED" if mode=="production"
                else "BLOCKED"
            ),
            "project_id": self.config.project_id,
            "checks": checks,
            "warnings": warnings,
            **context,
        }
        self.config.quality_report_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.quality_report_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result
