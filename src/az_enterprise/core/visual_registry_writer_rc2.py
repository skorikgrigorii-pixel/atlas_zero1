from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp01(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)

    return max(0.0, min(1.0, number))


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


class VisualRegistryWriterRC2:
    """
    Canonical writer for semantic visual profiles.

    The analyzer remains responsible for inference.
    This writer is responsible only for persistence.
    """

    SCHEMA = "atlas_zero.visual_registry.rc2.v1"

    def __init__(
        self,
        *,
        db: Any,
        project_id: str,
    ) -> None:
        self.db = db
        self.project_id = str(project_id).strip()

        if not self.project_id:
            raise ValueError("project_id is required")

    def persist(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError(
                "Visual Registry payload must be a dictionary"
            )

        asset_id = clean_text(
            payload.get("asset_id")
        )

        if not asset_id:
            raise ValueError(
                "Visual Registry payload has no asset_id"
            )

        canonical_payload = self._canonical_payload(
            payload
        )

        style_score = self._style_score(
            canonical_payload
        )

        plan_type = self._plan_type(
            canonical_payload
        )

        palette = self._palette(
            canonical_payload
        )

        profile_json = json.dumps(
            canonical_payload,
            ensure_ascii=False,
            sort_keys=True,
        )

        self.db.execute(
            """
            INSERT INTO visual_profiles(
                asset_id,
                project_id,
                profile_json,
                style_score,
                plan_type,
                palette,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id)
            DO UPDATE SET
                project_id=excluded.project_id,
                profile_json=excluded.profile_json,
                style_score=excluded.style_score,
                plan_type=excluded.plan_type,
                palette=excluded.palette,
                created_at=excluded.created_at
            """,
            (
                asset_id,
                self.project_id,
                profile_json,
                style_score,
                plan_type,
                palette,
                utc_now(),
            ),
        )

        return {
            "state": "VISUAL_PROFILE_PERSISTED",
            "schema": self.SCHEMA,
            "project_id": self.project_id,
            "asset_id": asset_id,
            "style_score": style_score,
            "plan_type": plan_type,
            "palette": palette,
        }

    def _canonical_payload(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        canonical = dict(payload)

        canonical["schema"] = self.SCHEMA
        canonical["project_id"] = self.project_id

        canonical.setdefault(
            "registry_updated_at_utc",
            utc_now(),
        )

        evidence = canonical.get("evidence")

        if not isinstance(evidence, dict):
            evidence = {}

        canonical["evidence"] = evidence

        canonical.setdefault(
            "semantic_class",
            canonical.get("event_type"),
        )

        canonical.setdefault(
            "semantic_description",
            canonical.get("description"),
        )

        canonical.setdefault(
            "semantic_confidence",
            canonical.get("event_confidence"),
        )

        canonical.setdefault(
            "visual_plan",
            self._plan_type(canonical),
        )

        canonical.setdefault(
            "palette",
            self._palette(canonical),
        )

        canonical.setdefault(
            "style_consistency",
            self._style_score(canonical),
        )

        return canonical

    def _style_score(
        self,
        payload: dict[str, Any],
    ) -> float:
        evidence = payload.get("evidence")

        if not isinstance(evidence, dict):
            evidence = {}

        candidates = (
            evidence.get("cinematic_grade"),
            payload.get("style_consistency"),
            payload.get("story_value"),
            payload.get("event_confidence"),
            payload.get("relevance_score"),
        )

        for value in candidates:
            if value is None:
                continue

            try:
                return round(
                    clamp01(value),
                    6,
                )
            except (TypeError, ValueError):
                continue

        return 0.0

    def _plan_type(
        self,
        payload: dict[str, Any],
    ) -> str:
        existing = clean_text(
            payload.get("visual_plan")
            or payload.get("plan_type")
        )

        if existing:
            return existing

        event_type = clean_text(
            payload.get("event_type")
        ).lower()

        filename = clean_text(
            payload.get("filename")
        ).lower()

        combined = f"{event_type} {filename}"

        if any(
            marker in combined
            for marker in (
                "close",
                "detail",
                "artifact",
                "document",
                "note",
                "bones",
                "medical",
            )
        ):
            return "крупный план"

        if any(
            marker in combined
            for marker in (
                "aerial",
                "wide",
                "arctic",
                "ship",
                "landscape",
                "city",
            )
        ):
            return "общий план"

        if any(
            marker in combined
            for marker in (
                "crew",
                "person",
                "commander",
                "portrait",
                "preparation",
            )
        ):
            return "средний план"

        return "универсальный план"

    def _palette(
        self,
        payload: dict[str, Any],
    ) -> str:
        existing = clean_text(
            payload.get("palette")
        )

        if existing:
            return existing

        evidence = payload.get("evidence")

        if isinstance(evidence, dict):
            existing = clean_text(
                evidence.get("dominant_palette")
            )

            if existing:
                return existing

        time_period = clean_text(
            payload.get("time_period")
        ).lower()

        if time_period == "night":
            return "тёмная холодная"

        if time_period == "evening":
            return "приглушённая вечерняя"

        if time_period in {
            "morning",
            "day",
        }:
            return "естественная дневная"

        return "не определена"


def persist_visual_profile_rc2(
    *,
    db: Any,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    writer = VisualRegistryWriterRC2(
        db=db,
        project_id=project_id,
    )

    return writer.persist(payload)
