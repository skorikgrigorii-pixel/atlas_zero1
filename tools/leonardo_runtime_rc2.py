from __future__ import annotations

import argparse
import json
from pathlib import Path

from az_enterprise.core.leonardo_runtime_rc2 import (
    LeonardoRuntimeRC2,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ATLAS ZERO RC2 Leonardo Runtime"
    )

    parser.add_argument(
        "command",
        choices=("doctor", "dry-run", "live"),
    )
    parser.add_argument("project_id")
    parser.add_argument("--root", default=".")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument(
        "--confirm-paid",
        action="store_true",
    )

    args = parser.parse_args()

    runtime = LeonardoRuntimeRC2(
        root=Path(args.root),
        project_id=args.project_id,
    )

    if args.command == "doctor":
        result = runtime.doctor()

    elif args.command == "dry-run":
        result = runtime.dry_run(
            limit=args.limit,
        )

    else:
        result = runtime.run_live(
            limit=args.limit,
            confirm_paid=args.confirm_paid,
        )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    return (
        0
        if result.get("state")
        in {
            "READY",
            "DRY_RUN_READY",
            "COMPLETED",
        }
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
