from __future__ import annotations

import argparse
from pathlib import Path

from az_enterprise.core.production_registry_rc2 import (
    ProductionRegistryRC2,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ATLAS ZERO RC2 Production Registry"
    )

    parser.add_argument(
        "command",
        choices=("migrate", "validate", "status", "set-stage"),
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--project")
    parser.add_argument("--domain")
    parser.add_argument("--status")
    parser.add_argument("--path")
    parser.add_argument("--note")

    args = parser.parse_args()
    registry = ProductionRegistryRC2(Path(args.root))

    if args.command == "migrate":
        payload = registry.migrate_v1_to_v2()

        print("ATLAS ZERO RC2 — REGISTRY V2 MIGRATED")
        print("SCHEMA:", payload["schema"])
        print("PROJECTS:", len(payload["projects"]))
        print("PATH:", registry.path)

        for project_id, project in payload["projects"].items():
            print(
                project_id,
                "|",
                project["production_state"],
            )

        return 0

    if args.command == "validate":
        result = registry.validate()

        print("ATLAS ZERO RC2 — REGISTRY V2 VALIDATION")
        print("STATE:", result["state"])
        print("BLOCKING:", result["blocking_count"])

        for row in result["checks"]:
            print(
                row["state"],
                "|",
                row["project_id"],
                "|",
                row["domain"],
                "| status=",
                row["status"],
                "|",
                row["path"],
            )

        return 0 if result["state"] == "VALID" else 2

    if args.command == "status":
        payload = registry.load()

        print("ATLAS ZERO RC2 — PRODUCTION STATUS")

        for project_id, project in payload["projects"].items():
            print()
            print(
                "PROJECT:",
                project_id,
                "| STATE:",
                project["production_state"],
            )

            for domain, record in project["stages"].items():
                print(
                    record["status"],
                    "|",
                    domain,
                    "|",
                    record.get("path"),
                )

        return 0

    if args.command == "set-stage":
        if not args.project or not args.domain or not args.status:
            parser.error(
                "set-stage requires --project, --domain and --status"
            )

        record = registry.set_stage(
            project_id=args.project,
            domain=args.domain,
            status=args.status,
            path=args.path,
            note=args.note,
        )

        print("ATLAS ZERO RC2 — STAGE UPDATED")
        print("PROJECT:", args.project)
        print("DOMAIN:", args.domain)
        print("STATUS:", record["status"])
        print("PATH:", record["path"])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
