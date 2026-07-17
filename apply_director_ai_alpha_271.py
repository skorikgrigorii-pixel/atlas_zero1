from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys

TARGET = Path('src/az_enterprise/core/postproduction_quality_rc2.py')
TEST_TARGET = Path('tests/test_postproduction_rhythm_alpha271.py')


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = path.with_name(f'{path.name}.alpha271.{stamp}.bak')
    shutil.copy2(path, backup_path)
    return backup_path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patch marker '{label}' expected exactly once, found {count} times."
        )
    return text.replace(old, new, 1)


def patch_module(text: str) -> str:
    text = replace_once(
        text,
        'import json\nfrom collections import defaultdict\nfrom typing import Any\n',
        'import json\nimport statistics\nfrom collections import defaultdict\nfrom typing import Any\n',
        'statistics import',
    )

    text = replace_once(
        text,
        '        min_reuse_gap = int(getattr(self.config, "minimum_asset_reuse_gap", 3))\n',
        '        min_reuse_gap = int(getattr(self.config, "minimum_asset_reuse_gap", 3))\n'
        '        minimum_scene_duration = float(\n'
        '            getattr(self.config, "minimum_scene_duration_sec", 0.75)\n'
        '        )\n'
        '        maximum_scene_duration = float(\n'
        '            getattr(self.config, "maximum_scene_duration_sec", 12.0)\n'
        '        )\n'
        '        rhythm_run_length = int(\n'
        '            getattr(self.config, "rhythm_sequence_length", 3)\n'
        '        )\n',
        'rhythm config',
    )

    marker = '''        natural_ratio = (
            len(natural_audio) / len(video_with_audio)
            if video_with_audio else 1.0
        )

        issues: list[dict[str, Any]] = []
'''
    replacement = '''        natural_ratio = (
            len(natural_audio) / len(video_with_audio)
            if video_with_audio else 1.0
        )

        durations = [row["duration_sec"] for row in normalized]
        average_scene_duration = statistics.fmean(durations) if durations else 0.0
        median_scene_duration = statistics.median(durations) if durations else 0.0
        scene_duration_stddev = (
            statistics.pstdev(durations) if len(durations) > 1 else 0.0
        )
        short_scenes = [
            row for row in normalized
            if 0.0 < row["duration_sec"] < minimum_scene_duration
        ]
        long_scenes = [
            row for row in normalized
            if row["duration_sec"] > maximum_scene_duration
        ]
        short_scene_runs = self._find_duration_runs(
            normalized,
            lambda row: 0.0 < row["duration_sec"] < minimum_scene_duration,
            rhythm_run_length,
        )
        long_scene_runs = self._find_duration_runs(
            normalized,
            lambda row: row["duration_sec"] > maximum_scene_duration,
            rhythm_run_length,
        )
        if average_scene_duration > 0.0:
            coefficient_of_variation = scene_duration_stddev / average_scene_duration
            rhythm_balance_index = max(
                0.0,
                min(1.0, 1.0 - abs(coefficient_of_variation - 0.65)),
            )
        else:
            coefficient_of_variation = 0.0
            rhythm_balance_index = 1.0

        issues: list[dict[str, Any]] = []
'''
    text = replace_once(text, marker, replacement, 'rhythm calculations')

    marker = '''        metrics = {
            "film_duration_sec": round(total_duration, 3),
'''
    issues_block = '''        for row in short_scenes:
            issues.append({
                "rule_code": "SCENE_TOO_SHORT",
                "severity": "low",
                "title": "Сцена слишком короткая",
                "reason": f"Позиция {row['index']}: {row['duration_sec']:.2f} сек.",
                "recommendation": (
                    f"Проверить необходимость сцены или увеличить её "
                    f"до {minimum_scene_duration:g} сек."
                ),
                "asset_id": row["asset_id"],
                "timeline_index": row["index"],
            })

        for row in long_scenes:
            issues.append({
                "rule_code": "SCENE_TOO_LONG",
                "severity": "medium",
                "title": "Сцена слишком длинная",
                "reason": f"Позиция {row['index']}: {row['duration_sec']:.2f} сек.",
                "recommendation": (
                    f"Сократить сцену, разделить её сменой плана или удерживать "
                    f"не более {maximum_scene_duration:g} сек."
                ),
                "asset_id": row["asset_id"],
                "timeline_index": row["index"],
            })

        for run in short_scene_runs:
            issues.append({
                "rule_code": "PACE_TOO_FAST",
                "severity": "medium",
                "title": "Темп монтажа слишком высокий",
                "reason": (
                    f"{run['length']} коротких сцен подряд: позиции "
                    f"{run['start_index']}–{run['end_index']}."
                ),
                "recommendation": (
                    "Добавить более длинный опорный кадр, чтобы зритель "
                    "успел воспринять информацию."
                ),
                "timeline_index": run["start_index"],
            })

        for run in long_scene_runs:
            issues.append({
                "rule_code": "PACE_TOO_SLOW",
                "severity": "medium",
                "title": "Темп монтажа слишком низкий",
                "reason": (
                    f"{run['length']} длинных сцен подряд: позиции "
                    f"{run['start_index']}–{run['end_index']}."
                ),
                "recommendation": (
                    "Ускорить последовательность сменой планов, вставками "
                    "или сокращением сцен."
                ),
                "timeline_index": run["start_index"],
            })

        if len(durations) >= 4 and rhythm_balance_index < 0.35:
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
                    "Сгладить резкие перепады длительности сцен, сохранив "
                    "осознанное ускорение перед кульминацией."
                ),
            })

        metrics = {
            "film_duration_sec": round(total_duration, 3),
'''
    text = replace_once(text, marker, issues_block, 'rhythm issues')

    marker = '''            "natural_audio_ratio": round(natural_ratio, 4),
        }
        return {"state": "ANALYZED", "metrics": metrics, "issues": issues}

    @staticmethod
    def _normalize(row: dict[str, Any], index: int) -> dict[str, Any]:
'''
    replacement = '''            "natural_audio_ratio": round(natural_ratio, 4),
            "minimum_scene_duration_sec": minimum_scene_duration,
            "maximum_scene_duration_sec": maximum_scene_duration,
            "minimum_observed_scene_duration_sec": round(min(durations), 3) if durations else 0.0,
            "maximum_observed_scene_duration_sec": round(max(durations), 3) if durations else 0.0,
            "average_scene_duration_sec": round(average_scene_duration, 3),
            "median_scene_duration_sec": round(median_scene_duration, 3),
            "scene_duration_stddev_sec": round(scene_duration_stddev, 3),
            "scene_duration_coefficient_of_variation": round(coefficient_of_variation, 4),
            "short_scenes": len(short_scenes),
            "long_scenes": len(long_scenes),
            "short_scene_runs": len(short_scene_runs),
            "long_scene_runs": len(long_scene_runs),
            "rhythm_balance_index": round(rhythm_balance_index, 4),
        }
        return {"state": "ANALYZED", "metrics": metrics, "issues": issues}

    @staticmethod
    def _find_duration_runs(rows, predicate, minimum_length: int):
        runs = []
        start = None
        for index, row in enumerate(rows):
            if predicate(row):
                if start is None:
                    start = index
                continue
            if start is not None and index - start >= minimum_length:
                runs.append({
                    "start_index": start,
                    "end_index": index - 1,
                    "length": index - start,
                })
            start = None
        if start is not None and len(rows) - start >= minimum_length:
            runs.append({
                "start_index": start,
                "end_index": len(rows) - 1,
                "length": len(rows) - start,
            })
        return runs

    @staticmethod
    def _normalize(row: dict[str, Any], index: int) -> dict[str, Any]:
'''
    text = replace_once(text, marker, replacement, 'rhythm metrics helper')
    return text


TEST_CONTENT = '''from __future__ import annotations

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
'''


def main() -> int:
    if not TARGET.exists():
        print(f'ERROR: file not found: {TARGET}')
        return 1

    module_backup = backup(TARGET)
    test_backup = backup(TEST_TARGET)

    original = TARGET.read_text(encoding='utf-8')
    patched = patch_module(original)
    TARGET.write_text(patched, encoding='utf-8', newline='\n')
    TEST_TARGET.write_text(TEST_CONTENT, encoding='utf-8', newline='\n')

    print('Director AI Alpha 2.7.1 applied successfully.')
    print(f'Module backup: {module_backup}')
    if test_backup:
        print(f'Test backup: {test_backup}')
    else:
        print('Test backup: not required (new test file)')
    print(f'Created test: {TEST_TARGET}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {exc}')
        sys.exit(1)
