from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SUPPORTED_MOTIONS = {
    "static", "push_in", "push_out", "slow_push", "slow_pull",
    "slow_pan", "pan_left", "pan_right", "pan_up", "pan_down",
    "tilt_up", "tilt_down", "slow_drift", "parallax", "ken_burns", "custom",
}
SUPPORTED_EASING = {"linear", "ease_in", "ease_out", "ease_in_out", "smoothstep", "cubic"}


@dataclass(frozen=True)
class MotionProfile:
    motion_type: str
    duration_sec: float
    fps: int
    zoom_start: float = 1.0
    zoom_end: float = 1.0
    pan_start_x: float = 0.5
    pan_start_y: float = 0.5
    pan_end_x: float = 0.5
    pan_end_y: float = 0.5
    easing: str = "ease_in_out"
    enabled: bool = False
    fallback_used: bool = False

    @property
    def total_frames(self) -> int:
        return max(1, round(self.duration_sec * self.fps))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"total_frames": self.total_frames}


class MotionValidator:
    @staticmethod
    def clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, float(value)))

    @classmethod
    def validate(cls, profile: MotionProfile) -> MotionProfile:
        return MotionProfile(
            motion_type=profile.motion_type if profile.motion_type in SUPPORTED_MOTIONS else "static",
            duration_sec=max(0.01, float(profile.duration_sec)),
            fps=max(1, int(profile.fps)),
            zoom_start=cls.clamp(profile.zoom_start, 1.0, 1.50),
            zoom_end=cls.clamp(profile.zoom_end, 1.0, 1.50),
            pan_start_x=cls.clamp(profile.pan_start_x, 0.0, 1.0),
            pan_start_y=cls.clamp(profile.pan_start_y, 0.0, 1.0),
            pan_end_x=cls.clamp(profile.pan_end_x, 0.0, 1.0),
            pan_end_y=cls.clamp(profile.pan_end_y, 0.0, 1.0),
            easing=profile.easing if profile.easing in SUPPORTED_EASING else "ease_in_out",
            enabled=bool(profile.enabled),
            fallback_used=bool(profile.fallback_used),
        )


class MotionInterpolator:
    @staticmethod
    def progress(total_frames: int) -> str:
        return f"min(1,max(0,on/{max(1, int(total_frames)-1)}))"

    @classmethod
    def eased_progress(cls, easing: str, total_frames: int) -> str:
        p = cls.progress(total_frames)
        if easing == "linear": return p
        if easing == "ease_in": return f"pow({p},2)"
        if easing == "ease_out": return f"(1-pow(1-({p}),2))"
        if easing == "smoothstep": return f"(({p})*({p})*(3-2*({p})))"
        if easing == "cubic": return f"pow({p},3)"
        return f"((1-cos(PI*({p})))/2)"

    @staticmethod
    def interpolate(start: float, end: float, progress_expr: str) -> str:
        delta = float(end) - float(start)
        if abs(delta) < 1e-9:
            return f"{float(start):.8f}"
        return f"({float(start):.8f}+({delta:.8f})*({progress_expr}))"


class CameraMotionEngine:
    def __init__(self, *, fps: int) -> None:
        self.fps = max(1, int(fps))

    def build_profile(self, clip: Any) -> MotionProfile:
        duration = max(0.01, float(getattr(clip, "duration_sec", 0.01)))
        motion = self.normalize(getattr(clip, "camera_motion", "static"))
        fallback = motion not in SUPPORTED_MOTIONS
        if fallback:
            motion = "static"
        defaults = self._defaults(motion)
        profile = MotionProfile(
            motion_type=motion,
            duration_sec=float(getattr(clip, "motion_duration_sec", duration) or duration),
            fps=self.fps,
            zoom_start=self._value(clip, "zoom_start", defaults["zoom_start"]),
            zoom_end=self._value(clip, "zoom_end", defaults["zoom_end"]),
            pan_start_x=self._value(clip, "pan_start_x", defaults["pan_start_x"]),
            pan_start_y=self._value(clip, "pan_start_y", defaults["pan_start_y"]),
            pan_end_x=self._value(clip, "pan_end_x", defaults["pan_end_x"]),
            pan_end_y=self._value(clip, "pan_end_y", defaults["pan_end_y"]),
            easing=str(getattr(clip, "easing", "ease_in_out") or "ease_in_out").strip().lower(),
            enabled=motion != "static",
            fallback_used=fallback,
        )
        return MotionValidator.validate(profile)

    @staticmethod
    def _value(clip: Any, name: str, default: float) -> float:
        value = getattr(clip, name, None)
        return float(default if value in (None, "") else value)

    @staticmethod
    def normalize(value: Any) -> str:
        text = str(value or "static").strip().lower()
        aliases = {
            "": "static", "none": "static", "no_motion": "static",
            "push in": "push_in", "slow push-in": "push_in", "slow push-in 100→108%": "push_in",
            "push out": "push_out", "slow push-out": "push_out",
            "pan left": "pan_left", "pan right": "pan_right", "pan up": "pan_up", "pan down": "pan_down",
            "tilt up": "tilt_up", "tilt down": "tilt_down",
            "slow cinematic motion": "slow_drift", "slow aerial drift / ken burns": "slow_drift",
            "static + subtle parallax": "parallax", "ken burns": "ken_burns",
        }
        return aliases.get(text, text.replace("-", "_").replace(" ", "_"))

    @staticmethod
    def _defaults(motion: str) -> dict[str, float]:
        p = {
            "static": (1.0,1.0,.5,.5,.5,.5),
            "push_in": (1.0,1.10,.5,.5,.5,.5), "slow_push": (1.0,1.08,.5,.5,.5,.5),
            "push_out": (1.10,1.0,.5,.5,.5,.5), "slow_pull": (1.08,1.0,.5,.5,.5,.5),
            "pan_left": (1.10,1.10,.70,.5,.30,.5), "pan_right": (1.10,1.10,.30,.5,.70,.5),
            "pan_up": (1.10,1.10,.5,.70,.5,.30), "tilt_up": (1.10,1.10,.5,.70,.5,.30),
            "pan_down": (1.10,1.10,.5,.30,.5,.70), "tilt_down": (1.10,1.10,.5,.30,.5,.70),
            "slow_pan": (1.08,1.08,.40,.5,.60,.5),
            "slow_drift": (1.02,1.09,.44,.54,.56,.46),
            "parallax": (1.03,1.10,.46,.52,.54,.48),
            "ken_burns": (1.0,1.12,.40,.58,.60,.42),
            "custom": (1.0,1.0,.5,.5,.5,.5),
        }.get(motion, (1.0,1.0,.5,.5,.5,.5))
        keys = ("zoom_start","zoom_end","pan_start_x","pan_start_y","pan_end_x","pan_end_y")
        return dict(zip(keys, p))


class FFmpegMotionBuilder:
    def __init__(self, *, width: int, height: int, fps: int) -> None:
        self.width, self.height, self.fps = int(width), int(height), int(fps)

    def build(self, profile: MotionProfile) -> str:
        if not profile.enabled:
            return (
                f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps={self.fps},setsar=1,format=yuv420p"
            )
        p = MotionInterpolator.eased_progress(profile.easing, profile.total_frames)
        zoom = MotionInterpolator.interpolate(profile.zoom_start, profile.zoom_end, p)
        cx = MotionInterpolator.interpolate(profile.pan_start_x, profile.pan_end_x, p)
        cy = MotionInterpolator.interpolate(profile.pan_start_y, profile.pan_end_y, p)
        ow, oh = int(round(self.width*1.55)), int(round(self.height*1.55))
        x = f"max(0,min(iw-iw/zoom,(iw-iw/zoom)*({cx})))"
        y = f"max(0,min(ih-ih/zoom,(ih-ih/zoom)*({cy})))"
        return (
            f"fps={self.fps},scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},"
            f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s={self.width}x{self.height}:fps={self.fps},"
            "setsar=1,format=yuv420p"
        )
