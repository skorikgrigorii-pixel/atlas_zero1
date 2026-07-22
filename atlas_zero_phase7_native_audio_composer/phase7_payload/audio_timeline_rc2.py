from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class AudioEventRC2:
    event_id: str
    kind: str
    asset_path: str
    start_sec: float
    duration_sec: float
    gain_db: float = 0.0
    fade_in_sec: float = 0.0
    fade_out_sec: float = 0.0
    loop: bool = False

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AudioTimelineValidatorRC2:
    SUPPORTED_KINDS = {"voice", "music", "sfx"}

    @classmethod
    def validate(cls, events: Iterable[AudioEventRC2]) -> list[AudioEventRC2]:
        validated: list[AudioEventRC2] = []
        for event in events:
            if event.kind not in cls.SUPPORTED_KINDS:
                raise ValueError(f"Unsupported audio event kind: {event.kind}")
            path = Path(event.asset_path)
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"Audio asset is missing: {path}")
            if event.start_sec < 0:
                raise ValueError(f"Negative audio start: {event.event_id}")
            if event.duration_sec <= 0:
                raise ValueError(f"Invalid audio duration: {event.event_id}")
            if event.fade_in_sec < 0 or event.fade_out_sec < 0:
                raise ValueError(f"Negative fade duration: {event.event_id}")
            if event.fade_in_sec + event.fade_out_sec > event.duration_sec:
                raise ValueError(f"Fades exceed event duration: {event.event_id}")
            validated.append(event)
        return sorted(validated, key=lambda e: (e.start_sec, e.kind, e.event_id))


class AudioTimelineBuilderRC2:
    """Build normalized RC2 audio events from generic timeline objects."""

    @classmethod
    def build(cls, items: Iterable[Any]) -> list[AudioEventRC2]:
        events: list[AudioEventRC2] = []
        for index, item in enumerate(items, start=1):
            kind = str(
                getattr(item, "kind", None)
                or getattr(item, "audio_kind", None)
                or getattr(item, "track_type", None)
                or "sfx"
            ).strip().lower()

            asset_path = str(
                getattr(item, "asset_path", None)
                or getattr(item, "path", None)
                or getattr(item, "file_path", None)
                or ""
            )
            event_id = str(
                getattr(item, "event_id", None)
                or getattr(item, "audio_id", None)
                or getattr(item, "shot_id", None)
                or f"audio_{index:04d}"
            )

            start_sec = float(
                getattr(item, "start_sec", None)
                or getattr(item, "timeline_start_sec", None)
                or 0.0
            )
            duration_sec = float(
                getattr(item, "duration_sec", None)
                or getattr(item, "length_sec", None)
                or 0.0
            )
            gain_db = float(getattr(item, "gain_db", 0.0) or 0.0)
            fade_in_sec = float(getattr(item, "fade_in_sec", 0.0) or 0.0)
            fade_out_sec = float(getattr(item, "fade_out_sec", 0.0) or 0.0)
            loop = bool(getattr(item, "loop", False))

            events.append(
                AudioEventRC2(
                    event_id=event_id,
                    kind=kind,
                    asset_path=asset_path,
                    start_sec=start_sec,
                    duration_sec=duration_sec,
                    gain_db=gain_db,
                    fade_in_sec=fade_in_sec,
                    fade_out_sec=fade_out_sec,
                    loop=loop,
                )
            )
        return AudioTimelineValidatorRC2.validate(events)
