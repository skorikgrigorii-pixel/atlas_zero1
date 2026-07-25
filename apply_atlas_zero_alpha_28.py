from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys


ENGINE_TARGET = Path("src/az_enterprise/core/recommendation_engine_alpha28.py")
TEST_TARGET = Path("tests/test_recommendation_engine_alpha28.py")

TEST_MODULES = [
    "tests.test_postproduction_quality_rc2",
    "tests.test_postproduction_rhythm_alpha271",
    "tests.test_postproduction_visual_alpha272",
    "tests.test_project_profiles_alpha273",
    "tests.test_recommendation_engine_alpha28",
    "tests.test_director_ai_alpha25",
]

ENGINE_CONTENT = r'''from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


SEVERITY_WEIGHT = {
    "critical": 100,
    "high": 75,
    "medium": 45,
    "low": 20,
    "info": 5,
}

RULE_IMPACT = {
    "VIDEO_GAP": 18,
    "STATIC_SEQUENCE": 16,
    "LOW_VISUAL_DYNAMICS": 22,
    "REPEATED_VISUAL_PATTERN": 10,
    "SCENE_TOO_LONG": 14,
    "SCENE_TOO_SHORT": 8,
    "SLOW_SEQUENCE": 12,
    "FAST_SEQUENCE": 9,
    "MISSING_ASSET": 30,
    "EXCLUDED_ASSET": 28,
    "PROJECT_BLOCKED": 40,
}

RULE_CATEGORY = {
    "VIDEO_GAP": "visual",
    "STATIC_SEQUENCE": "visual",
    "LOW_VISUAL_DYNAMICS": "visual",
    "REPEATED_VISUAL_PATTERN": "visual",
    "SCENE_TOO_LONG": "rhythm",
    "SCENE_TOO_SHORT": "rhythm",
    "SLOW_SEQUENCE": "rhythm",
    "FAST_SEQUENCE": "rhythm",
    "MISSING_ASSET": "assets",
    "EXCLUDED_ASSET": "assets",
    "PROJECT_BLOCKED": "system",
}


@dataclass(frozen=True)
class Decision:
    decision_id: str
    rule_code: str
    category: str
    severity: str
    priority_score: int
    expected_impact_percent: int
    timeline_index: int | None
    title: str
    reason: str


@dataclass(frozen=True)
class Recommendation:
    recommendation_id: str
    decision_id: str
    option: str
    action_type: str
    summary: str
    expected_impact_percent: int
    effort_minutes: int
    confidence: float
    automatic: bool
    operation: dict[str, Any]


class DecisionEngine:
    def build(self, analysis_result: dict[str, Any]) -> list[Decision]:
        issues = analysis_result.get("issues") or []
        deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}

        for raw in issues:
            if not isinstance(raw, dict):
                continue

            rule_code = str(raw.get("rule_code") or "UNKNOWN").upper()
            timeline_index = _optional_int(raw.get("timeline_index"))
            reason = str(raw.get("reason") or "")
            severity = str(raw.get("severity") or "medium").lower()
            key = (rule_code, timeline_index, _normalize_text(reason))

            current = deduplicated.get(key)
            if current is None:
                deduplicated[key] = raw
                continue

            old_weight = SEVERITY_WEIGHT.get(
                str(current.get("severity") or "medium").lower(),
                SEVERITY_WEIGHT["medium"],
            )
            new_weight = SEVERITY_WEIGHT.get(
                severity,
                SEVERITY_WEIGHT["medium"],
            )
            if new_weight > old_weight:
                deduplicated[key] = raw

        decisions: list[Decision] = []
        for sequence, raw in enumerate(deduplicated.values(), start=1):
            rule_code = str(raw.get("rule_code") or "UNKNOWN").upper()
            severity = str(raw.get("severity") or "medium").lower()
            timeline_index = _optional_int(raw.get("timeline_index"))
            impact = int(
                raw.get(
                    "expected_impact_percent",
                    RULE_IMPACT.get(rule_code, 8),
                )
            )
            priority = (
                SEVERITY_WEIGHT.get(
                    severity,
                    SEVERITY_WEIGHT["medium"],
                )
                + impact
                + (5 if timeline_index is not None else 0)
            )
            decisions.append(
                Decision(
                    decision_id=f"D{sequence:03d}",
                    rule_code=rule_code,
                    category=RULE_CATEGORY.get(rule_code, "general"),
                    severity=severity,
                    priority_score=priority,
                    expected_impact_percent=max(0, min(100, impact)),
                    timeline_index=timeline_index,
                    title=str(raw.get("title") or rule_code),
                    reason=str(raw.get("reason") or ""),
                )
            )

        decisions.sort(
            key=lambda item: (
                -item.priority_score,
                item.timeline_index
                if item.timeline_index is not None
                else 10**9,
                item.rule_code,
            )
        )

        return [
            Decision(
                decision_id=f"D{index:03d}",
                rule_code=item.rule_code,
                category=item.category,
                severity=item.severity,
                priority_score=item.priority_score,
                expected_impact_percent=item.expected_impact_percent,
                timeline_index=item.timeline_index,
                title=item.title,
                reason=item.reason,
            )
            for index, item in enumerate(decisions, start=1)
        ]


class RecommendationEngine:
    def build(
        self,
        decisions: Iterable[Decision],
        *,
        assets: Iterable[dict[str, Any]] | None = None,
    ) -> list[Recommendation]:
        asset_rows = [
            row for row in (assets or []) if isinstance(row, dict)
        ]
        recommendations: list[Recommendation] = []

        for decision in decisions:
            options = self._options_for(
                decision=decision,
                assets=asset_rows,
            )
            for option_index, option in enumerate(options, start=1):
                recommendations.append(
                    Recommendation(
                        recommendation_id=(
                            f"{decision.decision_id}-R{option_index}"
                        ),
                        decision_id=decision.decision_id,
                        **option,
                    )
                )

        recommendations.sort(
            key=lambda item: (
                item.decision_id,
                -_value_score(item),
                item.effort_minutes,
            )
        )
        return recommendations

    def _options_for(
        self,
        *,
        decision: Decision,
        assets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rule = decision.rule_code
        index = decision.timeline_index

        if rule == "STATIC_SEQUENCE":
            candidate = _best_video_asset(assets)
            return [
                {
                    "option": "A",
                    "action_type": "insert",
                    "summary": "Вставить видеокадр внутрь статичной последовательности.",
                    "expected_impact_percent": 14,
                    "effort_minutes": 4,
                    "confidence": 0.88,
                    "automatic": candidate is not None,
                    "operation": {
                        "type": "insert",
                        "asset_id": candidate.get("asset_id") if candidate else None,
                        "after_scene": index,
                    },
                },
                {
                    "option": "B",
                    "action_type": "animate",
                    "summary": "Добавить панорамирование или увеличение к статичному кадру.",
                    "expected_impact_percent": 9,
                    "effort_minutes": 3,
                    "confidence": 0.78,
                    "automatic": True,
                    "operation": {
                        "type": "animate",
                        "scene": index,
                        "preset": "slow_push_in",
                    },
                },
                {
                    "option": "C",
                    "action_type": "trim",
                    "summary": "Сократить центральную сцену последовательности.",
                    "expected_impact_percent": 7,
                    "effort_minutes": 2,
                    "confidence": 0.73,
                    "automatic": True,
                    "operation": {
                        "type": "trim",
                        "scene": index,
                        "target_duration_sec": 2.4,
                    },
                },
            ]

        if rule == "VIDEO_GAP":
            candidate = _best_video_asset(assets)
            return [
                {
                    "option": "A",
                    "action_type": "insert",
                    "summary": "Добавить видеоклип в длинный участок без видео.",
                    "expected_impact_percent": 17,
                    "effort_minutes": 5,
                    "confidence": 0.90,
                    "automatic": candidate is not None,
                    "operation": {
                        "type": "insert",
                        "asset_id": candidate.get("asset_id") if candidate else None,
                        "after_scene": index,
                    },
                },
                {
                    "option": "B",
                    "action_type": "replace",
                    "summary": "Заменить один статичный кадр видеоматериалом.",
                    "expected_impact_percent": 15,
                    "effort_minutes": 7,
                    "confidence": 0.84,
                    "automatic": candidate is not None,
                    "operation": {
                        "type": "replace",
                        "scene": index,
                        "asset_id": candidate.get("asset_id") if candidate else None,
                    },
                },
            ]

        if rule == "LOW_VISUAL_DYNAMICS":
            return [
                {
                    "option": "A",
                    "action_type": "rebalance",
                    "summary": "Увеличить долю видео и частоту смены планов.",
                    "expected_impact_percent": 20,
                    "effort_minutes": 18,
                    "confidence": 0.82,
                    "automatic": False,
                    "operation": {
                        "type": "rebalance_visuals",
                        "target_video_ratio": 0.65,
                    },
                },
                {
                    "option": "B",
                    "action_type": "reorder",
                    "summary": "Переставить сцены для чередования типов материала.",
                    "expected_impact_percent": 13,
                    "effort_minutes": 9,
                    "confidence": 0.76,
                    "automatic": True,
                    "operation": {
                        "type": "reorder",
                        "strategy": "alternate_visual_types",
                    },
                },
            ]

        if rule == "REPEATED_VISUAL_PATTERN":
            return [
                {
                    "option": "A",
                    "action_type": "swap",
                    "summary": "Поменять местами один из кадров повторяющегося шаблона.",
                    "expected_impact_percent": 8,
                    "effort_minutes": 3,
                    "confidence": 0.81,
                    "automatic": True,
                    "operation": {
                        "type": "swap",
                        "scene_a": index,
                        "scene_b": index + 1 if index is not None else None,
                    },
                },
                {
                    "option": "B",
                    "action_type": "replace",
                    "summary": "Заменить один повторяющийся визуальный элемент.",
                    "expected_impact_percent": 10,
                    "effort_minutes": 6,
                    "confidence": 0.79,
                    "automatic": False,
                    "operation": {
                        "type": "replace",
                        "scene": index,
                        "asset_id": None,
                    },
                },
            ]

        if rule in {"SCENE_TOO_LONG", "SLOW_SEQUENCE"}:
            return [
                {
                    "option": "A",
                    "action_type": "trim",
                    "summary": "Сократить сцену или последовательность до нормы профиля.",
                    "expected_impact_percent": 12,
                    "effort_minutes": 3,
                    "confidence": 0.91,
                    "automatic": True,
                    "operation": {
                        "type": "trim",
                        "scene": index,
                        "target_duration_sec": 3.0,
                    },
                },
                {
                    "option": "B",
                    "action_type": "split",
                    "summary": "Разделить длинную сцену монтажной перебивкой.",
                    "expected_impact_percent": 14,
                    "effort_minutes": 7,
                    "confidence": 0.83,
                    "automatic": False,
                    "operation": {
                        "type": "split",
                        "scene": index,
                        "parts": 2,
                    },
                },
            ]

        if rule in {"SCENE_TOO_SHORT", "FAST_SEQUENCE"}:
            return [
                {
                    "option": "A",
                    "action_type": "extend",
                    "summary": "Увеличить длительность сцены до читаемого значения.",
                    "expected_impact_percent": 7,
                    "effort_minutes": 2,
                    "confidence": 0.84,
                    "automatic": True,
                    "operation": {
                        "type": "extend",
                        "scene": index,
                        "target_duration_sec": 1.2,
                    },
                },
                {
                    "option": "B",
                    "action_type": "merge",
                    "summary": "Объединить короткую сцену с соседней.",
                    "expected_impact_percent": 8,
                    "effort_minutes": 4,
                    "confidence": 0.75,
                    "automatic": False,
                    "operation": {
                        "type": "merge",
                        "scene": index,
                        "with_next": True,
                    },
                },
            ]

        if rule in {"MISSING_ASSET", "EXCLUDED_ASSET"}:
            return [
                {
                    "option": "A",
                    "action_type": "assign_asset",
                    "summary": "Назначить лучший доступный материал из библиотеки.",
                    "expected_impact_percent": 25,
                    "effort_minutes": 4,
                    "confidence": 0.86,
                    "automatic": bool(assets),
                    "operation": {
                        "type": "assign_asset",
                        "scene": index,
                        "asset_id": assets[0].get("asset_id") if assets else None,
                    },
                },
                {
                    "option": "B",
                    "action_type": "create_task",
                    "summary": "Создать задачу на получение недостающего материала.",
                    "expected_impact_percent": 18,
                    "effort_minutes": 1,
                    "confidence": 0.95,
                    "automatic": True,
                    "operation": {
                        "type": "create_task",
                        "task_type": "acquire_asset",
                        "scene": index,
                    },
                },
            ]

        return [
            {
                "option": "A",
                "action_type": "manual_review",
                "summary": "Передать проблему на ручную проверку редактору.",
                "expected_impact_percent": max(
                    1,
                    decision.expected_impact_percent // 2,
                ),
                "effort_minutes": 10,
                "confidence": 0.50,
                "automatic": False,
                "operation": {
                    "type": "manual_review",
                    "rule_code": rule,
                    "scene": index,
                },
            }
        ]


class ActionPlanGenerator:
    def build(
        self,
        decisions: Iterable[Decision],
        recommendations: Iterable[Recommendation],
        *,
        automatic_only: bool = False,
    ) -> dict[str, Any]:
        decision_rows = list(decisions)
        recommendation_rows = list(recommendations)

        by_decision: dict[str, list[Recommendation]] = {}
        for item in recommendation_rows:
            by_decision.setdefault(item.decision_id, []).append(item)

        operations: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for decision in decision_rows:
            options = by_decision.get(decision.decision_id, [])
            if automatic_only:
                options = [item for item in options if item.automatic]

            if not options:
                skipped.append({
                    "decision_id": decision.decision_id,
                    "rule_code": decision.rule_code,
                    "reason": "No eligible recommendation.",
                })
                continue

            selected = max(
                options,
                key=lambda item: (
                    _value_score(item),
                    -item.effort_minutes,
                    item.confidence,
                ),
            )

            operation = dict(selected.operation)
            operation.update({
                "decision_id": decision.decision_id,
                "recommendation_id": selected.recommendation_id,
                "rule_code": decision.rule_code,
                "priority_score": decision.priority_score,
                "expected_impact_percent": selected.expected_impact_percent,
                "effort_minutes": selected.effort_minutes,
                "confidence": selected.confidence,
                "automatic": selected.automatic,
            })
            operations.append(operation)

        operations.sort(
            key=lambda item: (
                -int(item["priority_score"]),
                -int(item["expected_impact_percent"]),
                int(item["effort_minutes"]),
            )
        )

        total_effort = sum(
            int(item["effort_minutes"]) for item in operations
        )
        aggregate_impact = min(
            100,
            sum(
                int(item["expected_impact_percent"])
                for item in operations
            ),
        )

        return {
            "status": "ready" if operations else "no_actions",
            "operations": operations,
            "skipped": skipped,
            "summary": {
                "decision_count": len(decision_rows),
                "operation_count": len(operations),
                "skipped_count": len(skipped),
                "estimated_effort_minutes": total_effort,
                "aggregate_expected_impact_percent": aggregate_impact,
                "automatic_operation_count": sum(
                    1 for item in operations if item["automatic"]
                ),
            },
        }


def build_recommendation_plan(
    analysis_result: dict[str, Any],
    *,
    assets: Iterable[dict[str, Any]] | None = None,
    automatic_only: bool = False,
) -> dict[str, Any]:
    decisions = DecisionEngine().build(analysis_result)
    recommendations = RecommendationEngine().build(
        decisions,
        assets=assets,
    )
    action_plan = ActionPlanGenerator().build(
        decisions,
        recommendations,
        automatic_only=automatic_only,
    )

    return {
        "engine": "recommendation_engine_alpha28",
        "version": "2.8.0",
        "decisions": [asdict(item) for item in decisions],
        "recommendations": [
            asdict(item) for item in recommendations
        ],
        "action_plan": action_plan,
    }


def _best_video_asset(
    assets: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in assets
        if str(row.get("media_type") or "").lower()
        in {"video", "clip", "footage"}
        and not bool(row.get("excluded"))
    ]
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda row: (
            float(row.get("quality_score") or 0.0),
            float(row.get("relevance_score") or 0.0),
            -float(row.get("duration_sec") or 0.0),
        ),
    )


def _value_score(item: Recommendation) -> float:
    return (
        item.expected_impact_percent
        * item.confidence
        / max(1, item.effort_minutes)
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
'''

TEST_CONTENT = r'''from __future__ import annotations

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
'''


def create_backup(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.alpha28.{stamp}.bak")
    shutil.copy2(path, backup)
    return backup


def restore(
    path: Path,
    backup: Path | None,
    existed_before: bool,
) -> None:
    if backup and backup.exists():
        shutil.copy2(backup, path)
    elif not existed_before and path.exists():
        path.unlink()


def run_tests() -> tuple[bool, str]:
    env = os.environ.copy()
    src = str(Path("src").resolve())
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src + os.pathsep + current if current else src
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            *TEST_MODULES,
            "-v",
        ],
        env=env,
        text=True,
        capture_output=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output


def main() -> int:
    required = [
        Path("src/az_enterprise/core/project_profiles_alpha273.py"),
        Path("src/az_enterprise/core/visual_dynamics_alpha272.py"),
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        print("ERROR: Alpha 2.7.3 installation was not detected.")
        for path in missing:
            print(f"Missing: {path}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tracked = [ENGINE_TARGET, TEST_TARGET]
    existed_before = {path: path.exists() for path in tracked}
    backups = {
        path: create_backup(path, stamp)
        for path in tracked
    }

    try:
        compile(ENGINE_CONTENT, str(ENGINE_TARGET), "exec")
        compile(TEST_CONTENT, str(TEST_TARGET), "exec")

        ENGINE_TARGET.write_text(
            ENGINE_CONTENT,
            encoding="utf-8",
            newline="\n",
        )
        TEST_TARGET.write_text(
            TEST_CONTENT,
            encoding="utf-8",
            newline="\n",
        )

        passed, output = run_tests()
        print(output)
        if not passed:
            raise RuntimeError("One or more tests failed.")

    except Exception as exc:
        for path in tracked:
            restore(path, backups[path], existed_before[path])
        print(f"ERROR: {exc}")
        print("Rollback completed. Original files restored.")
        return 1

    print("ATLAS ZERO Alpha 2.8 Recommendation Engine applied successfully.")
    for path in tracked:
        backup = backups[path]
        if backup:
            print(f"Backup: {backup}")
        else:
            print(f"Backup not required (new file): {path}")
    print(f"Test modules passed: {len(TEST_MODULES)}")
    print("Components:")
    print("- Decision Engine")
    print("- Recommendation Engine")
    print("- Action Plan Generator")
    print("Public entry point:")
    print("- build_recommendation_plan(...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
