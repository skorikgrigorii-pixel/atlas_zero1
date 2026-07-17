from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys


VISUAL_TARGET = Path("src/az_enterprise/core/visual_dynamics_alpha272.py")
PROFILE_TARGET = Path("src/az_enterprise/core/project_profiles_alpha273.py")
TEST_TARGET = Path("tests/test_project_profiles_alpha273.py")

TEST_MODULES = [
    "tests.test_postproduction_quality_rc2",
    "tests.test_postproduction_rhythm_alpha271",
    "tests.test_postproduction_visual_alpha272",
    "tests.test_project_profiles_alpha273",
    "tests.test_director_ai_alpha25",
]

PROFILE_MODULE_CONTENT = r'''from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any


@dataclass(frozen=True)
class ProjectProfile:
    name: str
    description: str
    static_sequence_length: int
    maximum_video_gap_sec: float
    repeated_visual_pattern_length: int
    minimum_visual_dynamics_index: float


PROFILES: dict[str, ProjectProfile] = {
    "balanced": ProjectProfile(
        name="balanced",
        description="Universal balanced profile and backward-compatible default.",
        static_sequence_length=3,
        maximum_video_gap_sec=18.0,
        repeated_visual_pattern_length=3,
        minimum_visual_dynamics_index=0.40,
    ),
    "event_short": ProjectProfile(
        name="event_short",
        description="Dynamic short event video such as Hogueras.",
        static_sequence_length=2,
        maximum_video_gap_sec=6.0,
        repeated_visual_pattern_length=3,
        minimum_visual_dynamics_index=0.62,
    ),
    "documentary": ProjectProfile(
        name="documentary",
        description="Measured long-form documentary storytelling.",
        static_sequence_length=6,
        maximum_video_gap_sec=24.0,
        repeated_visual_pattern_length=4,
        minimum_visual_dynamics_index=0.34,
    ),
    "interview": ProjectProfile(
        name="interview",
        description="Interview or talking-head production.",
        static_sequence_length=12,
        maximum_video_gap_sec=90.0,
        repeated_visual_pattern_length=5,
        minimum_visual_dynamics_index=0.20,
    ),
}


def resolve_project_profile(config: Any) -> ProjectProfile:
    requested = str(
        getattr(
            config,
            "project_profile",
            getattr(config, "project_type", "balanced"),
        )
        or "balanced"
    ).strip().lower()

    aliases = {
        "hogueras": "event_short",
        "festival": "event_short",
        "short": "event_short",
        "shorts": "event_short",
        "tiktok": "event_short",
        "youtube_short": "event_short",
        "doc": "documentary",
        "longform_documentary": "documentary",
        "talking_head": "interview",
    }
    profile_name = aliases.get(requested, requested)

    if profile_name not in PROFILES:
        available = ", ".join(sorted(PROFILES))
        raise ValueError(
            f"Unknown project profile {requested!r}. Available profiles: {available}."
        )

    profile = PROFILES[profile_name]
    overrides: dict[str, Any] = {}

    for name in (
        "static_sequence_length",
        "maximum_video_gap_sec",
        "repeated_visual_pattern_length",
        "minimum_visual_dynamics_index",
    ):
        value = getattr(config, name, None)
        if value is not None:
            overrides[name] = value

    if "static_sequence_length" in overrides:
        overrides["static_sequence_length"] = max(
            1, int(overrides["static_sequence_length"])
        )
    if "maximum_video_gap_sec" in overrides:
        overrides["maximum_video_gap_sec"] = max(
            0.0, float(overrides["maximum_video_gap_sec"])
        )
    if "repeated_visual_pattern_length" in overrides:
        overrides["repeated_visual_pattern_length"] = max(
            2, int(overrides["repeated_visual_pattern_length"])
        )
    if "minimum_visual_dynamics_index" in overrides:
        overrides["minimum_visual_dynamics_index"] = min(
            1.0,
            max(0.0, float(overrides["minimum_visual_dynamics_index"])),
        )

    return replace(profile, **overrides)


def profile_to_dict(profile: ProjectProfile) -> dict[str, Any]:
    return asdict(profile)


def available_profiles() -> tuple[str, ...]:
    return tuple(sorted(PROFILES))
'''

VISUAL_MODULE_CONTENT = r'''from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .project_profiles_alpha273 import (
    profile_to_dict,
    resolve_project_profile,
)


def enrich_visual_dynamics(
    *,
    config: Any,
    base_result: dict[str, Any],
    normalize: Callable[[dict[str, Any], int], dict[str, Any]],
) -> dict[str, Any]:
    rows = _load_rows(config=config, normalize=normalize)
    profile = resolve_project_profile(config)

    metrics = base_result.setdefault("metrics", {})
    issues = base_result.setdefault("issues", [])

    static_sequence_length = profile.static_sequence_length
    maximum_video_gap_sec = profile.maximum_video_gap_sec
    repeated_pattern_length = profile.repeated_visual_pattern_length
    minimum_visual_dynamics_index = profile.minimum_visual_dynamics_index

    video_scenes = [row for row in rows if row["visual_type"] == "video"]
    static_scenes = [row for row in rows if row["visual_type"] == "static"]
    scene_count = len(rows)

    video_scene_ratio = len(video_scenes) / scene_count if scene_count else 0.0
    static_scene_ratio = len(static_scenes) / scene_count if scene_count else 0.0

    static_runs = _find_visual_runs(
        rows=rows,
        visual_type="static",
        minimum_length=static_sequence_length,
    )
    video_runs = _find_visual_runs(
        rows=rows,
        visual_type="video",
        minimum_length=1,
    )
    video_gaps = _find_video_gaps(
        rows=rows,
        maximum_gap_sec=maximum_video_gap_sec,
    )
    repeated_patterns = _find_repeated_patterns(
        rows=rows,
        pattern_length=repeated_pattern_length,
    )

    transitions = sum(
        1
        for previous, current in zip(rows, rows[1:])
        if (
            previous["visual_type"] != current["visual_type"]
            or previous["asset_id"] != current["asset_id"]
        )
    )
    transition_ratio = transitions / (scene_count - 1) if scene_count > 1 else 1.0

    unique_assets = len({row["asset_id"] for row in rows if row["asset_id"]})
    variety_index = unique_assets / scene_count if scene_count else 1.0

    total_duration = sum(row["duration_sec"] for row in rows)
    static_run_duration = sum(run["duration_sec"] for run in static_runs)
    static_penalty = min(
        1.0,
        static_run_duration / max(total_duration, 1.0),
    )
    repeated_penalty = min(
        1.0,
        len(repeated_patterns) / max(1, scene_count // 3),
    )

    dynamics_index = max(
        0.0,
        min(
            1.0,
            (
                0.35 * transition_ratio
                + 0.30 * variety_index
                + 0.20 * video_scene_ratio
                + 0.15 * (1.0 - static_penalty)
                - 0.20 * repeated_penalty
            ),
        ),
    )

    existing_issue_keys = {
        (
            issue.get("rule_code"),
            issue.get("timeline_index"),
            issue.get("reason"),
        )
        for issue in issues
    }

    def add_issue(issue: dict[str, Any]) -> None:
        issue.setdefault("project_profile", profile.name)
        key = (
            issue.get("rule_code"),
            issue.get("timeline_index"),
            issue.get("reason"),
        )
        if key not in existing_issue_keys:
            issues.append(issue)
            existing_issue_keys.add(key)

    for run in static_runs:
        add_issue({
            "rule_code": "STATIC_SEQUENCE",
            "severity": "medium",
            "title": "Обнаружена длинная статичная последовательность",
            "reason": (
                f"{run['length']} статичных сцен подряд, "
                f"позиции {run['start_index']}–{run['end_index']}, "
                f"общая длительность {run['duration_sec']:.2f} сек. "
                f"Порог профиля: {static_sequence_length} сцен."
            ),
            "recommendation": (
                "Добавить видео, движение камеры, анимацию, "
                "крупные планы или монтажные перебивки."
            ),
            "timeline_index": run["start_index"],
        })

    for gap in video_gaps:
        add_issue({
            "rule_code": "VIDEO_GAP",
            "severity": "medium",
            "title": "Длинный участок без видеоматериала",
            "reason": (
                f"Позиции {gap['start_index']}–{gap['end_index']}: "
                f"{gap['duration_sec']:.2f} сек. без видео. "
                f"Порог профиля: {maximum_video_gap_sec:.2f} сек."
            ),
            "recommendation": (
                "Добавить видеокадр или визуально активную вставку "
                "внутрь этого участка."
            ),
            "timeline_index": gap["start_index"],
        })

    for pattern in repeated_patterns:
        add_issue({
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

    if scene_count >= 4 and dynamics_index < minimum_visual_dynamics_index:
        add_issue({
            "rule_code": "LOW_VISUAL_DYNAMICS",
            "severity": "high",
            "title": "Низкая визуальная динамика",
            "reason": (
                f"Индекс визуальной динамики: {dynamics_index:.3f}; "
                f"минимум профиля: {minimum_visual_dynamics_index:.3f}; "
                f"доля видео: {video_scene_ratio:.3f}; "
                f"разнообразие: {variety_index:.3f}."
            ),
            "recommendation": (
                "Увеличить сменяемость планов, разнообразие материалов "
                "и долю движущегося изображения."
            ),
        })

    metrics.update({
        "project_profile": profile.name,
        "project_profile_thresholds": profile_to_dict(profile),
        "video_scenes": len(video_scenes),
        "static_scenes": len(static_scenes),
        "video_scene_ratio": round(video_scene_ratio, 4),
        "static_scene_ratio": round(static_scene_ratio, 4),
        "visual_transitions": transitions,
        "visual_transition_ratio": round(transition_ratio, 4),
        "unique_visual_assets": unique_assets,
        "visual_variety_index": round(variety_index, 4),
        "static_sequences": len(static_runs),
        "video_sequences": len(video_runs),
        "video_gaps": len(video_gaps),
        "repeated_visual_patterns": len(repeated_patterns),
        "maximum_static_sequence_length": max(
            (run["length"] for run in static_runs),
            default=0,
        ),
        "maximum_static_sequence_duration_sec": round(
            max((run["duration_sec"] for run in static_runs), default=0.0),
            3,
        ),
        "maximum_video_sequence_length": max(
            (run["length"] for run in video_runs),
            default=0,
        ),
        "visual_dynamics_index": round(dynamics_index, 4),
    })
    return base_result


def _load_rows(
    *,
    config: Any,
    normalize: Callable[[dict[str, Any], int], dict[str, Any]],
) -> list[dict[str, Any]]:
    timeline_path = Path(getattr(config, "timeline_path"))
    payload = json.loads(timeline_path.read_text(encoding="utf-8"))

    if isinstance(payload, list):
        raw_rows = payload
    elif isinstance(payload, dict):
        raw_rows = (
            payload.get("timeline")
            or payload.get("scenes")
            or payload.get("items")
            or []
        )
    else:
        raise ValueError("Unsupported timeline JSON structure.")

    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        normalized = normalize(raw, index)
        normalized["visual_type"] = _visual_type(normalized)
        rows.append(normalized)
    return rows


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


def _find_visual_runs(
    *,
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


def _find_video_gaps(
    *,
    rows: list[dict[str, Any]],
    maximum_gap_sec: float,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    start: int | None = None
    duration = 0.0

    for index, row in enumerate(rows):
        if row["visual_type"] != "video":
            if start is None:
                start = index
            duration += row["duration_sec"]
            continue

        if start is not None and duration > maximum_gap_sec:
            gaps.append({
                "start_index": start,
                "end_index": index - 1,
                "duration_sec": duration,
            })
        start = None
        duration = 0.0

    if start is not None and duration > maximum_gap_sec:
        gaps.append({
            "start_index": start,
            "end_index": len(rows) - 1,
            "duration_sec": duration,
        })

    return gaps


def _find_repeated_patterns(
    *,
    rows: list[dict[str, Any]],
    pattern_length: int,
) -> list[dict[str, int]]:
    if pattern_length < 2 or len(rows) < pattern_length * 2:
        return []

    first_seen: dict[tuple[str, ...], int] = {}
    repeated: list[dict[str, int]] = []

    for index in range(len(rows) - pattern_length + 1):
        pattern = tuple(
            row["visual_type"]
            for row in rows[index:index + pattern_length]
        )
        first_index = first_seen.get(pattern)
        if first_index is None:
            first_seen[pattern] = index
            continue

        if index - first_index >= pattern_length:
            repeated.append({
                "first_index": first_index,
                "repeat_index": index,
                "pattern_length": pattern_length,
            })

    return repeated
'''

TEST_CONTENT = r'''from __future__ import annotations

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
'''


def create_backup(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.alpha273.{stamp}.bak")
    shutil.copy2(path, backup)
    return backup


def restore(path: Path, backup: Path | None, existed_before: bool) -> None:
    if backup and backup.exists():
        shutil.copy2(backup, path)
    elif not existed_before and path.exists():
        path.unlink()


def validate_existing_visual_module(source: str) -> None:
    required_markers = (
        "def enrich_visual_dynamics(",
        "def _find_visual_runs(",
        "def _find_video_gaps(",
        "def _find_repeated_patterns(",
    )
    missing = [marker for marker in required_markers if marker not in source]
    if missing:
        raise RuntimeError(
            "Alpha 2.7.2 v3 module was not detected. "
            f"Missing markers: {', '.join(missing)}"
        )


def run_tests() -> tuple[bool, str]:
    env = os.environ.copy()
    src = str(Path("src").resolve())
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + os.pathsep + current if current else src

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
    if not VISUAL_TARGET.exists():
        print(f"ERROR: file not found: {VISUAL_TARGET}")
        print("Alpha 2.7.2 v3 must be installed first.")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tracked = [VISUAL_TARGET, PROFILE_TARGET, TEST_TARGET]
    existed_before = {path: path.exists() for path in tracked}
    backups = {path: create_backup(path, stamp) for path in tracked}

    try:
        existing_visual = VISUAL_TARGET.read_text(encoding="utf-8")
        validate_existing_visual_module(existing_visual)

        compile(PROFILE_MODULE_CONTENT, str(PROFILE_TARGET), "exec")
        compile(VISUAL_MODULE_CONTENT, str(VISUAL_TARGET), "exec")
        compile(TEST_CONTENT, str(TEST_TARGET), "exec")

        PROFILE_TARGET.write_text(
            PROFILE_MODULE_CONTENT,
            encoding="utf-8",
            newline="\n",
        )
        VISUAL_TARGET.write_text(
            VISUAL_MODULE_CONTENT,
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

    print("Director AI Alpha 2.7.3 Project Profile System applied successfully.")
    for path in tracked:
        backup = backups[path]
        if backup:
            print(f"Backup: {backup}")
        else:
            print(f"Backup not required (new file): {path}")
    print(f"Test modules passed: {len(TEST_MODULES)}")
    print("Default profile: balanced")
    print("Hogueras profile: event_short (alias: hogueras)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
