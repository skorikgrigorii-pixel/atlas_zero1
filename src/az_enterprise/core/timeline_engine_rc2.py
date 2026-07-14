from __future__ import annotations

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
                    ]
                )

        return path

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

        return {
            "state": "TIMELINE_READY",
            "project_id": self.config.project_id,
            "items": len(rows),
            "incomplete": len(incomplete),
            "artifact": str(json_path),
            "artifact_json": str(json_path),
            "artifact_csv": str(csv_path),
            "authority": "TimelineEngineRC2",
        }
