from __future__ import annotations

import unittest

from az_enterprise.core.recommendation_engine_alpha28 import (
    ActionPlanGenerator,
    DecisionEngine,
    RecommendationEngine,
    build_recommendation_plan,
)


class RecommendationEngineAlpha28Test(unittest.TestCase):
    def test_decision_engine_deduplicates_and_prioritizes(self):
        analysis = {
            "issues": [
                {
                    "rule_code": "STATIC_SEQUENCE",
                    "severity": "medium",
                    "timeline_index": 5,
                    "title": "Static",
                    "reason": "Five stills",
                },
                {
                    "rule_code": "STATIC_SEQUENCE",
                    "severity": "high",
                    "timeline_index": 5,
                    "title": "Static",
                    "reason": "Five stills",
                },
                {
                    "rule_code": "LOW_VISUAL_DYNAMICS",
                    "severity": "high",
                    "title": "Low dynamics",
                    "reason": "Index below profile",
                },
            ]
        }

        decisions = DecisionEngine().build(analysis)

        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[0].rule_code, "LOW_VISUAL_DYNAMICS")
        static = next(
            item
            for item in decisions
            if item.rule_code == "STATIC_SEQUENCE"
        )
        self.assertEqual(static.severity, "high")

    def test_static_sequence_generates_ranked_options(self):
        decisions = DecisionEngine().build({
            "issues": [{
                "rule_code": "STATIC_SEQUENCE",
                "severity": "medium",
                "timeline_index": 3,
                "reason": "Static run",
            }]
        })

        recommendations = RecommendationEngine().build(
            decisions,
            assets=[{
                "asset_id": "clip_184.mp4",
                "media_type": "video",
                "quality_score": 0.91,
                "relevance_score": 0.83,
            }],
        )

        self.assertEqual(len(recommendations), 3)
        insert = next(
            item
            for item in recommendations
            if item.action_type == "insert"
        )
        self.assertTrue(insert.automatic)
        self.assertEqual(
            insert.operation["asset_id"],
            "clip_184.mp4",
        )

    def test_action_plan_selects_one_option_per_decision(self):
        result = build_recommendation_plan({
            "issues": [
                {
                    "rule_code": "VIDEO_GAP",
                    "severity": "high",
                    "timeline_index": 8,
                    "reason": "Long gap",
                },
                {
                    "rule_code": "SCENE_TOO_LONG",
                    "severity": "medium",
                    "timeline_index": 12,
                    "reason": "Long scene",
                },
            ]
        })

        plan = result["action_plan"]

        self.assertEqual(plan["summary"]["decision_count"], 2)
        self.assertEqual(plan["summary"]["operation_count"], 2)
        self.assertEqual(len(plan["operations"]), 2)
        self.assertGreater(
            plan["operations"][0]["priority_score"],
            plan["operations"][1]["priority_score"],
        )

    def test_automatic_only_skips_manual_options(self):
        decisions = DecisionEngine().build({
            "issues": [{
                "rule_code": "UNKNOWN_RULE",
                "severity": "low",
                "reason": "Manual inspection required",
            }]
        })
        recommendations = RecommendationEngine().build(decisions)
        plan = ActionPlanGenerator().build(
            decisions,
            recommendations,
            automatic_only=True,
        )

        self.assertEqual(plan["status"], "no_actions")
        self.assertEqual(plan["summary"]["skipped_count"], 1)

    def test_missing_asset_creates_executable_task(self):
        result = build_recommendation_plan(
            {
                "issues": [{
                    "rule_code": "MISSING_ASSET",
                    "severity": "high",
                    "timeline_index": 4,
                    "reason": "No visual assigned",
                }]
            },
            automatic_only=True,
        )

        operations = result["action_plan"]["operations"]

        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]["type"], "create_task")
        self.assertEqual(
            operations[0]["task_type"],
            "acquire_asset",
        )

    def test_result_contains_stable_public_contract(self):
        result = build_recommendation_plan({
            "issues": [{
                "rule_code": "REPEATED_VISUAL_PATTERN",
                "severity": "low",
                "timeline_index": 6,
                "reason": "Repeated pattern",
            }]
        })

        self.assertEqual(
            result["engine"],
            "recommendation_engine_alpha28",
        )
        self.assertEqual(result["version"], "2.8.0")
        self.assertIn("decisions", result)
        self.assertIn("recommendations", result)
        self.assertIn("action_plan", result)


if __name__ == "__main__":
    unittest.main()
