from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .director_core_rc2 import DirectorCoreRC2
from .production_state_rc2 import ProductionStateStoreRC2
from .project_config_rc2 import ProjectConfigRC2
from .runtime_governance_rc2 import governance_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ATLAS ZERO RC2")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run canonical RC2 production pipeline")
    run.add_argument("project_id")
    run.add_argument("--no-resume", action="store_true")
    run.add_argument("--force", action="store_true")

    status = sub.add_parser("status", help="Read canonical RC2 production state")
    status.add_argument("project_id")

    plan = sub.add_parser("plan", help="Show canonical stage plan without running")
    plan.add_argument("project_id")

    sub.add_parser("governance", help="Show runtime authority policy")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run":
        result = DirectorCoreRC2(args.project_id).run(
            resume=not args.no_resume,
            force=args.force,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "plan":
        print(json.dumps(DirectorCoreRC2(args.project_id).plan(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "governance":
        print(json.dumps(governance_report(), ensure_ascii=False, indent=2))
        return 0

    config = ProjectConfigRC2(project_id=args.project_id)
    state = ProductionStateStoreRC2(config.state_path, project_id=args.project_id).load()
    print(json.dumps(asdict(state), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
