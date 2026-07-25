from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .system_governance_gate_rc2 import (
    GovernanceBlockedError,
    SystemGovernanceGateRC2,
)


def locate_project_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "src" / "az_enterprise").exists():
            return candidate
    raise FileNotFoundError("ATLAS ZERO project root was not found")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ATLAS ZERO RC2 system governance gate."
    )
    parser.add_argument(
        "command",
        choices=("check", "enforce", "refresh"),
        nargs="?",
        default="check",
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Use existing system_health.json instead of rebuilding intelligence.",
    )
    parser.add_argument("--context", default="cli")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve() if args.root else locate_project_root(Path.cwd())
    output = (
        args.output.resolve()
        if args.output
        else root / "workspace" / "system"
    )
    gate = SystemGovernanceGateRC2(
        root,
        output,
        policy_path=args.policy,
    )

    if args.command == "refresh":
        gate.refresh()
        result = gate.evaluate(
            refresh=False,
            context={"entrypoint": args.context, "command": "refresh"},
        )
    else:
        try:
            if args.command == "enforce":
                result = gate.enforce(
                    refresh=not args.no_refresh,
                    context={"entrypoint": args.context, "command": "enforce"},
                )
            else:
                result = gate.evaluate(
                    refresh=not args.no_refresh,
                    context={"entrypoint": args.context, "command": "check"},
                )
        except GovernanceBlockedError as exc:
            result = exc.result

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("ATLAS ZERO RC2 — SYSTEM GOVERNANCE")
        print("=" * 72)
        print(f"Decision:           {payload['decision'].upper()}")
        print(f"Allowed:            {payload['allowed']}")
        print(f"Status:             {payload['status']}")
        print(f"Architecture score: {payload['architecture_score']}")
        print(f"Syntax errors:      {payload['syntax_errors']}")
        print(f"Layer violations:   {payload['layer_violations']}")
        if payload["reasons"]:
            print("Reasons:")
            for item in payload["reasons"]:
                print(f"  - {item}")
        if payload["warnings"]:
            print("Warnings:")
            for item in payload["warnings"]:
                print(f"  - {item}")
        print(f"Decision file:      {gate.latest_path}")
        print("=" * 72)

    return 0 if result.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
