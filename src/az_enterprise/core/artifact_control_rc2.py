from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REGISTRY_SCHEMA_V1 = "atlas_zero.system_registry.rc2.v1"
REGISTRY_SCHEMA_V2 = "atlas_zero.production_registry.rc2.v2"
ARTIFACT_SCHEMA = "atlas_zero.artifact_inventory.rc2.v1"
CLEANUP_SCHEMA = "atlas_zero.cleanup_plan.rc2.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def normalize(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    size_bytes: int
    modified_utc: str
    category: str
    reason: str
    canonical: bool
    protected: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "modified_utc": self.modified_utc,
            "category": self.category,
            "reason": self.reason,
            "canonical": self.canonical,
            "protected": self.protected,
        }


class RegistryError(RuntimeError):
    pass


class SystemRegistryRC2:
    """Single source of truth for canonical RC2 project artifacts."""

    def __init__(self, root: Path | str) -> None:
        self.root = normalize(root)
        self.workspace = self.root / "workspace"
        self.registry_dir = self.workspace / "registry"
        self.registry_path = self.registry_dir / "system_registry.json"

    def load(self) -> dict[str, Any]:
        if not self.registry_path.is_file():
            raise RegistryError(
                f"System Registry not found: {self.registry_path}"
            )

        payload = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )

        schema = payload.get("schema")

        if schema not in {
            REGISTRY_SCHEMA_V1,
            REGISTRY_SCHEMA_V2,
        }:
            raise RegistryError(
                "Unsupported System Registry schema: "
                f"{schema!r}"
            )

        return payload

    def save(self, payload: dict[str, Any]) -> None:
        self.registry_dir.mkdir(parents=True, exist_ok=True)

        if self.registry_path.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = (
                self.registry_dir
                / f"system_registry_before_update_{stamp}.json"
            )
            shutil.copy2(self.registry_path, backup)

        payload["generated_at_utc"] = utc_now()

        self.registry_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def canonical_paths(self) -> set[Path]:
        payload = self.load()
        result: set[Path] = set()
        schema = payload.get("schema")

        for project in payload.get("projects", {}).values():
            if schema == REGISTRY_SCHEMA_V1:
                records = project.get("canonical", {}).values()
            else:
                records = project.get("stages", {}).values()

            for record in records:
                raw_path = record.get("path")
                status = record.get("status")

                if not raw_path:
                    continue

                if schema == REGISTRY_SCHEMA_V2 and status in {
                    "SUPERSEDED",
                    "ARCHIVED",
                    "FAILED",
                }:
                    continue

                result.add(normalize(raw_path))

        return result

    def promote(
        self,
        project_id: str,
        domain: str,
        artifact_path: Path | str,
    ) -> dict[str, Any]:
        path = normalize(artifact_path)

        if not path.is_file():
            raise FileNotFoundError(path)

        if not is_inside(path, self.workspace):
            raise RegistryError(
                f"Canonical artifact must be inside workspace: {path}"
            )

        payload = self.load()
        projects = payload.setdefault("projects", {})

        if project_id not in projects:
            project_root = self.workspace / "projects" / project_id
            export_root = self.workspace / "exports" / project_id / "rc2"

            projects[project_id] = {
                "project_id": project_id,
                "project_root": str(project_root.resolve()),
                "export_root": str(export_root.resolve()),
                "canonical": {},
            }

        stat = path.stat()

        record = {
            "role": domain,
            "path": str(path),
            "exists": True,
            "size_bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(
                stat.st_mtime,
                tz=timezone.utc,
            ).isoformat(),
            "sha256": sha256_file(path),
        }

        projects[project_id].setdefault("canonical", {})[domain] = record
        self.save(payload)
        return record

    def validate(self) -> dict[str, Any]:
        payload = self.load()
        checks: list[dict[str, Any]] = []

        for project_id, project in payload.get("projects", {}).items():
            for domain, record in project.get("canonical", {}).items():
                raw_path = record.get("path")

                if not raw_path:
                    checks.append({
                        "project_id": project_id,
                        "domain": domain,
                        "state": "MISSING_PATH",
                        "path": None,
                    })
                    continue

                path = normalize(raw_path)

                if not path.is_file():
                    checks.append({
                        "project_id": project_id,
                        "domain": domain,
                        "state": "MISSING_FILE",
                        "path": str(path),
                    })
                    continue

                expected_hash = record.get("sha256")
                actual_hash = sha256_file(path)

                state = (
                    "VALID"
                    if not expected_hash or expected_hash == actual_hash
                    else "HASH_MISMATCH"
                )

                checks.append({
                    "project_id": project_id,
                    "domain": domain,
                    "state": state,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "sha256": actual_hash,
                })

        invalid = [
            row for row in checks
            if row["state"] not in {"VALID", "MISSING_PATH"}
        ]

        return {
            "schema": "atlas_zero.registry_validation.rc2.v1",
            "generated_at_utc": utc_now(),
            "state": "VALID" if not invalid else "INVALID",
            "checks": checks,
            "invalid_count": len(invalid),
        }


class ArtifactManagerRC2:
    """Inventory and classification of files created inside workspace."""

    TEMP_NAME_MARKERS = (
        ".partial",
        "_tmp",
        ".tmp",
        ".temp",
        "_test",
        "test_",
        "_debug",
        "debug_",
        "_failed",
        "failed_",
        "_before_",
        "before_",
        "_old",
        "old_",
        "_copy",
        "copy_",
    )

    TEMP_DIRECTORIES = {
        "_native_visual_tmp",
        "_api_tests",
        "__pycache__",
        ".pytest_cache",
    }

    def __init__(
        self,
        root: Path | str,
        registry: SystemRegistryRC2,
    ) -> None:
        self.root = normalize(root)
        self.workspace = self.root / "workspace"
        self.registry = registry
        self.audit_dir = self.workspace / "audit"

    def classify(
        self,
        path: Path,
        canonical_paths: set[Path],
    ) -> ArtifactRecord:
        resolved = path.resolve()
        lower_name = resolved.name.lower()
        canonical = resolved in canonical_paths

        protected_roots = (
            self.workspace / "registry",
            self.workspace / "audit",
            self.workspace / "projects" / "franklin",
        )

        protected = any(
            is_inside(resolved, root.resolve())
            for root in protected_roots
            if root.exists()
        )

        if canonical:
            category = "CANONICAL"
            reason = "Registered as canonical in System Registry"
        elif protected:
            category = "PROTECTED"
            reason = "Located inside a protected RC2 area"
        elif any(
            part.lower() in self.TEMP_DIRECTORIES
            for part in resolved.parts
        ):
            category = "TEMPORARY"
            reason = "Located inside a temporary directory"
        elif any(marker in lower_name for marker in self.TEMP_NAME_MARKERS):
            category = "TEMPORARY"
            reason = "Filename matches an explicit temporary marker"
        else:
            category = "WORKING"
            reason = "Unregistered working or source artifact"

        stat = resolved.stat()

        return ArtifactRecord(
            path=str(resolved),
            size_bytes=stat.st_size,
            modified_utc=datetime.fromtimestamp(
                stat.st_mtime,
                tz=timezone.utc,
            ).isoformat(),
            category=category,
            reason=reason,
            canonical=canonical,
            protected=protected,
        )

    def scan(self) -> dict[str, Any]:
        canonical_paths = self.registry.canonical_paths()
        records: list[ArtifactRecord] = []

        if not self.workspace.is_dir():
            raise FileNotFoundError(self.workspace)

        for path in self.workspace.rglob("*"):
            if not path.is_file():
                continue

            records.append(self.classify(path, canonical_paths))

        summary: dict[str, dict[str, int]] = {}

        for record in records:
            bucket = summary.setdefault(
                record.category,
                {"files": 0, "size_bytes": 0},
            )
            bucket["files"] += 1
            bucket["size_bytes"] += record.size_bytes

        payload = {
            "schema": ARTIFACT_SCHEMA,
            "state": "ARTIFACT_INVENTORY_READY",
            "generated_at_utc": utc_now(),
            "root": str(self.root),
            "workspace": str(self.workspace),
            "summary": summary,
            "artifacts": [record.to_dict() for record in records],
        }

        self.audit_dir.mkdir(parents=True, exist_ok=True)
        output = self.audit_dir / "artifact_inventory_rc2.json"
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return payload


class GarbageCollectorRC2:
    """
    Conservative RC2 garbage collector.

    It never deletes immediately. With apply=True it moves approved
    artifacts into workspace/_trash/<timestamp>/ for rollback.
    """

    def __init__(
        self,
        root: Path | str,
        registry: SystemRegistryRC2,
        artifact_manager: ArtifactManagerRC2,
    ) -> None:
        self.root = normalize(root)
        self.workspace = self.root / "workspace"
        self.registry = registry
        self.artifact_manager = artifact_manager
        self.audit_dir = self.workspace / "audit"

    def build_plan(
        self,
        inventory: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        inventory = inventory or self.artifact_manager.scan()
        canonical_paths = self.registry.canonical_paths()

        candidates: list[dict[str, Any]] = []

        for row in inventory.get("artifacts", []):
            path = normalize(row["path"])

            if row.get("category") != "TEMPORARY":
                continue

            if row.get("protected"):
                continue

            if path in canonical_paths:
                continue

            if not is_inside(path, self.workspace):
                continue

            candidates.append(row)

        total_bytes = sum(
            int(row.get("size_bytes") or 0)
            for row in candidates
        )

        payload = {
            "schema": CLEANUP_SCHEMA,
            "state": "CLEANUP_PLAN_READY",
            "generated_at_utc": utc_now(),
            "mode": "QUARANTINE_ONLY",
            "candidate_count": len(candidates),
            "total_bytes": total_bytes,
            "candidates": candidates,
        }

        self.audit_dir.mkdir(parents=True, exist_ok=True)
        output = self.audit_dir / "cleanup_plan_rc2.json"
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return payload

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        if plan.get("schema") != CLEANUP_SCHEMA:
            raise RuntimeError("Invalid cleanup plan schema")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_root = self.workspace / "_trash" / stamp
        trash_root.mkdir(parents=True, exist_ok=True)

        moved: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        canonical_paths = self.registry.canonical_paths()

        for candidate in plan.get("candidates", []):
            source = normalize(candidate["path"])

            if source in canonical_paths:
                skipped.append({
                    "path": str(source),
                    "reason": "Canonical artifact",
                })
                continue

            if not source.exists():
                skipped.append({
                    "path": str(source),
                    "reason": "Already missing",
                })
                continue

            if not is_inside(source, self.workspace):
                skipped.append({
                    "path": str(source),
                    "reason": "Outside workspace",
                })
                continue

            relative = source.relative_to(self.workspace)
            destination = trash_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(str(source), str(destination))

            moved.append({
                "source": str(source),
                "destination": str(destination),
                "size_bytes": candidate.get("size_bytes", 0),
            })

        report = {
            "schema": "atlas_zero.cleanup_execution.rc2.v1",
            "state": "ARTIFACTS_QUARANTINED",
            "generated_at_utc": utc_now(),
            "trash_root": str(trash_root.resolve()),
            "moved_count": len(moved),
            "moved_bytes": sum(
                int(row.get("size_bytes") or 0)
                for row in moved
            ),
            "moved": moved,
            "skipped": skipped,
        }

        report_path = (
            self.audit_dir
            / f"cleanup_execution_rc2_{stamp}.json"
        )
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return report

