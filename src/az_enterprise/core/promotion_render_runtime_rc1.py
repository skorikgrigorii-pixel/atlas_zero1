from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import shutil

from .render_engine_rc2 import (
    RenderEngineRC2,
)


@dataclass(frozen=True)
class PromotionRenderSpecRC1:
    candidate_id: str
    source_start_sec: float
    source_end_sec: float
    source_path: Path
    output_path: Path
    width: int = 1080
    height: int = 1920

    @property
    def duration_sec(self) -> float:
        return max(
            0.0,
            self.source_end_sec
            - self.source_start_sec,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id":
                self.candidate_id,
            "source_start_sec":
                self.source_start_sec,
            "source_end_sec":
                self.source_end_sec,
            "duration_sec":
                self.duration_sec,
            "source_path":
                str(self.source_path),
            "output_path":
                str(self.output_path),
            "width":
                self.width,
            "height":
                self.height,
        }


class PromotionRenderRuntimeRC1:
    """
    ATLAS ZERO ? Promotion Render Runtime RC1.

    Downstream promotion renderer.

    Architectural rules:

    1. Never rebuild the documentary timeline.
    2. Never modify the canonical RC2 master.
    3. Promotion clips are derived from the final
       documentary master.
    4. One physical vertical master is created per
       promotion candidate.
    5. Platform packaging is downstream from the
       physical promotion master.
    """

    DEFAULT_WIDTH = 1080
    DEFAULT_HEIGHT = 1920
    DEFAULT_FPS = 30
    DEFAULT_CRF = 18
    DEFAULT_PRESET = "medium"
    DEFAULT_AUDIO_BITRATE = "192k"

    def __init__(
        self,
        *,
        project_id: str,
        root: Path | str,
        source_path: Path | str | None = None,
        ffmpeg_path: str | None = None,
    ) -> None:

        self.project_id = (
            str(project_id).strip()
        )

        if not self.project_id:
            raise ValueError(
                "project_id is required"
            )

        self.root = Path(root)

        if source_path is None:
            source_path = (
                self.root
                / "workspace"
                / "exports"
                / self.project_id
                / "rc2"
                / "render"
                / f"{self.project_id}_RC2.mp4"
            )

        self.source_path = Path(
            source_path
        )

        self.ffmpeg_path = (
            str(ffmpeg_path)
            if ffmpeg_path is not None
            else None
        )

        self.output_root = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "promotion"
            / "masters"
        )

    def validate_source(self) -> Path:

        if not self.source_path.is_file():
            raise FileNotFoundError(
                "Canonical documentary master "
                f"not found: {self.source_path}"
            )

        if self.source_path.stat().st_size <= 0:
            raise RuntimeError(
                "Canonical documentary master "
                "is empty."
            )

        return self.source_path

    def build_spec(
        self,
        *,
        candidate_id: str,
        source_start_sec: float,
        source_end_sec: float,
    ) -> PromotionRenderSpecRC1:

        candidate_id = (
            str(candidate_id).strip()
        )

        if not candidate_id:
            raise ValueError(
                "candidate_id is required"
            )

        start = float(
            source_start_sec
        )

        end = float(
            source_end_sec
        )

        if start < 0:
            raise ValueError(
                "source_start_sec cannot "
                "be negative"
            )

        if end <= start:
            raise ValueError(
                "source_end_sec must be "
                "greater than source_start_sec"
            )

        output_path = (
            self.output_root
            / f"{candidate_id}.mp4"
        )

        return PromotionRenderSpecRC1(
            candidate_id=candidate_id,
            source_start_sec=start,
            source_end_sec=end,
            source_path=self.source_path,
            output_path=output_path,
            width=self.DEFAULT_WIDTH,
            height=self.DEFAULT_HEIGHT,
        )

    def build_specs(
        self,
        candidates: list[Any],
        *,
        limit: int = 3,
    ) -> list[PromotionRenderSpecRC1]:

        if limit < 1:
            return []

        result: list[
            PromotionRenderSpecRC1
        ] = []

        for candidate in candidates[:limit]:

            if isinstance(
                candidate,
                dict,
            ):
                candidate_id = candidate[
                    "candidate_id"
                ]
                start = candidate[
                    "source_start_sec"
                ]
                end = candidate[
                    "source_end_sec"
                ]

            else:
                candidate_id = getattr(
                    candidate,
                    "candidate_id",
                )
                start = getattr(
                    candidate,
                    "source_start_sec",
                )
                end = getattr(
                    candidate,
                    "source_end_sec",
                )

            result.append(
                self.build_spec(
                    candidate_id=candidate_id,
                    source_start_sec=start,
                    source_end_sec=end,
                )
            )

        return result

    def resolve_ffmpeg(
        self,
    ) -> str:

        ffmpeg = (
            self.ffmpeg_path
            or shutil.which("ffmpeg")
        )

        if not ffmpeg:
            raise RuntimeError(
                "ffmpeg is not available in PATH"
            )

        return str(
            ffmpeg
        )

    def build_render_command(
        self,
        spec: PromotionRenderSpecRC1,
        *,
        output_path: Path | None = None,
    ) -> list[str]:
        """
        Build the canonical promotion render command.

        Vertical policy v2:
        - fill the complete 9:16 canvas;
        - preserve original aspect ratio before cropping;
        - remove blurred letterbox/background treatment;
        - use centered documentary-safe crop as current
          autonomous fallback;
        - preserve source audio;
        - encode H.264/AAC.

        Future semantic reframing may override the crop
        position per shot. This renderer provides the
        canonical full-screen vertical baseline.
        """

        ffmpeg = self.resolve_ffmpeg()

        destination = (
            Path(output_path)
            if output_path is not None
            else spec.output_path
        )

        width = int(
            spec.width
        )

        height = int(
            spec.height
        )

        duration = (
            spec.duration_sec
        )

        if duration <= 0:
            raise ValueError(
                "Promotion duration must be positive"
            )

        filter_graph = (
            f"[0:v]"
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=increase:"
            "flags=lanczos,"
            f"crop={width}:{height}:"
            "(in_w-out_w)/2:"
            "(in_h-out_h)/2,"
            "setsar=1,"
            "format=yuv420p"
            "[vout]"
        )

        return [
            ffmpeg,
            "-y",
            "-nostdin",

            "-ss",
            f"{spec.source_start_sec:.6f}",

            "-i",
            str(spec.source_path),

            "-t",
            f"{duration:.6f}",

            "-filter_complex",
            filter_graph,

            "-map",
            "[vout]",

            "-map",
            "0:a?",

            "-r",
            str(self.DEFAULT_FPS),

            "-c:v",
            "libx264",

            "-preset",
            self.DEFAULT_PRESET,

            "-crf",
            str(self.DEFAULT_CRF),

            "-pix_fmt",
            "yuv420p",

            "-c:a",
            "aac",

            "-b:a",
            self.DEFAULT_AUDIO_BITRATE,

            "-ar",
            "48000",

            "-ac",
            "2",

            "-movflags",
            "+faststart",

            str(destination),
        ]

    def render_spec(
        self,
        spec: PromotionRenderSpecRC1,
        *,
        overwrite: bool = False,
    ) -> Path:
        """
        Render one physical vertical promotion master.

        Uses RenderEngineRC2._run_ffmpeg as the existing
        canonical FFmpeg execution authority.
        """

        self.validate_source()

        spec.output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if (
            spec.output_path.is_file()
            and spec.output_path.stat().st_size > 0
            and not overwrite
        ):
            return spec.output_path

        partial = (
            spec.output_path.with_name(
                spec.output_path.stem
                + ".partial"
                + spec.output_path.suffix
            )
        )

        partial.unlink(
            missing_ok=True
        )

        command = (
            self.build_render_command(
                spec,
                output_path=partial,
            )
        )

        RenderEngineRC2._run_ffmpeg(
            command,
            step=(
                "Promotion vertical master "
                + spec.candidate_id
            ),
        )

        if (
            not partial.is_file()
            or partial.stat().st_size <= 0
        ):
            raise RuntimeError(
                "Promotion render produced "
                "no valid output: "
                f"{partial}"
            )

        spec.output_path.unlink(
            missing_ok=True
        )

        partial.replace(
            spec.output_path
        )

        return spec.output_path

    def render_specs(
        self,
        specs: list[PromotionRenderSpecRC1],
        *,
        limit: int = 3,
        overwrite: bool = False,
    ) -> list[Path]:

        if limit < 1:
            return []

        outputs = []

        for spec in specs[:limit]:

            outputs.append(
                self.render_spec(
                    spec,
                    overwrite=overwrite,
                )
            )

        return outputs

    def prepare(
        self,
        candidates: list[Any],
        *,
        limit: int = 3,
    ) -> list[PromotionRenderSpecRC1]:

        self.validate_source()

        self.output_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        return self.build_specs(
            candidates,
            limit=limit,
        )
