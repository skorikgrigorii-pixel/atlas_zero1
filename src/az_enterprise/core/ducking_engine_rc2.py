from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DuckingProfileRC2:
    enabled: bool = True
    threshold: float = 0.03
    ratio: float = 8.0
    attack_ms: int = 40
    release_ms: int = 450
    makeup_gain_db: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DuckingEngineRC2:
    @staticmethod
    def build_filter(
        *,
        music_label: str,
        voice_label: str,
        output_label: str,
        profile: DuckingProfileRC2,
    ) -> str:
        if not profile.enabled:
            return f"{music_label}anull{output_label}"
        return (
            f"{music_label}{voice_label}"
            f"sidechaincompress="
            f"threshold={profile.threshold}:"
            f"ratio={profile.ratio}:"
            f"attack={profile.attack_ms}:"
            f"release={profile.release_ms}:"
            f"makeup={profile.makeup_gain_db}"
            f"{output_label}"
        )
