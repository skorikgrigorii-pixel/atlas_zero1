from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .project_config_rc2 import ProjectConfigRC2
from .render_engine_rc2 import RenderEngineRC2


class QualityGateRC2:
    """Mandatory release gate based on real artifacts, not stage labels."""

    def __init__(self, config: ProjectConfigRC2) -> None:
        self.config = config

    def run(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add(code: str, passed: bool, details: dict[str, Any] | None = None) -> None:
            checks.append({"code": code, "passed": bool(passed), "details": details or {}})

        timeline_path = self.config.timeline_path
        add("TIMELINE_EXISTS", timeline_path.exists(), {"path": str(timeline_path)})
        if not timeline_path.exists():
            return {"state": "BLOCKED", "checks": checks}

        rows = json.loads(timeline_path.read_text(encoding="utf-8"))
        incomplete = [
            row for row in rows
            if row.get("status") != "assigned" or not row.get("asset_path")
        ]
        unique_assets = {
            str(row.get("asset_path")) for row in rows if row.get("asset_path")
        }
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

        passed = all(row["passed"] for row in checks)
        return {
            "state": "PASSED" if passed else "BLOCKED",
            "project_id": self.config.project_id,
            "checks": checks,
            "timeline": {
                "items": len(rows),
                "incomplete": len(incomplete),
                "unique_assets": len(unique_assets),
                "media_usage": dict(media_usage),
            },
            "media_probe": media_probe,
        }
