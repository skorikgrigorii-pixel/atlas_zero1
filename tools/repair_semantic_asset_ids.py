from __future__ import annotations

import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from az_enterprise.core.database import Database
from az_enterprise.core.movie_runtime_rc1 import MovieRuntimeRC1


PROJECT_ID = "franklin"

SEMANTIC_REPORT = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "semantic_director_v1"
    / "semantic_assignment_report.json"
)

TIMELINE_PATH = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "movie_runtime_rc1"
    / "timeline.json"
)

OUTPUT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "semantic_director_v1"
)

REPAIR_REPORT = (
    OUTPUT_DIR
    / "semantic_asset_id_repair.json"
)


def normalize_path(value: str | Path) -> str:
    return os.path.normcase(
        os.path.normpath(
            str(Path(value).resolve())
        )
    )


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not SEMANTIC_REPORT.exists():
        raise FileNotFoundError(
            f"Semantic report not found: {SEMANTIC_REPORT}"
        )

    semantic_payload = json.loads(
        SEMANTIC_REPORT.read_text(
            encoding="utf-8"
        )
    )

    assignments = semantic_payload.get(
        "assignments",
        [],
    )

    if not assignments:
        raise RuntimeError(
            "Semantic assignment report contains no assignments."
        )

    db = Database()
    db.init()

    assets = [
        dict(row)
        for row in db.rows(
            """
            SELECT
                id,
                project_id,
                path,
                filename,
                media_type
            FROM assets
            WHERE project_id=?
              AND media_type IN ('image','video')
            """,
            (PROJECT_ID,),
        )
    ]

    by_path = {}
    by_filename = {}

    for asset in assets:
        resolved_path = normalize_path(
            asset["path"]
        )

        by_path[resolved_path] = asset

        filename_key = str(
            asset["filename"]
        ).lower()

        by_filename.setdefault(
            filename_key,
            [],
        ).append(asset)

    print("=" * 72)
    print("ATLAS ZERO — SEMANTIC ASSET ID REPAIR")
    print("=" * 72)
    print("Assignments :", len(assignments))
    print("DB assets    :", len(assets))

    if TIMELINE_PATH.exists():
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        backup = (
            TIMELINE_PATH.parent
            / f"timeline_before_repair_{timestamp}.json"
        )

        shutil.copy2(
            TIMELINE_PATH,
            backup,
        )

        print("Backup       :", backup)

    repaired = []
    unresolved = []

    for item in assignments:
        shot_id = str(
            item.get("shot_id") or ""
        )

        selected_path = str(
            item.get("selected_path") or ""
        )

        selected_filename = str(
            item.get("selected_filename") or ""
        )

        asset = None

        if selected_path:
            asset = by_path.get(
                normalize_path(selected_path)
            )

        if asset is None and selected_filename:
            candidates = by_filename.get(
                selected_filename.lower(),
                [],
            )

            if len(candidates) == 1:
                asset = candidates[0]

        if asset is None:
            unresolved.append(
                {
                    "shot_id": shot_id,
                    "shot_index": item.get(
                        "shot_index"
                    ),
                    "selected_filename": (
                        selected_filename
                    ),
                    "selected_path": selected_path,
                }
            )
            continue

        db.execute(
            """
            UPDATE shots
            SET
                assigned_asset_id=?,
                status='assigned'
            WHERE project_id=?
              AND id=?
            """,
            (
                asset["id"],
                PROJECT_ID,
                shot_id,
            ),
        )

        repaired.append(
            {
                "shot_id": shot_id,
                "shot_index": item.get(
                    "shot_index"
                ),
                "asset_id": asset["id"],
                "filename": asset["filename"],
                "path": asset["path"],
            }
        )

    if unresolved:
        REPAIR_REPORT.write_text(
            json.dumps(
                {
                    "state": "FAILED",
                    "repaired": repaired,
                    "unresolved": unresolved,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        raise RuntimeError(
            f"Unresolved assignments: {len(unresolved)}. "
            f"Report: {REPAIR_REPORT}"
        )

    runtime = MovieRuntimeRC1(
        db,
        PROJECT_ID,
    )

    timeline_result = (
        runtime._build_timeline()
    )

    timeline = json.loads(
        TIMELINE_PATH.read_text(
            encoding="utf-8"
        )
    )

    usage = Counter(
        row.get("asset_path")
        for row in timeline
        if row.get("asset_path")
    )

    incomplete = [
        row
        for row in timeline
        if (
            row.get("status") != "assigned"
            or not row.get("asset_path")
        )
    ]

    database_state = db.one(
        """
        SELECT
            COUNT(*) AS total_shots,
            COUNT(DISTINCT assigned_asset_id)
                AS unique_assigned_assets
        FROM shots
        WHERE project_id=?
        """,
        (PROJECT_ID,),
    )

    joined_state = db.one(
        """
        SELECT
            COUNT(*) AS joined_shots,
            COUNT(DISTINCT a.id)
                AS joined_unique_assets
        FROM shots s
        JOIN assets a
          ON a.id=s.assigned_asset_id
        WHERE s.project_id=?
        """,
        (PROJECT_ID,),
    )

    report = {
        "state": "REPAIRED",
        "assignments_repaired": len(
            repaired
        ),
        "unresolved": len(unresolved),
        "database": {
            "total_shots": int(
                database_state[
                    "total_shots"
                ] or 0
            ),
            "unique_assigned_assets": int(
                database_state[
                    "unique_assigned_assets"
                ] or 0
            ),
            "joined_shots": int(
                joined_state[
                    "joined_shots"
                ] or 0
            ),
            "joined_unique_assets": int(
                joined_state[
                    "joined_unique_assets"
                ] or 0
            ),
        },
        "timeline": {
            "items": len(timeline),
            "incomplete": len(incomplete),
            "unique_assets": len(usage),
            "usage": [
                {
                    "filename": Path(
                        path
                    ).name,
                    "uses": count,
                }
                for path, count
                in usage.most_common()
            ],
        },
        "timeline_result": timeline_result,
    }

    REPAIR_REPORT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("REPAIR RESULT")
    print("=" * 72)
    print(
        "Assignments repaired =",
        len(repaired),
    )
    print(
        "Timeline items        =",
        len(timeline),
    )
    print(
        "Timeline incomplete   =",
        len(incomplete),
    )
    print(
        "Timeline unique assets=",
        len(usage),
    )
    print(
        "Joined unique assets  =",
        joined_state[
            "joined_unique_assets"
        ],
    )

    print()
    print("TOP ASSET USAGE")

    for path, count in usage.most_common(
        20
    ):
        print(
            f"{count:3d}  "
            f"{Path(path).name}"
        )

    print()
    print("Report =", REPAIR_REPORT)

    if len(timeline) != 149:
        raise RuntimeError(
            f"Expected 149 shots, found "
            f"{len(timeline)}."
        )

    if incomplete:
        raise RuntimeError(
            f"Incomplete timeline shots: "
            f"{len(incomplete)}."
        )

    if len(usage) < 30:
        raise RuntimeError(
            f"Only {len(usage)} unique assets "
            f"are present in timeline. "
            f"Render blocked."
        )

    print()
    print("SEMANTIC TIMELINE VERIFIED.")
    print("RENDER PERMITTED.")


if __name__ == "__main__":
    main()
