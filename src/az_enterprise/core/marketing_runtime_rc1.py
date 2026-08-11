from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import Database
from .events import EventBus
from .marketing_learning_bridge_rc1 import (
    MarketingLearningBridgeRC1,
)
from .director_learning_adapter_rc1 import (
    DirectorLearningAdapterRC1,
)


class MarketingRuntimeRC1:
    """
    ATLAS ZERO — Marketing Runtime RC1.

    Production entry point for post-release feedback.

    Flow:
        metrics
          ->
        analytics snapshot
          ->
        performance summary
          ->
        learning update
          ->
        event bus
          ->
        director advisory
          ->
        report artifact
    """

    def __init__(
        self,
        *,
        db: Database,
        project_id: str,
        root: Path | None = None,
    ) -> None:

        self.db = db
        self.project_id = str(project_id).strip()

        if not self.project_id:
            raise ValueError("project_id is required")

        self.root = (
            Path(root)
            if root is not None
            else Path.cwd()
        )

        self.event_bus = EventBus(
            db=db,
            project_id=self.project_id,
        )

        self.bridge = MarketingLearningBridgeRC1(
            db=db,
            project_id=self.project_id,
            event_bus=self.event_bus,
        )

        self.director_adapter = (
            DirectorLearningAdapterRC1(
                db=db,
                project_id=self.project_id,
                event_bus=self.event_bus,
            )
        )

        self.output_dir = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "marketing"
        )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def record(
        self,
        *,
        platform: str,
        metrics: dict[str, Any],
        captured_at: str | None = None,
    ) -> dict[str, Any]:

        snapshot = self.bridge.marketing.record_snapshot(
            platform=platform,
            metrics=metrics,
            captured_at=captured_at,
        )

        cycle = self.bridge.process_platform(
            platform
        )

        advisory = (
            self.director_adapter.latest_advisory()
        )

        report = {
            "schema":
                "atlas_zero.marketing_runtime.rc1",

            "state":
                "MARKETING_RUNTIME_COMPLETE",

            "project_id":
                self.project_id,

            "platform":
                str(platform).lower(),

            "captured_at":
                snapshot["captured_at"],

            "snapshot":
                snapshot,

            "cycle":
                cycle,

            "director_advisory":
                advisory,

            "created_at":
                self._now(),
        }

        report_path = (
            self.output_dir
            / f"{str(platform).lower()}_latest.json"
        )

        report_path.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        history_path = (
            self.output_dir
            / "history.jsonl"
        )

        with history_path.open(
            "a",
            encoding="utf-8",
        ) as stream:

            stream.write(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

        report["artifact"] = str(
            report_path.resolve()
        )

        return report

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "ATLAS ZERO Marketing Runtime RC1"
        )
    )

    parser.add_argument(
        "project_id"
    )

    parser.add_argument(
        "--platform",
        required=True,
        choices=(
            "youtube",
            "instagram",
            "tiktok",
        ),
    )

    parser.add_argument(
        "--views",
        type=int,
    )

    parser.add_argument(
        "--impressions",
        type=int,
    )

    parser.add_argument(
        "--ctr",
        type=float,
    )

    parser.add_argument(
        "--watch-time-sec",
        type=float,
    )

    parser.add_argument(
        "--avg-view-duration-sec",
        type=float,
    )

    parser.add_argument(
        "--likes",
        type=int,
    )

    parser.add_argument(
        "--comments",
        type=int,
    )

    parser.add_argument(
        "--shares",
        type=int,
    )

    parser.add_argument(
        "--subscribers-delta",
        type=int,
    )

    parser.add_argument(
        "--captured-at",
        default=None,
    )

    return parser.parse_args()


def main() -> int:

    args = parse_args()

    db = Database()
    db.init()

    runtime = MarketingRuntimeRC1(
        db=db,
        project_id=args.project_id,
    )

    metrics = {
        "views":
            args.views,

        "impressions":
            args.impressions,

        "ctr":
            args.ctr,

        "watch_time_sec":
            args.watch_time_sec,

        "avg_view_duration_sec":
            args.avg_view_duration_sec,

        "likes":
            args.likes,

        "comments":
            args.comments,

        "shares":
            args.shares,

        "subscribers_delta":
            args.subscribers_delta,
    }

    metrics = {
        key: value
        for key, value in metrics.items()
        if value is not None
    }

    result = runtime.record(
        platform=args.platform,
        metrics=metrics,
        captured_at=args.captured_at,
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
