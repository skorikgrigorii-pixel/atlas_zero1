from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def _value(item: Any, *names: str, default: Any = None) -> Any:
    """Read the first non-None value from an object or mapping."""
    for name in names:
        if isinstance(item, Mapping):
            value = item.get(name)
        else:
            value = getattr(item, name, None)
        if value is not None:
            return value
    return default


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


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

    # RC2 persistent synchronization metadata.
    anchor_type: str = "timeline"
    source_asset_id: str | None = None
    source_path: str | None = None
    source_start_sec: float | None = None
    source_end_sec: float | None = None
    clip_id: str | None = None
    scene_id: str | None = None
    timeline_hash: str | None = None
    preserve_sync: bool = False
    original_start_sec: float | None = None
    rebind_status: str = "timeline_locked"

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VideoTimelineRC2:
    """Normalized access to the final visual timeline used for audio rebinding."""

    @staticmethod
    def normalize(items: Iterable[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            timeline_start = _optional_float(
                _value(
                    item,
                    "timeline_start_sec",
                    "start_sec",
                    "start",
                    "timeline_in",
                    default=None,
                )
            )
            duration = _optional_float(
                _value(item, "duration_sec", "length_sec", "duration", default=None)
            )
            timeline_end = _optional_float(
                _value(item, "timeline_end_sec", "end_sec", "end", "timeline_out")
            )

            if timeline_start is None:
                continue
            if timeline_end is None and duration is not None:
                timeline_end = timeline_start + duration
            if duration is None and timeline_end is not None:
                duration = timeline_end - timeline_start
            if duration is None or duration <= 0:
                continue

            source_in = float(
                _value(
                    item,
                    "source_in_sec",
                    "source_start_sec",
                    "trim_in_sec",
                    "in_sec",
                    default=0.0,
                )
                or 0.0
            )
            source_out = _optional_float(
                _value(
                    item,
                    "source_out_sec",
                    "source_end_sec",
                    "trim_out_sec",
                    "out_sec",
                )
            )
            if source_out is None:
                source_out = source_in + duration

            normalized.append(
                {
                    "clip_id": str(
                        _value(
                            item,
                            "clip_id",
                            "shot_id",
                            "timeline_item_id",
                            "id",
                            default=f"clip_{index:04d}",
                        )
                    ),
                    "scene_id": (
                        str(_value(item, "scene_id"))
                        if _value(item, "scene_id") is not None
                        else None
                    ),
                    "source_asset_id": (
                        str(
                            _value(
                                item,
                                "source_asset_id",
                                "asset_id",
                                "media_asset_id",
                            )
                        )
                        if _value(
                            item,
                            "source_asset_id",
                            "asset_id",
                            "media_asset_id",
                        )
                        is not None
                        else None
                    ),
                    "source_path": (
                        str(
                            _value(
                                item,
                                "source_path",
                                "asset_path",
                                "file_path",
                                "path",
                            )
                        )
                        if _value(
                            item,
                            "source_path",
                            "asset_path",
                            "file_path",
                            "path",
                        )
                        is not None
                        else None
                    ),
                    "timeline_start_sec": float(timeline_start),
                    "timeline_end_sec": float(timeline_start + duration),
                    "duration_sec": float(duration),
                    "source_in_sec": float(source_in),
                    "source_out_sec": float(source_out),
                }
            )

        return sorted(
            normalized,
            key=lambda clip: (
                clip["timeline_start_sec"],
                clip["clip_id"],
            ),
        )

    @staticmethod
    def digest(items: Iterable[Any]) -> str:
        normalized = VideoTimelineRC2.normalize(items)
        canonical = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AudioTimelineValidatorRC2:
    SUPPORTED_KINDS = {"voice", "music", "sfx"}
    SUPPORTED_ANCHORS = {"timeline", "source_clip", "scene"}

    @classmethod
    def validate(cls, events: Iterable[AudioEventRC2]) -> list[AudioEventRC2]:
        validated: list[AudioEventRC2] = []
        for event in events:
            if event.kind not in cls.SUPPORTED_KINDS:
                raise ValueError(f"Unsupported audio event kind: {event.kind}")
            if event.anchor_type not in cls.SUPPORTED_ANCHORS:
                raise ValueError(
                    f"Unsupported audio anchor type: {event.anchor_type}"
                )
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
            if event.preserve_sync and event.anchor_type == "source_clip":
                if not event.source_asset_id and not event.source_path:
                    raise ValueError(
                        f"Missing source reference for synchronized event: "
                        f"{event.event_id}"
                    )
                if event.source_start_sec is None:
                    raise ValueError(
                        f"Missing source_start_sec for synchronized event: "
                        f"{event.event_id}"
                    )
            validated.append(event)
        return sorted(validated, key=lambda e: (e.start_sec, e.kind, e.event_id))

    @classmethod
    def validate_against_video(
        cls,
        events: Iterable[AudioEventRC2],
        *,
        target_duration_sec: float,
        require_resolved_sync: bool = True,
    ) -> list[AudioEventRC2]:
        events = cls.validate(events)
        failures: list[str] = []
        for event in events:
            if event.start_sec >= target_duration_sec:
                failures.append(
                    f"{event.event_id}: starts after visual timeline "
                    f"({event.start_sec:.3f} >= {target_duration_sec:.3f})"
                )
            if (
                event.preserve_sync
                and require_resolved_sync
                and event.rebind_status not in {"rebound", "already_current"}
            ):
                failures.append(
                    f"{event.event_id}: synchronized event is unresolved "
                    f"({event.rebind_status})"
                )
        if failures:
            raise RuntimeError(
                "Audio/video synchronization validation failed:\n- "
                + "\n- ".join(failures)
            )
        return events


class AudioTimelineBuilderRC2:
    """Build, preserve, and rebind RC2 audio events."""

    @classmethod
    def build(
        cls,
        items: Iterable[Any],
        *,
        video_timeline: Iterable[Any] | None = None,
        timeline_hash: str | None = None,
        strict_rebind: bool = True,
    ) -> list[AudioEventRC2]:
        events: list[AudioEventRC2] = []
        for index, item in enumerate(items, start=1):
            kind = str(
                _value(
                    item,
                    "kind",
                    "audio_kind",
                    "track_type",
                    default="sfx",
                )
            ).strip().lower()

            asset_path = str(
                _value(
                    item,
                    "asset_path",
                    "path",
                    "file_path",
                    default="",
                )
            )
            event_id = str(
                _value(
                    item,
                    "event_id",
                    "audio_id",
                    "shot_id",
                    default=f"audio_{index:04d}",
                )
            )

            start_sec = float(
                _value(
                    item,
                    "start_sec",
                    "timeline_start_sec",
                    default=0.0,
                )
                or 0.0
            )
            duration_sec = float(
                _value(item, "duration_sec", "length_sec", default=0.0)
                or 0.0
            )

            original_start = _optional_float(
                _value(item, "original_start_sec", default=None)
            )
            if original_start is None:
                original_start = start_sec

            events.append(
                AudioEventRC2(
                    event_id=event_id,
                    kind=kind,
                    asset_path=asset_path,
                    start_sec=start_sec,
                    duration_sec=duration_sec,
                    gain_db=float(_value(item, "gain_db", default=0.0) or 0.0),
                    fade_in_sec=float(
                        _value(item, "fade_in_sec", default=0.0) or 0.0
                    ),
                    fade_out_sec=float(
                        _value(item, "fade_out_sec", default=0.0) or 0.0
                    ),
                    loop=bool(_value(item, "loop", default=False)),
                    anchor_type=str(
                        _value(item, "anchor_type", default="timeline")
                    ).strip().lower(),
                    source_asset_id=(
                        str(
                            _value(
                                item,
                                "source_asset_id",
                                "video_asset_id",
                                default=None,
                            )
                        )
                        if _value(
                            item,
                            "source_asset_id",
                            "video_asset_id",
                            default=None,
                        )
                        is not None
                        else None
                    ),
                    source_path=(
                        str(_value(item, "source_path", default=None))
                        if _value(item, "source_path", default=None) is not None
                        else None
                    ),
                    source_start_sec=_optional_float(
                        _value(
                            item,
                            "source_start_sec",
                            "source_in_sec",
                            default=None,
                        )
                    ),
                    source_end_sec=_optional_float(
                        _value(
                            item,
                            "source_end_sec",
                            "source_out_sec",
                            default=None,
                        )
                    ),
                    clip_id=(
                        str(_value(item, "clip_id", default=None))
                        if _value(item, "clip_id", default=None) is not None
                        else None
                    ),
                    scene_id=(
                        str(_value(item, "scene_id", default=None))
                        if _value(item, "scene_id", default=None) is not None
                        else None
                    ),
                    timeline_hash=(
                        str(_value(item, "timeline_hash", default=None))
                        if _value(item, "timeline_hash", default=None) is not None
                        else None
                    ),
                    preserve_sync=bool(
                        _value(item, "preserve_sync", default=False)
                    ),
                    original_start_sec=original_start,
                    rebind_status=str(
                        _value(
                            item,
                            "rebind_status",
                            default="timeline_locked",
                        )
                    ),
                )
            )

        if video_timeline is not None:
            events, _ = cls.rebind(
                events,
                video_timeline=video_timeline,
                timeline_hash=timeline_hash,
                strict=strict_rebind,
            )
        return AudioTimelineValidatorRC2.validate(events)

    @classmethod
    def rebind(
        cls,
        events: Iterable[AudioEventRC2],
        *,
        video_timeline: Iterable[Any],
        timeline_hash: str | None = None,
        strict: bool = True,
    ) -> tuple[list[AudioEventRC2], dict[str, Any]]:
        clips = VideoTimelineRC2.normalize(video_timeline)
        current_hash = timeline_hash or VideoTimelineRC2.digest(clips)

        rebound: list[AudioEventRC2] = []
        unresolved: list[dict[str, str]] = []
        rebound_count = 0

        for event in events:
            if not event.preserve_sync or event.anchor_type == "timeline":
                rebound.append(
                    replace(
                        event,
                        timeline_hash=current_hash,
                        rebind_status="timeline_locked",
                    )
                )
                continue

            candidates = cls._candidates_for_event(event, clips)
            selected = cls._select_candidate(event, candidates)

            if selected is None:
                unresolved.append(
                    {
                        "event_id": event.event_id,
                        "reason": "source clip not found in final timeline",
                    }
                )
                rebound.append(
                    replace(
                        event,
                        timeline_hash=current_hash,
                        rebind_status="unresolved_source",
                    )
                )
                continue

            if event.anchor_type == "scene":
                new_start = selected["timeline_start_sec"]
            else:
                assert event.source_start_sec is not None
                new_start = (
                    selected["timeline_start_sec"]
                    + event.source_start_sec
                    - selected["source_in_sec"]
                )

            if new_start < selected["timeline_start_sec"] - 0.001:
                unresolved.append(
                    {
                        "event_id": event.event_id,
                        "reason": "audio anchor precedes selected clip trim-in",
                    }
                )
                rebound.append(
                    replace(
                        event,
                        timeline_hash=current_hash,
                        rebind_status="outside_clip_before",
                    )
                )
                continue

            if new_start >= selected["timeline_end_sec"] - 0.001:
                unresolved.append(
                    {
                        "event_id": event.event_id,
                        "reason": "audio anchor is outside selected clip",
                    }
                )
                rebound.append(
                    replace(
                        event,
                        timeline_hash=current_hash,
                        rebind_status="outside_clip_after",
                    )
                )
                continue

            rebound_count += 1
            rebound.append(
                replace(
                    event,
                    start_sec=round(float(new_start), 6),
                    clip_id=selected["clip_id"],
                    scene_id=event.scene_id or selected["scene_id"],
                    source_asset_id=(
                        event.source_asset_id or selected["source_asset_id"]
                    ),
                    source_path=event.source_path or selected["source_path"],
                    timeline_hash=current_hash,
                    rebind_status="rebound",
                )
            )

        report = {
            "schema": "atlas_zero.audio_rebind.rc2.v1",
            "timeline_hash": current_hash,
            "clips_total": len(clips),
            "events_total": len(rebound),
            "events_rebound": rebound_count,
            "events_unresolved": len(unresolved),
            "unresolved": unresolved,
        }

        if strict and unresolved:
            details = "\n".join(
                f"- {item['event_id']}: {item['reason']}"
                for item in unresolved
            )
            raise RuntimeError(
                "RC2 audio rebinding failed. Final render blocked:\n" + details
            )

        return (
            sorted(rebound, key=lambda e: (e.start_sec, e.kind, e.event_id)),
            report,
        )

    @staticmethod
    def _candidates_for_event(
        event: AudioEventRC2,
        clips: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if event.clip_id:
            exact = [clip for clip in clips if clip["clip_id"] == event.clip_id]
            if exact:
                return exact

        candidates = list(clips)
        if event.source_asset_id:
            candidates = [
                clip
                for clip in candidates
                if clip["source_asset_id"] == event.source_asset_id
            ]
        elif event.source_path:
            wanted = Path(event.source_path).name.lower()
            candidates = [
                clip
                for clip in candidates
                if clip["source_path"]
                and Path(clip["source_path"]).name.lower() == wanted
            ]

        if event.scene_id:
            scene_matches = [
                clip for clip in candidates if clip["scene_id"] == event.scene_id
            ]
            if scene_matches:
                candidates = scene_matches

        return candidates

    @staticmethod
    def _select_candidate(
        event: AudioEventRC2,
        candidates: Sequence[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not candidates:
            return None
        if event.anchor_type == "scene":
            return candidates[0]
        if event.source_start_sec is None:
            return None

        containing = [
            clip
            for clip in candidates
            if clip["source_in_sec"] - 0.001
            <= event.source_start_sec
            < clip["source_out_sec"] + 0.001
        ]
        if not containing:
            return None

        if event.original_start_sec is not None and len(containing) > 1:
            return min(
                containing,
                key=lambda clip: abs(
                    clip["timeline_start_sec"] - event.original_start_sec
                ),
            )
        return containing[0]
