from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LoudnessProfileRC2:
    integrated_lufs: float = -16.0
    loudness_range: float = 11.0
    true_peak_db: float = -1.5
    limiter_db: float = -1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LoudnessEngineRC2:
    @staticmethod
    def build_filter(
        input_label: str,
        output_label: str,
        profile: LoudnessProfileRC2,
    ) -> str:
        return (
            f"{input_label}"
            f"loudnorm=I={profile.integrated_lufs}:"
            f"LRA={profile.loudness_range}:"
            f"TP={profile.true_peak_db},"
            f"alimiter=limit={10 ** (profile.limiter_db / 20):.8f}"
            f"{output_label}"
        )
