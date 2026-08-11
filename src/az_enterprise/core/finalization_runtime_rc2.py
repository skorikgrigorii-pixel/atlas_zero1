from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .production_state_rc2 import ProductionStateStoreRC2
from .project_config_rc2 import ProjectConfigRC2


ProgressCallback = Callable[[dict[str, Any]], None]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FinalizationRuntimeRC2:
    """Controlled RC2 transition from verified preview to the next lifecycle state.

    Modes:
    - approve_preview(): records human approval and leaves the project ready for
      narration/final release production.
    - promote_preview_as_final(): explicitly promotes a verified preview to a
      technical final without claiming release authorization.

    This runtime never starts the heavy visual renderer.
    """

    APPROVABLE_STATUSES = {
        "PREVIEW_RENDERED",
        "PREVIEW_APPROVED",
    }
    PROMOTABLE_STATUSES = {
        "PREVIEW_RENDERED",
        "PREVIEW_APPROVED",
        "FINAL_RENDERED_TECHNICAL",
    }

    def __init__(
        self,
        project_id: str,
        *,
        root_dir: str | Path | None = None,
        progress: ProgressCallback | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"project_id": project_id}
        if root_dir is not None:
            kwargs["root_dir"] = Path(root_dir)

        self.config = ProjectConfigRC2(**kwargs)
        self.store = ProductionStateStoreRC2(
            self.config.state_path,
            project_id=project_id,
        )
        self.progress = progress or self._default_progress
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffprobe:
            raise RuntimeError("ffprobe is not available in PATH")

        self.report_path = (
            self.config.render_dir / "finalization_report_rc2.json"
        )
        self.lock_path = self.config.rc2_dir / "finalization_runtime.lock"

    @staticmethod
    def _default_progress(payload: dict[str, Any]) -> None:
        stage = payload.get("stage", "FINALIZATION")
        details = " ".join(
            f"{key}={value}"
            for key, value in payload.items()
            if key != "stage"
        )
        print(f"[RC2 {stage}] {details}".rstrip(), flush=True)

    @contextmanager
    def _exclusive_run(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                self.lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as exc:
            raise RuntimeError(
                "Another FinalizationRuntimeRC2 run is active: "
                f"{self.lock_path}"
            ) from exc

        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)

    def approve_preview(self) -> dict[str, Any]:
        """Record human approval without falsely publishing a release."""

        with self._exclusive_run():
            state = self.store.load()
            self._require_status(state.status, self.APPROVABLE_STATUSES)

            preview = self._resolve_verified_preview(state)
            probe = self._probe_media(preview)

            state.status = "PREVIEW_APPROVED"
            state.current_stage = None
            state.release_authorized = False
            state.error = None
            state.artifacts["approved_preview"] = str(preview)
            state.artifacts["finalization_report"] = str(self.report_path)

            report = {
                "schema": "atlas_zero.finalization.rc2.v1",
                "state": "PREVIEW_APPROVED",
                "mode": "approve_preview",
                "project_id": self.config.project_id,
                "created_at": utc_now(),
                "source": str(preview),
                "source_probe": probe,
                "release_authorized": False,
                "heavy_render_started": False,
                "next_required_action": (
                    "Produce and approve narration/music, then run the "
                    "canonical RC2 release pipeline."
                ),
            }
            self._write_json_atomic(self.report_path, report)
            self.store.save(state)
            self.progress(
                {
                    "stage": "FINALIZATION",
                    "status": "PREVIEW_APPROVED",
                    "source": str(preview),
                }
            )
            return report

    def promote_preview_as_final(
        self,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Promote preview to a technical final without rerendering.

        The resulting artifact is intentionally not release-authorized because
        narration/music may be absent.
        """

        with self._exclusive_run():
            state = self.store.load()
            self._require_status(state.status, self.PROMOTABLE_STATUSES)

            source = self._resolve_verified_preview(state)
            source_probe = self._probe_media(source)
            destination = self.config.canonical_render_path

            if destination.exists() and not overwrite:
                if self._sha256(destination) != self._sha256(source):
                    raise FileExistsError(
                        "Canonical final already exists and differs from the "
                        f"preview: {destination}. Use --overwrite explicitly."
                    )
            else:
                self._copy_atomic(source, destination)

            destination_probe = self._probe_media(destination)
            if not self._equivalent_media(source_probe, destination_probe):
                destination.unlink(missing_ok=True)
                raise RuntimeError(
                    "Promoted artifact verification failed; destination removed"
                )

            state.status = "FINAL_RENDERED_TECHNICAL"
            state.current_stage = None
            state.release_authorized = False
            state.error = None
            state.artifacts["technical_final"] = str(destination)
            state.artifacts["render"] = str(destination)
            state.artifacts["finalization_report"] = str(self.report_path)

            report = {
                "schema": "atlas_zero.finalization.rc2.v1",
                "state": "FINAL_RENDERED_TECHNICAL",
                "mode": "promote_preview_as_final",
                "project_id": self.config.project_id,
                "created_at": utc_now(),
                "source": str(source),
                "output": str(destination),
                "source_sha256": self._sha256(source),
                "output_sha256": self._sha256(destination),
                "source_probe": source_probe,
                "output_probe": destination_probe,
                "release_authorized": False,
                "technical_final": True,
                "heavy_render_started": False,
                "warnings": [
                    "Preview was promoted without a new render.",
                    "This artifact is not a release-authorized final.",
                    "Narration and final music may be absent.",
                ],
            }
            self._write_json_atomic(self.report_path, report)
            self.store.save(state)
            self.progress(
                {
                    "stage": "FINALIZATION",
                    "status": "FINAL_RENDERED_TECHNICAL",
                    "output": str(destination),
                }
            )
            return report

    @staticmethod
    def _require_status(status: str, allowed: set[str]) -> None:
        if status not in allowed:
            raise RuntimeError(
                f"Finalization is not allowed from state {status!r}; "
                f"allowed states: {sorted(allowed)}"
            )

    def _resolve_verified_preview(self, state: Any) -> Path:
        render_stage = state.stages.get("render")
        details = render_stage.details if render_stage is not None else {}
        render_state = str(details.get("state") or "")
        if render_state not in {
            "RENDER_PREVIEW_VERIFIED",
            "RENDERED_VERIFIED",
        }:
            raise RuntimeError(
                "The render stage does not contain a verified media result"
            )

        candidates = [
            Path(str(details.get("output"))) if details.get("output") else None,
            self.config.preview_render_path,
            Path(str(details.get("source"))) if details.get("source") else None,
        ]
        for candidate in candidates:
            if candidate is not None and candidate.is_file():
                return candidate

        raise FileNotFoundError(
            "Verified preview/source artifact was not found"
        )

    def _probe_media(self, path: Path) -> dict[str, Any]:
        completed = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-show_entries",
                (
                    "stream=index,codec_name,codec_type,width,height,"
                    "r_frame_rate:format=format_name,duration,size"
                ),
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"ffprobe failed for {path}: {completed.stderr.strip()}"
            )

        probe = json.loads(completed.stdout or "{}")
        streams = probe.get("streams")
        if not isinstance(streams, list) or not streams:
            raise RuntimeError(f"No media streams discovered in {path}")

        video = [
            item for item in streams
            if item.get("codec_type") == "video"
        ]
        if not video:
            raise RuntimeError(f"No video stream discovered in {path}")

        duration = float((probe.get("format") or {}).get("duration") or 0.0)
        if duration <= 0:
            raise RuntimeError(f"Invalid media duration for {path}")

        return probe

    @staticmethod
    def _equivalent_media(
        source: dict[str, Any],
        destination: dict[str, Any],
    ) -> bool:
        def signature(probe: dict[str, Any]) -> tuple[Any, ...]:
            streams = probe.get("streams") or []
            video = next(
                (
                    item for item in streams
                    if item.get("codec_type") == "video"
                ),
                {},
            )
            audio_count = sum(
                1 for item in streams
                if item.get("codec_type") == "audio"
            )
            duration = round(
                float((probe.get("format") or {}).get("duration") or 0.0),
                3,
            )
            return (
                video.get("codec_name"),
                video.get("width"),
                video.get("height"),
                video.get("r_frame_rate"),
                audio_count,
                duration,
            )

        return signature(source) == signature(destination)

    @staticmethod
    def _copy_atomic(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".partial")
        temporary.unlink(missing_ok=True)
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ATLAS ZERO FinalizationRuntimeRC2"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    approve = subparsers.add_parser(
        "approve-preview",
        help="Approve verified preview for subsequent final production",
    )
    approve.add_argument("project_id")
    approve.add_argument("--root-dir", default=None)

    promote = subparsers.add_parser(
        "promote-preview",
        help="Promote verified preview to a technical final",
    )
    promote.add_argument("project_id")
    promote.add_argument(
        "--as-final",
        action="store_true",
        required=True,
        help="Explicit acknowledgement that this is a technical final",
    )
    promote.add_argument("--overwrite", action="store_true")
    promote.add_argument("--root-dir", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = FinalizationRuntimeRC2(
        args.project_id,
        root_dir=args.root_dir,
    )

    if args.command == "approve-preview":
        result = runtime.approve_preview()
    elif args.command == "promote-preview":
        result = runtime.promote_preview_as_final(
            overwrite=args.overwrite,
        )
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
