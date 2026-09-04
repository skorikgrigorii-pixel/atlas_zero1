from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SCHEMA = "ATLAS_ZERO_VISUAL_PRODUCTION_SEMANTICS_RC2_3"


# -----------------------------------------------------------------------------
# Exact production-field priority
# -----------------------------------------------------------------------------

ACTION_KEYS = (
    "screen_action",
    "visual_action",
    "action",
    "shot_action",
    "editorial_action",
    "subject_action",
    "performance",
)

LOCATION_KEYS = (
    "location",
    "location_id",
    "environment",
    "setting",
    "room",
)

TIME_KEYS = (
    "time_state",
    "time_of_day",
    "time",
    "lighting_state",
)

CHARACTER_KEYS = (
    "characters",
    "character",
    "subjects",
    "subject",
    "people",
)

EVIDENCE_KEYS = (
    "evidence_required",
    "requires_evidence",
    "evidence",
    "source_requirement",
    "evidence_source",
)

UI_KEYS = (
    "ui_required",
    "requires_ui",
    "ui",
    "interface_required",
)

EDITORIAL_KEYS = (
    "editorial_intent",
    "visual_intent",
    "shot_purpose",
    "purpose",
)

CONTINUITY_KEYS = (
    "continuity_before",
    "continuity_after",
    "continuity_state",
    "continuity",
)


LOCATION_PATTERNS = (
    ("HOME_OFFICE", (
        "home office",
        "office",
        "desk",
    )),
    ("LIVING_ROOM", (
        "living room",
        "lounge",
        "sofa",
        "couch",
    )),
    ("KITCHEN", (
        "kitchen",
        "kitchen table",
        "counter",
    )),
    ("HALLWAY", (
        "hallway",
        "corridor",
        "front door",
        "entryway",
    )),
    ("BEDROOM", (
        "bedroom",
        "child bedroom",
        "child's bedroom",
    )),
    ("STREET", (
        "street",
        "sidewalk",
    )),
    ("COURTROOM", (
        "courtroom",
    )),
    ("CLASSROOM", (
        "classroom",
    )),
    ("HOSPITAL", (
        "hospital",
        "clinic",
    )),
    ("CAR", (
        "car interior",
        "inside car",
    )),
)


TIME_PATTERNS = (
    ("EARLY_MORNING", (
        "early morning",
        "dawn",
    )),
    ("MORNING", (
        "morning",
    )),
    ("DAYLIGHT", (
        "daylight",
        "daytime",
        "day time",
    )),
    ("AFTERNOON", (
        "afternoon",
    )),
    ("EVENING", (
        "evening",
    )),
    ("LATE_NIGHT", (
        "late night",
        "deep night",
    )),
    ("NIGHT", (
        "night",
        "nighttime",
    )),
)


STRONG_MOTION_PHRASES = (
    "walks out",
    "walk out",
    "walks away",
    "walk away",
    "walks through",
    "walk through",
    "walks toward",
    "walk toward",
    "opens front door",
    "opens the front door",
    "closes front door",
    "closes the front door",
    "leaves house",
    "leaves the house",
    "leaves home",
    "enters room",
    "enters the room",
    "crosses room",
    "crosses the room",
    "gets up",
    "stands up",
    "sits down",
    "moves across",
    "moves toward",
    "turns away",
    "turns toward",
    "picks up",
    "puts down",
    "hands over",
    "arrives",
    "departs",
)


OPTIONAL_MOTION_PHRASES = (
    "withdraws from conversation",
    "returns to conversation",
    "speaks cautiously",
    "gestures",
    "types message",
    "types messages",
    "scrolls",
    "looks toward",
    "looks back",
    "turns head",
    "reaches for",
    "holds phone",
)


EVIDENCE_PHRASES = (
    "scientific study",
    "research paper",
    "study methodology",
    "study result",
    "dataset",
    "court filing",
    "court document",
    "lawsuit filing",
    "published report",
    "headline",
    "statistics",
    "chart",
    "graph",
    "evidence source",
)


UI_PHRASES = (
    "chat interface",
    "app interface",
    "message interface",
    "browser window",
    "website interface",
    "phone screen ui",
    "screen capture",
)


HUMAN_TERMS = (
    "scott",
    "wife",
    "son",
    "child",
    "family",
    "travis",
    "lily",
    "sewell",
    "megan",
    "mother",
    "father",
    "man",
    "woman",
)


@dataclass
class ProductionSemanticsRC2:
    shot_id: str

    screen_action: str
    location: str
    time_state: str
    characters: tuple[str, ...]

    evidence_required: bool
    ui_required: bool

    motion_class: str
    motion_score: int

    semantic_source: str
    semantic_confidence: float

    continuity_context: str = ""

    upstream_visual_type: str = "UNKNOWN"
    upstream_editorial_intent: str = ""

    raw_semantic_text: str = ""

    warnings: list[str] = field(default_factory=list)


# -----------------------------------------------------------------------------
# Generic helpers
# -----------------------------------------------------------------------------

def _normalize(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        text = value
    else:
        text = str(value)

    # Important RC2.3:
    # production packages frequently store semantic tokens as:
    # SCOTT_OPENS_FRONT_DOOR
    # Normalize them for NLP / heuristic reading.
    text = text.replace("_", " ")
    text = text.replace("-", " ")

    return " ".join(
        text.split()
    )


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return _normalize(value)

    if isinstance(value, (int, float, bool)):
        return _normalize(value)

    if isinstance(value, list):
        return " ".join(
            x
            for x in (
                _value_to_text(item)
                for item in value
            )
            if x
        )

    if isinstance(value, dict):
        preferred = []

        for key in (
            "name",
            "id",
            "label",
            "value",
            "description",
            "action",
            "state",
        ):
            if key in value:
                text = _value_to_text(
                    value.get(key)
                )

                if text:
                    preferred.append(text)

        if preferred:
            return " ".join(preferred)

        return " ".join(
            x
            for x in (
                _value_to_text(v)
                for v in value.values()
            )
            if x
        )

    return ""


def _direct_value(
    obj: dict[str, Any],
    keys: tuple[str, ...],
) -> Any:

    for key in keys:
        if key in obj:
            value = obj.get(key)

            if value not in (
                None,
                "",
                [],
                {},
            ):
                return value

    return None


def _nested_exact_value(
    obj: dict[str, Any],
    keys: tuple[str, ...],
    *,
    max_depth: int = 4,
) -> Any:
    """
    Search only for an exact field belonging to THIS shot object.

    This deliberately does NOT flatten complete continuity structures,
    sibling shot arrays, references, or scene packages.
    """

    direct = _direct_value(
        obj,
        keys,
    )

    if direct is not None:
        return direct

    safe_parents = (
        "production",
        "visual",
        "shot",
        "semantics",
        "director",
        "camera",
        "timing",
        "setting",
        "subject",
        "performance",
    )

    def walk(
        value: Any,
        depth: int,
    ) -> Any:

        if depth > max_depth:
            return None

        if not isinstance(value, dict):
            return None

        direct = _direct_value(
            value,
            keys,
        )

        if direct is not None:
            return direct

        for parent in safe_parents:
            child = value.get(parent)

            if isinstance(child, dict):
                found = walk(
                    child,
                    depth + 1,
                )

                if found is not None:
                    return found

        return None

    return walk(
        obj,
        0,
    )


def _editorial_intent(
    obj: dict[str, Any],
) -> str:

    value = _nested_exact_value(
        obj,
        EDITORIAL_KEYS,
    )

    return _value_to_text(
        value
    )


def _visual_type(
    obj: dict[str, Any],
) -> str:

    for key in (
        "visual_type",
        "asset_type",
        "shot_type",
        "type",
    ):
        value = obj.get(key)

        if isinstance(value, str):
            value = value.strip()

            if value:
                return value.upper()

    return "UNKNOWN"


def _infer_location(
    explicit_value: Any,
    action_text: str,
) -> str:

    explicit = _normalize(
        _value_to_text(
            explicit_value
        )
    )

    text = (
        explicit
        if explicit
        else action_text
    )

    lower = text.lower()

    # Exact normalized labels first.
    canonical = {
        "home office": "HOME_OFFICE",
        "living room": "LIVING_ROOM",
        "kitchen": "KITCHEN",
        "hallway": "HALLWAY",
        "bedroom": "BEDROOM",
        "street": "STREET",
        "courtroom": "COURTROOM",
        "classroom": "CLASSROOM",
        "hospital": "HOSPITAL",
        "car": "CAR",
    }

    if lower in canonical:
        return canonical[lower]

    for label, patterns in LOCATION_PATTERNS:
        for pattern in patterns:
            if pattern in lower:
                return label

    return "UNKNOWN_LOCATION"


def _infer_time(
    explicit_value: Any,
    action_text: str,
) -> str:

    explicit = _normalize(
        _value_to_text(
            explicit_value
        )
    )

    text = (
        explicit
        if explicit
        else action_text
    )

    lower = text.lower()

    canonical = {
        "early morning": "EARLY_MORNING",
        "morning": "MORNING",
        "daylight": "DAYLIGHT",
        "daytime": "DAYLIGHT",
        "afternoon": "AFTERNOON",
        "evening": "EVENING",
        "late night": "LATE_NIGHT",
        "night": "NIGHT",
    }

    if lower in canonical:
        return canonical[lower]

    for label, patterns in TIME_PATTERNS:
        for pattern in patterns:
            if pattern in lower:
                return label

    return "UNKNOWN_TIME"


def _characters_from_value(
    value: Any,
) -> tuple[str, ...]:

    found: list[str] = []

    def collect(v: Any) -> None:
        if isinstance(v, str):
            text = _normalize(v).lower()

            if text:
                found.append(
                    text.replace(" ", "_")
                )

        elif isinstance(v, list):
            for item in v:
                collect(item)

        elif isinstance(v, dict):
            name = (
                v.get("name")
                or v.get("id")
                or v.get("character")
                or v.get("subject")
            )

            if name is not None:
                collect(name)

    collect(value)

    return tuple(
        sorted(
            set(found)
        )
    )


def _infer_characters(
    explicit_value: Any,
    action_text: str,
) -> tuple[str, ...]:

    explicit = _characters_from_value(
        explicit_value
    )

    if explicit:
        return explicit

    lower = action_text.lower()

    found = []

    for term in HUMAN_TERMS:
        if re.search(
            rf"\b{re.escape(term)}\b",
            lower,
        ):
            found.append(term)

    return tuple(
        sorted(
            set(found)
        )
    )


def _boolish(
    value: Any,
) -> bool | None:

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = (
            value
            .strip()
            .lower()
        )

        if normalized in {
            "true",
            "yes",
            "required",
            "require",
            "1",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "not required",
            "none",
            "0",
        }:
            return False

    return None


def _has_phrase(
    text: str,
    phrases: tuple[str, ...],
) -> bool:

    lower = text.lower()

    return any(
        phrase in lower
        for phrase in phrases
    )


def _motion(
    action_text: str,
    editorial_intent: str,
    evidence_required: bool,
    ui_required: bool,
) -> tuple[str, int]:

    if evidence_required or ui_required:
        return "STILL_PREFERRED", 0

    action = _normalize(
        action_text
    ).lower()

    if _has_phrase(
        action,
        STRONG_MOTION_PHRASES,
    ):
        return "VIDEO_REQUIRED", 3

    optional_hits = sum(
        1
        for phrase in OPTIONAL_MOTION_PHRASES
        if phrase in action
    )

    if optional_hits:
        return (
            "VIDEO_OPTIONAL",
            optional_hits,
        )

    # Generic verbs after underscore normalization.
    verbs = (
        "walk",
        "open",
        "close",
        "leave",
        "enter",
        "cross",
        "move",
        "turn",
        "reach",
        "pick",
        "put",
        "stand",
        "sit",
        "type",
        "scroll",
        "gesture",
    )

    verb_hits = sum(
        1
        for verb in verbs
        if re.search(
            rf"\b{verb}(?:s|ed|ing)?\b",
            action,
        )
    )

    if verb_hits >= 3:
        return (
            "VIDEO_OPTIONAL",
            verb_hits,
        )

    intent = (
        editorial_intent
        .upper()
        .replace(" ", "_")
    )

    if (
        "OBSERVE_CHARACTER_BEHAVIOR"
        in intent
        and verb_hits >= 1
    ):
        return (
            "VIDEO_OPTIONAL",
            max(
                1,
                verb_hits,
            ),
        )

    return (
        "STILL_PREFERRED",
        verb_hits,
    )


# -----------------------------------------------------------------------------
# Exact-shot overlay index
# -----------------------------------------------------------------------------

class ProductionSemanticOverlayIndexRC2:
    """
    Exact-shot overlay index.

    Critical RC2.3 invariant:
      metadata for shot X must never be inferred from sibling shot Y.
    """

    def __init__(self) -> None:
        self._items: dict[
            str,
            list[dict[str, Any]],
        ] = {}

    def add_object(
        self,
        obj: Any,
        *,
        source: str,
    ) -> None:

        def walk(
            value: Any,
        ) -> None:

            if isinstance(value, dict):
                shot_id = value.get(
                    "shot_id"
                )

                if (
                    isinstance(
                        shot_id,
                        str,
                    )
                    and shot_id.strip()
                ):
                    # Copy exactly THIS dictionary.
                    # Do not transform parent package into overlay.
                    item = dict(value)

                    item[
                        "_semantic_overlay_source"
                    ] = source

                    self._items.setdefault(
                        shot_id.strip(),
                        [],
                    ).append(item)

                for key, child in value.items():
                    # Traverse to FIND shot objects,
                    # but parent/sibling content is never copied
                    # into the found shot.
                    if key == "_semantic_overlay_source":
                        continue

                    walk(child)

            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(obj)

    def add_json_file(
        self,
        path: str | Path,
    ) -> None:

        path = Path(path)

        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            )
        except Exception:
            return

        self.add_object(
            payload,
            source=str(path),
        )

    def add_tree(
        self,
        root: str | Path,
        *,
        max_file_mb: float = 20.0,
    ) -> None:

        root = Path(root)

        if not root.exists():
            return

        for path in root.rglob(
            "*.json"
        ):
            try:
                size = path.stat().st_size
            except OSError:
                continue

            if (
                size
                > max_file_mb
                * 1024
                * 1024
            ):
                continue

            self.add_json_file(
                path
            )

    def get(
        self,
        shot_id: str,
    ) -> list[dict[str, Any]]:

        return list(
            self._items.get(
                shot_id,
                [],
            )
        )

    @staticmethod
    def _candidate_score(
        obj: dict[str, Any],
    ) -> int:

        score = 0

        source = str(
            obj.get(
                "_semantic_overlay_source",
                "",
            )
        ).lower()

        if "production_package" in source:
            score += 120

        if "shot_cards" in source:
            score += 110

        if "leonardo_manual" in source:
            score += 100

        if "editorial_visual_treatment" in source:
            score += 50

        if _nested_exact_value(
            obj,
            ACTION_KEYS,
        ) is not None:
            score += 50

        if _nested_exact_value(
            obj,
            LOCATION_KEYS,
        ) is not None:
            score += 30

        if _nested_exact_value(
            obj,
            TIME_KEYS,
        ) is not None:
            score += 20

        if _nested_exact_value(
            obj,
            CHARACTER_KEYS,
        ) is not None:
            score += 20

        return score

    def best(
        self,
        shot_id: str,
    ) -> dict[str, Any] | None:

        items = self.get(
            shot_id
        )

        if not items:
            return None

        ranked = sorted(
            items,
            key=self._candidate_score,
            reverse=True,
        )

        return ranked[0]


# -----------------------------------------------------------------------------
# Semantic engine
# -----------------------------------------------------------------------------

class VisualProductionSemanticsRC2:
    def __init__(
        self,
        overlay_index: ProductionSemanticOverlayIndexRC2 | None = None,
    ) -> None:

        self.overlay_index = (
            overlay_index
            or ProductionSemanticOverlayIndexRC2()
        )

    def analyze(
        self,
        shot: dict[str, Any],
        *,
        fallback_shot_id: str,
    ) -> ProductionSemanticsRC2:

        shot_id = str(
            shot.get("shot_id")
            or shot.get("id")
            or fallback_shot_id
        )

        upstream_type = _visual_type(
            shot
        )

        editorial_intent = (
            _editorial_intent(
                shot
            )
        )

        overlay = (
            self.overlay_index.best(
                shot_id
            )
        )

        source_obj = (
            overlay
            if overlay is not None
            else shot
        )

        action_value = (
            _nested_exact_value(
                source_obj,
                ACTION_KEYS,
            )
        )

        action_text = _value_to_text(
            action_value
        )

        if not action_text:
            if (
                "OBSERVE"
                in editorial_intent.upper()
            ):
                action_text = (
                    "Observe restrained character behavior."
                )

            elif (
                "DETAIL"
                in editorial_intent.upper()
            ):
                action_text = (
                    "Use a restrained reaction or detail."
                )

            else:
                action_text = (
                    "Establish the current editorial beat."
                )

        location_value = (
            _nested_exact_value(
                source_obj,
                LOCATION_KEYS,
            )
        )

        time_value = (
            _nested_exact_value(
                source_obj,
                TIME_KEYS,
            )
        )

        characters_value = (
            _nested_exact_value(
                source_obj,
                CHARACTER_KEYS,
            )
        )

        evidence_value = (
            _nested_exact_value(
                source_obj,
                EVIDENCE_KEYS,
            )
        )

        ui_value = (
            _nested_exact_value(
                source_obj,
                UI_KEYS,
            )
        )

        location = _infer_location(
            location_value,
            action_text,
        )

        time_state = _infer_time(
            time_value,
            action_text,
        )

        characters = _infer_characters(
            characters_value,
            action_text,
        )

        explicit_evidence = _boolish(
            evidence_value
        )

        explicit_ui = _boolish(
            ui_value
        )

        evidence_language = _has_phrase(
            action_text,
            EVIDENCE_PHRASES,
        )

        ui_language = _has_phrase(
            action_text,
            UI_PHRASES,
        )

        # RC2.3 precedence:
        # exact production semantics outrank stale upstream category.
        if explicit_evidence is not None:
            evidence_required = explicit_evidence

        elif overlay is not None:
            evidence_required = (
                evidence_language
            )

        else:
            evidence_required = (
                upstream_type
                == "RESEARCH_EVIDENCE"
            )

        if explicit_ui is not None:
            ui_required = explicit_ui

        elif overlay is not None:
            ui_required = ui_language

        else:
            ui_required = (
                upstream_type == "UI"
            )

        motion_class, motion_score = (
            _motion(
                action_text,
                editorial_intent,
                evidence_required,
                ui_required,
            )
        )

        continuity_value = (
            _nested_exact_value(
                source_obj,
                CONTINUITY_KEYS,
            )
        )

        continuity_context = (
            _value_to_text(
                continuity_value
            )
        )

        warnings: list[str] = []

        if overlay is None:
            warnings.append(
                "NO_RICH_PRODUCTION_OVERLAY"
            )

        if (
            location
            == "UNKNOWN_LOCATION"
        ):
            warnings.append(
                "LOCATION_NOT_DEFINED"
            )

        if (
            time_state
            == "UNKNOWN_TIME"
        ):
            warnings.append(
                "TIME_STATE_NOT_DEFINED"
            )

        if (
            upstream_type
            == "RESEARCH_EVIDENCE"
            and not evidence_required
        ):
            warnings.append(
                "STALE_UPSTREAM_EVIDENCE_LABEL_OVERRIDDEN"
            )

        if overlay is not None:
            semantic_source = (
                "EXACT_SHOT_PRODUCTION_OVERLAY"
            )
            confidence = 0.98

        else:
            semantic_source = (
                "EDITORIAL_MAP_FALLBACK"
            )
            confidence = 0.55

        raw = " | ".join(
            x
            for x in (
                f"ACTION={action_text}",
                f"LOCATION={location}",
                f"TIME={time_state}",
                f"CHARACTERS={characters}",
                f"CONTINUITY={continuity_context}",
            )
            if x
        )

        return ProductionSemanticsRC2(
            shot_id=shot_id,
            screen_action=action_text,
            location=location,
            time_state=time_state,
            characters=characters,
            evidence_required=evidence_required,
            ui_required=ui_required,
            motion_class=motion_class,
            motion_score=motion_score,
            semantic_source=semantic_source,
            semantic_confidence=confidence,
            continuity_context=continuity_context[:1000],
            upstream_visual_type=upstream_type,
            upstream_editorial_intent=editorial_intent,
            raw_semantic_text=raw[:3000],
            warnings=warnings,
        )


def semantics_to_dict(
    value: ProductionSemanticsRC2,
) -> dict[str, Any]:

    return asdict(
        value
    )