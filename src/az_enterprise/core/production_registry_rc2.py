from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_V1 = "atlas_zero.system_registry.rc2.v1"
SCHEMA_V2 = "atlas_zero.production_registry.rc2.v2"

ALLOWED_STATUSES = {
    "PENDING",
    "READY",
    "DRAFT",
    "SUPERSEDED",
    "ARCHIVED",
    "NEEDS_RELOCATION",
    "FAILED",
}

DEFAULT_PIPELINE = (
    "production_script",
    "voice_master",
    "timeline",
    "voice_placement",
    "visual_master",
    "final_render",
    "thumbnail",
    "publication",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(path: str | Path | None) -> Path | None:
    if not path:
        return None
    return Path(path).expanduser().resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


class ProductionRegistryRC2:
    """
    Central production-state authority for ATLAS ZERO RC2.

    The registry describes the lifecycle of each production stage.
    A missing PENDING artifact is normal.
    A missing READY artifact is an integrity failure.
    """

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()
        self.workspace = self.root / "workspace"
        self.registry_dir = self.workspace / "registry"
        self.path = self.registry_dir / "system_registry.json"

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(
        self,
        payload: dict[str, Any],
        *,
        backup: bool = True,
    ) -> None:
        self.registry_dir.mkdir(parents=True, exist_ok=True)

        if backup and self.path.is_file():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = (
                self.registry_dir
                / f"system_registry_before_v2_{stamp}.json"
            )
            shutil.copy2(self.path, backup_path)

        payload["updated_at_utc"] = utc_now()

        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _artifact_record(
        self,
        *,
        domain: str,
        path: str | Path | None,
        status: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        resolved = normalize(path)
        exists = bool(resolved and resolved.is_file())

        record: dict[str, Any] = {
            "domain": domain,
            "status": status,
            "path": str(resolved) if resolved else None,
            "exists": exists,
            "size_bytes": (
                resolved.stat().st_size
                if exists and resolved
                else None
            ),
            "modified_utc": (
                datetime.fromtimestamp(
                    resolved.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat()
                if exists and resolved
                else None
            ),
            "sha256": (
                sha256_file(resolved)
                if exists and resolved
                else None
            ),
            "note": note,
            "history": [],
        }

        return record

    def migrate_v1_to_v2(self) -> dict[str, Any]:
        old = self.load()

        if old.get("schema") == SCHEMA_V2:
            return old

        if old.get("schema") != SCHEMA_V1:
            raise RuntimeError(
                f"Unsupported registry schema: {old.get('schema')!r}"
            )

        projects: dict[str, Any] = {}

        for project_id, old_project in old.get("projects", {}).items():
            old_canonical = old_project.get("canonical", {})
            stages: dict[str, Any] = {}

            for domain in DEFAULT_PIPELINE:
                old_record = old_canonical.get(domain, {})
                raw_path = old_record.get("path")
                exists = bool(raw_path and Path(raw_path).is_file())

                status = "READY" if exists else "PENDING"
                note = None

                if project_id == "franklin":
                    if domain == "production_script":
                        root_script = self.root / "production_script.json"

                        if (
                            raw_path
                            and normalize(raw_path) == root_script.resolve()
                        ):
                            status = "NEEDS_RELOCATION"
                            note = (
                                "Script exists outside the canonical "
                                "Franklin project directory."
                            )

                    elif domain == "final_render" and exists:
                        status = "DRAFT"
                        note = (
                            "Existing Franklin render is an earlier "
                            "test/draft, not the approved final film."
                        )

                    elif domain in {
                        "voice_master",
                        "timeline",
                        "voice_placement",
                        "visual_master",
                        "thumbnail",
                        "publication",
                    }:
                        if not exists:
                            status = "PENDING"

                if project_id == "hogueras":
                    if domain == "thumbnail" and not exists:
                        status = "PENDING"

                    if domain == "publication":
                        status = "READY"
                        note = "Film uploaded to YouTube."

                stages[domain] = self._artifact_record(
                    domain=domain,
                    path=raw_path,
                    status=status,
                    note=note,
                )

            projects[project_id] = {
                "project_id": project_id,
                "project_root": old_project.get("project_root"),
                "export_root": old_project.get("export_root"),
                "production_state": self._derive_project_state(stages),
                "stages": stages,
            }

        payload = {
            "schema": SCHEMA_V2,
            "authority": "ATLAS_ZERO_RC2",
            "state": "PRODUCTION_REGISTRY_READY",
            "created_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
            "root": str(self.root),
            "projects": projects,
        }

        self.save(payload, backup=True)
        return payload

    @staticmethod
    def _derive_project_state(
        stages: dict[str, Any],
    ) -> str:
        statuses = {
            record.get("status")
            for record in stages.values()
        }

        if "FAILED" in statuses:
            return "BLOCKED"

        if all(
            stages.get(domain, {}).get("status") == "READY"
            for domain in DEFAULT_PIPELINE
        ):
            return "COMPLETE"

        if any(
            status in {
                "READY",
                "DRAFT",
                "NEEDS_RELOCATION",
            }
            for status in statuses
        ):
            return "IN_PRODUCTION"

        return "PLANNED"

    def validate(self) -> dict[str, Any]:
        payload = self.load()

        if payload.get("schema") != SCHEMA_V2:
            raise RuntimeError(
                "Registry must be migrated to RC2 v2 first."
            )

        checks: list[dict[str, Any]] = []

        for project_id, project in payload.get("projects", {}).items():
            stages = project.get("stages", {})

            for domain in DEFAULT_PIPELINE:
                record = stages.get(domain)

                if record is None:
                    checks.append({
                        "project_id": project_id,
                        "domain": domain,
                        "status": None,
                        "state": "MISSING_STAGE_RECORD",
                        "blocking": True,
                        "path": None,
                    })
                    continue

                status = record.get("status")
                raw_path = record.get("path")
                path = normalize(raw_path)

                if status not in ALLOWED_STATUSES:
                    checks.append({
                        "project_id": project_id,
                        "domain": domain,
                        "status": status,
                        "state": "INVALID_STATUS",
                        "blocking": True,
                        "path": raw_path,
                    })
                    continue

                exists = bool(path and path.is_file())

                if domain == "publication" and status == "READY":
                    state = "VALID_READY_METADATA"
                    blocking = False

                elif status == "READY" and not exists:
                    state = "READY_FILE_MISSING"
                    blocking = True

                elif status == "READY" and exists:
                    expected_hash = record.get("sha256")
                    actual_hash = sha256_file(path)

                    if expected_hash and expected_hash != actual_hash:
                        state = "HASH_MISMATCH"
                        blocking = True
                    else:
                        state = "VALID_READY"
                        blocking = False

                elif status == "PENDING":
                    state = "VALID_PENDING"
                    blocking = False

                elif status == "DRAFT":
                    state = (
                        "VALID_DRAFT"
                        if exists
                        else "DRAFT_FILE_MISSING"
                    )
                    blocking = False

                elif status == "NEEDS_RELOCATION":
                    state = (
                        "VALID_NEEDS_RELOCATION"
                        if exists
                        else "RELOCATION_SOURCE_MISSING"
                    )
                    blocking = False

                else:
                    state = f"VALID_{status}"
                    blocking = False

                checks.append({
                    "project_id": project_id,
                    "domain": domain,
                    "status": status,
                    "state": state,
                    "blocking": blocking,
                    "path": str(path) if path else None,
                })

        blocking = [row for row in checks if row["blocking"]]

        return {
            "schema": "atlas_zero.production_registry_validation.rc2.v2",
            "state": "VALID" if not blocking else "INVALID",
            "blocking_count": len(blocking),
            "checks": checks,
        }

    def set_stage(
        self,
        *,
        project_id: str,
        domain: str,
        status: str,
        path: str | Path | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        if status not in ALLOWED_STATUSES:
            raise ValueError(
                f"Unsupported status {status!r}. "
                f"Allowed: {sorted(ALLOWED_STATUSES)}"
            )

        payload = self.load()

        if payload.get("schema") != SCHEMA_V2:
            raise RuntimeError("Registry v2 required.")

        project = payload["projects"][project_id]
        stages = project["stages"]
        previous = stages.get(domain)

        selected_path = path

        if selected_path is None and previous:
            selected_path = previous.get("path")

        record = self._artifact_record(
            domain=domain,
            path=selected_path,
            status=status,
            note=note,
        )

        if previous:
            history = list(previous.get("history") or [])
            history.append({
                "changed_at_utc": utc_now(),
                "previous_status": previous.get("status"),
                "previous_path": previous.get("path"),
                "previous_sha256": previous.get("sha256"),
            })
            record["history"] = history

        stages[domain] = record
        project["production_state"] = self._derive_project_state(stages)

        self.save(payload, backup=True)
        return record

