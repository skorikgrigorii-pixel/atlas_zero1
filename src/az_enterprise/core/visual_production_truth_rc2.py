from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SCHEMA = "ATLAS_ZERO_VISUAL_PRODUCTION_TRUTH_RC2_4"


MOTION_REQUIRED_PATTERNS = (
    r"\bwalks?\b",
    r"\bwalking\b",
    r"\bcrosses?\b",
    r"\bleaves?\b",
    r"\benters?\b",
    r"\bopens?\b.*\bdoor\b",
    r"\bcloses?\b.*\bdoor\b",
    r"\bgets up\b",
    r"\bstands up\b",
    r"\bsits down\b",
    r"\bpicks? up\b",
    r"\bputs? down\b",
    r"\bhands? .* over\b",
)


MOTION_OPTIONAL_PATTERNS = (
    r"\btypes?\b",
    r"\bscrolls?\b",
    r"\bturns?\b",
    r"\breaches?\b",
    r"\bgestures?\b",
    r"\blooks? back\b",
    r"\blooks? toward\b",
    r"\bpauses?\b",
    r"\bspeaks?\b",
)


STATIC_PATTERNS = (
    r"\bsits? quietly\b",
    r"\bstands? quietly\b",
    r"\bwatches?\b",
    r"\bobserves?\b",
    r"\bremains?\b",
    r"\bholds?\b",
    r"\bfinal .* image\b",
)


@dataclass
class ProductionTruthRC2:
    shot_id: str
    scene_id: str

    production_type: str
    director_action: str

    location: str
    time_state: str
    characters: tuple[str, ...]

    continuity_mode: str
    continuity_sequence: str
    continuity_before: dict[str, Any]
    continuity_after: dict[str, Any]

    evidence_required: bool
    ui_required: bool

    motion_class: str
    motion_reason: str

    asset_requirement: str

    approved_existing: bool
    approved_asset_kind: str | None

    semantic_source: str
    source_file: str

    upstream_visual_type: str
    stale_upstream_override: bool

    warnings: list[str] = field(default_factory=list)


def _read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )
    )


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _upper(value: Any, fallback: str) -> str:
    text = _norm(value)
    return text.upper() if text else fallback


def _extract_time(action: str) -> str:
    lower = action.lower()

    checks = (
        ("EARLY_MORNING", ("early morning", "dawn")),
        ("MORNING", ("morning",)),
        ("DAYLIGHT", ("daylight", "daytime")),
        ("AFTERNOON", ("afternoon",)),
        ("EVENING", ("evening",)),
        ("LATE_NIGHT", ("late night", "deep night")),
        ("NIGHT", ("night",)),
    )

    for label, phrases in checks:
        if any(p in lower for p in phrases):
            return label

    return "UNKNOWN_TIME"


def _motion_class(action: str) -> tuple[str, str]:
    """
    Screen action only.

    Camera instructions from video_motion_prompt are intentionally ignored.
    """

    lower = action.lower()

    # A final observational tableau should not become required video merely
    # because a person "stands" in the composition.
    if any(re.search(p, lower) for p in STATIC_PATTERNS):
        strong = [
            p for p in MOTION_REQUIRED_PATTERNS
            if re.search(p, lower)
        ]

        if not strong:
            return (
                "STILL_PREFERRED",
                "observational/static screen action",
            )

    required = [
        p for p in MOTION_REQUIRED_PATTERNS
        if re.search(p, lower)
    ]

    if required:
        return (
            "VIDEO_REQUIRED",
            "temporal physical action changes screen state",
        )

    optional = [
        p for p in MOTION_OPTIONAL_PATTERNS
        if re.search(p, lower)
    ]

    if optional:
        return (
            "VIDEO_OPTIONAL",
            "motion can add screen value but is not essential",
        )

    return (
        "STILL_PREFERRED",
        "no essential temporal screen action",
    )


class ApprovedAssetRegistryRC2:
    def __init__(self, path: Path | None = None) -> None:
        self.items: dict[str, dict[str, Any]] = {}

        if path is not None and path.exists():
            payload = _read_json(path)

            for item in payload.get("assets", []):
                sid = _norm(item.get("shot_id"))

                if sid:
                    self.items[sid] = item

    def get(self, shot_id: str) -> dict[str, Any] | None:
        return self.items.get(shot_id)

    def approved(self, shot_id: str) -> bool:
        item = self.get(shot_id)

        return bool(
            item
            and item.get("approval_status") == "APPROVED"
        )


    def reference_only(
        self,
        shot_id: str,
    ) -> bool:

        item = self.get(
            shot_id
        )

        if not item:
            return False

        status = str(
            item.get(
                "approval_status",
                "",
            )
        ).strip().upper()

        rights = str(
            item.get(
                "rights_status",
                item.get(
                    "rights_decision",
                    "",
                ),
            )
        ).strip().upper()

        return (
            status == "REFERENCE_ONLY"
            or rights == "REFERENCE_ONLY"
        )


class ProductionTruthIndexRC2:
    """
    Generic production-package reader.

    No Film 08 / SC07-specific semantics are hardcoded here.
    Any JSON object containing shot_id + director_action is considered
    production truth for that shot.
    """

    def __init__(self) -> None:
        self.items: dict[str, list[dict[str, Any]]] = {}

    def add_json_file(self, path: Path) -> None:
        try:
            payload = _read_json(path)
        except Exception:
            return

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                sid = _norm(value.get("shot_id"))

                if sid and _norm(value.get("director_action")):
                    obj = dict(value)
                    obj["_production_truth_source"] = str(path)

                    self.items.setdefault(
                        sid,
                        [],
                    ).append(obj)

                for child in value.values():
                    walk(child)

            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)

    def add_tree(self, root: Path) -> None:
        if not root.exists():
            return

        for path in root.rglob("*.json"):
            try:
                if path.stat().st_size > 20 * 1024 * 1024:
                    continue
            except OSError:
                continue

            self.add_json_file(path)

    def best(self, shot_id: str) -> dict[str, Any] | None:
        candidates = self.items.get(
            shot_id,
            [],
        )

        if not candidates:
            return None

        def score(obj: dict[str, Any]) -> int:
            result = 0
            source = str(
                obj.get(
                    "_production_truth_source",
                    "",
                )
            ).lower()

            if "production_package" in source:
                result += 1000

            if obj.get("director_action"):
                result += 200

            if obj.get("location"):
                result += 100

            if obj.get("characters"):
                result += 100

            if obj.get("continuity"):
                result += 150

            if obj.get("image_keyframe_prompt"):
                result += 20

            return result

        return max(
            candidates,
            key=score,
        )


class ProductionTruthEngineRC2:
    def __init__(
        self,
        truth_index: ProductionTruthIndexRC2,
        approved_registry: ApprovedAssetRegistryRC2,
    ) -> None:
        self.truth_index = truth_index
        self.approved_registry = approved_registry

    def analyze(
        self,
        shot: dict[str, Any],
        *,
        scene_id: str,
        fallback_shot_id: str,
    ) -> ProductionTruthRC2:

        shot_id = _norm(
            shot.get("shot_id")
            or shot.get("id")
            or fallback_shot_id
        )

        upstream_type = _upper(
            shot.get("visual_type")
            or shot.get("type"),
            "UNKNOWN",
        )

        truth = self.truth_index.best(
            shot_id
        )

        approved_item = (
            self.approved_registry.get(
                shot_id
            )
        )

        approved = bool(
            approved_item
            and approved_item.get(
                "approval_status"
            ) == "APPROVED"
        )

        reference_only = (
            self.approved_registry.reference_only(
                shot_id
            )
        )

        warnings: list[str] = []

        if reference_only:
            warnings.append(
                "REFERENCE_ONLY_SOURCE_AVAILABLE_"
                "GENERATE_ORIGINAL_REPLACEMENT"
            )

        if truth is not None:
            action = _norm(
                truth.get(
                    "director_action"
                )
            )

            location = _upper(
                truth.get("location"),
                "UNKNOWN_LOCATION",
            )

            characters = tuple(
                sorted(
                    {
                        _upper(x, "")
                        for x in truth.get(
                            "characters",
                            [],
                        )
                        if _norm(x)
                    }
                )
            )

            continuity = (
                truth.get("continuity")
                if isinstance(
                    truth.get("continuity"),
                    dict,
                )
                else {}
            )

            before = (
                continuity.get("before")
                if isinstance(
                    continuity.get("before"),
                    dict,
                )
                else {}
            )

            after = (
                continuity.get("after")
                if isinstance(
                    continuity.get("after"),
                    dict,
                )
                else {}
            )

            production_type = _upper(
                truth.get("visual_type"),
                upstream_type,
            )

            source = str(
                truth.get(
                    "_production_truth_source",
                    "",
                )
            )

            semantic_source = (
                "PRODUCTION_PACKAGE_TRUTH"
            )

        else:
            action = _norm(
                shot.get("director_action")
                or shot.get("screen_action")
                or shot.get("action")
            )

            location = _upper(
                shot.get("location"),
                "UNKNOWN_LOCATION",
            )

            chars = shot.get(
                "characters",
                [],
            )

            if not isinstance(chars, list):
                chars = []

            characters = tuple(
                sorted(
                    {
                        _upper(x, "")
                        for x in chars
                        if _norm(x)
                    }
                )
            )

            before = {}
            after = {}
            continuity = {}

            production_type = (
                upstream_type
            )

            source = ""
            semantic_source = (
                "EDITORIAL_MAP_FALLBACK"
            )

            warnings.append(
                "NO_PRODUCTION_PACKAGE_TRUTH"
            )

        time_state = _extract_time(
            action
        )

        # Production action can prove that a stale RESEARCH_EVIDENCE label
        # is actually a human cinematic reconstruction.
        lower_action = action.lower()

        human_reconstruction = bool(
            characters
            and (
                location
                != "UNKNOWN_LOCATION"
            )
            and not any(
                phrase in lower_action
                for phrase in (
                    "research paper",
                    "scientific study",
                    "court document",
                    "court filing",
                    "headline",
                    "chart",
                    "graph",
                    "dataset",
                    "statistics",
                )
            )
        )

        stale_override = False

        if (
            production_type
            == "RESEARCH_EVIDENCE"
            and human_reconstruction
        ):
            production_type = (
                "CINEMATIC_RECONSTRUCTION"
            )

            stale_override = True

            warnings.append(
                "STALE_UPSTREAM_EVIDENCE_LABEL_OVERRIDDEN"
            )

        evidence_required = (
            production_type
            == "RESEARCH_EVIDENCE"
        )

        ui_required = (
            production_type == "UI"
        )

        motion_class, motion_reason = (
            _motion_class(
                action
            )
        )

        if evidence_required or ui_required:
            motion_class = (
                "SOURCE_NATIVE"
            )

            motion_reason = (
                "evidence/UI acquisition uses native source behavior"
            )

        if approved:
            asset_requirement = (
                "REUSE_APPROVED"
            )
        elif reference_only:
            asset_requirement = (
                "NEW_GENERATED_REFERENCE_GUIDED"
            )
        elif evidence_required:
            asset_requirement = (
                "REAL_ASSET"
            )

        elif ui_required:
            asset_requirement = (
                "EVIDENCE_UI"
            )

        else:
            asset_requirement = (
                "NEW_GENERATED"
            )

        return ProductionTruthRC2(
            shot_id=shot_id,
            scene_id=scene_id,
            production_type=production_type,
            director_action=action,
            location=location,
            time_state=time_state,
            characters=characters,
            continuity_mode=_upper(
                continuity.get("mode"),
                "UNKNOWN",
            ),
            continuity_sequence=_norm(
                continuity.get(
                    "sequence"
                )
            ),
            continuity_before=before,
            continuity_after=after,
            evidence_required=evidence_required,
            ui_required=ui_required,
            motion_class=motion_class,
            motion_reason=motion_reason,
            asset_requirement=asset_requirement,
            approved_existing=approved,
            approved_asset_kind=(
                _norm(
                    approved_item.get(
                        "asset_kind"
                    )
                )
                if approved_item
                else None
            ),
            semantic_source=semantic_source,
            source_file=source,
            upstream_visual_type=upstream_type,
            stale_upstream_override=stale_override,
            warnings=warnings,
        )


def to_dict(value: ProductionTruthRC2) -> dict[str, Any]:
    return asdict(value)