from __future__ import annotations

import ast
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


TARGET = Path("src/az_enterprise/core/postproduction_quality_rc2.py")
TEST_TARGET = Path("tests/test_postproduction_visual_alpha272.py")
TEST_MODULES = [
    "tests.test_postproduction_quality_rc2",
    "tests.test_postproduction_rhythm_alpha271",
    "tests.test_postproduction_visual_alpha272",
    "tests.test_director_ai_alpha25",
]

WRAPPER_BODY = 'def analyze(self) -> dict[str, Any]:\n    """Run Alpha 2.7.1 checks and enrich the report with visual dynamics."""\n    result = self._analyze_alpha271()\n    rows = self._load_visual_rows_alpha272()\n\n    metrics = result.setdefault("metrics", {})\n    issues = result.setdefault("issues", [])\n\n    static_sequence_length = max(\n        1,\n        int(getattr(self.config, "static_sequence_length", 3)),\n    )\n    maximum_video_gap_sec = float(\n        getattr(self.config, "maximum_video_gap_sec", 18.0)\n    )\n    repeated_pattern_length = max(\n        2,\n        int(getattr(self.config, "repeated_visual_pattern_length", 3)),\n    )\n\n    video_scenes = [row for row in rows if row["visual_type"] == "video"]\n    static_scenes = [row for row in rows if row["visual_type"] == "static"]\n    scene_count = len(rows)\n\n    video_scene_ratio = len(video_scenes) / scene_count if scene_count else 0.0\n    static_scene_ratio = len(static_scenes) / scene_count if scene_count else 0.0\n\n    static_runs = self._find_visual_runs_alpha272(\n        rows, "static", static_sequence_length\n    )\n    video_runs = self._find_visual_runs_alpha272(rows, "video", 1)\n    video_gaps = self._find_video_gaps_alpha272(\n        rows, maximum_video_gap_sec\n    )\n    repeated_patterns = self._find_repeated_patterns_alpha272(\n        rows, repeated_pattern_length\n    )\n\n    transitions = sum(\n        1\n        for previous, current in zip(rows, rows[1:])\n        if (\n            previous["visual_type"] != current["visual_type"]\n            or previous["asset_id"] != current["asset_id"]\n        )\n    )\n    transition_ratio = transitions / (scene_count - 1) if scene_count > 1 else 1.0\n\n    unique_assets = len({\n        row["asset_id"] for row in rows if row["asset_id"]\n    })\n    variety_index = unique_assets / scene_count if scene_count else 1.0\n\n    total_duration = sum(row["duration_sec"] for row in rows)\n    static_run_duration = sum(run["duration_sec"] for run in static_runs)\n    static_penalty = min(\n        1.0, static_run_duration / max(total_duration, 1.0)\n    )\n    repeated_penalty = min(\n        1.0, len(repeated_patterns) / max(1, scene_count // 3)\n    )\n\n    dynamics_index = max(\n        0.0,\n        min(\n            1.0,\n            (\n                0.35 * transition_ratio\n                + 0.30 * variety_index\n                + 0.20 * video_scene_ratio\n                + 0.15 * (1.0 - static_penalty)\n                - 0.20 * repeated_penalty\n            ),\n        ),\n    )\n\n    existing_issue_keys = {\n        (\n            issue.get("rule_code"),\n            issue.get("timeline_index"),\n            issue.get("reason"),\n        )\n        for issue in issues\n    }\n\n    def add_issue(issue: dict[str, Any]) -> None:\n        key = (\n            issue.get("rule_code"),\n            issue.get("timeline_index"),\n            issue.get("reason"),\n        )\n        if key not in existing_issue_keys:\n            issues.append(issue)\n            existing_issue_keys.add(key)\n\n    for run in static_runs:\n        add_issue({\n            "rule_code": "STATIC_SEQUENCE",\n            "severity": "medium",\n            "title": "Обнаружена длинная статичная последовательность",\n            "reason": (\n                f"{run[\'length\']} статичных сцен подряд, "\n                f"позиции {run[\'start_index\']}–{run[\'end_index\']}, "\n                f"общая длительность {run[\'duration_sec\']:.2f} сек."\n            ),\n            "recommendation": (\n                "Добавить видео, движение камеры, анимацию, "\n                "крупные планы или монтажные перебивки."\n            ),\n            "timeline_index": run["start_index"],\n        })\n\n    for gap in video_gaps:\n        add_issue({\n            "rule_code": "VIDEO_GAP",\n            "severity": "medium",\n            "title": "Длинный участок без видеоматериала",\n            "reason": (\n                f"Позиции {gap[\'start_index\']}–{gap[\'end_index\']}: "\n                f"{gap[\'duration_sec\']:.2f} сек. без видео."\n            ),\n            "recommendation": (\n                "Добавить видеокадр или визуально активную вставку "\n                "внутрь этого участка."\n            ),\n            "timeline_index": gap["start_index"],\n        })\n\n    for pattern in repeated_patterns:\n        add_issue({\n            "rule_code": "REPEATED_VISUAL_PATTERN",\n            "severity": "low",\n            "title": "Повторяется визуальный шаблон",\n            "reason": (\n                f"Шаблон длиной {pattern[\'pattern_length\']} сцен "\n                f"повторяется с позиции {pattern[\'first_index\']} "\n                f"на позиции {pattern[\'repeat_index\']}."\n            ),\n            "recommendation": (\n                "Изменить порядок кадров, тип плана или заменить "\n                "один из повторяющихся визуальных элементов."\n            ),\n            "timeline_index": pattern["repeat_index"],\n        })\n\n    if scene_count >= 4 and dynamics_index < 0.40:\n        add_issue({\n            "rule_code": "LOW_VISUAL_DYNAMICS",\n            "severity": "high",\n            "title": "Низкая визуальная динамика",\n            "reason": (\n                f"Индекс визуальной динамики: {dynamics_index:.3f}; "\n                f"доля видео: {video_scene_ratio:.3f}; "\n                f"разнообразие: {variety_index:.3f}."\n            ),\n            "recommendation": (\n                "Увеличить сменяемость планов, разнообразие материалов "\n                "и долю движущегося изображения."\n            ),\n        })\n\n    metrics.update({\n        "video_scenes": len(video_scenes),\n        "static_scenes": len(static_scenes),\n        "video_scene_ratio": round(video_scene_ratio, 4),\n        "static_scene_ratio": round(static_scene_ratio, 4),\n        "visual_transitions": transitions,\n        "visual_transition_ratio": round(transition_ratio, 4),\n        "unique_visual_assets": unique_assets,\n        "visual_variety_index": round(variety_index, 4),\n        "static_sequences": len(static_runs),\n        "video_sequences": len(video_runs),\n        "video_gaps": len(video_gaps),\n        "repeated_visual_patterns": len(repeated_patterns),\n        "maximum_static_sequence_length": max(\n            (run["length"] for run in static_runs), default=0\n        ),\n        "maximum_static_sequence_duration_sec": round(\n            max((run["duration_sec"] for run in static_runs), default=0.0),\n            3,\n        ),\n        "maximum_video_sequence_length": max(\n            (run["length"] for run in video_runs), default=0\n        ),\n        "visual_dynamics_index": round(dynamics_index, 4),\n    })\n    return result\n\ndef _load_visual_rows_alpha272(self) -> list[dict[str, Any]]:\n    timeline_path = Path(getattr(self.config, "timeline_path"))\n    payload = json.loads(timeline_path.read_text(encoding="utf-8"))\n\n    if isinstance(payload, list):\n        raw_rows = payload\n    elif isinstance(payload, dict):\n        raw_rows = (\n            payload.get("timeline")\n            or payload.get("scenes")\n            or payload.get("items")\n            or []\n        )\n    else:\n        raise ValueError("Unsupported timeline JSON structure.")\n\n    rows: list[dict[str, Any]] = []\n    for index, raw in enumerate(raw_rows):\n        normalized = self._normalize(raw, index)\n        normalized["visual_type"] = self._visual_type_alpha272(normalized)\n        rows.append(normalized)\n    return rows\n\n@staticmethod\ndef _visual_type_alpha272(row: dict[str, Any]) -> str:\n    media_type = str(row.get("media_type", "")).strip().lower()\n    if media_type in {"video", "clip", "footage"}:\n        return "video"\n    if media_type in {\n        "image", "photo", "still", "illustration", "graphic"\n    }:\n        return "static"\n    return "other"\n\n@staticmethod\ndef _find_visual_runs_alpha272(\n    rows: list[dict[str, Any]],\n    visual_type: str,\n    minimum_length: int,\n) -> list[dict[str, Any]]:\n    runs: list[dict[str, Any]] = []\n    start: int | None = None\n\n    for index, row in enumerate(rows):\n        if row["visual_type"] == visual_type:\n            if start is None:\n                start = index\n            continue\n\n        if start is not None and index - start >= minimum_length:\n            selected = rows[start:index]\n            runs.append({\n                "start_index": start,\n                "end_index": index - 1,\n                "length": index - start,\n                "duration_sec": sum(\n                    item["duration_sec"] for item in selected\n                ),\n            })\n        start = None\n\n    if start is not None and len(rows) - start >= minimum_length:\n        selected = rows[start:]\n        runs.append({\n            "start_index": start,\n            "end_index": len(rows) - 1,\n            "length": len(rows) - start,\n            "duration_sec": sum(\n                item["duration_sec"] for item in selected\n            ),\n        })\n\n    return runs\n\n@staticmethod\ndef _find_video_gaps_alpha272(\n    rows: list[dict[str, Any]],\n    maximum_gap_sec: float,\n) -> list[dict[str, Any]]:\n    gaps: list[dict[str, Any]] = []\n    start: int | None = None\n\n    for index, row in enumerate(rows):\n        if row["visual_type"] != "video":\n            if start is None:\n                start = index\n            continue\n\n        if start is not None:\n            selected = rows[start:index]\n            duration = sum(item["duration_sec"] for item in selected)\n            if duration > maximum_gap_sec:\n                gaps.append({\n                    "start_index": start,\n                    "end_index": index - 1,\n                    "duration_sec": duration,\n                })\n        start = None\n\n    if start is not None:\n        selected = rows[start:]\n        duration = sum(item["duration_sec"] for item in selected)\n        if duration > maximum_gap_sec:\n            gaps.append({\n                "start_index": start,\n                "end_index": len(rows) - 1,\n                "duration_sec": duration,\n            })\n\n    return gaps\n\n@staticmethod\ndef _find_repeated_patterns_alpha272(\n    rows: list[dict[str, Any]],\n    pattern_length: int,\n) -> list[dict[str, int]]:\n    if pattern_length < 2 or len(rows) < pattern_length * 2:\n        return []\n\n    first_seen: dict[tuple[str, ...], int] = {}\n    repeated: list[dict[str, int]] = []\n\n    for index in range(len(rows) - pattern_length + 1):\n        pattern = tuple(\n            row["visual_type"]\n            for row in rows[index:index + pattern_length]\n        )\n        first_index = first_seen.get(pattern)\n        if first_index is None:\n            first_seen[pattern] = index\n            continue\n\n        if index - first_index >= pattern_length:\n            repeated.append({\n                "first_index": first_index,\n                "repeat_index": index,\n                "pattern_length": pattern_length,\n            })\n\n    return repeated'
TEST_CONTENT = 'from __future__ import annotations\n\nimport json\nimport tempfile\nimport unittest\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nfrom az_enterprise.core.postproduction_quality_rc2 import PostProductionQualityRC2\n\n\nclass PostProductionVisualAlpha272Test(unittest.TestCase):\n    def _analyze(self, rows):\n        with tempfile.TemporaryDirectory() as temp_dir:\n            timeline_path = Path(temp_dir) / "timeline.json"\n            timeline_path.write_text(json.dumps(rows), encoding="utf-8")\n            config = SimpleNamespace(\n                timeline_path=timeline_path,\n                maximum_film_duration_sec=999.0,\n                maximum_static_image_duration_sec=999.0,\n                opening_audit_window_sec=0.0,\n                minimum_opening_cut_count=0,\n                maximum_same_asset_uses=99,\n                minimum_asset_reuse_gap=0,\n                minimum_scene_duration_sec=0.1,\n                maximum_scene_duration_sec=999.0,\n                rhythm_sequence_length=3,\n                static_sequence_length=3,\n                maximum_video_gap_sec=10.0,\n                repeated_visual_pattern_length=3,\n            )\n            return PostProductionQualityRC2(config).analyze()\n\n    def test_detects_static_sequence_and_video_gap(self):\n        result = self._analyze([\n            {"duration_sec": 4.0, "media_type": "image", "asset_id": "a"},\n            {"duration_sec": 4.0, "media_type": "photo", "asset_id": "b"},\n            {"duration_sec": 4.0, "media_type": "still", "asset_id": "c"},\n            {"duration_sec": 3.0, "media_type": "video", "asset_id": "d"},\n        ])\n        codes = {issue["rule_code"] for issue in result["issues"]}\n        self.assertIn("STATIC_SEQUENCE", codes)\n        self.assertIn("VIDEO_GAP", codes)\n        self.assertEqual(result["metrics"]["static_sequences"], 1)\n        self.assertEqual(result["metrics"]["video_gaps"], 1)\n\n    def test_detects_repeated_visual_pattern(self):\n        result = self._analyze([\n            {"duration_sec": 2.0, "media_type": "video", "asset_id": "a"},\n            {"duration_sec": 2.0, "media_type": "image", "asset_id": "b"},\n            {"duration_sec": 2.0, "media_type": "video", "asset_id": "c"},\n            {"duration_sec": 2.0, "media_type": "video", "asset_id": "d"},\n            {"duration_sec": 2.0, "media_type": "image", "asset_id": "e"},\n            {"duration_sec": 2.0, "media_type": "video", "asset_id": "f"},\n        ])\n        codes = {issue["rule_code"] for issue in result["issues"]}\n        self.assertIn("REPEATED_VISUAL_PATTERN", codes)\n\n    def test_dynamic_timeline_has_bounded_indices(self):\n        result = self._analyze([\n            {"duration_sec": 2.0, "media_type": "video", "asset_id": "a"},\n            {"duration_sec": 2.0, "media_type": "image", "asset_id": "b"},\n            {"duration_sec": 2.0, "media_type": "video", "asset_id": "c"},\n            {"duration_sec": 2.0, "media_type": "graphic", "asset_id": "d"},\n            {"duration_sec": 2.0, "media_type": "video", "asset_id": "e"},\n        ])\n        metrics = result["metrics"]\n        self.assertGreaterEqual(metrics["visual_variety_index"], 0.0)\n        self.assertLessEqual(metrics["visual_variety_index"], 1.0)\n        self.assertGreaterEqual(metrics["visual_dynamics_index"], 0.0)\n        self.assertLessEqual(metrics["visual_dynamics_index"], 1.0)\n        self.assertEqual(metrics["video_scenes"], 3)\n        self.assertEqual(metrics["static_scenes"], 2)\n\n\nif __name__ == "__main__":\n    unittest.main()\n'


def create_backup(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    backup_path = path.with_name(f"{path.name}.alpha272v2.{stamp}.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def restore_file(path: Path, backup_path: Path | None, existed_before: bool) -> None:
    if backup_path and backup_path.exists():
        shutil.copy2(backup_path, path)
    elif not existed_before and path.exists():
        path.unlink()


def find_class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise RuntimeError(f"Class {name!r} was not found.")


def find_method(class_node: ast.ClassDef, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one method {name!r}, found {len(matches)}."
        )
    return matches[0]


def build_wrapper(indent: str) -> str:
    return "\n".join(
        indent + line if line else ""
        for line in WRAPPER_BODY.splitlines()
    ) + "\n"


def patch_module(source: str) -> str:
    if "def _analyze_alpha271(" in source:
        raise RuntimeError("Alpha 2.7.2 v2 appears to be already applied.")
    if '"visual_dynamics_index"' in source:
        raise RuntimeError("Visual dynamics code already exists.")

    tree = ast.parse(source)
    class_node = find_class(tree, "PostProductionQualityRC2")
    analyze_node = find_method(class_node, "analyze")

    args = list(analyze_node.args.posonlyargs) + list(analyze_node.args.args)
    if len(args) != 1 or args[0].arg != "self":
        raise RuntimeError("Expected analyze(self) signature.")

    lines = source.splitlines(keepends=True)
    def_index = analyze_node.lineno - 1
    if "def analyze(" not in lines[def_index]:
        raise RuntimeError("Could not safely rename analyze method.")

    lines[def_index] = lines[def_index].replace(
        "def analyze(", "def _analyze_alpha271(", 1
    )

    indent = " " * analyze_node.col_offset
    insertion_index = analyze_node.end_lineno
    lines.insert(insertion_index, "\n" + build_wrapper(indent))

    patched = "".join(lines)
    ast.parse(patched)
    compile(patched, str(TARGET), "exec")
    return patched


def run_tests() -> tuple[bool, str]:
    env = os.environ.copy()
    src_path = str(Path("src").resolve())
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path + (os.pathsep + current if current else "")

    command = [sys.executable, "-m", "unittest", *TEST_MODULES, "-v"]
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
        compile(TEST_CONTENT, str(TEST_TARGET), "exec")

        TARGET.write_text(patched, encoding="utf-8", newline="\n")
        TEST_TARGET.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")

        passed, output = run_tests()
        print(output)
        if not passed:
            raise RuntimeError("One or more tests failed.")

    except Exception as exc:
        restore_file(TARGET, module_backup, module_existed)
        restore_file(TEST_TARGET, test_backup, test_existed)
        print(f"ERROR: {exc}")
        print("Rollback completed. Original files restored.")
        return 1

    print("Director AI Alpha 2.7.2 v2 applied successfully.")
    print(f"Module backup: {module_backup}")
    print(
        f"Test backup: {test_backup}"
        if test_backup
        else "Test backup: not required (new test file)"
    )
    print(f"Created test: {TEST_TARGET}")
    print(f"Test modules passed: {len(TEST_MODULES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
