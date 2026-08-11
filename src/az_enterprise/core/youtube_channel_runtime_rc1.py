from __future__ import annotations

import argparse
import json
from pathlib import Path

from .database import Database
from .youtube_connector_rc1 import (
    YouTubeConnectorRC1,
)
from .youtube_oauth_rc1 import (
    YouTubeOAuthRC1,
)
from .youtube_channel_collector_rc1 import (
    YouTubeChannelCollectorRC1,
)
from .youtube_channel_intelligence_rc1 import (
    YouTubeChannelIntelligenceRC1,
)


class YouTubeChannelRuntimeRC1:
    """
    Full YouTube channel analytics runtime.

    OAuth
      ->
    Connector
      ->
    Collector
      ->
    Channel Intelligence
      ->
    Learning Core
    """

    def __init__(
        self,
        *,
        db: Database,
        connector:
            YouTubeConnectorRC1 | None = None,
        root: Path | None = None,
    ) -> None:

        self.db = db

        self.root = (
            Path(root)
            if root is not None
            else Path.cwd()
        )

        self.connector = (
            connector
            or self._build_live_connector()
        )

        self.collector = (
            YouTubeChannelCollectorRC1(
                connector=self.connector,
                root=self.root,
            )
        )

        self.intelligence = (
            YouTubeChannelIntelligenceRC1(
                db=db,
            )
        )

    def _build_live_connector(
        self,
    ) -> YouTubeConnectorRC1:

        token_file = (
            self.root
            / "workspace"
            / "secrets"
            / "youtube"
            / "google_oauth_token.json"
        )

        if not token_file.is_file():
            raise RuntimeError(
                f"YouTube OAuth token file not found: "
                f"{token_file}"
            )

        credentials = json.loads(
            token_file.read_text(
                encoding="utf-8-sig"
            )
        )

        oauth = YouTubeOAuthRC1(
            client_id=
                credentials.get(
                    "client_id"
                ),

            client_secret=
                credentials.get(
                    "client_secret"
                ),

            refresh_token=
                credentials.get(
                    "refresh_token"
                ),
        )

        return YouTubeConnectorRC1(
            oauth=oauth
        )

    def run(
        self,
        *,
        start_date: str = "2005-01-01",
        end_date: str | None = None,
    ) -> dict:

        snapshot = self.collector.collect(
            start_date=start_date,
            end_date=end_date,
        )

        intelligence = (
            self.intelligence
            .ingest_channel_snapshot(
                snapshot
            )
        )

        return {
            "schema":
                "atlas_zero.youtube_channel_runtime.rc1",

            "state":
                "YOUTUBE_CHANNEL_RUNTIME_COMPLETE",

            "snapshot":
                snapshot,

            "intelligence":
                intelligence,
        }


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "ATLAS ZERO YouTube "
            "Channel Runtime RC1"
        )
    )

    parser.add_argument(
        "--start-date",
        default="2005-01-01",
    )

    parser.add_argument(
        "--end-date",
        default=None,
    )

    args = parser.parse_args()

    db = Database()
    db.init()

    runtime = (
        YouTubeChannelRuntimeRC1(
            db=db,
        )
    )

    result = runtime.run(
        start_date=args.start_date,
        end_date=args.end_date,
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
