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

    def _parse_alternative_assets(
        self,
        value: Any,
    ) -> list[dict[str, Any]]:
        """Return verified alternative assets from director decisions.

        Structured RC2 payloads are preferred. Legacy filename-only lists are
        resolved through the canonical assets table for backward compatibility.
        """
        if value in (None, ""):
            return []

        if isinstance(value, list):
            raw_items = value
        else:
            try:
                raw_items = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return []

        if not isinstance(raw_items, list):
            return []

        structured: list[dict[str, Any]] = []
        legacy_names: list[str] = []

        for item in raw_items:
            if isinstance(item, dict):
                asset_path = str(item.get("asset_path") or item.get("path") or "").strip()
                asset_name = str(item.get("asset_name") or item.get("filename") or "").strip()
                media_type = str(item.get("media_type") or "").strip().lower()
                if asset_path and asset_name and media_type in {"image", "video"}:
                    structured.append({
                        "asset_id": str(item.get("asset_id") or item.get("id") or ""),
                        "asset_name": asset_name,
                        "asset_path": asset_path,
                        "media_type": media_type,
                        "duration_sec": float(item.get("duration_sec") or 0.0),
                        "quality": float(item.get("quality") or 0.0),
                        "assignment_score": float(item.get("assignment_score") or item.get("score") or 0.0),
                        "provenance": str(item.get("provenance") or "director_decision"),
                        "verified": bool(item.get("verified", True)),
                    })
            elif str(item or "").strip():
                legacy_names.append(str(item).strip())

        if legacy_names:
            placeholders = ",".join("?" for _ in legacy_names)
            rows = self.db.rows(
                f"""
                SELECT id, filename, path, media_type, duration_sec, quality
                FROM assets
                WHERE project_id=?
                  AND filename IN ({placeholders})
                  AND media_type IN ('image','video')
                """,
                (self.config.project_id, *legacy_names),
            )
            by_name = {str(row["filename"]): row for row in rows}
            for name in legacy_names:
                asset = by_name.get(name)
                if asset is None:
                    continue
                structured.append({
                    "asset_id": str(asset["id"]),
                    "asset_name": str(asset["filename"]),
                    "asset_path": str(asset["path"]),
                    "media_type": str(asset["media_type"] or "").strip().lower(),
                    "duration_sec": float(asset["duration_sec"] or 0.0),
                    "quality": float(asset["quality"] or 0.0),
                    "assignment_score": 0.0,
                    "provenance": "legacy_director_decision",
                    "verified": True,
                })

        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in structured:
            identity = str(item.get("asset_path") or item.get("asset_id") or "").strip().lower()
            if not identity or identity in seen:
                continue
            seen.add(identity)
            unique.append(item)
        return unique[:3]

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
                a.media_type AS media_type,
                (
                    SELECT dd.alternatives
                    FROM director_decisions dd
                    WHERE dd.project_id=s.project_id
                      AND dd.shot_id=s.id
                    ORDER BY dd.id DESC
                    LIMIT 1
                ) AS assignment_alternatives
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
            duration_sec = round(
                max(0.0, end_sec - start_sec),
                3,
            )

            media_type = str(
                row["media_type"] or ""
            ).strip().lower()

            asset_path = str(
                row["asset_path"] or ""
            ).strip()

            status = str(
                row["status"] or ""
            ).strip().lower()

            # CHANGE-005:
            # Timeline only identifies whether the clip is a potential
            # source-audio candidate. The final editorial decision belongs
            # exclusively to RenderEngineRC2.
            natural_sound_candidate = bool(
                media_type == "video"
                and asset_path
                and status == "assigned"
                and duration_sec > 0.0
            )

            natural_sound_windows = (
                [[0.0, duration_sec]]
                if natural_sound_candidate
                else []
            )

            alternative_assets = self._parse_alternative_assets(
                row["assignment_alternatives"]
            )

            timeline_rows.append(
                {
                    "shot_id": row["id"],
                    "shot_index": row["idx"],
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "duration_sec": duration_sec,
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
                    "alternative_assets": alternative_assets,
                    "natural_sound_candidate":
                        natural_sound_candidate,

                    # Compatibility field:
                    # this no longer represents the final editorial decision.
                    # RenderEngineRC2 recalculates natural_sound_enabled.
                    "natural_sound_enabled":
                        natural_sound_candidate,

                    "natural_sound_window":
                        natural_sound_candidate,
                    "natural_sound_windows":
                        natural_sound_windows,
                    "natural_sound_reason": (
                        "embedded_source_audio_candidate"
                        if natural_sound_candidate
                        else ""
                    ),

                    # Timeline does not assign editorial priority.
                    "natural_sound_priority": 0,
                    "source_mode": "canonical_database",
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
                    "alternative_assets",
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
                    "natural_sound_candidate",
                    "natural_sound_enabled",
                    "natural_sound_windows",
                    "natural_sound_reason",
                    "natural_sound_priority",
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
                        json.dumps(
                            row.get("alternative_assets", []),
                            ensure_ascii=False,
                        ),
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
                        row.get("natural_sound_candidate"),
                        row.get("natural_sound_enabled"),
                        json.dumps(
                            row.get("natural_sound_windows", []),
                            ensure_ascii=False,
                        ),
                        row.get("natural_sound_reason"),
                        row.get("natural_sound_priority"),
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
        """Build the current project timeline from canonical Production Script.

        RC2 Production Script is the timeline authority when running from a
        project. Scene IDs, scene order and scene durations therefore remain
        stable across narration, voice, timeline and render stages.

        This behavior is project-independent.
        """

        script_path = (
            self._discover_production_script_path()
        )

        if script_path is None:
            raise FileNotFoundError(
                "Production script JSON was not found "
                f"for project {self.config.project_id!r}"
            )

        try:
            production_script = json.loads(
                script_path.read_text(
                    encoding="utf-8-sig"
                )
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Production script JSON is invalid: "
                f"{script_path}"
            ) from exc

        if not isinstance(
            production_script,
            dict,
        ):
            raise ValueError(
                "Production script JSON root "
                "must be an object"
            )

        result = (
            self.run_from_production_script(
                production_script,
                average_shot_duration_sec=(
                    average_shot_duration_sec
                ),
                minimum_shot_duration_sec=(
                    minimum_shot_duration_sec
                ),
                maximum_shot_duration_sec=(
                    maximum_shot_duration_sec
                ),
            )
        )

        result["discovery_mode"] = (
            "project_auto_discovery"
        )

        result["production_script_path"] = (
            str(script_path)
        )

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

                # Production Script is the timeline authority.
                #
                # A scene may require several editorial shots while having
                # fewer source assets. Reuse is therefore permitted inside
                # the scene. Static images can support different crop, zoom,
                # pan and camera-motion treatments. Video safety remains
                # protected by the physical source-duration calculation
                # performed above.
                asset_id = (
                    asset_ids[
                        local_index
                        % len(asset_ids)
                    ]
                    if asset_ids
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
                    "alternative_assets": [],
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
