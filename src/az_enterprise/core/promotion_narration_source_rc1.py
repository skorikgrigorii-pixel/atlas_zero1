from __future__ import annotations

import re

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromotionNarrationSceneRC1:
    scene_uid: str
    scene_number: str
    source_start_sec: float
    source_end_sec: float
    duration_sec: float
    narration_text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PromotionNarrationSourceRC1:
    """
    Canonical promotion-semantic source.

    Authority:
        workspace/projects/<project>/script/production_script.txt

    Uses:
        scene duration
        +
        actual 'Текст диктора'

    Important:
        Scene numbering may restart between production-script blocks.
        Therefore time is reconstructed cumulatively from scene durations.
    """

    SCENE_RE = re.compile(
        r"(?im)^\s*СЦЕНА\s+([^\r\n]+)\s*$"
    )

    TIME_RE = re.compile(
        r"(?m)^\s*"
        r"(\d{1,2}:\d{2}(?::\d{2})?)"
        r"\s*[–—-]\s*"
        r"(\d{1,2}:\d{2}(?::\d{2})?)"
        r"\s*$"
    )

    def __init__(
        self,
        *,
        project_id: str,
        root: str | Path,
        script_path: str | Path | None = None,
    ) -> None:

        self.project_id = str(
            project_id
        ).strip()

        self.root = Path(root)

        self.script_path = (
            Path(script_path)
            if script_path is not None
            else (
                self.root
                / "workspace"
                / "projects"
                / self.project_id
                / "script"
                / "production_script.txt"
            )
        )

    def load(
        self,
    ) -> list[PromotionNarrationSceneRC1]:

        if not self.script_path.is_file():
            raise FileNotFoundError(
                self.script_path
            )

        text = self.script_path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        matches = list(
            self.SCENE_RE.finditer(
                text
            )
        )

        if not matches:
            raise RuntimeError(
                "No SCENE sections found in production script"
            )

        scenes = []
        cumulative = 0.0

        for position, match in enumerate(
            matches,
            1,
        ):

            section_start = match.start()

            section_end = (
                matches[position].start()
                if position < len(matches)
                else len(text)
            )

            section = text[
                section_start:
                section_end
            ]

            duration = self._scene_duration(
                section
            )

            narration = self._narration_text(
                section
            )

            if (
                duration is None
                or duration <= 0
                or not narration
            ):
                continue

            start_sec = cumulative
            end_sec = (
                cumulative
                + duration
            )

            scenes.append(
                PromotionNarrationSceneRC1(
                    scene_uid=(
                        f"{self.project_id}"
                        f"_narr_scene_"
                        f"{len(scenes)+1:04d}"
                    ),
                    scene_number=str(
                        match.group(1)
                    ).strip(),
                    source_start_sec=start_sec,
                    source_end_sec=end_sec,
                    duration_sec=duration,
                    narration_text=narration,
                )
            )

            cumulative = end_sec

        if not scenes:
            raise RuntimeError(
                "Production script contains no usable "
                "timed narration scenes"
            )

        return scenes

    def aligned(
        self,
        *,
        target_duration_sec: float,
    ) -> list[PromotionNarrationSceneRC1]:

        scenes = self.load()

        script_duration = (
            scenes[-1].source_end_sec
        )

        if (
            script_duration <= 0
            or target_duration_sec <= 0
        ):
            return scenes

        scale = (
            float(target_duration_sec)
            / float(script_duration)
        )

        return [
            PromotionNarrationSceneRC1(
                scene_uid=item.scene_uid,
                scene_number=item.scene_number,
                source_start_sec=(
                    item.source_start_sec
                    * scale
                ),
                source_end_sec=(
                    item.source_end_sec
                    * scale
                ),
                duration_sec=(
                    item.duration_sec
                    * scale
                ),
                narration_text=item.narration_text,
            )
            for item in scenes
        ]

    @classmethod
    def _scene_duration(
        cls,
        section: str,
    ) -> float | None:

        marker = re.search(
            r"(?im)^\s*2\.\s*Продолжительность\s*$",
            section,
        )

        search_text = (
            section[
                marker.end():
                marker.end() + 300
            ]
            if marker
            else section[:500]
        )

        match = cls.TIME_RE.search(
            search_text
        )

        if not match:
            return None

        start = cls._seconds(
            match.group(1)
        )

        end = cls._seconds(
            match.group(2)
        )

        duration = end - start

        return (
            duration
            if duration > 0
            else None
        )

    @staticmethod
    def _narration_text(
        section: str,
    ) -> str:

        start = re.search(
            r"(?im)^\s*4\.\s*Текст диктора\s*$",
            section,
        )

        if not start:
            return ""

        remainder = section[
            start.end():
        ]

        end = re.search(
            r"(?im)^\s*5\.\s*",
            remainder,
        )

        raw = (
            remainder[:end.start()]
            if end
            else remainder
        )

        lines = []

        for line in raw.splitlines():

            value = line.strip()

            if not value:
                continue

            if re.match(
                r"^\d+\.\s+",
                value,
            ):
                break

            lines.append(
                value
            )

        return " ".join(
            lines
        ).strip()

    @staticmethod
    def _seconds(
        value: str,
    ) -> float:

        parts = [
            int(part)
            for part in value.split(":")
        ]

        if len(parts) == 2:
            minutes, seconds = parts
            return (
                minutes * 60
                + seconds
            )

        if len(parts) == 3:
            hours, minutes, seconds = parts
            return (
                hours * 3600
                + minutes * 60
                + seconds
            )

        raise ValueError(
            value
        )
