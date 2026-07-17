from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from az_enterprise.core.postproduction_quality_rc2 import PostProductionQualityRC2


class PostProductionVisualAlpha272Test(unittest.TestCase):
    def _analyze(self, rows):
        with tempfile.TemporaryDirectory() as temp_dir:
            timeline_path = Path(temp_dir) / "timeline.json"
            timeline_path.write_text(
                json.dumps(rows),
                encoding="utf-8",
            )
            config = SimpleNamespace(
                timeline_path=timeline_path,
                maximum_film_duration_sec=999.0,
                maximum_static_image_duration_sec=999.0,
                opening_audit_window_sec=0.0,
                minimum_opening_cut_count=0,
                maximum_same_asset_uses=99,
                minimum_asset_reuse_gap=0,
                minimum_scene_duration_sec=0.1,
                maximum_scene_duration_sec=999.0,
                rhythm_sequence_length=3,
                static_sequence_length=3,
                maximum_video_gap_sec=10.0,
                repeated_visual_pattern_length=3,
            )
            return PostProductionQualityRC2(config).analyze()

    def test_detects_static_sequence_and_video_gap(self):
        result = self._analyze([
            {"duration_sec": 4.0, "media_type": "image", "asset_id": "a"},
            {"duration_sec": 4.0, "media_type": "photo", "asset_id": "b"},
            {"duration_sec": 4.0, "media_type": "still", "asset_id": "c"},
            {"duration_sec": 3.0, "media_type": "video", "asset_id": "d"},
        ])
        codes = {issue["rule_code"] for issue in result["issues"]}
        self.assertIn("STATIC_SEQUENCE", codes)
        self.assertIn("VIDEO_GAP", codes)
        self.assertEqual(result["metrics"]["static_sequences"], 1)
        self.assertEqual(result["metrics"]["video_gaps"], 1)

    def test_detects_repeated_visual_pattern(self):
        result = self._analyze([
            {"duration_sec": 2.0, "media_type": "video", "asset_id": "a"},
            {"duration_sec": 2.0, "media_type": "image", "asset_id": "b"},
            {"duration_sec": 2.0, "media_type": "video", "asset_id": "c"},
            {"duration_sec": 2.0, "media_type": "video", "asset_id": "d"},
            {"duration_sec": 2.0, "media_type": "image", "asset_id": "e"},
            {"duration_sec": 2.0, "media_type": "video", "asset_id": "f"},
        ])
        codes = {issue["rule_code"] for issue in result["issues"]}
        self.assertIn("REPEATED_VISUAL_PATTERN", codes)

    def test_dynamic_timeline_has_bounded_indices(self):
        result = self._analyze([
            {"duration_sec": 2.0, "media_type": "video", "asset_id": "a"},
            {"duration_sec": 2.0, "media_type": "image", "asset_id": "b"},
            {"duration_sec": 2.0, "media_type": "video", "asset_id": "c"},
            {"duration_sec": 2.0, "media_type": "graphic", "asset_id": "d"},
            {"duration_sec": 2.0, "media_type": "video", "asset_id": "e"},
        ])
        metrics = result["metrics"]
        self.assertGreaterEqual(metrics["visual_variety_index"], 0.0)
        self.assertLessEqual(metrics["visual_variety_index"], 1.0)
        self.assertGreaterEqual(metrics["visual_dynamics_index"], 0.0)
        self.assertLessEqual(metrics["visual_dynamics_index"], 1.0)
        self.assertEqual(metrics["video_scenes"], 3)
        self.assertEqual(metrics["static_scenes"], 2)


if __name__ == "__main__":
    unittest.main()
