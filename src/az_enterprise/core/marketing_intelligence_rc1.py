from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


class MarketingIntelligenceRC1:
    """
    ATLAS ZERO — Marketing Intelligence RC1.

    Phase 1 platforms:
    - YouTube
    - Instagram
    - TikTok

    Responsibilities:
    - store platform publication packages;
    - store performance snapshots;
    - provide normalized analytics;
    - produce deterministic performance summaries.

    This module does NOT publish directly and does NOT own credentials.
    External platform adapters remain separate integration concerns.
    """

    SUPPORTED_PLATFORMS = (
        "youtube",
        "instagram",
        "tiktok",
    )

    def __init__(
        self,
        db: Any,
        project_id: str,
    ) -> None:
        self.db = db
        self.project_id = str(project_id).strip()

        if not self.project_id:
            raise ValueError("project_id is required")

        self.ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        self.db.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS marketing_publication_packages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                package_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, platform)
            );

            CREATE TABLE IF NOT EXISTS analytics_snapshots(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                captured_at TEXT NOT NULL,

                views INTEGER,
                impressions INTEGER,
                ctr REAL,
                watch_time_sec REAL,
                avg_view_duration_sec REAL,

                likes INTEGER,
                comments INTEGER,
                shares INTEGER,
                subscribers_delta INTEGER,

                payload_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_analytics_project_platform_time
            ON analytics_snapshots(
                project_id,
                platform,
                captured_at
            );
            """
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # Publication package
    # ------------------------------------------------------------------

    def build_publication_package(
        self,
        *,
        title: str,
        description: str,
        tags: list[str] | None = None,
        hashtags: list[str] | None = None,
        source_video: str | None = None,
    ) -> dict[str, Any]:

        tags = [
            str(item).strip()
            for item in (tags or [])
            if str(item).strip()
        ]

        hashtags = [
            self._normalize_hashtag(item)
            for item in (hashtags or [])
            if str(item).strip()
        ]

        base = {
            "project_id": self.project_id,
            "source_video": source_video,
            "generated_at": self._now(),
        }

        package = {
            "schema":
                "atlas_zero.marketing_publication_package.rc1",
            "project_id":
                self.project_id,
            "platforms": {
                "youtube": {
                    **base,
                    "title": str(title).strip(),
                    "description": str(description).strip(),
                    "tags": tags,
                    "hashtags": hashtags,
                    "content_type": "long_form",
                },
                "instagram": {
                    **base,
                    "caption": str(description).strip(),
                    "hashtags": hashtags,
                    "content_type": "reel",
                },
                "tiktok": {
                    **base,
                    "caption": str(title).strip(),
                    "description": str(description).strip(),
                    "hashtags": hashtags,
                    "content_type": "video",
                },
            },
        }

        return package

    def save_publication_package(
        self,
        platform: str,
        package: dict[str, Any],
    ) -> dict[str, Any]:

        platform = self._platform(platform)
        now = self._now()

        payload = json.dumps(
            package,
            ensure_ascii=False,
            sort_keys=True,
        )

        self.db.conn.execute(
            """
            INSERT INTO marketing_publication_packages(
                project_id,
                platform,
                package_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(project_id, platform)
            DO UPDATE SET
                package_json=excluded.package_json,
                updated_at=excluded.updated_at
            """,
            (
                self.project_id,
                platform,
                payload,
                now,
                now,
            ),
        )

        self.db.conn.commit()

        return {
            "state": "MARKETING_PACKAGE_READY",
            "project_id": self.project_id,
            "platform": platform,
        }

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def record_snapshot(
        self,
        *,
        platform: str,
        metrics: dict[str, Any],
        captured_at: str | None = None,
    ) -> dict[str, Any]:

        platform = self._platform(platform)
        captured_at = captured_at or self._now()

        normalized = self._normalize_metrics(metrics)

        cursor = self.db.conn.execute(
            """
            INSERT INTO analytics_snapshots(
                project_id,
                platform,
                captured_at,
                views,
                impressions,
                ctr,
                watch_time_sec,
                avg_view_duration_sec,
                likes,
                comments,
                shares,
                subscribers_delta,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.project_id,
                platform,
                captured_at,
                normalized["views"],
                normalized["impressions"],
                normalized["ctr"],
                normalized["watch_time_sec"],
                normalized["avg_view_duration_sec"],
                normalized["likes"],
                normalized["comments"],
                normalized["shares"],
                normalized["subscribers_delta"],
                json.dumps(
                    metrics,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )

        self.db.conn.commit()

        return {
            "state": "ANALYTICS_SNAPSHOT_RECORDED",
            "snapshot_id": cursor.lastrowid,
            "project_id": self.project_id,
            "platform": platform,
            "captured_at": captured_at,
        }

    def latest_snapshot(
        self,
        platform: str,
    ) -> dict[str, Any] | None:

        platform = self._platform(platform)

        row = self.db.conn.execute(
            """
            SELECT
                id,
                captured_at,
                views,
                impressions,
                ctr,
                watch_time_sec,
                avg_view_duration_sec,
                likes,
                comments,
                shares,
                subscribers_delta,
                payload_json
            FROM analytics_snapshots
            WHERE project_id=?
              AND platform=?
            ORDER BY captured_at DESC, id DESC
            LIMIT 1
            """,
            (
                self.project_id,
                platform,
            ),
        ).fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "project_id": self.project_id,
            "platform": platform,
            "captured_at": row[1],
            "views": row[2],
            "impressions": row[3],
            "ctr": row[4],
            "watch_time_sec": row[5],
            "avg_view_duration_sec": row[6],
            "likes": row[7],
            "comments": row[8],
            "shares": row[9],
            "subscribers_delta": row[10],
            "payload": json.loads(row[11]),
        }

    def recent_snapshots(
        self,
        platform: str,
        *,
        limit: int = 2,
    ) -> list[dict[str, Any]]:

        platform = self._platform(platform)

        rows = self.db.conn.execute(
            """
            SELECT
                id,
                captured_at,
                views,
                impressions,
                ctr,
                watch_time_sec,
                avg_view_duration_sec,
                likes,
                comments,
                shares,
                subscribers_delta
            FROM analytics_snapshots
            WHERE project_id=?
              AND platform=?
            ORDER BY captured_at DESC, id DESC
            LIMIT ?
            """,
            (
                self.project_id,
                platform,
                max(1, int(limit)),
            ),
        ).fetchall()

        return [
            {
                "id": row[0],
                "captured_at": row[1],
                "views": row[2],
                "impressions": row[3],
                "ctr": row[4],
                "watch_time_sec": row[5],
                "avg_view_duration_sec": row[6],
                "likes": row[7],
                "comments": row[8],
                "shares": row[9],
                "subscribers_delta": row[10],
            }
            for row in rows
        ]

    def performance_summary(
        self,
        platform: str,
    ) -> dict[str, Any]:

        platform = self._platform(platform)
        snapshots = self.recent_snapshots(
            platform,
            limit=2,
        )

        if not snapshots:
            return {
                "state": "NO_ANALYTICS",
                "project_id": self.project_id,
                "platform": platform,
            }

        latest = snapshots[0]
        previous = snapshots[1] if len(snapshots) > 1 else None

        views = int(latest.get("views") or 0)
        likes = int(latest.get("likes") or 0)
        comments = int(latest.get("comments") or 0)
        shares = int(latest.get("shares") or 0)

        engagement_rate = (
            (likes + comments + shares) / views
            if views > 0
            else 0.0
        )

        summary = {
            "state": "PERFORMANCE_SUMMARY_READY",
            "project_id": self.project_id,
            "platform": platform,
            "latest": latest,
            "engagement_rate": engagement_rate,
            "deltas": {},
        }

        if previous:
            for field in (
                "views",
                "impressions",
                "watch_time_sec",
                "likes",
                "comments",
                "shares",
                "subscribers_delta",
            ):
                current = float(latest.get(field) or 0)
                old = float(previous.get(field) or 0)

                summary["deltas"][field] = current - old

        return summary

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _platform(cls, value: str) -> str:
        platform = str(value).strip().lower()

        if platform not in cls.SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Unsupported platform: {platform}"
            )

        return platform

    @staticmethod
    def _normalize_metrics(
        metrics: dict[str, Any],
    ) -> dict[str, Any]:

        def integer(name: str) -> int | None:
            value = metrics.get(name)
            return None if value is None else int(value)

        def number(name: str) -> float | None:
            value = metrics.get(name)
            return None if value is None else float(value)

        return {
            "views": integer("views"),
            "impressions": integer("impressions"),
            "ctr": number("ctr"),
            "watch_time_sec": number("watch_time_sec"),
            "avg_view_duration_sec":
                number("avg_view_duration_sec"),
            "likes": integer("likes"),
            "comments": integer("comments"),
            "shares": integer("shares"),
            "subscribers_delta":
                integer("subscribers_delta"),
        }

    @staticmethod
    def _normalize_hashtag(value: str) -> str:
        value = str(value).strip()

        if not value:
            return value

        return (
            value
            if value.startswith("#")
            else "#" + value
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()
