from __future__ import annotations

import argparse
import json
from pathlib import Path

from az_enterprise.core.artifact_control_rc2 import (
    ArtifactManagerRC2,
    GarbageCollectorRC2,
    SystemRegistryRC2,
)


def mb(value: int | float) -> float:
    return round(float(value) / (1024 * 1024), 2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ATLAS ZERO RC2 artifact control"
    )
    parser.add_argument(
        "command",
        choices=("validate", "scan", "plan", "clean", "promote"),
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--project")
    parser.add_argument("--domain")
    parser.add_argument("--path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move cleanup candidates to quarantine",
    )

    args = parser.parse_args()
    root = Path(args.root).resolve()

    registry = SystemRegistryRC2(root)
    artifacts = ArtifactManagerRC2(root, registry)
    collector = GarbageCollectorRC2(root, registry, artifacts)

    if args.command == "validate":
        result = registry.validate()

        print("ATLAS ZERO RC2 — REGISTRY VALIDATION")
        print("STATE:", result["state"])
        print("INVALID:", result["invalid_count"])

        for row in result["checks"]:
            print(
                row["state"],
                "|",
                row["project_id"],
                "|",
                row["domain"],
                "|",
                row.get("path"),
            )

        return 0 if result["state"] == "VALID" else 2

    if args.command == "scan":
        result = artifacts.scan()

        print("ATLAS ZERO RC2 — ARTIFACT INVENTORY")
        print("STATE:", result["state"])

        for category, values in result["summary"].items():
            print(
                category,
                "| files=",
                values["files"],
                "| MB=",
                mb(values["size_bytes"]),
            )

        print(
            "REPORT:",
            root / "workspace" / "audit"
            / "artifact_inventory_rc2.json",
        )
        return 0

    if args.command in {"plan", "clean"}:
        inventory = artifacts.scan()
        plan = collector.build_plan(inventory)

        print("ATLAS ZERO RC2 — CLEANUP PLAN")
        print("CANDIDATES:", plan["candidate_count"])
        print("TOTAL MB:", mb(plan["total_bytes"]))
        print(
            "PLAN:",
            root / "workspace" / "audit" / "cleanup_plan_rc2.json",
        )

        if args.command == "clean" and args.apply:
            report = collector.apply(plan)

            print("STATE:", report["state"])
            print("MOVED:", report["moved_count"])
            print("MOVED MB:", mb(report["moved_bytes"]))
            print("TRASH:", report["trash_root"])
        else:
            print("DRY RUN: nothing moved")

        return 0

    if args.command == "promote":
        if not args.project or not args.domain or not args.path:
            parser.error(
                "promote requires --project, --domain and --path"
            )

        record = registry.promote(
            args.project,
            args.domain,
            args.path,
        )

        print("ATLAS ZERO RC2 — CANONICAL ARTIFACT PROMOTED")
        print("PROJECT:", args.project)
        print("DOMAIN:", args.domain)
        print("PATH:", record["path"])
        print("SHA256:", record["sha256"])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
