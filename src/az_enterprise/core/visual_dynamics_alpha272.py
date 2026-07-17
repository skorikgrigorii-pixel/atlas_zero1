from __future__ import annotations

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
