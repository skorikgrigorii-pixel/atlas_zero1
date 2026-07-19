from __future__ import annotations

import json
import re
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

    @staticmethod
    def _tokens(value: Any) -> list[str]:
        """Normalize text into comparable semantic tokens.

        Splits values on spaces, hyphens, underscores and punctuation.
        Very short tokens are ignored because they create noisy matches.
        """
        return [
            token
            for token in re.findall(r"[\\w]+", str(value or "").lower())
            if len(token) >= 3
        ]

    def score(self, shot: Any, asset: Any) -> float:
        need_tokens = self._tokens(shot["visual_need"])
        raw_tags = asset["tags"] or "[]"

        try:
            tags = json.loads(raw_tags)
        except (TypeError, ValueError):
            tags = [
                item.strip("'\\\"")
                for item in str(raw_tags).strip("[]").split(",")
                if item.strip()
            ]

        if not isinstance(tags, list):
            tags = [str(tags)]

        searchable_values = [
            asset["filename"],
            asset["category"],
            asset["emotion"],
            *tags,
        ]

        haystack_tokens: set[str] = set()
        haystack_text_parts: list[str] = []

        for value in searchable_values:
            normalized = str(value or "").lower()
            haystack_text_parts.append(normalized)
            haystack_tokens.update(self._tokens(normalized))

        haystack_text = " ".join(haystack_text_parts)

        exact_matches = sum(
            1
            for token in need_tokens
            if token in haystack_tokens
        )

        partial_matches = sum(
            1
            for token in need_tokens
            if token not in haystack_tokens
            and any(
                token in candidate or candidate in token
                for candidate in haystack_tokens
                if len(candidate) >= 4
            )
        )

        phrase_bonus = 0.0
        visual_need = str(shot["visual_need"] or "").lower().strip()
        if visual_need and visual_need in haystack_text:
            phrase_bonus = 0.15

        score = float(asset["quality"] or 0)
        score += exact_matches * 0.18
        score += partial_matches * 0.08
        score += phrase_bonus

        shot_emotion = str(shot["emotion"] or "").strip().lower()
        asset_emotion = str(asset["emotion"] or "").strip().lower()
        if shot_emotion and shot_emotion == asset_emotion:
            score += 0.12

        if self.usage[str(asset["id"])] >= 4:
            score -= 0.4

        if asset["duplicate_of"]:
            score -= 0.25

        return round(max(score, 0.0), 4)

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
                    f"Selected asset '{asset['filename']}' "
                    f"for visual need '{shot['visual_need']}'. "
                    f"Score={score}. "
                    f"Usage={self.usage[asset_id]}."
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
                    f"Required visual: {shot['visual_need']}. "
                    f"Story goal: {shot['story_goal']}. "
                    f"Emotion: {shot['emotion']}."
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
                        "No asset reached the acceptance threshold.",
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
