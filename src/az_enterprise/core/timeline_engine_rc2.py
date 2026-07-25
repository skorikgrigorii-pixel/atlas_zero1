from __future__ import annotations

import math

import csv
import json
from pathlib import Path
from typing import Any

from .database import Database
from .project_config_rc2 import ProjectConfigRC2


class TimelineEngineRC2:
    """Canonical timeline builder for RC2.

    This class is the only owner of canonical timeline creation.
    """

    def __init__(
        self,
        db: Database,
        config: ProjectConfigRC2,
    ) -> None:
        self.db = db
        self.config = config

    def _load_rows(self) -> list[dict[str, Any]]:
        rows = self.db.rows(
            """
            SELECT
                s.id,
                s.idx,
                s.start_sec,
                s.end_sec,
                s.block,
                s.story_goal,
                s.visual_need,
                s.emotion,
                s.status,
                s.transition,
                s.camera_motion,
                a.filename AS asset,
                a.path AS asset_path,
                a.media_type AS media_type
            FROM shots s
            LEFT JOIN assets a
                ON a.id=s.assigned_asset_id
            WHERE s.project_id=?
            ORDER BY s.idx
            """,
            (self.config.project_id,),
        )

        timeline_rows: list[dict[str, Any]] = []

        for row in rows:
            start_sec = float(row["start_sec"] or 0.0)
            end_sec = float(row["end_sec"] or start_sec)

            timeline_rows.append(
                {
                    "shot_id": row["id"],
                    "shot_index": row["idx"],
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "duration_sec": round(
                        max(0.0, end_sec - start_sec),
                        3,
                    ),
                    "block": row["block"],
                    "story_goal": row["story_goal"],
                    "visual_need": row["visual_need"],
                    "emotion": row["emotion"],
                    "status": row["status"],
                    "transition": row["transition"],
                    "camera_motion": row["camera_motion"],
                    "asset_name": row["asset"],
                    "asset_path": row["asset_path"],
                    "media_type": row["media_type"],
                }
            )

        return timeline_rows

    def _write_json(
        self,
        rows: list[dict[str, Any]],
    ) -> Path:
        path = self.config.timeline_path
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                rows,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return path

    def _write_csv(
        self,
        rows: list[dict[str, Any]],
    ) -> Path:
        path = self.config.timeline_path.with_suffix(
            ".csv"
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as handle:
            writer = csv.writer(handle)

            writer.writerow(
                [
                    "shot_index",
                    "start_sec",
                    "end_sec",
                    "duration_sec",
                    "media_type",
                    "asset_name",
                    "asset_path",
                    "story_goal",
                    "visual_need",
                    "scene_id",
                    "scene_title",
                    "asset_id",
                    "status",
                    "transition",
                    "camera_motion",
                    "voiceover_text",
                    "natural_sound_window",
                    "source_mode",
                ]
            )

            for row in rows:
                writer.writerow(
                    [
                        row["shot_index"],
                        row["start_sec"],
                        row["end_sec"],
                        row["duration_sec"],
                        row["media_type"],
                        row["asset_name"],
                        row["asset_path"],
                        row["story_goal"],
                        row["visual_need"],
                        row.get("scene_id"),
                        row.get("scene_title"),
                        row.get("asset_id"),
                        row.get("status"),
                        row.get("transition"),
                        row.get("camera_motion"),
                        row.get("voiceover_text"),
                        row.get("natural_sound_window"),
                        row.get("source_mode"),
                    ]
                )

        return path

    def run_from_project(
        self,
        *,
        average_shot_duration_sec: float = 6.5,
        minimum_shot_duration_sec: float = 2.0,
        maximum_shot_duration_sec: float = 12.0,
    ) -> dict[str, Any]:
        """Build the current project timeline from canonical SQLite shots.

        The RC2 project timeline authority is the shots table produced by
        StoryStrategyEngineRC2 and StoryEngine. Production-script discovery is
        intentionally not used here, because an obsolete script may contain a
        legacy duration such as 1500 seconds.
        """
        del average_shot_duration_sec
        del minimum_shot_duration_sec
        del maximum_shot_duration_sec

        result = self.run()
        result["mode"] = "canonical_database"
        result["discovery_mode"] = "canonical_database"
        return result

    def _discover_production_script_path(
        self,
    ) -> Path | None:
        """Return the preferred production script for any project."""

        project_dir = self.config.project_dir
        export_dir = self.config.export_dir

        candidates = (
            project_dir
            / "script"
            / "production_script.json",

            project_dir
            / "production_script.json",

            export_dir
            / "production_script.json",

            export_dir
            / "rc2"
            / "production_script"
            / "production_script.json",
        )

        for candidate in candidates:
            if (
                candidate.exists()
                and candidate.is_file()
            ):
                return candidate

        script_dir = (
            project_dir
            / "script"
        )

        if script_dir.exists():
            versioned_candidates = sorted(
                script_dir.glob(
                    "production_script*.json"
                ),
                key=lambda path: (
                    path.stat().st_mtime,
                    path.name,
                ),
                reverse=True,
            )

            if versioned_candidates:
                return versioned_candidates[0]

        return None

    def run_from_production_script(
        self,
        production_script: dict[str, Any],
        *,
        average_shot_duration_sec: float = 6.5,
        minimum_shot_duration_sec: float = 2.0,
        maximum_shot_duration_sec: float = 12.0,
    ) -> dict[str, Any]:
        """Build canonical timeline directly from a production script.

        This mode is project-independent. Scene duration, asset IDs,
        narrative intent and transition data are read from the supplied
        production script.
        """
        scenes = list(
            production_script.get(
                "scenes",
                [],
            )
        )

        if not scenes:
            raise ValueError(
                "Production script contains no scenes"
            )

        average_duration = max(
            1.0,
            float(average_shot_duration_sec),
        )
        minimum_duration = max(
            0.5,
            float(minimum_shot_duration_sec),
        )
        maximum_duration = max(
            minimum_duration,
            float(maximum_shot_duration_sec),
        )

        timeline_rows: list[dict[str, Any]] = []
        shot_index = 1
        current_time = 0.0

        for scene in scenes:
            scene_id = str(
                scene.get(
                    "scene_id",
                    f"SC{len(timeline_rows) + 1:02d}",
                )
            )

            scene_title = str(
                scene.get(
                    "title",
                    scene_id,
                )
            )

            scene_duration = float(
                scene.get(
                    "duration_sec",
                    0.0,
                )
            )

            if scene_duration <= 0:
                raise ValueError(
                    f"Scene {scene_id} duration must be > 0"
                )

            video = dict(
                scene.get(
                    "video",
                    {},
                )
            )

            asset_ids = [
                str(asset_id)
                for asset_id in video.get(
                    "asset_ids",
                    [],
                )
                if str(asset_id).strip()
            ]

            if not asset_ids:
                raise ValueError(
                    f"Scene {scene_id} contains no asset IDs"
                )

            assets = self._resolve_assets(
                asset_ids
            )

            target_shots = max(
                1,
                round(
                    scene_duration
                    / average_duration
                ),
            )

            target_shots = max(
                target_shots,
                len(asset_ids),
            )

            shot_duration = (
                scene_duration
                / target_shots
            )

            if shot_duration < minimum_duration:
                target_shots = max(
                    1,
                    int(
                        scene_duration
                        / minimum_duration
                    ),
                )

            elif shot_duration > maximum_duration:
                target_shots = max(
                    1,
                    int(
                        round(
                            scene_duration
                            / maximum_duration
                        )
                    ),
                )

            target_shots = max(
                target_shots,
                1,
            )

            # Video assets cannot be displayed beyond their physical source
            # duration. Increase the number of equal-duration timeline shots
            # when necessary, while preserving the authoritative duration of
            # the scene.
            video_durations = []

            for asset_id in asset_ids:
                resolved_asset = assets.get(
                    asset_id
                )

                if resolved_asset is None:
                    continue

                media_type = str(
                    resolved_asset.get(
                        "media_type",
                        "",
                    )
                    or ""
                ).strip().lower()

                if media_type != "video":
                    continue

                try:
                    asset_duration = float(
                        resolved_asset.get(
                            "duration_sec",
                            0.0,
                        )
                        or 0.0
                    )
                except (TypeError, ValueError):
                    asset_duration = 0.0

                if asset_duration > 0.0:
                    video_durations.append(
                        asset_duration
                    )

            if video_durations:
                # Small safety margin protects against container/ffprobe
                # rounding differences near the physical end of a file.
                shortest_video_duration = max(
                    0.05,
                    min(video_durations) - 0.05,
                )

                duration_limited_shots = max(
                    1,
                    math.ceil(
                        scene_duration
                        / shortest_video_duration
                    ),
                )

                target_shots = max(
                    target_shots,
                    duration_limited_shots,
                )

            transition = dict(
                scene.get(
                    "transition",
                    {},
                )
            )

            voiceover = dict(
                scene.get(
                    "voiceover",
                    {},
                )
            )

            narrative_goal = str(
                scene.get(
                    "narrative_goal",
                    "",
                )
            )

            emotional_goal = str(
                scene.get(
                    "emotional_goal",
                    "neutral",
                )
            )

            visual_strategy = str(
                video.get(
                    "visual_strategy",
                    "",
                )
            )

            for local_index in range(
                target_shots
            ):
                start_sec = round(
                    current_time
                    + (
                        local_index
                        * scene_duration
                        / target_shots
                    ),
                    3,
                )

                end_sec = round(
                    current_time
                    + (
                        (local_index + 1)
                        * scene_duration
                        / target_shots
                    ),
                    3,
                )

                # Each production asset may be used only once in a scene.
                # When the scene requires more shots than available assets,
                # keep the shot explicitly missing instead of cyclically
                # repeating existing material. This exposes the coverage gap
                # to AssignmentEngineRC2 and Director AI.
                asset_id = (
                    asset_ids[local_index]
                    if local_index < len(asset_ids)
                    else None
                )

                asset = (
                    assets.get(asset_id)
                    if asset_id is not None
                    else None
                )

                status = (
                    "assigned"
                    if asset is not None
                    else "missing"
                )

                timeline_rows.append({
                    "shot_id": (
                        f"{scene_id}_SHOT_{local_index + 1:03d}"
                    ),
                    "shot_index": shot_index,
                    "scene_id": scene_id,
                    "scene_title": scene_title,
                    "scene_order": scene.get(
                        "order",
                    ),
                    "act_id": scene.get(
                        "act_id",
                        "",
                    ),
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "duration_sec": round(
                        max(
                            0.0,
                            end_sec - start_sec,
                        ),
                        3,
                    ),
                    "block": scene.get(
                        "act_id",
                        "",
                    ),
                    "story_goal": narrative_goal,
                    "visual_need": visual_strategy,
                    "emotion": emotional_goal,
                    "status": status,
                    "transition": (
                        transition.get(
                            "type",
                            "cut",
                        )
                        if local_index
                        == target_shots - 1
                        else "cut"
                    ),
                    "camera_motion":
                        self._camera_motion(
                            local_index
                        ),
                    "asset_id": asset_id,
                    "asset_name": (
                        asset["filename"]
                        if asset is not None
                        else None
                    ),
                    "asset_path": (
                        asset["path"]
                        if asset is not None
                        else None
                    ),
                    "media_type": (
                        asset["media_type"]
                        if asset is not None
                        else None
                    ),
                    "voiceover_text": (
                        voiceover.get(
                            "text",
                            "",
                        )
                        if local_index == 0
                        else ""
                    ),
                    "natural_sound_window": (
                        local_index > 0
                    ),
                    "source_mode":
                        "production_script",
                })

                shot_index += 1

            current_time = round(
                current_time
                + scene_duration,
                3,
            )

        json_path = self._write_json(
            timeline_rows
        )

        csv_path = self._write_csv(
            timeline_rows
        )

        incomplete = [
            row
            for row in timeline_rows
            if (
                row.get("status")
                != "assigned"
                or not row.get(
                    "asset_path"
                )
            )
        ]

        return {
            "state": (
                "TIMELINE_READY"
                if not incomplete
                else "TIMELINE_INCOMPLETE"
            ),
            "project_id":
                self.config.project_id,
            "mode":
                "production_script",
            "items": len(
                timeline_rows
            ),
            "scenes": len(
                scenes
            ),
            "duration_sec": round(
                current_time,
                3,
            ),
            "incomplete": len(
                incomplete
            ),
            "artifact": str(
                json_path
            ),
            "artifact_json": str(
                json_path
            ),
            "artifact_csv": str(
                csv_path
            ),
            "authority":
                "TimelineEngineRC2",
        }

    def _resolve_assets(
        self,
        asset_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not asset_ids:
            return {}

        placeholders = ",".join(
            "?"
            for _ in asset_ids
        )

        rows = self.db.rows(
            f"""
            SELECT
                id,
                filename,
                path,
                media_type,
                duration_sec,
                quality
            FROM assets
            WHERE project_id=?
              AND id IN ({placeholders})
            """,
            (
                self.config.project_id,
                *asset_ids,
            ),
        )

        return {
            str(row["id"]): {
                "id": str(
                    row["id"]
                ),
                "filename": row[
                    "filename"
                ],
                "path": row["path"],
                "media_type": row[
                    "media_type"
                ],
                "duration_sec": row[
                    "duration_sec"
                ],
                "quality": row[
                    "quality"
                ],
            }
            for row in rows
        }

    @staticmethod
    def _camera_motion(
        local_index: int,
    ) -> str:
        motions = (
            "static",
            "slow_push",
            "slow_pan",
            "static",
        )

        return motions[
            local_index
            % len(motions)
        ]

    def run(self) -> dict[str, Any]:
        rows = self._load_rows()

        json_path = self._write_json(rows)
        csv_path = self._write_csv(rows)

        incomplete = [
            row
            for row in rows
            if (
                row.get("status") != "assigned"
                or not row.get("asset_path")
            )
        ]

        duration_sec = round(
            max(
                (
                    float(row.get("end_sec") or 0.0)
                    for row in rows
                ),
                default=0.0,
            ),
            3,
        )

        return {
            "state": (
                "TIMELINE_READY"
                if not incomplete
                else "TIMELINE_INCOMPLETE"
            ),
            "project_id": self.config.project_id,
            "mode": "canonical_database",
            "items": len(rows),
            "duration_sec": duration_sec,
            "incomplete": len(incomplete),
            "artifact": str(json_path),
            "artifact_json": str(json_path),
            "artifact_csv": str(csv_path),
            "authority": "TimelineEngineRC2",
        }
