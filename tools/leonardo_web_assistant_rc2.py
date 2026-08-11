from __future__ import annotations

import argparse
import json
from pathlib import Path

from az_enterprise.core.leonardo_web_assistant_rc2 import (
    LeonardoWebAssistantRC2,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ATLAS ZERO RC2 Leonardo "
            "semi-automatic web assistant"
        )
    )

    parser.add_argument(
        "command",
        choices=(
            "status",
            "next",
            "capture",
        ),
    )

    parser.add_argument("project_id")
    parser.add_argument("--root", default=".")
    parser.add_argument("--downloads")
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
    )

    args = parser.parse_args()

    assistant = LeonardoWebAssistantRC2(
        root=Path(args.root),
        project_id=args.project_id,
        downloads_dir=args.downloads,
    )

    if args.command == "status":
        result = assistant.status()

    elif args.command == "next":
        result = assistant.prepare_next()

    else:
        result = assistant.capture_next(
            timeout_sec=args.timeout,
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
