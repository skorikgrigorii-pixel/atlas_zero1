from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LeonardoWebAssistantRC2:
    def __init__(
        self,
        *,
        root: Path | str,
        project_id: str,
        downloads_dir: Path | str | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.project_id = str(project_id).strip()

        self.workspace = self.root / "workspace"

        self.queue_path = (
            self.workspace
            / "exports"
            / self.project_id
            / "rc2"
            / "leonardo_queue_canonical.json"
        )

        self.output_dir = (
            self.workspace
            / "projects"
            / self.project_id
            / "02_Visual"
            / "generated"
            / "leonardo"
        )

        self.state_path = (
            self.workspace
            / "exports"
            / self.project_id
            / "rc2"
            / "leonardo_web_assistant_state.json"
        )

        self.downloads_dir = (
            Path(downloads_dir).expanduser().resolve()
            if downloads_dir
            else Path.home() / "Downloads"
        )

    def load_queue(self) -> dict[str, Any]:
        if not self.queue_path.is_file():
            raise FileNotFoundError(self.queue_path)

        payload = json.loads(
            self.queue_path.read_text(
                encoding="utf-8-sig",
            )
        )

        jobs = payload.get("jobs")

        if not isinstance(jobs, list):
            raise RuntimeError(
                "Canonical Leonardo queue has no jobs list"
            )

        return payload

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {
                "schema":
                    "atlas_zero.leonardo_web_assistant.rc2.v1",
                "project_id": self.project_id,
                "completed_shots": {},
                "failed_shots": {},
                "updated_at_utc": utc_now(),
            }

        payload = json.loads(
            self.state_path.read_text(
                encoding="utf-8"
            )
        )

        payload.setdefault(
            "completed_shots",
            {},
        )
        payload.setdefault(
            "failed_shots",
            {},
        )

        return payload

    def save_state(
        self,
        state: dict[str, Any],
    ) -> None:
        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        state["updated_at_utc"] = utc_now()

        self.state_path.write_text(
            json.dumps(
                state,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def completed_ids(self) -> set[str]:
        state = self.load_state()

        completed = set(
            state.get(
                "completed_shots",
                {},
            ).keys()
        )

        if self.output_dir.is_dir():
            for path in self.output_dir.iterdir():
                if (
                    path.is_file()
                    and path.suffix.lower()
                    in VALID_IMAGE_SUFFIXES
                ):
                    completed.add(path.stem)

        return completed

    def next_job(self) -> dict[str, Any] | None:
        queue = self.load_queue()
        completed = self.completed_ids()

        for job in queue["jobs"]:
            shot_id = str(
                job.get("shot_id")
                or job.get("payload", {}).get("shot_id")
                or ""
            ).strip()

            if not shot_id:
                continue

            if shot_id in completed:
                continue

            payload = job.get("payload")

            if not isinstance(payload, dict):
                continue

            return {
                "shot_id": shot_id,
                "scene_id": payload.get("scene_id"),
                "prompt": str(
                    payload.get("prompt")
                    or ""
                ).strip(),
                "negative_prompt": str(
                    payload.get("negative_prompt")
                    or ""
                ).strip(),
                "aspect_ratio": (
                    payload.get("aspect_ratio")
                    or "16:9"
                ),
                "style": payload.get("style"),
            }

        return None

    def copy_prompt(
        self,
        job: dict[str, Any],
    ) -> None:
        import subprocess
        import tempfile

        prompt = str(job["prompt"]).strip()

        if not prompt:
            raise RuntimeError("Prompt is empty")

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".txt",
                delete=False,
            ) as stream:
                stream.write(prompt)
                temporary_path = Path(stream.name)

            command = (
                "Get-Content -LiteralPath "
                f"'{str(temporary_path).replace(chr(39), chr(39) * 2)}' "
                "-Raw -Encoding UTF8 | Set-Clipboard"
            )

            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    command,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if completed.returncode != 0:
                raise RuntimeError(
                    completed.stderr.strip()
                    or "Set-Clipboard failed"
                )

        except Exception as exc:
            raise RuntimeError(
                "Cannot copy prompt to Windows clipboard"
            ) from exc

        finally:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()

    def snapshot_downloads(
        self,
    ) -> dict[str, float]:
        if not self.downloads_dir.is_dir():
            raise FileNotFoundError(
                self.downloads_dir
            )

        result: dict[str, float] = {}

        for path in self.downloads_dir.iterdir():
            if (
                path.is_file()
                and path.suffix.lower()
                in VALID_IMAGE_SUFFIXES
            ):
                result[str(path.resolve())] = (
                    path.stat().st_mtime
                )

        return result

    def wait_for_download(
        self,
        *,
        before: dict[str, float],
        timeout_sec: int = 600,
    ) -> Path:
        started = time.monotonic()

        while True:
            candidates: list[Path] = []

            for path in self.downloads_dir.iterdir():
                if not path.is_file():
                    continue

                if (
                    path.suffix.lower()
                    not in VALID_IMAGE_SUFFIXES
                ):
                    continue

                resolved = str(path.resolve())
                modified = path.stat().st_mtime

                previous = before.get(resolved)

                if previous is None or modified > previous:
                    candidates.append(path)

            if candidates:
                return max(
                    candidates,
                    key=lambda path:
                        path.stat().st_mtime,
                )

            if (
                time.monotonic() - started
                >= timeout_sec
            ):
                raise TimeoutError(
                    "No new downloaded image detected"
                )

            time.sleep(2)

    def register_download(
        self,
        *,
        job: dict[str, Any],
        source: Path,
    ) -> Path:
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        suffix = source.suffix.lower()

        if suffix not in VALID_IMAGE_SUFFIXES:
            suffix = ".png"

        destination = (
            self.output_dir
            / f"{job['shot_id']}{suffix}"
        )

        temporary = destination.with_suffix(
            destination.suffix + ".partial"
        )

        shutil.copy2(
            source,
            temporary,
        )

        temporary.replace(destination)

        state = self.load_state()

        state.setdefault(
            "completed_shots",
            {},
        )[job["shot_id"]] = {
            "status": "COMPLETED",
            "scene_id": job.get("scene_id"),
            "source_download": str(
                source.resolve()
            ),
            "output_path": str(
                destination.resolve()
            ),
            "completed_at_utc": utc_now(),
        }

        self.save_state(state)

        return destination

    def status(self) -> dict[str, Any]:
        queue = self.load_queue()
        completed = self.completed_ids()
        total = len(queue["jobs"])

        return {
            "state": "READY",
            "project_id": self.project_id,
            "queue_jobs": total,
            "completed": len(completed),
            "remaining": max(
                0,
                total - len(completed),
            ),
            "queue_path": str(
                self.queue_path.resolve()
            ),
            "downloads_dir": str(
                self.downloads_dir.resolve()
            ),
            "output_dir": str(
                self.output_dir.resolve()
            ),
        }

    def prepare_next(self) -> dict[str, Any]:
        job = self.next_job()

        if job is None:
            return {
                "state": "QUEUE_COMPLETE",
                "project_id": self.project_id,
            }

        self.copy_prompt(job)

        return {
            "state": "PROMPT_COPIED",
            "project_id": self.project_id,
            "job": job,
            "message":
                "Prompt copied to clipboard. "
                "Paste it into Leonardo.",
        }

    def capture_next(
        self,
        *,
        timeout_sec: int = 600,
    ) -> dict[str, Any]:
        job = self.next_job()

        if job is None:
            return {
                "state": "QUEUE_COMPLETE",
                "project_id": self.project_id,
            }

        before = self.snapshot_downloads()

        source = self.wait_for_download(
            before=before,
            timeout_sec=timeout_sec,
        )

        destination = self.register_download(
            job=job,
            source=source,
        )

        return {
            "state": "SHOT_COMPLETED",
            "project_id": self.project_id,
            "shot_id": job["shot_id"],
            "source": str(source.resolve()),
            "destination": str(
                destination.resolve()
            ),
        }

