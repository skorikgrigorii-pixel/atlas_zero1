from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from az_enterprise.core.postproduction_quality_rc2 import PostProductionQualityRC2


class PostProductionRhythmAlpha271Test(unittest.TestCase):
    def _analyze(self, rows):
        with tempfile.TemporaryDirectory() as temp_dir:
            timeline_path = Path(temp_dir) / "timeline.json"
            timeline_path.write_text(json.dumps(rows), encoding="utf-8")
            config = SimpleNamespace(
                timeline_path=timeline_path,
                maximum_film_duration_sec=999.0,
                maximum_static_image_duration_sec=999.0,
                opening_audit_window_sec=0.0,
                minimum_opening_cut_count=0,
                maximum_same_asset_uses=99,
                minimum_asset_reuse_gap=0,
                minimum_scene_duration_sec=1.0,
                maximum_scene_duration_sec=10.0,
                rhythm_sequence_length=3,
            )
            return PostProductionQualityRC2(config).analyze()

    def test_detects_short_and_long_scenes(self):
        result = self._analyze([
            {"start_sec": 0.0, "duration_sec": 0.5, "media_type": "video", "asset_id": "short"},
            {"start_sec": 0.5, "duration_sec": 4.0, "media_type": "video", "asset_id": "normal"},
            {"start_sec": 4.5, "duration_sec": 14.0, "media_type": "video", "asset_id": "long"},
        ])
        codes = {issue["rule_code"] for issue in result["issues"]}
        self.assertIn("SCENE_TOO_SHORT", codes)
        self.assertIn("SCENE_TOO_LONG", codes)
        self.assertEqual(result["metrics"]["short_scenes"], 1)
        self.assertEqual(result["metrics"]["long_scenes"], 1)

    def test_detects_fast_and_slow_runs(self):
        result = self._analyze([
            {"start_sec": 0.0, "duration_sec": 0.4, "asset_id": "a"},
            {"start_sec": 0.4, "duration_sec": 0.5, "asset_id": "b"},
            {"start_sec": 0.9, "duration_sec": 0.6, "asset_id": "c"},
            {"start_sec": 1.5, "duration_sec": 4.0, "asset_id": "d"},
            {"start_sec": 5.5, "duration_sec": 12.0, "asset_id": "e"},
            {"start_sec": 17.5, "duration_sec": 13.0, "asset_id": "f"},
            {"start_sec": 30.5, "duration_sec": 14.0, "asset_id": "g"},
        ])
        codes = {issue["rule_code"] for issue in result["issues"]}
        self.assertIn("PACE_TOO_FAST", codes)
        self.assertIn("PACE_TOO_SLOW", codes)
        self.assertEqual(result["metrics"]["short_scene_runs"], 1)
        self.assertEqual(result["metrics"]["long_scene_runs"], 1)

    def test_balanced_timeline_has_rhythm_metrics(self):
        result = self._analyze([
            {"start_sec": 0.0, "duration_sec": 3.0, "asset_id": "a"},
            {"start_sec": 3.0, "duration_sec": 4.0, "asset_id": "b"},
            {"start_sec": 7.0, "duration_sec": 5.0, "asset_id": "c"},
            {"start_sec": 12.0, "duration_sec": 4.0, "asset_id": "d"},
        ])
        metrics = result["metrics"]
        self.assertEqual(metrics["short_scenes"], 0)
        self.assertEqual(metrics["long_scenes"], 0)
        self.assertGreaterEqual(metrics["rhythm_balance_index"], 0.0)
        self.assertLessEqual(metrics["rhythm_balance_index"], 1.0)


if __name__ == "__main__":
    unittest.main()
