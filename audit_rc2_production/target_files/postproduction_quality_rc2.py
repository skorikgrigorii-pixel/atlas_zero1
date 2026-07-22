from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Any


class PostProductionQualityRC2:
    """Stateless post-production metrics helper owned by DirectorAIRuntime."""

    def __init__(self, config) -> None:
        self.config = config

    @staticmethod
    def _read_json(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def _analyze_alpha271(self) -> dict[str, Any]:
        path = self.config.timeline_path
        if not path.exists():
            return {
                "state": "MISSING_TIMELINE",
                "metrics": {},
                "issues": [{
                    "rule_code": "TIMELINE_MISSING",
                    "severity": "blocking",
                    "title": "Не найден финальный таймлайн",
                    "reason": str(path),
                    "recommendation": "Сначала построить финальный таймлайн.",
                }],
            }

        rows = self._read_json(path)
        if not isinstance(rows, list):
            raise ValueError("Timeline JSON must contain a list.")

        max_film = float(getattr(self.config, "maximum_film_duration_sec", 960.0))
        max_static = float(getattr(self.config, "maximum_static_image_duration_sec", 8.0))
        opening_window = float(getattr(self.config, "opening_audit_window_sec", 15.0))
        min_opening_cuts = int(getattr(self.config, "minimum_opening_cut_count", 3))
        max_asset_uses = int(getattr(self.config, "maximum_same_asset_uses", 4))
        min_reuse_gap = int(getattr(self.config, "minimum_asset_reuse_gap", 3))
        minimum_scene_duration = float(
            getattr(self.config, "minimum_scene_duration_sec", 0.75)
        )
        maximum_scene_duration = float(
            getattr(self.config, "maximum_scene_duration_sec", 12.0)
        )
        rhythm_run_length = int(
            getattr(self.config, "rhythm_sequence_length", 3)
        )

        normalized = [self._normalize(row, idx) for idx, row in enumerate(rows)]
        total_duration = max((row["end_sec"] for row in normalized), default=0.0)

        static_overruns = [
            row for row in normalized
            if row["media_type"] == "image" and row["duration_sec"] > max_static
        ]

        positions: dict[str, list[int]] = defaultdict(list)
        for idx, row in enumerate(normalized):
            if row["asset_key"]:
                positions[row["asset_key"]].append(idx)

        overused = {
            asset: indexes for asset, indexes in positions.items()
            if len(indexes) > max_asset_uses
        }

        rapid_reuse = []
        for asset, indexes in positions.items():
            for previous, current in zip(indexes, indexes[1:]):
                if current - previous <= min_reuse_gap:
                    rapid_reuse.append({
                        "asset": asset,
                        "previous_index": previous,
                        "current_index": current,
                    })

        excluded = [
            row for row in normalized
            if row["excluded"] or row["rejected"]
        ]

        opening = [row for row in normalized if row["start_sec"] < opening_window]
        opening_assets = {row["asset_key"] for row in opening if row["asset_key"]}
        opening_video = sum(1 for row in opening if row["media_type"] == "video")
        weak_opening = (
            len(opening) < min_opening_cuts
            or len(opening_assets) < min_opening_cuts
            or opening_video == 0
        )

        video_with_audio = [
            row for row in normalized
            if row["media_type"] == "video" and row["has_source_audio"]
        ]
        natural_audio = [
            row for row in video_with_audio if row["natural_audio_used"]
        ]
        natural_ratio = (
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

        if total_duration > max_film:
            issues.append({
                "rule_code": "FILM_TOO_LONG",
                "severity": "high",
                "title": "Фильм превышает целевую длительность",
                "reason": f"{total_duration:.2f} сек. при максимуме {max_film:.2f} сек.",
                "recommendation": "Сформировать режиссёрскую версию и сократить слабые фрагменты.",
            })

        if weak_opening:
            issues.append({
                "rule_code": "OPENING_HOOK_WEAK",
                "severity": "high",
                "title": "Слабое вступление",
                "reason": (
                    f"За первые {opening_window:g} сек.: {len(opening)} элементов, "
                    f"{len(opening_assets)} уникальных материалов, {opening_video} видео."
                ),
                "recommendation": (
                    "Усилить начало движением, быстрыми сменами кадров "
                    "и выразительным звуком."
                ),
            })

        for row in static_overruns:
            issues.append({
                "rule_code": "STATIC_IMAGE_TOO_LONG",
                "severity": "medium",
                "title": "Статичное изображение показывается слишком долго",
                "reason": f"{row['asset_key']}: {row['duration_sec']:.2f} сек.",
                "recommendation": (
                    f"Сократить показ до {max_static:g} сек. "
                    "или добавить движение внутри кадра."
                ),
                "asset_id": row["asset_id"],
                "timeline_index": row["index"],
            })

        for asset, indexes in overused.items():
            issues.append({
                "rule_code": "ASSET_OVERUSED",
                "severity": "medium",
                "title": "Материал используется слишком часто",
                "reason": f"{asset}: {len(indexes)} использований.",
                "recommendation": (
                    "Оставить наиболее сильные появления материала, "
                    "остальные заменить."
                ),
                "asset_id": asset,
            })

        for item in rapid_reuse:
            issues.append({
                "rule_code": "ASSET_REUSED_TOO_SOON",
                "severity": "medium",
                "title": "Материал повторяется слишком быстро",
                "reason": (
                    f"{item['asset']}: позиции "
                    f"{item['previous_index']} и {item['current_index']}."
                ),
                "recommendation": (
                    "Увеличить интервал между повторами "
                    "или заменить повторяющийся материал."
                ),
                "asset_id": item["asset"],
            })

        for row in excluded:
            issues.append({
                "rule_code": "EXCLUDED_ASSET_USED",
                "severity": "blocking",
                "title": "Использован запрещённый материал",
                "reason": row["asset_key"] or f"timeline index {row['index']}",
                "recommendation": (
                    "Удалить материал из таймлайна "
                    "и заменить разрешённым вариантом."
                ),
                "asset_id": row["asset_id"],
                "timeline_index": row["index"],
            })

        if video_with_audio and not natural_audio:
            issues.append({
                "rule_code": "NATURAL_SOUND_MISSING",
                "severity": "medium",
                "title": "Натуральный звук видео не используется",
                "reason": (
                    f"Видео с исходным звуком: {len(video_with_audio)}; "
                    "используется: 0."
                ),
                "recommendation": (
                    "Добавить фрагменты натурального звука "
                    "и при необходимости приглушить диктора."
                ),
            })

        for row in short_scenes:
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
            "maximum_film_duration_sec": max_film,
            "timeline_items": len(normalized),
            "static_image_overruns": len(static_overruns),
            "overused_assets": len(overused),
            "rapid_asset_reuse": len(rapid_reuse),
            "excluded_assets_used": len(excluded),
            "opening_window_sec": opening_window,
            "opening_items": len(opening),
            "opening_unique_assets": len(opening_assets),
            "opening_video_items": opening_video,
            "opening_hook_weak": weak_opening,
            "video_with_source_audio": len(video_with_audio),
            "natural_audio_items": len(natural_audio),
            "natural_audio_ratio": round(natural_ratio, 4),
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

    def analyze(self):
        from .visual_dynamics_alpha272 import enrich_visual_dynamics
        base_result = self._analyze_alpha271()
        return enrich_visual_dynamics(
            config=self.config,
            base_result=base_result,
            normalize=self._normalize,
        )

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
        start = float(row.get("start_sec") or row.get("timeline_start_sec") or 0.0)
        end = row.get("end_sec") or row.get("timeline_end_sec")
        duration = row.get("duration_sec")
        if duration is None and end is not None:
            duration = float(end) - start
        duration = float(duration or 0.0)
        if end is None:
            end = start + duration
        end = float(end)

        media_type = str(
            row.get("media_type") or row.get("asset_type") or "unknown"
        ).lower()
        asset_id = row.get("asset_id")
        asset_path = row.get("asset_path") or row.get("path")
        asset_key = str(asset_id or asset_path or "")
        status = str(row.get("asset_status") or row.get("status") or "").lower()

        return {
            "index": index,
            "start_sec": start,
            "end_sec": end,
            "duration_sec": max(0.0, duration),
            "media_type": media_type,
            "asset_id": asset_id,
            "asset_key": asset_key,
            "excluded": bool(
                row.get("excluded")
                or row.get("is_excluded")
                or status == "excluded"
            ),
            "rejected": bool(
                row.get("rejected")
                or row.get("is_rejected")
                or status == "rejected"
            ),
            "has_source_audio": bool(
                row.get("has_source_audio")
                or row.get("source_audio_present")
                or row.get("audio_streams")
            ),
            "natural_audio_used": bool(
                row.get("natural_audio_used")
                or row.get("use_source_audio")
                or row.get("source_audio_gain")
            ),
        }
