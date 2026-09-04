from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NarrationAlignedSceneRC1:
    scene_number: int
    block_number: int
    text: str
    start_sec: float
    end_sec: float
    duration_sec: float
    weight: float


class PromotionNarrationAlignmentRC1:
    """
    ATLAS ZERO ? Promotion Narration Alignment RC1.

    Maps Production Script narrator scenes to the real voice master
    through six canonical voice blocks.

    Authority:
        Production Script narrator text
            ->
        script block
            ->
        voice_block_N duration
            ->
        proportional Unicode text weight
            ->
        voice_master timeline

    This layer deliberately does NOT use declared production-scene
    durations as narrator timing.
    """

    BLOCK_SCENES = {
        1: range(1, 8),
        2: range(8, 13),
        3: range(13, 18),
        4: range(18, 24),
        5: range(24, 30),
        6: range(30, 36),
    }

    def __init__(
        self,
        *,
        project_id: str,
        root: str | Path,
        script_path: str | Path | None = None,
        audio_dir: str | Path | None = None,
    ) -> None:

        self.project_id = str(project_id)
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

        self.audio_dir = (
            Path(audio_dir)
            if audio_dir is not None
            else (
                self.root
                / "workspace"
                / "projects"
                / self.project_id
                / "01_Audio"
            )
        )

    @staticmethod
    def _unicode_tokens(text: str) -> list[str]:

        tokens: list[str] = []
        current: list[str] = []

        for char in text:

            if char.isalnum():
                current.append(char)
                continue

            if current:
                tokens.append(
                    "".join(current)
                )
                current = []

        if current:
            tokens.append(
                "".join(current)
            )

        return tokens

    @classmethod
    def _text_weight(
        cls,
        text: str,
    ) -> int:

        tokens = cls._unicode_tokens(
            text
        )

        return max(
            1,
            len(tokens),
        )

    @staticmethod
    def _probe_duration(
        path: Path,
    ) -> float:

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            raise RuntimeError(
                "ffprobe failed for "
                + str(path)
            )

        value = result.stdout.strip()

        if not value:
            raise RuntimeError(
                "No duration returned for "
                + str(path)
            )

        return float(value)

    def _voice_blocks(
        self,
    ) -> dict[int, float]:

        result: dict[int, float] = {}

        base_dir = Path(
            self.audio_dir
        )

        # ------------------------------------------------------------
        # Canonical RC2 scene audio authority
        # ------------------------------------------------------------
        #
        # Final documentary timing is built from SCxx.wav scene files.
        # Promotion must use the same clock as the rendered film.
        # MP3 voice_blocks remain a compatibility fallback.
        #

        scene_dir = (
            base_dir
            / "scenes"
        )

        scene_first = (
            scene_dir
            / "SC01.wav"
        )

        if scene_first.is_file():

            discovered_scene_audio: dict[
                int,
                Path,
            ] = {}

            for path in sorted(
                scene_dir.glob(
                    "SC*.wav"
                )
            ):

                match = re.fullmatch(
                    r"SC(\d+)\.wav",
                    path.name,
                    flags=re.IGNORECASE,
                )

                if match is None:
                    continue

                number = int(
                    match.group(1)
                )

                discovered_scene_audio[
                    number
                ] = path

            if discovered_scene_audio:

                expected = set(
                    range(
                        1,
                        max(
                            discovered_scene_audio
                        )
                        + 1,
                    )
                )

                actual = set(
                    discovered_scene_audio
                )

                if actual != expected:

                    missing = sorted(
                        expected
                        - actual
                    )

                    raise RuntimeError(
                        "RC2 scene WAV sequence mismatch. "
                        f"missing={missing}"
                    )

                for number in sorted(
                    discovered_scene_audio
                ):

                    result[
                        number
                    ] = self._probe_duration(
                        discovered_scene_audio[
                            number
                        ]
                    )

                return result

        rc2_dir = (
            base_dir
            / "voice_blocks"
        )

        # ------------------------------------------------------------
        # RC2 scene-level voice authority
        # ------------------------------------------------------------

        rc2_first = (
            rc2_dir
            / "voice_block_01.mp3"
        )

        if rc2_first.is_file():

            discovered: dict[
                int,
                Path,
            ] = {}

            for path in sorted(
                rc2_dir.glob(
                    "voice_block_*.mp3"
                )
            ):

                match = re.fullmatch(
                    r"voice_block_(\d+)\.mp3",
                    path.name,
                )

                if match is None:
                    continue

                number = int(
                    match.group(
                        1
                    )
                )

                discovered[
                    number
                ] = path

            if not discovered:

                raise FileNotFoundError(
                    rc2_first
                )

            expected = set(
                range(
                    1,
                    max(
                        discovered
                    )
                    + 1,
                )
            )

            actual = set(
                discovered
            )

            if actual != expected:

                missing = sorted(
                    expected
                    - actual
                )

                raise RuntimeError(
                    "RC2 voice block sequence mismatch. "
                    f"missing={missing}"
                )

            for number in sorted(
                discovered
            ):

                result[
                    number
                ] = (
                    self._probe_duration(
                        discovered[
                            number
                        ]
                    )
                )

            return result

        # ------------------------------------------------------------
        # Legacy Promotion RC1 block authority
        # ------------------------------------------------------------

        for number in range(
            1,
            7,
        ):

            path = (
                base_dir
                / (
                    f"voice_block_"
                    f"{number:02d}.mp3"
                )
            )

            if not path.is_file():

                raise FileNotFoundError(
                    path
                )

            result[number] = (
                self._probe_duration(
                    path
                )
            )

        return result

    @staticmethod
    def _narrator_marker(
        line: str,
    ) -> bool:

        normalized = (
            " ".join(
                line.strip().split()
            )
            .lower()
        )

        target = (
            "\u0442\u0435\u043a\u0441\u0442 "
            "\u0434\u0438\u043a\u0442\u043e\u0440\u0430"
        )

        if normalized == "voiceover":
            return True

        return (
            normalized.startswith("3.")
            or normalized.startswith("4.")
        ) and target in normalized

    @staticmethod
    def _scene_heading(
        line: str,
    ) -> int | None:

        value = (
            " ".join(
                line.strip().split()
            )
        )

        # RC2 textual Production Script:
        # scene_001, scene_002, ...
        rc2_match = re.fullmatch(
            r"scene[_\s-]?(\d+)",
            value,
            flags=re.IGNORECASE,
        )

        if rc2_match:
            return int(
                rc2_match.group(1)
            )

        prefix = "\u0441\u0446\u0435\u043d\u0430"

        lowered = value.lower()

        if not lowered.startswith(
            prefix
        ):
            return None

        tail = value[
            len(prefix):
        ].strip()

        match = re.match(
            r"^(\d+)\s*$",
            tail,
        )

        if not match:
            return None

        return int(
            match.group(1)
        )

    def _extract_narrator_scenes(
        self,
    ) -> dict[int, str]:

        # ------------------------------------------------------------
        # RC2 canonical JSON Production Script authority
        # ------------------------------------------------------------
        #
        # New RC2 scripts store narration structurally:
        #
        # scenes[] -> order -> voiceover -> text
        #
        # The legacy Promotion RC1 parser expected a formatted textual
        # screenplay with scene headings and narrator markers.
        #
        # Preserve both contracts:
        #
        #   RC2 JSON  -> structured extraction
        #   legacy    -> original text parser fallback
        #
        # ------------------------------------------------------------

        text = self.script_path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        stripped = text.lstrip()

        if stripped.startswith(
            "{"
        ):

            try:
                import json

                payload = json.loads(
                    text
                )

            except json.JSONDecodeError:
                payload = None

            if isinstance(
                payload,
                dict,
            ):

                scenes = payload.get(
                    "scenes"
                )

                if isinstance(
                    scenes,
                    list,
                ):

                    result: dict[
                        int,
                        str,
                    ] = {}

                    for position, scene in enumerate(
                        scenes,
                        1,
                    ):

                        if not isinstance(
                            scene,
                            dict,
                        ):
                            continue

                        scene_number = (
                            scene.get(
                                "order"
                            )
                        )

                        if scene_number is None:

                            scene_id = str(
                                scene.get(
                                    "scene_id",
                                    "",
                                )
                            )

                            match = re.search(
                                r"(\d+)$",
                                scene_id,
                            )

                            if match:
                                scene_number = int(
                                    match.group(
                                        1
                                    )
                                )

                        try:
                            scene_number = int(
                                scene_number
                            )

                        except (
                            TypeError,
                            ValueError,
                        ):
                            scene_number = position

                        voiceover = scene.get(
                            "voiceover"
                        )

                        narration = ""

                        if isinstance(
                            voiceover,
                            dict,
                        ):

                            narration = str(
                                voiceover.get(
                                    "text",
                                    "",
                                )
                                or ""
                            ).strip()

                        elif isinstance(
                            voiceover,
                            str,
                        ):

                            narration = (
                                voiceover.strip()
                            )

                        # Compatibility with possible earlier
                        # JSON production-script variants.
                        if not narration:

                            for key in (
                                "narrator_text",
                                "narration",
                                "voice_text",
                            ):

                                value = scene.get(
                                    key
                                )

                                if isinstance(
                                    value,
                                    str,
                                ) and value.strip():

                                    narration = (
                                        value.strip()
                                    )

                                    break

                        if narration:

                            result[
                                scene_number
                            ] = narration

                    # A structured RC2 Production Script was
                    # positively identified. Do not silently fall
                    # through to the legacy parser if its contract
                    # is malformed.
                    if scenes:

                        expected = set(
                            range(
                                1,
                                len(
                                    scenes
                                )
                                + 1,
                            )
                        )

                        actual = set(
                            result
                        )

                        if actual != expected:

                            missing = sorted(
                                expected
                                - actual
                            )

                            extra = sorted(
                                actual
                                - expected
                            )

                            raise RuntimeError(
                                "Narrator scene extraction mismatch. "
                                f"missing={missing}; "
                                f"extra={extra}"
                            )

                        return result

        # ------------------------------------------------------------
        # Legacy Promotion RC1 textual screenplay parser
        # ------------------------------------------------------------

        lines = text.splitlines()

        result: dict[int, str] = {}

        current_scene: int | None = None
        index = 0

        while index < len(lines):

            line = lines[index]

            scene = self._scene_heading(
                line
            )

            if scene is not None:
                current_scene = scene

            if (
                current_scene is not None
                and self._narrator_marker(
                    line
                )
            ):

                body: list[str] = []

                index += 1

                while index < len(
                    lines
                ):

                    candidate = (
                        lines[
                            index
                        ].strip()
                    )

                    if re.match(
                        r"^\s*[4-9]\.\s+",
                        candidate,
                    ):
                        break

                    next_scene = (
                        self._scene_heading(
                            candidate
                        )
                    )

                    if next_scene is not None:
                        break

                    if candidate:
                        body.append(
                            candidate
                        )

                    index += 1

                narration = " ".join(
                    body
                ).strip()

                if narration:

                    result[
                        current_scene
                    ] = narration

                continue

            index += 1

        # Preserve the original legacy RC1 contract.
        expected = set(
            range(
                1,
                36,
            )
        )

        actual = set(
            result
        )

        if actual != expected:

            missing = sorted(
                expected
                - actual
            )

            extra = sorted(
                actual
                - expected
            )

            raise RuntimeError(
                "Narrator scene extraction mismatch. "
                f"missing={missing}; "
                f"extra={extra}"
            )

        return result

    def align(
        self,
    ) -> dict[str, Any]:

        narration = (
            self._extract_narrator_scenes()
        )

        block_durations = (
            self._voice_blocks()
        )

        # ------------------------------------------------------------
        # RC2 scene-level narration authority.
        #
        # A current RC2 project has one canonical audio file per
        # Production Script scene. Its actual measured duration is
        # authoritative; no text-weight approximation is necessary.
        #
        # Legacy six-block projects continue below unchanged.
        # ------------------------------------------------------------

        rc2_scene_level = (
            (
                Path(
                    self.audio_dir
                )
                / "voice_blocks"
                / "voice_block_01.mp3"
            ).is_file()
        )

        if rc2_scene_level:

            narration_keys = set(
                narration
            )

            duration_keys = set(
                block_durations
            )

            if duration_keys != narration_keys:

                missing_audio = sorted(
                    narration_keys
                    - duration_keys
                )

                extra_audio = sorted(
                    duration_keys
                    - narration_keys
                )

                raise RuntimeError(
                    "RC2 narration/audio scene mismatch. "
                    f"missing_audio={missing_audio}; "
                    f"extra_audio={extra_audio}"
                )

            aligned: list[
                NarrationAlignedSceneRC1
            ] = []

            cursor = 0.0

            for scene_number in sorted(
                narration
            ):

                duration = float(
                    block_durations[
                        scene_number
                    ]
                )

                start = cursor
                end = (
                    start
                    + duration
                )

                aligned.append(
                    NarrationAlignedSceneRC1(
                        scene_number=
                            scene_number,
                        block_number=
                            scene_number,
                        text=narration[
                            scene_number
                        ],
                        start_sec=start,
                        end_sec=end,
                        duration_sec=duration,
                        weight=1.0,
                    )
                )

                cursor = end

            return {
                "project_id":
                    self.project_id,
                "alignment_source":
                    "scene_level_voice_blocks",
                "voice_duration_sec":
                    cursor,
                "narration_duration_sec":
                    cursor,
                "scenes": [
                    {
                        "scene_number":
                            row.scene_number,
                        "block_number":
                            row.block_number,
                        "text":
                            row.text,
                        "start_sec":
                            row.start_sec,
                        "end_sec":
                            row.end_sec,
                        "duration_sec":
                            row.duration_sec,
                        "weight":
                            row.weight,
                    }
                    for row in aligned
                ],
            }


        aligned: list[
            NarrationAlignedSceneRC1
        ] = []

        block_start = 0.0

        for block_number in range(
            1,
            7,
        ):

            scene_numbers = list(
                self.BLOCK_SCENES[
                    block_number
                ]
            )

            weights = {
                number: self._text_weight(
                    narration[number]
                )
                for number
                in scene_numbers
            }

            total_weight = sum(
                weights.values()
            )

            block_duration = (
                block_durations[
                    block_number
                ]
            )

            cursor = block_start

            for position, scene_number in enumerate(
                scene_numbers
            ):

                weight = (
                    weights[scene_number]
                    / total_weight
                )

                if position == (
                    len(scene_numbers) - 1
                ):
                    end = (
                        block_start
                        + block_duration
                    )
                else:
                    end = (
                        cursor
                        + block_duration
                        * weight
                    )

                aligned.append(
                    NarrationAlignedSceneRC1(
                        scene_number=scene_number,
                        block_number=block_number,
                        text=narration[
                            scene_number
                        ],
                        start_sec=cursor,
                        end_sec=end,
                        duration_sec=end - cursor,
                        weight=weight,
                    )
                )

                cursor = end

            block_start += (
                block_duration
            )

        return {
            "project_id":
                self.project_id,

            "alignment_source":
                "voice_blocks_proportional_unicode_text",

            "scene_count":
                len(aligned),

            "block_count":
                6,

            "voice_duration_sec":
                block_start,

            "block_durations_sec": {
                str(key): value
                for key, value
                in block_durations.items()
            },

            "scenes": [
                {
                    "scene_number":
                        item.scene_number,

                    "block_number":
                        item.block_number,

                    "text":
                        item.text,

                    "start_sec":
                        item.start_sec,

                    "end_sec":
                        item.end_sec,

                    "duration_sec":
                        item.duration_sec,

                    "weight":
                        item.weight,
                }
                for item in aligned
            ],
        }
