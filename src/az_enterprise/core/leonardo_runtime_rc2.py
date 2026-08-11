from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from az_enterprise.core.leonardo_provider_rc2 import (
    LeonardoProviderRC2,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LeonardoRuntimeRC2:
    QUEUE_STATUSES = {
        "ready_for_live_or_dry_run",
        "waiting_api",
    }

    SUPPORTED_JOB_TYPES = {
        "image_generation",
        "generate_asset",
    }

    def __init__(
        self,
        *,
        root: Path | str,
        project_id: str,
        provider: LeonardoProviderRC2 | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.project_id = str(project_id).strip()
        self.provider = (
            provider or LeonardoProviderRC2()
        )

        self.workspace = self.root / "workspace"
        self.export_dir = (
            self.workspace
            / "exports"
            / self.project_id
        )
        self.project_dir = (
            self.workspace
            / "projects"
            / self.project_id
        )

        self.queue_path = (
            self.export_dir
            / "rc2"
            / "leonardo_queue_canonical.json"
        )

        self.output_dir = (
            self.project_dir
            / "02_Visual"
            / "generated"
            / "leonardo"
        )

        self.runtime_dir = (
            self.export_dir
            / "leonardo_runtime_rc2"
        )

        self.manifest_path = (
            self.runtime_dir
            / "leonardo_generation_manifest.json"
        )

    def doctor(self) -> dict[str, Any]:
        config = (
            self.provider.validate_configuration()
        )

        queue_exists = self.queue_path.is_file()

        queue_count = 0
        ready_count = 0

        if queue_exists:
            jobs = self.load_queue()
            queue_count = len(jobs)
            ready_count = len(
                self.select_jobs(jobs)
            )

        return {
            "schema":
                "atlas_zero.leonardo_doctor.rc2.v1",
            "state": (
                "READY"
                if config["configured"] and queue_exists
                else "NOT_READY"
            ),
            "project_id": self.project_id,
            "queue_path": str(
                self.queue_path.resolve()
            ),
            "queue_exists": queue_exists,
            "queue_jobs": queue_count,
            "ready_jobs": ready_count,
            "provider": config,
            "output_dir": str(
                self.output_dir.resolve()
            ),
        }

    def load_queue(self) -> list[dict[str, Any]]:
        if not self.queue_path.is_file():
            raise FileNotFoundError(
                self.queue_path
            )

        payload = json.loads(
            self.queue_path.read_text(
                encoding="utf-8-sig",
            )
        )

        if isinstance(payload, list):
            jobs = payload

        elif isinstance(payload, dict):
            jobs = (
                payload.get("jobs")
                or payload.get("api_jobs")
                or payload.get("queue")
                or payload.get("items")
                or []
            )

        else:
            raise RuntimeError(
                "Unsupported Leonardo queue format"
            )

        if not isinstance(jobs, list):
            raise RuntimeError(
                "Leonardo queue jobs field is not a list"
            )

        return [
            job for job in jobs
            if isinstance(job, dict)
        ]

    def select_jobs(
        self,
        jobs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []

        for index, job in enumerate(jobs):
            service = str(
                job.get("service") or ""
            ).lower()

            status = str(
                job.get("status") or ""
            ).lower()

            job_type = str(
                job.get("job_type") or ""
            ).lower()

            if service != "leonardo":
                continue

            if status not in self.QUEUE_STATUSES:
                continue

            if job_type not in self.SUPPORTED_JOB_TYPES:
                continue

            normalized = dict(job)
            normalized["_queue_index"] = index
            selected.append(normalized)

        return selected

    def dry_run(
        self,
        *,
        limit: int = 1,
    ) -> dict[str, Any]:
        jobs = self.select_jobs(
            self.load_queue()
        )[: max(1, int(limit))]

        prepared = [
            self._prepare_job(job)
            for job in jobs
        ]

        report = {
            "schema":
                "atlas_zero.leonardo_dry_run.rc2.v1",
            "state": "DRY_RUN_READY",
            "project_id": self.project_id,
            "selected_jobs": len(prepared),
            "jobs": prepared,
        }

        self._write_report(
            "leonardo_dry_run.json",
            report,
        )

        return report

    def run_live(
        self,
        *,
        limit: int = 1,
        confirm_paid: bool = False,
    ) -> dict[str, Any]:
        if not confirm_paid:
            raise RuntimeError(
                "Paid Leonardo execution requires "
                "--confirm-paid"
            )

        jobs = self.select_jobs(
            self.load_queue()
        )[: max(1, int(limit))]

        if not jobs:
            raise RuntimeError(
                "No eligible Leonardo jobs found"
            )

        results: list[dict[str, Any]] = []

        for job in jobs:
            prepared = self._prepare_job(job)
            payload = prepared["payload"]
            shot_id = prepared["shot_id"]

            started_at = utc_now()

            try:
                created = (
                    self.provider.create_generation(
                        prompt=payload["prompt"],
                        negative_prompt=payload.get(
                            "negative_prompt"
                        ),
                    )
                )

                completed = (
                    self.provider.wait_for_generation(
                        created["generation_id"]
                    )
                )

                images = (
                    self.provider.download_images(
                        result=completed,
                        destination_dir=self.output_dir,
                        basename=shot_id,
                    )
                )

                row = {
                    "shot_id": shot_id,
                    "status": "COMPLETED",
                    "generation_id":
                        created["generation_id"],
                    "started_at_utc": started_at,
                    "completed_at_utc": utc_now(),
                    "images": images,
                    "request": created["request"],
                }

            except Exception as exc:
                row = {
                    "shot_id": shot_id,
                    "status": "FAILED",
                    "started_at_utc": started_at,
                    "completed_at_utc": utc_now(),
                    "error": str(exc),
                }

            results.append(row)
            self._append_manifest(row)

            if row["status"] == "FAILED":
                break

        completed_count = sum(
            row["status"] == "COMPLETED"
            for row in results
        )

        report = {
            "schema":
                "atlas_zero.leonardo_execution.rc2.v1",
            "state": (
                "COMPLETED"
                if completed_count == len(results)
                else "FAILED"
            ),
            "project_id": self.project_id,
            "requested": len(jobs),
            "completed": completed_count,
            "failed": sum(
                row["status"] == "FAILED"
                for row in results
            ),
            "results": results,
            "manifest": str(
                self.manifest_path.resolve()
            ),
        }

        self._write_report(
            "leonardo_execution_report.json",
            report,
        )

        return report

    def _prepare_job(
        self,
        job: dict[str, Any],
    ) -> dict[str, Any]:
        raw_payload = job.get("payload")

        if isinstance(raw_payload, str):
            payload = json.loads(raw_payload)
        elif isinstance(raw_payload, dict):
            payload = dict(raw_payload)
        else:
            raise RuntimeError(
                "Leonardo job has invalid payload"
            )

        prompt = str(
            payload.get("prompt") or ""
        ).strip()

        if not prompt:
            raise RuntimeError(
                "Leonardo job has no prompt"
            )

        shot_id = str(
            payload.get("shot_id")
            or f"job_{job['_queue_index']:05d}"
        ).strip()

        return {
            "queue_index": job["_queue_index"],
            "shot_id": shot_id,
            "job_type": job.get("job_type"),
            "status": job.get("status"),
            "payload": {
                "prompt": prompt,
                "negative_prompt": str(
                    payload.get(
                        "negative_prompt"
                    )
                    or (
                        "cartoon, illustration, CGI, "
                        "modern objects, incorrect period "
                        "details, text, watermark, blurry, "
                        "low quality"
                    )
                ).strip(),
                "aspect_ratio": (
                    payload.get("aspect_ratio")
                    or "16:9"
                ),
                "style": payload.get("style"),
            },
        }

    def _append_manifest(
        self,
        row: dict[str, Any],
    ) -> None:
        self.runtime_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if self.manifest_path.is_file():
            manifest = json.loads(
                self.manifest_path.read_text(
                    encoding="utf-8"
                )
            )
        else:
            manifest = {
                "schema":
                    "atlas_zero.leonardo_manifest.rc2.v1",
                "project_id": self.project_id,
                "created_at_utc": utc_now(),
                "generations": [],
            }

        generations = manifest.setdefault(
            "generations",
            [],
        )

        generations.append(row)
        manifest["updated_at_utc"] = utc_now()

        self.manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _write_report(
        self,
        filename: str,
        payload: dict[str, Any],
    ) -> None:
        self.runtime_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        (
            self.runtime_dir / filename
        ).write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

