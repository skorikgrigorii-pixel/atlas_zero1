from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any


@dataclass(frozen=True)
class ProjectProfile:
    name: str
    description: str
    static_sequence_length: int
    maximum_video_gap_sec: float
    repeated_visual_pattern_length: int
    minimum_visual_dynamics_index: float


PROFILES: dict[str, ProjectProfile] = {
    "balanced": ProjectProfile(
        name="balanced",
        description="Universal balanced profile and backward-compatible default.",
        static_sequence_length=3,
        maximum_video_gap_sec=18.0,
        repeated_visual_pattern_length=3,
        minimum_visual_dynamics_index=0.40,
    ),
    "event_short": ProjectProfile(
        name="event_short",
        description="Dynamic short event video such as Hogueras.",
        static_sequence_length=2,
        maximum_video_gap_sec=6.0,
        repeated_visual_pattern_length=3,
        minimum_visual_dynamics_index=0.62,
    ),
    "documentary": ProjectProfile(
        name="documentary",
        description="Measured long-form documentary storytelling.",
        static_sequence_length=6,
        maximum_video_gap_sec=24.0,
        repeated_visual_pattern_length=4,
        minimum_visual_dynamics_index=0.34,
    ),
    "interview": ProjectProfile(
        name="interview",
        description="Interview or talking-head production.",
        static_sequence_length=12,
        maximum_video_gap_sec=90.0,
        repeated_visual_pattern_length=5,
        minimum_visual_dynamics_index=0.20,
    ),
}


def resolve_project_profile(config: Any) -> ProjectProfile:
    requested = str(
        getattr(
            config,
            "project_profile",
            getattr(config, "project_type", "balanced"),
        )
        or "balanced"
    ).strip().lower()

    aliases = {
        "hogueras": "event_short",
        "festival": "event_short",
        "short": "event_short",
        "shorts": "event_short",
        "tiktok": "event_short",
        "youtube_short": "event_short",
        "doc": "documentary",
        "longform_documentary": "documentary",
        "talking_head": "interview",
    }
    profile_name = aliases.get(requested, requested)

    if profile_name not in PROFILES:
        available = ", ".join(sorted(PROFILES))
        raise ValueError(
            f"Unknown project profile {requested!r}. Available profiles: {available}."
        )

    profile = PROFILES[profile_name]
    overrides: dict[str, Any] = {}

    for name in (
        "static_sequence_length",
        "maximum_video_gap_sec",
        "repeated_visual_pattern_length",
        "minimum_visual_dynamics_index",
    ):
        value = getattr(config, name, None)
        if value is not None:
            overrides[name] = value

    if "static_sequence_length" in overrides:
        overrides["static_sequence_length"] = max(
            1, int(overrides["static_sequence_length"])
        )
    if "maximum_video_gap_sec" in overrides:
        overrides["maximum_video_gap_sec"] = max(
            0.0, float(overrides["maximum_video_gap_sec"])
        )
    if "repeated_visual_pattern_length" in overrides:
        overrides["repeated_visual_pattern_length"] = max(
            2, int(overrides["repeated_visual_pattern_length"])
        )
    if "minimum_visual_dynamics_index" in overrides:
        overrides["minimum_visual_dynamics_index"] = min(
            1.0,
            max(0.0, float(overrides["minimum_visual_dynamics_index"])),
        )

    return replace(profile, **overrides)


def profile_to_dict(profile: ProjectProfile) -> dict[str, Any]:
    return asdict(profile)


def available_profiles() -> tuple[str, ...]:
    return tuple(sorted(PROFILES))
