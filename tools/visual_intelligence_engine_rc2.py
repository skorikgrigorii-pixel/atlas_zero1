from __future__ import annotations

import argparse
import json
from pathlib import Path

from az_enterprise.core.visual_intelligence_engine_rc2 import (
    VisualIntelligenceEngineRC2,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ATLAS ZERO RC2 — scenario-driven "
            "visual intelligence engine"
        )
    )

    parser.add_argument(
        "command",
        choices=(
            "analyze",
            "status",
        ),
    )

    parser.add_argument("project_id")
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--asset-limit",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--only-unassigned-assets",
        action="store_true",
    )

    args = parser.parse_args()

    engine = VisualIntelligenceEngineRC2(
        root=Path(args.root),
        project_id=args.project_id,
    )

    if args.command == "status":
        result = {
            "state": (
                "READY"
                if engine.db_path.is_file()
                else "NOT_READY"
            ),
            "project_id": args.project_id,
            "database": str(
                engine.db_path.resolve()
            ),
            "report": str(
                engine.report_path.resolve()
            ),
            "report_exists":
                engine.report_path.is_file(),
        }

    else:
        result = engine.analyze(
            asset_limit=args.asset_limit,
            top_k=args.top_k,
            only_unassigned_assets=(
                args.only_unassigned_assets
            ),
        )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
