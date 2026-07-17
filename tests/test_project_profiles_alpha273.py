from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from az_enterprise.core.postproduction_quality_rc2 import PostProductionQualityRC2
from az_enterprise.core.project_profiles_alpha273 import (
    available_profiles,
    resolve_project_profile,
)


class ProjectProfilesAlpha273Test(unittest.TestCase):
    def _analyze(self, rows, project_profile="balanced", **overrides):
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
                minimum_scene_duration_sec=0.1,
                maximum_scene_duration_sec=999.0,
                rhythm_sequence_length=3,
                project_profile=project_profile,
                **overrides,
            )
            return PostProductionQualityRC2(config).analyze()

    def test_profiles_are_available(self):
        self.assertEqual(
            available_profiles(),
            ("balanced", "documentary", "event_short", "interview"),
        )

    def test_hogueras_alias_resolves_to_event_short(self):
        profile = resolve_project_profile(
            SimpleNamespace(project_profile="hogueras")
        )
        self.assertEqual(profile.name, "event_short")

    def test_same_timeline_is_interpreted_by_profile(self):
        rows = [
            {"duration_sec": 4.0, "media_type": "image", "asset_id": "a"},
            {"duration_sec": 4.0, "media_type": "image", "asset_id": "b"},
            {"duration_sec": 4.0, "media_type": "video", "asset_id": "c"},
            {"duration_sec": 4.0, "media_type": "video", "asset_id": "d"},
        ]

        event_result = self._analyze(rows, "event_short")
        documentary_result = self._analyze(rows, "documentary")

        event_codes = {
            issue["rule_code"] for issue in event_result["issues"]
        }
        documentary_codes = {
            issue["rule_code"] for issue in documentary_result["issues"]
        }

        self.assertIn("STATIC_SEQUENCE", event_codes)
        self.assertIn("VIDEO_GAP", event_codes)
        self.assertNotIn("STATIC_SEQUENCE", documentary_codes)
        self.assertNotIn("VIDEO_GAP", documentary_codes)
        self.assertEqual(
            event_result["metrics"]["project_profile"],
            "event_short",
        )
        self.assertEqual(
            documentary_result["metrics"]["project_profile"],
            "documentary",
        )

    def test_project_override_has_priority(self):
        result = self._analyze(
            [
                {"duration_sec": 4.0, "media_type": "image", "asset_id": "a"},
                {"duration_sec": 4.0, "media_type": "image", "asset_id": "b"},
                {"duration_sec": 4.0, "media_type": "video", "asset_id": "c"},
            ],
            "documentary",
            static_sequence_length=2,
            maximum_video_gap_sec=5.0,
        )
        codes = {issue["rule_code"] for issue in result["issues"]}
        self.assertIn("STATIC_SEQUENCE", codes)
        self.assertIn("VIDEO_GAP", codes)

        thresholds = result["metrics"]["project_profile_thresholds"]
        self.assertEqual(thresholds["static_sequence_length"], 2)
        self.assertEqual(thresholds["maximum_video_gap_sec"], 5.0)

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_project_profile(
                SimpleNamespace(project_profile="unknown_format")
            )


if __name__ == "__main__":
    unittest.main()
