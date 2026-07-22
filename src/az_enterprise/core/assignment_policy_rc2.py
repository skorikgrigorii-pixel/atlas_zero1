from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from .database import Database
from .events import EventBus


class AssignmentPolicyRC2:
    """Canonical assignment decision policy.

    Assignment priority:
    1. Use explicit Story Engine decisions from story_scenes.required_assets.
    2. Fall back to legacy semantic scoring only when Story Engine did not
       provide a usable asset for the shot.

    This class is the only owner of assignment writes.
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
        """Normalize text into comparable semantic tokens."""
        return [
            token
            for token in re.findall(r"[\w]+", str(value or "").lower())
            if len(token) >= 3
        ]

    @staticmethod
    def _parse_required_assets(value: Any) -> dict[str, Any]:
        """Safely parse story_scenes.required_assets."""
        if isinstance(value, dict):
            data = value
        else:
            try:
                data = json.loads(value or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                return {
                    "asset_ids": [],
                    "cluster_ids": [],
                    "use_existing_assets_only": False,
                }

        if not isinstance(data, dict):
            return {
                "asset_ids": [],
                "cluster_ids": [],
                "use_existing_assets_only": False,
            }

        asset_ids = data.get("asset_ids") or []
        cluster_ids = data.get("cluster_ids") or []

        if not isinstance(asset_ids, list):
            asset_ids = [asset_ids]
        if not isinstance(cluster_ids, list):
            cluster_ids = [cluster_ids]

        return {
            "asset_ids": [
                str(asset_id)
                for asset_id in asset_ids
                if asset_id not in (None, "")
            ],
            "cluster_ids": [
                str(cluster_id)
                for cluster_id in cluster_ids
                if cluster_id not in (None, "")
            ],
            "use_existing_assets_only": bool(
                data.get("use_existing_assets_only", False)
            ),
        }

    @staticmethod
    def _shot_belongs_to_scene(shot: Any, scene: Any) -> bool:
        """Return True when a shot falls inside a story scene.

        Time range is the primary mapping because shots do not currently
        contain scene_id. Block matching is used as an additional guard when
        both records contain a block value.
        """
        shot_start = float(shot["start_sec"] or 0.0)
        shot_end = float(shot["end_sec"] or shot_start)
        scene_start = float(scene["start_sec"] or 0.0)
        scene_end = float(scene["end_sec"] or scene_start)

        overlaps = (
            shot_start < scene_end
            and shot_end > scene_start
        )

        if not overlaps:
            return False

        shot_block = str(shot["block"] or "").strip()
        scene_block = str(scene["block"] or "").strip()

        if shot_block and scene_block and shot_block != scene_block:
            return False

        return True

    def _preferred_assets_for_shot(
        self,
        shot: Any,
        scenes: list[Any],
        assets_by_id: dict[str, Any],
    ) -> tuple[list[Any], str | None]:
        """Resolve explicit Story Engine assets for a shot."""
        matching_scenes = [
            scene
            for scene in scenes
            if self._shot_belongs_to_scene(shot, scene)
        ]

        if not matching_scenes:
            return [], None

        # Prefer the narrowest overlapping scene if malformed ranges overlap.
        matching_scenes.sort(
            key=lambda scene: (
                float(scene["end_sec"] or 0.0)
                - float(scene["start_sec"] or 0.0),
                int(scene["idx"] or 0),
            )
        )
        scene = matching_scenes[0]
        required = self._parse_required_assets(scene["required_assets"])

        preferred = [
            assets_by_id[asset_id]
            for asset_id in required["asset_ids"]
            if asset_id in assets_by_id
        ]

        return preferred, str(scene["id"])

    def _max_use(self, asset: Any) -> int:
        """Return a safe per-asset usage limit.

        Missing or non-positive max_use means no practical hard limit.
        """
        try:
            value = int(asset["max_use"])
        except (TypeError, ValueError, KeyError):
            return 10**9
        return value if value > 0 else 10**9


    def _asset_fits_shot(
        self,
        shot: Any,
        asset: Any,
    ) -> bool:
        """Return True when an asset can safely cover the shot duration."""
        media_type = str(asset["media_type"] or "").strip().lower()
        if media_type == "image":
            return True
        if media_type != "video":
            return False
        shot_start = float(shot["start_sec"] or 0.0)
        shot_end = float(shot["end_sec"] or shot_start)
        shot_duration = max(0.0, shot_end - shot_start)
        try:
            asset_duration = float(asset["duration_sec"] or 0.0)
        except (TypeError, ValueError):
            return False
        return asset_duration + 0.10 >= shot_duration

    def _select_story_asset(
        self,
        shot: Any,
        candidates: list[Any],
    ) -> Any | None:
        """Select the least-used compatible Story Engine candidate."""
        available = [
            asset
            for asset in candidates
            if self.usage[str(asset["id"])] < self._max_use(asset)
            and self._asset_fits_shot(shot, asset)
        ]

        if not available:
            return None

        return min(
            available,
            key=lambda asset: (
                self.usage[str(asset["id"])],
                -float(asset["quality"] or 0.0),
                str(asset["id"]),
            ),
        )

    def score(self, shot: Any, asset: Any) -> float:
        """Legacy fallback score for shots without an explicit Story asset."""
        need_tokens = self._tokens(shot["visual_need"])
        raw_tags = asset["tags"] or "[]"

        try:
            tags = json.loads(raw_tags)
        except (TypeError, ValueError, json.JSONDecodeError):
            tags = [
                item.strip("'\"")
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

        if self.usage[str(asset["id"])] >= self._max_use(asset):
            score -= 1.0

        if asset["duplicate_of"]:
            score -= 0.25

        return round(max(score, 0.0), 4)

    def _write_assignment(
        self,
        shot: Any,
        asset: Any,
        score: float,
        reason: str,
        alternatives: list[str],
    ) -> None:
        asset_id = str(asset["id"])
        self.usage[asset_id] += 1

        self.db.execute(
            """
            UPDATE shots
            SET assigned_asset_id=?, status='assigned'
            WHERE id=? AND project_id=?
            """,
            (
                asset_id,
                shot["id"],
                self.project_id,
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
                asset_id,
                score,
                reason,
                json.dumps(alternatives, ensure_ascii=False),
            ),
        )

    def _write_missing(
        self,
        shot: Any,
        best_score: float,
        reason: str,
    ) -> None:
        prompt = (
            f"Required visual: {shot['visual_need']}. "
            f"Story goal: {shot['story_goal']}. "
            f"Emotion: {shot['emotion']}."
        )

        self.db.execute(
            """
            UPDATE shots
            SET assigned_asset_id=NULL,
                status='missing'
            WHERE id=? AND project_id=?
            """,
            (
                shot["id"],
                self.project_id,
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
                None,
                best_score,
                reason,
                prompt,
            ),
        )

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

        scenes = self.db.rows(
            """
            SELECT *
            FROM story_scenes
            WHERE project_id=?
            ORDER BY idx
            """,
            (self.project_id,),
        )

        assets_by_id = {
            str(asset["id"]): asset
            for asset in assets
        }

        assigned = 0
        assigned_from_story = 0
        assigned_from_fallback = 0
        missing = 0
        self.usage.clear()

        for shot in shots:
            preferred_assets, scene_id = self._preferred_assets_for_shot(
                shot,
                scenes,
                assets_by_id,
            )
            story_asset = self._select_story_asset(
                shot,
                preferred_assets,
            )

            if story_asset is not None:
                story_asset_id = str(story_asset["id"])
                alternatives = [
                    str(asset["filename"])
                    for asset in preferred_assets
                    if str(asset["id"]) != story_asset_id
                ][:3]

                reason = (
                    f"Assigned explicit Story Engine asset "
                    f"'{story_asset['filename']}' from scene '{scene_id}' "
                    f"for visual need '{shot['visual_need']}'. "
                    f"Usage={self.usage[story_asset_id] + 1}/"
                    f"{self._max_use(story_asset)}."
                )

                # A Story Engine decision is authoritative. Score 1.0 marks
                # provenance, not a recomputed semantic confidence.
                self._write_assignment(
                    shot=shot,
                    asset=story_asset,
                    score=1.0,
                    reason=reason,
                    alternatives=alternatives,
                )
                assigned += 1
                assigned_from_story += 1
                continue

            ranked = sorted(
                (
                    (self.score(shot, asset), asset)
                    for asset in assets
                    if self.usage[str(asset["id"])] < self._max_use(asset)
                    and self._asset_fits_shot(shot, asset)
                ),
                key=lambda item: item[0],
                reverse=True,
            )

            if ranked and ranked[0][0] >= self.ACCEPTANCE_THRESHOLD:
                score, asset = ranked[0]
                asset_id = str(asset["id"])

                reason = (
                    f"Fallback assignment selected asset "
                    f"'{asset['filename']}' for visual need "
                    f"'{shot['visual_need']}'. Score={score}. "
                    f"Usage={self.usage[asset_id] + 1}/"
                    f"{self._max_use(asset)}."
                )

                alternatives = [
                    str(candidate[1]["filename"])
                    for candidate in ranked[1:4]
                ]

                self._write_assignment(
                    shot=shot,
                    asset=asset,
                    score=score,
                    reason=reason,
                    alternatives=alternatives,
                )
                assigned += 1
                assigned_from_fallback += 1
            else:
                best_score = float(ranked[0][0]) if ranked else 0.0

                if preferred_assets:
                    reason = (
                        "Story Engine assets exist, but none were usable because of duration or max_use constraints; "
                        "no fallback asset reached the acceptance threshold."
                    )
                elif scene_id:
                    reason = (
                        f"Scene '{scene_id}' has no usable explicit asset; "
                        "no fallback asset reached the acceptance threshold."
                    )
                else:
                    reason = (
                        "No matching story scene was found; no fallback asset "
                        "reached the acceptance threshold."
                    )

                self._write_missing(
                    shot=shot,
                    best_score=best_score,
                    reason=reason,
                )
                missing += 1

        result = {
            "state": "ASSIGNMENT_COMPLETED",
            "project_id": self.project_id,
            "assigned": assigned,
            "assigned_from_story": assigned_from_story,
            "assigned_from_fallback": assigned_from_fallback,
            "missing": missing,
            "threshold": self.ACCEPTANCE_THRESHOLD,
            "policy": "AssignmentPolicyRC2",
        }

        self.bus.emit(
            "ASSIGNMENT_POLICY_COMPLETED",
            result,
        )

        return result
