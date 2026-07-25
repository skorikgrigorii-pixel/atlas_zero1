from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys


TARGET = Path("src/az_enterprise/core/postproduction_quality_rc2.py")
TEST_TARGET = Path("tests/test_postproduction_visual_alpha272.py")

TEST_MODULES = [
    "tests.test_postproduction_quality_rc2",
    "tests.test_postproduction_rhythm_alpha271",
    "tests.test_postproduction_visual_alpha272",
    "tests.test_director_ai_alpha25",
]


def create_backup(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    backup_path = path.with_name(f"{path.name}.alpha272.{stamp}.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def restore_file(path: Path, backup_path: Path | None, existed_before: bool) -> None:
    if backup_path and backup_path.exists():
        shutil.copy2(backup_path, path)
    elif not existed_before and path.exists():
        path.unlink()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patch marker '{label}' expected exactly once, found {count}."
        )
    return text.replace(old, new, 1)


def patch_module(text: str) -> str:
    if '"visual_dynamics_index"' in text:
        raise RuntimeError("Alpha 2.7.2 appears to be already applied.")

    required_markers = [
        '"rhythm_balance_index"',
        "def _find_duration_runs(",
        "minimum_scene_duration_sec",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(
            "Expected Alpha 2.7.1 markers were not found: "
            + ", ".join(missing)
        )

    text = replace_once(
        text,
        '''        rhythm_run_length = int(
            getattr(self.config, "rhythm_sequence_length", 3)
        )
''',
        '''        rhythm_run_length = int(
            getattr(self.config, "rhythm_sequence_length", 3)
        )
        static_sequence_length = int(
            getattr(self.config, "static_sequence_length", 3)
        )
        maximum_video_gap_sec = float(
            getattr(self.config, "maximum_video_gap_sec", 18.0)
        )
        repeated_pattern_length = int(
            getattr(self.config, "repeated_visual_pattern_length", 3)
        )
''',
        "visual configuration",
    )

    text = replace_once(
        text,
        '''        else:
            coefficient_of_variation = 0.0
            rhythm_balance_index = 1.0

        issues: list[dict[str, Any]] = []
''',
        '''        else:
            coefficient_of_variation = 0.0
            rhythm_balance_index = 1.0

        visual_rows = [
            {
                **row,
                "visual_type": self._visual_type(row),
            }
            for row in normalized
        ]
        video_scenes = [
            row for row in visual_rows
            if row["visual_type"] == "video"
        ]
        static_scenes = [
            row for row in visual_rows
            if row["visual_type"] == "static"
        ]
        visual_scene_count = len(visual_rows)
        video_scene_ratio = (
            len(video_scenes) / visual_scene_count
            if visual_scene_count else 0.0
        )
        static_scene_ratio = (
            len(static_scenes) / visual_scene_count
            if visual_scene_count else 0.0
        )

        static_runs = self._find_visual_runs(
            visual_rows,
            "static",
            static_sequence_length,
        )
        video_runs = self._find_visual_runs(
            visual_rows,
            "video",
            1,
        )
        video_gaps = self._find_video_gaps(
            visual_rows,
            maximum_video_gap_sec,
        )
        repeated_patterns = self._find_repeated_visual_patterns(
            visual_rows,
            repeated_pattern_length,
        )

        visual_transitions = sum(
            1
            for previous, current in zip(visual_rows, visual_rows[1:])
            if (
                previous["visual_type"] != current["visual_type"]
                or previous["asset_id"] != current["asset_id"]
            )
        )
        transition_ratio = (
            visual_transitions / (visual_scene_count - 1)
            if visual_scene_count > 1 else 1.0
        )
        unique_visual_assets = len({
            row["asset_id"]
            for row in visual_rows
            if row["asset_id"]
        })
        visual_variety_index = (
            unique_visual_assets / visual_scene_count
            if visual_scene_count else 1.0
        )
        repeated_pattern_penalty = min(
            1.0,
            len(repeated_patterns) / max(1, visual_scene_count // 3),
        )
        static_penalty = min(
            1.0,
            sum(run["duration_sec"] for run in static_runs)
            / max(1.0, total_duration),
        )
        visual_dynamics_index = max(
            0.0,
            min(
                1.0,
                (
                    0.35 * transition_ratio
                    + 0.30 * visual_variety_index
                    + 0.20 * video_scene_ratio
                    + 0.15 * (1.0 - static_penalty)
                    - 0.20 * repeated_pattern_penalty
                ),
            ),
        )

        issues: list[dict[str, Any]] = []
''',
        "visual calculations",
    )

    text = replace_once(
        text,
        '''        if len(durations) >= 4 and rhythm_balance_index < 0.35:
            issues.append({
                "rule_code": "RHYTHM_IMBALANCE",
                "severity": "medium",
                "title": "Ритм фильма несбалансирован",
                "reason": (
                    f"Средняя сцена: {average_scene_duration:.2f} сек.; "
                    f"отклонение: {scene_duration_stddev:.2f} сек.; "
                    f"индекс ритма: {rhythm_balance_index:.3f}."
                ),
                "recommendation": (
                    "Сгладить резкие перепады длительности сцен, "
                    "сохранив осознанное ускорение перед кульминацией."
                ),
            })

        metrics = {
''',
        '''        if len(durations) >= 4 and rhythm_balance_index < 0.35:
            issues.append({
                "rule_code": "RHYTHM_IMBALANCE",
                "severity": "medium",
                "title": "Ритм фильма несбалансирован",
                "reason": (
                    f"Средняя сцена: {average_scene_duration:.2f} сек.; "
                    f"отклонение: {scene_duration_stddev:.2f} сек.; "
                    f"индекс ритма: {rhythm_balance_index:.3f}."
                ),
                "recommendation": (
                    "Сгладить резкие перепады длительности сцен, "
                    "сохранив осознанное ускорение перед кульминацией."
                ),
            })

        for run in static_runs:
            issues.append({
                "rule_code": "STATIC_SEQUENCE",
                "severity": "medium",
                "title": "Обнаружена длинная статичная последовательность",
                "reason": (
                    f"{run['length']} статичных сцен подряд, "
                    f"позиции {run['start_index']}–{run['end_index']}, "
                    f"общая длительность {run['duration_sec']:.2f} сек."
                ),
                "recommendation": (
                    "Добавить видео, движение камеры, анимацию, "
                    "крупные планы или монтажные перебивки."
                ),
                "timeline_index": run["start_index"],
            })

        for gap in video_gaps:
            issues.append({
                "rule_code": "VIDEO_GAP",
                "severity": "medium",
                "title": "Длинный участок без видеоматериала",
                "reason": (
                    f"Позиции {gap['start_index']}–{gap['end_index']}: "
                    f"{gap['duration_sec']:.2f} сек. без видео."
                ),
                "recommendation": (
                    "Добавить видеокадр или визуально активную вставку "
                    "внутрь этого участка."
                ),
                "timeline_index": gap["start_index"],
            })

        for pattern in repeated_patterns:
            issues.append({
                "rule_code": "REPEATED_VISUAL_PATTERN",
                "severity": "low",
                "title": "Повторяется визуальный шаблон",
                "reason": (
                    f"Шаблон длиной {pattern['pattern_length']} сцен "
                    f"повторяется с позиции {pattern['first_index']} "
                    f"на позиции {pattern['repeat_index']}."
                ),
                "recommendation": (
                    "Изменить порядок кадров, тип плана или заменить "
                    "один из повторяющихся визуальных элементов."
                ),
                "timeline_index": pattern["repeat_index"],
            })

        if visual_scene_count >= 4 and visual_dynamics_index < 0.40:
            issues.append({
                "rule_code": "LOW_VISUAL_DYNAMICS",
                "severity": "high",
                "title": "Низкая визуальная динамика",
                "reason": (
                    f"Индекс визуальной динамики: "
                    f"{visual_dynamics_index:.3f}; "
                    f"доля видео: {video_scene_ratio:.3f}; "
                    f"разнообразие: {visual_variety_index:.3f}."
                ),
                "recommendation": (
                    "Увеличить сменяемость планов, разнообразие материалов "
                    "и долю движущегося изображения."
                ),
            })

        metrics = {
''',
        "visual issues",
    )

    text = replace_once(
        text,
        '''            "rhythm_balance_index": round(rhythm_balance_index, 4),
        }
        return {"state": "ANALYZED", "metrics": metrics, "issues": issues}

    @staticmethod
    def _find_duration_runs(
''',
        '''            "rhythm_balance_index": round(rhythm_balance_index, 4),
            "video_scenes": len(video_scenes),
            "static_scenes": len(static_scenes),
            "video_scene_ratio": round(video_scene_ratio, 4),
            "static_scene_ratio": round(static_scene_ratio, 4),
            "visual_transitions": visual_transitions,
            "visual_transition_ratio": round(transition_ratio, 4),
            "unique_visual_assets": unique_visual_assets,
            "visual_variety_index": round(visual_variety_index, 4),
            "static_sequences": len(static_runs),
            "video_sequences": len(video_runs),
            "video_gaps": len(video_gaps),
            "repeated_visual_patterns": len(repeated_patterns),
            "maximum_static_sequence_length": max(
                (run["length"] for run in static_runs),
                default=0,
            ),
            "maximum_static_sequence_duration_sec": round(
                max(
                    (run["duration_sec"] for run in static_runs),
                    default=0.0,
                ),
                3,
            ),
            "maximum_video_sequence_length": max(
                (run["length"] for run in video_runs),
                default=0,
            ),
            "visual_dynamics_index": round(visual_dynamics_index, 4),
        }
        return {"state": "ANALYZED", "metrics": metrics, "issues": issues}

    @staticmethod
    def _visual_type(row: dict[str, Any]) -> str:
        media_type = str(row.get("media_type", "")).strip().lower()
        if media_type in {"video", "clip", "footage"}:
            return "video"
        if media_type in {
            "image",
            "photo",
            "still",
            "illustration",
            "graphic",
        }:
            return "static"
        return "other"

    @staticmethod
    def _find_visual_runs(
        rows: list[dict[str, Any]],
        visual_type: str,
        minimum_length: int,
    ) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        start: int | None = None

        for index, row in enumerate(rows):
            if row["visual_type"] == visual_type:
                if start is None:
                    start = index
                continue

            if start is not None and index - start >= minimum_length:
                selected = rows[start:index]
                runs.append({
                    "start_index": start,
                    "end_index": index - 1,
                    "length": index - start,
                    "duration_sec": sum(
                        item["duration_sec"] for item in selected
                    ),
                })
            start = None

        if start is not None and len(rows) - start >= minimum_length:
            selected = rows[start:]
            runs.append({
                "start_index": start,
                "end_index": len(rows) - 1,
                "length": len(rows) - start,
                "duration_sec": sum(
                    item["duration_sec"] for item in selected
                ),
            })

        return runs

    @staticmethod
    def _find_video_gaps(
        rows: list[dict[str, Any]],
        maximum_gap_sec: float,
    ) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        start: int | None = None

        for index, row in enumerate(rows):
            if row["visual_type"] != "video":
                if start is None:
                    start = index
                continue

            if start is not None:
                selected = rows[start:index]
                duration = sum(item["duration_sec"] for item in selected)
                if duration > maximum_gap_sec:
                    gaps.append({
                        "start_index": start,
                        "end_index": index - 1,
                        "duration_sec": duration,
                    })
            start = None

        if start is not None:
            selected = rows[start:]
            duration = sum(item["duration_sec"] for item in selected)
            if duration > maximum_gap_sec:
                gaps.append({
                    "start_index": start,
                    "end_index": len(rows) - 1,
                    "duration_sec": duration,
                })

        return gaps

    @staticmethod
    def _find_repeated_visual_patterns(
        rows: list[dict[str, Any]],
        pattern_length: int,
    ) -> list[dict[str, int]]:
        if pattern_length < 2 or len(rows) < pattern_length * 2:
            return []

        patterns: dict[tuple[str, ...], int] = {}
        repeated: list[dict[str, int]] = []

        for index in range(len(rows) - pattern_length + 1):
            pattern = tuple(
                row["visual_type"]
                for row in rows[index:index + pattern_length]
            )
            first_index = patterns.get(pattern)
            if first_index is None:
                patterns[pattern] = index
                continue

            if index - first_index >= pattern_length:
                repeated.append({
                    "first_index": first_index,
                    "repeat_index": index,
                    "pattern_length": pattern_length,
                })

        return repeated

    @staticmethod
    def _find_duration_runs(
''',
        "visual metrics and helpers",
    )

    return text


TEST_CONTENT = r'''from __future__ import annotations

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
            {
                "start_sec": 0.0,
                "duration_sec": 4.0,
                "media_type": "image",
                "asset_id": "image-a",
            },
            {
                "start_sec": 4.0,
                "duration_sec": 4.0,
                "media_type": "photo",
                "asset_id": "image-b",
            },
            {
                "start_sec": 8.0,
                "duration_sec": 4.0,
                "media_type": "still",
                "asset_id": "image-c",
            },
            {
                "start_sec": 12.0,
                "duration_sec": 3.0,
                "media_type": "video",
                "asset_id": "video-a",
            },
        ])

        codes = {issue["rule_code"] for issue in result["issues"]}
        self.assertIn("STATIC_SEQUENCE", codes)
        self.assertIn("VIDEO_GAP", codes)
        self.assertEqual(result["metrics"]["static_sequences"], 1)
        self.assertEqual(result["metrics"]["video_gaps"], 1)
        self.assertEqual(
            result["metrics"]["maximum_static_sequence_length"],
            3,
        )

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
        self.assertGreaterEqual(
            result["metrics"]["repeated_visual_patterns"],
            1,
        )

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
'''


def run_tests() -> tuple[bool, str]:
    env = os.environ.copy()
    src_path = str(Path("src").resolve())
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src_path + os.pathsep + current if current else src_path
    )

    command = [
        sys.executable,
        "-m",
        "unittest",
        *TEST_MODULES,
        "-v",
    ]
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        capture_output=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: file not found: {TARGET}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    module_existed = TARGET.exists()
    test_existed = TEST_TARGET.exists()

    module_backup = create_backup(TARGET, stamp)
    test_backup = create_backup(TEST_TARGET, stamp)

    try:
        original = TARGET.read_text(encoding="utf-8")
        patched = patch_module(original)

        compile(patched, str(TARGET), "exec")
        compile(TEST_CONTENT, str(TEST_TARGET), "exec")

        TARGET.write_text(patched, encoding="utf-8", newline="\n")
        TEST_TARGET.write_text(
            TEST_CONTENT,
            encoding="utf-8",
            newline="\n",
        )

        passed, test_output = run_tests()
        print(test_output)

        if not passed:
            raise RuntimeError("One or more tests failed.")

    except Exception as exc:
        restore_file(TARGET, module_backup, module_existed)
        restore_file(TEST_TARGET, test_backup, test_existed)
        print(f"ERROR: {exc}")
        print("Rollback completed. Original files restored.")
        return 1

    print("Director AI Alpha 2.7.2 applied successfully.")
    print(f"Module backup: {module_backup}")
    if test_backup:
        print(f"Test backup: {test_backup}")
    else:
        print("Test backup: not required (new test file)")
    print(f"Created test: {TEST_TARGET}")
    print(f"Test modules passed: {len(TEST_MODULES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
