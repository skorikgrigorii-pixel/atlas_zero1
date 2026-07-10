import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from az_enterprise.core.database import Database
from az_enterprise.core.director_ai import DirectorAI
from az_enterprise.core.story_engine import StoryEngine


class DirectorAIAlpha25Test(unittest.TestCase):
    def _make_db(self, name: str) -> Database:
        suffix = uuid.uuid4().hex
        path = Path("workspace") / f"{name}.{suffix}.sqlite3"
        db = Database(path)
        db.init()
        return db

    def test_assign_assets_generates_tasks_for_missing_material(self):
        db = self._make_db("test_alpha25.sqlite3")

        db.execute(
            "INSERT INTO assets(id, project_id, path, filename, media_type, sha256, category, tags, emotion, quality) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "asset_1",
                "franklin",
                "./assets/ice.jpg",
                "ice.jpg",
                "image",
                "sha1",
                "image",
                "['ice','arctic']",
                "cold",
                0.9,
            ),
        )
        db.execute(
            "INSERT INTO assets(id, project_id, path, filename, media_type, sha256, category, tags, emotion, quality) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "asset_2",
                "franklin",
                "./assets/ship.jpg",
                "ship.jpg",
                "image",
                "sha2",
                "image",
                "['ship','arctic']",
                "isolation",
                0.8,
            ),
        )

        StoryEngine(db, "franklin").build_shots(target_count=8)
        result = DirectorAI(db, "franklin").assign_assets()

        self.assertGreaterEqual(result["missing"], 1)
        self.assertGreaterEqual(db.one("SELECT COUNT(*) c FROM director_tasks WHERE project_id=?", ("franklin",))["c"], 1)
        self.assertGreaterEqual(db.one("SELECT COUNT(*) c FROM operator_tasks WHERE project_id=?", ("franklin",))["c"], 1)

    def test_transition_flow_and_readiness(self):
        db = self._make_db("test_phase1_state.sqlite3")
        ai = DirectorAI(db, "franklin")

        initial = ai.get_project_state()
        self.assertEqual(initial["current_stage"], "NEW")

        ai.transition_project_state("RESEARCH_READY", reason="Research complete")
        ai.transition_project_state("SCRIPT_READY", reason="Script ready")

        readiness = ai.evaluate_project_readiness()
        self.assertEqual(readiness["current_stage"], "SCRIPT_READY")
        self.assertGreaterEqual(readiness["completion_percent"], 25.0)
        self.assertEqual(readiness["overall_status"], "IN_PROGRESS")

    def test_invalid_transition_is_rejected(self):
        db = self._make_db("test_phase1_invalid.sqlite3")
        ai = DirectorAI(db, "franklin")

        with self.assertRaises(ValueError):
            ai.transition_project_state("VISUAL_READY", reason="invalid")

    def test_failed_modules_mark_project_blocked(self):
        db = self._make_db("test_phase1_failed.sqlite3")
        ai = DirectorAI(db, "franklin")

        ai.record_module_failure("research", "Research data missing")
        readiness = ai.evaluate_project_readiness()

        self.assertEqual(readiness["overall_status"], "FAILED")
        self.assertEqual(readiness["current_stage"], "FAILED")
        self.assertTrue(readiness["blocking_errors"])
        self.assertIn("research", readiness["blocking_reason"])

    def test_completed_project_reports_ready(self):
        db = self._make_db("test_phase1_complete.sqlite3")
        ai = DirectorAI(db, "franklin")

        for target in [
            "RESEARCH_READY",
            "SCRIPT_READY",
            "VOICE_READY",
            "VISUAL_READY",
            "EDIT_READY",
            "PACKAGING_READY",
            "FINAL_READY",
        ]:
            ai.transition_project_state(target, reason="progress")

        readiness = ai.evaluate_project_readiness()
        self.assertEqual(readiness["overall_status"], "READY")
        self.assertEqual(readiness["current_stage"], "FINAL_READY")
        self.assertEqual(readiness["completion_percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
