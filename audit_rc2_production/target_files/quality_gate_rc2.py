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

    def run(self) -> dict[str, Any]:
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
        add(
            "ASSET_LIBRARY_SUFFICIENT",
            unique_ratio >= self.config.minimum_unique_asset_ratio
            and average_reuse <= self.config.maximum_average_asset_reuse,
            {
                "unique_assets": len(unique_assets),
                "unique_ratio": round(unique_ratio, 4),
                "average_reuse": round(average_reuse, 3),
            },
            required=False,
        )
        add(
            "VIDEO_USAGE_PRESENT",
            media_usage.get("video", 0) >= self.config.minimum_video_shots,
            {"video_shots": media_usage.get("video", 0)},
            required=False,
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
        result = {
            "state": "PASSED" if required_passed else "BLOCKED",
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
