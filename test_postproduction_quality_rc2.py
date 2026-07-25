from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from az_enterprise.core.postproduction_quality_rc2 import PostProductionQualityRC2


class PostProductionQualityRC2Test(unittest.TestCase):
    def config(self, rows):
        root = Path(tempfile.mkdtemp())
        timeline = root / "timeline.json"
        timeline.write_text(json.dumps(rows), encoding="utf-8")
        return SimpleNamespace(
            project_id="test",
            timeline_path=timeline,
            maximum_film_duration_sec=960.0,
            maximum_static_image_duration_sec=8.0,
            opening_audit_window_sec=15.0,
            minimum_opening_cut_count=3,
            maximum_same_asset_uses=4,
            minimum_asset_reuse_gap=3,
        )

    def test_detects_core_problems(self):
        rows = [{
            "start_sec": 0,
            "duration_sec": 54,
            "media_type": "image",
            "asset_id": "hero",
        }]
        for idx in range(6):
            rows.append({
                "start_sec": 54 + idx * 170,
                "duration_sec": 170,
                "media_type": "image",
                "asset_id": "repeat",
            })

        result = PostProductionQualityRC2(self.config(rows)).analyze()
        codes = {item["rule_code"] for item in result["issues"]}
        self.assertIn("FILM_TOO_LONG", codes)
        self.assertIn("OPENING_HOOK_WEAK", codes)
        self.assertIn("STATIC_IMAGE_TOO_LONG", codes)
        self.assertIn("ASSET_OVERUSED", codes)

    def test_detects_excluded_asset(self):
        result = PostProductionQualityRC2(self.config([{
            "start_sec": 0,
            "duration_sec": 4,
            "media_type": "video",
            "asset_id": "bad",
            "status": "excluded",
        }])).analyze()
        codes = {item["rule_code"] for item in result["issues"]}
        self.assertIn("EXCLUDED_ASSET_USED", codes)


if __name__ == "__main__":
    unittest.main()
