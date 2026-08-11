from __future__ import annotations

import argparse
import json
from pathlib import Path

from az_enterprise.core.leonardo_queue_builder_rc2 import (
    LeonardoQueueBuilderRC2,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ATLAS ZERO RC2 canonical Leonardo "
            "queue builder"
        )
    )

    parser.add_argument("project_id")
    parser.add_argument("--root", default=".")

    args = parser.parse_args()

    builder = LeonardoQueueBuilderRC2(
        root=Path(args.root),
        project_id=args.project_id,
    )

    result = builder.build()

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
        == "CANONICAL_QUEUE_READY"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
