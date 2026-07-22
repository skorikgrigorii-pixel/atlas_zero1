from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SUPPORTED_TRANSITIONS = {
    "cut",
    "hard_cut",
    "crossfade",
    "dissolve",
    "fade",
    "fade_black",
    "fade_white",
    "dip_to_black",
    "dip_to_white",
    "wipe_left",
    "wipe_right",
    "wipe_up",
    "wipe_down",
    "slide_left",
    "slide_right",
    "slide_up",
    "slide_down",
    "push_left",
    "push_right",
    "push_up",
    "push_down",
    "circle_open",
    "circle_close",
    "pixelize",
    "radial",
    "smooth_left",
    "smooth_right",
    "smooth_up",
    "smooth_down",
    "zoom_in",
    "zoom_out",
    "custom",
}


@dataclass(frozen=True)
class TransitionProfile:
    transition_type: str
    duration_sec: float
    enabled: bool
    ffmpeg_name: str
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TransitionValidator:
    MIN_DURATION_SEC = 0.05
    MAX_DURATION_SEC = 3.0

    @classmethod
    def validate(
        cls,
        transition_type: str,
        duration_sec: float,
        *,
        left_duration_sec: float,
        right_duration_sec: float,
    ) -> tuple[str, float, bool]:
        normalized = TransitionEngineRC2.normalize(transition_type)
        fallback = normalized not in SUPPORTED_TRANSITIONS
        if fallback:
            normalized = "cut"

        if normalized in {"cut", "hard_cut"}:
            return "cut", 0.0, fallback

        maximum_allowed = min(
            cls.MAX_DURATION_SEC,
            max(0.0, left_duration_sec - 0.01),
            max(0.0, right_duration_sec - 0.01),
        )
        if maximum_allowed < cls.MIN_DURATION_SEC:
            return "cut", 0.0, True

        duration = max(cls.MIN_DURATION_SEC, float(duration_sec or 0.5))
        duration = min(duration, maximum_allowed)
        return normalized, duration, fallback


class TransitionEngineRC2:
    """Normalize timeline transition labels and map them to FFmpeg xfade names."""

    FFMPEG_MAP = {
        "crossfade": "fade",
        "dissolve": "dissolve",
        "fade": "fade",
        "fade_black": "fadeblack",
        "fade_white": "fadewhite",
        "dip_to_black": "fadeblack",
        "dip_to_white": "fadewhite",
        "wipe_left": "wipeleft",
        "wipe_right": "wiperight",
        "wipe_up": "wipeup",
        "wipe_down": "wipedown",
        "slide_left": "slideleft",
        "slide_right": "slideright",
        "slide_up": "slideup",
        "slide_down": "slidedown",
        "push_left": "smoothleft",
        "push_right": "smoothright",
        "push_up": "smoothup",
        "push_down": "smoothdown",
        "circle_open": "circleopen",
        "circle_close": "circleclose",
        "pixelize": "pixelize",
        "radial": "radial",
        "smooth_left": "smoothleft",
        "smooth_right": "smoothright",
        "smooth_up": "smoothup",
        "smooth_down": "smoothdown",
        "zoom_in": "zoomin",
        "zoom_out": "fade",
        "custom": "fade",
    }

    @classmethod
    def build_profile(
        cls,
        clip: Any,
        *,
        left_duration_sec: float,
        right_duration_sec: float,
    ) -> TransitionProfile:
        raw_type = getattr(clip, "transition", None)
        if raw_type in (None, ""):
            raw_type = getattr(clip, "transition_type", "cut")
        raw_duration = getattr(clip, "transition_duration_sec", 0.5)

        normalized, duration, fallback = TransitionValidator.validate(
            str(raw_type or "cut"),
            float(raw_duration or 0.5),
            left_duration_sec=float(left_duration_sec),
            right_duration_sec=float(right_duration_sec),
        )
        enabled = normalized != "cut"
        ffmpeg_name = cls.FFMPEG_MAP.get(normalized, "fade") if enabled else "cut"
        return TransitionProfile(
            transition_type=normalized,
            duration_sec=duration,
            enabled=enabled,
            ffmpeg_name=ffmpeg_name,
            fallback_used=fallback,
        )

    @staticmethod
    def normalize(value: Any) -> str:
        text = str(value or "cut").strip().lower()
        aliases = {
            "": "cut",
            "none": "cut",
            "static": "cut",
            "hard cut": "cut",
            "hard_cut": "cut",
            "cross fade": "crossfade",
            "cross dissolve": "dissolve",
            "cross_dissolve": "dissolve",
            "dip to black": "dip_to_black",
            "dip black": "dip_to_black",
            "dip to white": "dip_to_white",
            "dip white": "dip_to_white",
            "wipe left": "wipe_left",
            "wipe right": "wipe_right",
            "wipe up": "wipe_up",
            "wipe down": "wipe_down",
            "slide left": "slide_left",
            "slide right": "slide_right",
            "slide up": "slide_up",
            "slide down": "slide_down",
            "push left": "push_left",
            "push right": "push_right",
            "push up": "push_up",
            "push down": "push_down",
            "circle open": "circle_open",
            "circle close": "circle_close",
            "zoom transition": "zoom_in",
            "zoom": "zoom_in",
        }
        return aliases.get(text, text.replace("-", "_").replace(" ", "_"))


class FFmpegTransitionGraphBuilder:
    """Build a deterministic video-only xfade filter graph."""

    @staticmethod
    def build(
        *,
        segment_durations: list[float],
        profiles: list[TransitionProfile],
    ) -> tuple[str, str, float]:
        if len(segment_durations) < 2:
            raise ValueError("At least two segments are required for a transition graph")
        if len(profiles) != len(segment_durations) - 1:
            raise ValueError("Transition profile count must equal segment count minus one")

        chains: list[str] = []
        previous_label = "[0:v]"
        cumulative_output_duration = float(segment_durations[0])

        for index, profile in enumerate(profiles, start=1):
            next_label = f"[{index}:v]"
            output_label = f"[vxf{index}]"

            if not profile.enabled:
                # The caller must not request a graph containing cuts.
                raise ValueError("Cut transitions require grouping before xfade graph generation")

            offset = max(0.0, cumulative_output_duration - profile.duration_sec)
            chains.append(
                f"{previous_label}{next_label}"
                f"xfade=transition={profile.ffmpeg_name}:"
                f"duration={profile.duration_sec:.6f}:"
                f"offset={offset:.6f}"
                f"{output_label}"
            )
            cumulative_output_duration += float(segment_durations[index]) - profile.duration_sec
            previous_label = output_label

        return ";".join(chains), previous_label, cumulative_output_duration
