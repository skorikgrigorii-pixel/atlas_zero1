from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .database import Database
from .events import EventBus


class AssignmentPolicyRC2:
    """Canonical assignment decision policy.

    This class is the only owner of asset scoring and assignment writes.
    The current formula preserves legacy behaviour during RC2.5 migration.
    """

    ACCEPTANCE_THRESHOLD = 0.62

    def __init__(
        self,
        db: Database,
        project_id: str,
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)
        self.usage: defaultdict[str, int] = defaultdict(int)

    def score(self, shot: Any, asset: Any) -> float:
        need = str(shot["visual_need"] or "").lower().split()
        raw_tags = asset["tags"] or "[]"

        try:
            tags = json.loads(raw_tags)
        except (TypeError, ValueError):
            tags = [
                item.strip("'\"")
                for item in str(raw_tags).strip("[]").split(",")
                if item.strip()
            ]

        if not isinstance(tags, list):
            tags = [str(tags)]

        haystack = " ".join(
            [
                str(asset["filename"] or "").lower(),
                str(asset["category"] or ""),
                str(asset["emotion"] or ""),
                " ".join(str(tag) for tag in tags),
            ]
        ).lower()

        match = sum(
            1
            for word in need
            if word in haystack
        )

        score = float(asset["quality"] or 0)
        score += match * 0.18

        if (
            shot["emotion"]
            and shot["emotion"] == asset["emotion"]
        ):
            score += 0.12

        if self.usage[str(asset["id"])] >= 4:
            score -= 0.4

        if asset["duplicate_of"]:
            score -= 0.25

        return round(max(score, 0), 4)

    def run(self) -> dict[str, Any]:
        self.db.execute(
            "DELETE FROM director_decisions WHERE project_id=?",
            (self.project_id,),
        )

        shots = self.db.rows(
            """
            SELECT *
            FROM shots
            WHERE project_id=?
            ORDER BY idx
            """,
            (self.project_id,),
        )

        assets = self.db.rows(
            """
            SELECT *
            FROM assets
            WHERE project_id=?
              AND media_type IN ('image','video')
            """,
            (self.project_id,),
        )

        assigned = 0
        missing = 0
        self.usage.clear()

        for shot in shots:
            ranked = sorted(
                (
                    (self.score(shot, asset), asset)
                    for asset in assets
                ),
                key=lambda item: item[0],
                reverse=True,
            )

            if (
                ranked
                and ranked[0][0]
                >= self.ACCEPTANCE_THRESHOLD
            ):
                score, asset = ranked[0]
                asset_id = str(asset["id"])
                self.usage[asset_id] += 1

                reason = (
                    f"?????? ???????? '{asset['filename']}' "
                    f"??? ??????????? '{shot['visual_need']}'. "
                    f"??????={score}. "
                    f"?????????????={self.usage[asset_id]}."
                )

                alternatives = [
                    candidate[1]["filename"]
                    for candidate in ranked[1:4]
                ]

                self.db.execute(
                    """
                    UPDATE shots
                    SET assigned_asset_id=?, status=?
                    WHERE id=?
                    """,
                    (
                        asset["id"],
                        "assigned",
                        shot["id"],
                    ),
                )

                self.db.execute(
                    """
                    INSERT INTO director_decisions(
                        project_id,
                        shot_id,
                        asset_id,
                        score,
                        reason,
                        alternatives
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        self.project_id,
                        shot["id"],
                        asset["id"],
                        score,
                        reason,
                        json.dumps(
                            alternatives,
                            ensure_ascii=False,
                        ),
                    ),
                )

                assigned += 1

            else:
                prompt = (
                    f"????? ????????: {shot['visual_need']}. "
                    f"???????: {shot['story_goal']}. "
                    f"??????: {shot['emotion']}."
                )

                best_score = (
                    float(ranked[0][0])
                    if ranked
                    else 0.0
                )

                self.db.execute(
                    """
                    UPDATE shots
                    SET assigned_asset_id=NULL,
                        status='missing'
                    WHERE id=?
                    """,
                    (shot["id"],),
                )

                self.db.execute(
                    """
                    INSERT INTO director_decisions(
                        project_id,
                        shot_id,
                        asset_id,
                        score,
                        reason,
                        alternatives
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        self.project_id,
                        shot["id"],
                        None,
                        best_score,
                        "?????????? ???????? ?? ??????.",
                        prompt,
                    ),
                )

                missing += 1

        result = {
            "state": "ASSIGNMENT_COMPLETED",
            "project_id": self.project_id,
            "assigned": assigned,
            "missing": missing,
            "threshold": self.ACCEPTANCE_THRESHOLD,
            "policy": "AssignmentPolicyRC2",
        }

        self.bus.emit(
            "ASSIGNMENT_POLICY_COMPLETED",
            result,
        )

        return result
