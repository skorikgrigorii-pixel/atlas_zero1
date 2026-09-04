from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

from .learning_core_rc1 import LearningCoreRC1


class YouTubeChannelIntelligenceRC1:
    """
    ATLAS ZERO — YouTube Channel Intelligence RC1.

    Channel-wide analytics for ALL published videos.

    Important:
    - not bound to one project;
    - project links are optional;
    - fresh Analytics API zeroes can be marked ANALYTICS_PENDING;
    - pending retention/watch-time values must NOT train Learning Core.
    """

    CHANNEL_LEARNING_PROJECT = "__channel_youtube__"

    def __init__(
        self,
        *,
        db: Any,
    ) -> None:

        self.db = db
        self.ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:

        self.db.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS youtube_project_links(
                video_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                link_source TEXT NOT NULL DEFAULT 'manual',
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS youtube_video_snapshots(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                video_id TEXT NOT NULL,
                project_id TEXT,

                captured_at TEXT NOT NULL,

                title TEXT,
                published_at TEXT,
                privacy_status TEXT,
                analytics_state TEXT,

                views INTEGER,
                likes INTEGER,
                comments INTEGER,
                shares INTEGER,

                estimated_minutes_watched REAL,
                average_view_duration_sec REAL,
                average_view_percentage REAL,

                subscribers_gained INTEGER,
                subscribers_lost INTEGER,

                payload_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_youtube_video_snapshots_video_time
            ON youtube_video_snapshots(
                video_id,
                captured_at
            );

            CREATE INDEX IF NOT EXISTS
                idx_youtube_video_snapshots_project_time
            ON youtube_video_snapshots(
                project_id,
                captured_at
            );

            CREATE TABLE IF NOT EXISTS youtube_channel_reports(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                video_count INTEGER NOT NULL,
                report_json TEXT NOT NULL
            );
            """
        )

        self.db.conn.commit()

    # ------------------------------------------------------------------
    # Project links
    # ------------------------------------------------------------------

    def link_project(
        self,
        *,
        video_id: str,
        project_id: str,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> dict[str, Any]:

        video_id = str(video_id).strip()
        project_id = str(project_id).strip()

        if not video_id:
            raise ValueError("video_id is required")

        if not project_id:
            raise ValueError("project_id is required")

        confidence = float(confidence)

        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                "confidence must be between 0 and 1"
            )

        now = self._now()

        self.db.conn.execute(
            """
            INSERT INTO youtube_project_links(
                video_id,
                project_id,
                link_source,
                confidence,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(video_id)
            DO UPDATE SET
                project_id=excluded.project_id,
                link_source=excluded.link_source,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (
                video_id,
                project_id,
                str(source),
                confidence,
                now,
                now,
            ),
        )

        self.db.conn.commit()

        return {
            "state": "YOUTUBE_PROJECT_LINK_READY",
            "video_id": video_id,
            "project_id": project_id,
            "confidence": confidence,
        }

    def project_for_video(
        self,
        video_id: str,
    ) -> str | None:

        row = self.db.conn.execute(
            """
            SELECT project_id
            FROM youtube_project_links
            WHERE video_id=?
            """,
            (
                str(video_id).strip(),
            ),
        ).fetchone()

        return (
            str(row[0])
            if row is not None
            else None
        )

    # ------------------------------------------------------------------
    # Ingest collector snapshot
    # ------------------------------------------------------------------

    def ingest_channel_snapshot(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:

        if (
            snapshot.get("state")
            != "YOUTUBE_CHANNEL_SNAPSHOT_READY"
        ):
            raise ValueError(
                "Invalid YouTube channel snapshot"
            )

        captured_at = str(
            snapshot.get("captured_at")
            or self._now()
        )

        inserted = 0
        pending = 0

        for item in (
            snapshot.get("videos")
            or []
        ):

            video_id = str(
                item.get("video_id", "")
            ).strip()

            if not video_id:
                continue

            project_id = (
                self.project_for_video(
                    video_id
                )
            )

            data_stats = (
                item.get(
                    "data_api_statistics"
                )
                or {}
            )

            analytics = (
                item.get(
                    "analytics"
                )
                or {}
            )

            analytics_state = str(
                item.get(
                    "analytics_state"
                )
                or "ANALYTICS_READY"
            )

            analytics_pending = (
                analytics_state
                == "ANALYTICS_PENDING"
            )

            if analytics_pending:
                pending += 1

            views = self._integer(
                data_stats.get("views")
                if analytics_pending
                else analytics.get(
                    "views",
                    data_stats.get("views"),
                )
            )

            likes = self._integer(
                data_stats.get("likes")
                if analytics_pending
                else analytics.get(
                    "likes",
                    data_stats.get("likes"),
                )
            )

            comments = self._integer(
                data_stats.get("comments")
                if analytics_pending
                else analytics.get(
                    "comments",
                    data_stats.get("comments"),
                )
            )

            shares = (
                None
                if analytics_pending
                else self._integer(
                    analytics.get("shares")
                )
            )

            estimated_minutes_watched = (
                None
                if analytics_pending
                else self._number(
                    analytics.get(
                        "estimatedMinutesWatched"
                    )
                )
            )

            average_view_duration_sec = (
                None
                if analytics_pending
                else self._number(
                    analytics.get(
                        "averageViewDuration"
                    )
                )
            )

            average_view_percentage = (
                None
                if analytics_pending
                else self._number(
                    analytics.get(
                        "averageViewPercentage"
                    )
                )
            )

            subscribers_gained = (
                None
                if analytics_pending
                else self._integer(
                    analytics.get(
                        "subscribersGained"
                    )
                )
            )

            subscribers_lost = (
                None
                if analytics_pending
                else self._integer(
                    analytics.get(
                        "subscribersLost"
                    )
                )
            )

            self.db.conn.execute(
                """
                INSERT INTO youtube_video_snapshots(
                    video_id,
                    project_id,
                    captured_at,
                    title,
                    published_at,
                    privacy_status,
                    analytics_state,
                    views,
                    likes,
                    comments,
                    shares,
                    estimated_minutes_watched,
                    average_view_duration_sec,
                    average_view_percentage,
                    subscribers_gained,
                    subscribers_lost,
                    payload_json
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    video_id,
                    project_id,
                    captured_at,

                    item.get("title"),
                    item.get("published_at"),
                    item.get("privacy_status"),
                    analytics_state,

                    views,
                    likes,
                    comments,
                    shares,

                    estimated_minutes_watched,
                    average_view_duration_sec,
                    average_view_percentage,

                    subscribers_gained,
                    subscribers_lost,

                    json.dumps(
                        item,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            )

            inserted += 1

        self.db.conn.commit()

        report = self.build_channel_report(
            captured_at=captured_at,
        )

        # Channel-level analytics discovered by Collector.
        report['channel_analytics'] = dict(
            snapshot.get('channel_analytics') or {}
        )

        report['channel_analytics_failures'] = list(
            snapshot.get('channel_analytics_failures') or []
        )

        report['channel_signals'] = (
            self._build_channel_signals(
                report['channel_analytics']
            )
        )

        self._save_report(report)
        self._update_learning(report)

        return {
            "state":
                "YOUTUBE_CHANNEL_INTELLIGENCE_UPDATED",

            "captured_at":
                captured_at,

            "video_snapshots_inserted":
                inserted,

            "analytics_pending":
                pending,

            "channel_report":
                report,
        }

    # ------------------------------------------------------------------
    # Latest snapshots
    # ------------------------------------------------------------------

    def latest_video_snapshots(
        self,
    ) -> list[dict[str, Any]]:

        cursor = self.db.conn.execute(
            """
            SELECT s.*
            FROM youtube_video_snapshots s

            INNER JOIN (
                SELECT
                    video_id,
                    MAX(id) AS max_id
                FROM youtube_video_snapshots
                GROUP BY video_id
            ) latest

            ON s.id = latest.max_id

            ORDER BY
                COALESCE(s.views, 0) DESC,
                s.video_id
            """
        )

        columns = [
            description[0]
            for description
            in cursor.description
        ]

        rows = cursor.fetchall()

        return [
            dict(
                zip(
                    columns,
                    row,
                )
            )
            for row in rows
        ]


    # ------------------------------------------------------------------
    # AZ_CHANNEL_SIGNALS_RC1
    # Derived channel-wide signals for Director / Learning.
    # ------------------------------------------------------------------

    @staticmethod
    def _build_channel_signals(
        analytics: dict[str, Any],
    ) -> dict[str, Any]:

        def integer(
            value: Any,
        ) -> int:

            try:
                return int(value or 0)
            except (
                TypeError,
                ValueError,
            ):
                return 0


        def number(
            value: Any,
        ) -> float:

            try:
                return float(value or 0)
            except (
                TypeError,
                ValueError,
            ):
                return 0.0


        traffic = list(
            analytics.get(
                "traffic_source"
            )
            or []
        )

        devices = list(
            analytics.get(
                "device_type"
            )
            or []
        )

        geography = list(
            analytics.get(
                "geography"
            )
            or []
        )

        subscribed = list(
            analytics.get(
                "subscribed_status"
            )
            or []
        )

        days = list(
            analytics.get(
                "day_timeseries"
            )
            or []
        )

        traffic_views = sum(
            integer(
                x.get("views")
            )
            for x in traffic
        )

        traffic_watch = sum(
            integer(
                x.get(
                    "estimatedMinutesWatched"
                )
            )
            for x in traffic
        )

        traffic_ranked = sorted(
            traffic,
            key=lambda x: integer(
                x.get(
                    "estimatedMinutesWatched"
                )
            ),
            reverse=True,
        )

        traffic_map = {
            str(
                x.get(
                    "insightTrafficSourceType"
                )
            ):
                x

            for x in traffic
        }

        def source_share(
            source: str,
            metric: str,
            total: int,
        ) -> float:

            item = (
                traffic_map.get(source)
                or {}
            )

            return (
                integer(
                    item.get(metric)
                )
                / total
                if total > 0
                else 0.0
            )


        subscribed_rows = {
            str(
                x.get(
                    "subscribedStatus"
                )
            ):
                x

            for x in subscribed
        }

        audience = {}

        for state in (
            "UNSUBSCRIBED",
            "SUBSCRIBED",
        ):

            row = (
                subscribed_rows.get(state)
                or {}
            )

            views = integer(
                row.get("views")
            )

            watch = integer(
                row.get(
                    "estimatedMinutesWatched"
                )
            )

            audience[state.lower()] = {
                "views":
                    views,

                "watch_minutes":
                    watch,

                "average_minutes_per_view":
                    (
                        watch / views
                        if views > 0
                        else 0.0
                    ),
            }


        device_ranked = sorted(
            devices,
            key=lambda x: integer(
                x.get(
                    "estimatedMinutesWatched"
                )
            ),
            reverse=True,
        )

        device_summary = []

        for row in device_ranked:

            views = integer(
                row.get("views")
            )

            watch = integer(
                row.get(
                    "estimatedMinutesWatched"
                )
            )

            device_summary.append({
                "device":
                    row.get("deviceType"),

                "views":
                    views,

                "watch_minutes":
                    watch,

                "average_minutes_per_view":
                    (
                        watch / views
                        if views > 0
                        else 0.0
                    ),
            })


        country_ranked = sorted(
            geography,
            key=lambda x: integer(
                x.get(
                    "estimatedMinutesWatched"
                )
            ),
            reverse=True,
        )


        day_ranked_views = sorted(
            days,
            key=lambda x:
                integer(
                    x.get("views")
                ),
            reverse=True,
        )

        day_ranked_subs = sorted(
            days,
            key=lambda x:
                (
                    integer(
                        x.get(
                            "subscribersGained"
                        )
                    )
                    - integer(
                        x.get(
                            "subscribersLost"
                        )
                    )
                ),
            reverse=True,
        )

        return {
            "traffic": {
                "total_views":
                    traffic_views,

                "total_watch_minutes":
                    traffic_watch,

                "top_by_watch":
                    (
                        traffic_ranked[0]
                        if traffic_ranked
                        else None
                    ),

                "related_video_view_share":
                    source_share(
                        "RELATED_VIDEO",
                        "views",
                        traffic_views,
                    ),

                "related_video_watch_share":
                    source_share(
                        "RELATED_VIDEO",
                        "estimatedMinutesWatched",
                        traffic_watch,
                    ),

                "shorts_view_share":
                    source_share(
                        "SHORTS",
                        "views",
                        traffic_views,
                    ),

                "shorts_watch_share":
                    source_share(
                        "SHORTS",
                        "estimatedMinutesWatched",
                        traffic_watch,
                    ),

                "youtube_search_view_share":
                    source_share(
                        "YT_SEARCH",
                        "views",
                        traffic_views,
                    ),
            },

            "audience_subscription":
                audience,

            "devices":
                device_summary,

            "top_countries_by_watch":
                country_ranked[:10],

            "daily": {
                "peak_view_day":
                    (
                        day_ranked_views[0]
                        if day_ranked_views
                        else None
                    ),

                "peak_subscriber_day":
                    (
                        day_ranked_subs[0]
                        if day_ranked_subs
                        else None
                    ),

                "days_observed":
                    len(days),
            },
        }


    # ------------------------------------------------------------------
    # Channel report
    # ------------------------------------------------------------------


    def _build_release_trajectories(
        self,
        *,
        captured_at: str | None = None,
    ) -> dict[str, Any]:
        """
        Build release-age-normalized trajectories from historical
        youtube_video_snapshots.

        RC2 integrity rules:
        - project mapping may be resolved from youtube_project_links
        - checkpoints use nearest observations inside explicit tolerances
        - stale observations are never carried into distant checkpoints
        - missing analytics remain missing
        """

        checkpoint_hours = (
            1,
            6,
            12,
            24,
            48,
            72,
            168,
        )

        checkpoint_tolerance_hours = {
            1: 1.0,
            6: 2.0,
            12: 3.0,
            24: 6.0,
            48: 8.0,
            72: 12.0,
            168: 24.0,
        }

        def parse_time(value: Any):
            if not value:
                return None

            text = str(value).strip()

            if not text:
                return None

            if text.endswith("Z"):
                text = text[:-1] + "+00:00"

            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        now = (
            parse_time(captured_at)
            or datetime.now(timezone.utc)
        )

        cursor = self.db.conn.execute(
            """
            SELECT
                video_id,
                project_id,
                captured_at,
                title,
                published_at,
                analytics_state,
                views,
                average_view_duration_sec,
                average_view_percentage,
                subscribers_gained,
                subscribers_lost
            FROM youtube_video_snapshots
            WHERE privacy_status IS NULL
               OR privacy_status='public'
            ORDER BY
                video_id,
                captured_at,
                id
            """
        )

        columns = [
            description[0]
            for description
            in cursor.description
        ]

        rows = [
            dict(
                zip(
                    columns,
                    row,
                )
            )
            for row in cursor.fetchall()
        ]

        grouped = {}

        for row in rows:

            video_id = str(
                row.get("video_id")
                or ""
            ).strip()

            if not video_id:
                continue

            grouped.setdefault(
                video_id,
                [],
            ).append(row)

        videos = []

        for video_id, history in grouped.items():

            history = sorted(
                history,
                key=lambda item:
                    parse_time(
                        item.get(
                            "captured_at"
                        )
                    )
                    or datetime.min.replace(
                        tzinfo=timezone.utc
                    ),
            )

            latest = history[-1]

            project_id = (
                latest.get(
                    "project_id"
                )
                or self.project_for_video(
                    video_id
                )
            )

            published = parse_time(
                latest.get(
                    "published_at"
                )
            )

            if published is None:

                for item in history:

                    published = parse_time(
                        item.get(
                            "published_at"
                        )
                    )

                    if published is not None:
                        break

            if published is None:

                videos.append({
                    "video_id":
                        video_id,

                    "project_id":
                        project_id,

                    "title":
                        latest.get(
                            "title"
                        ),

                    "state":
                        "PUBLISHED_AT_UNAVAILABLE",

                    "checkpoints":
                        {},
                })

                continue

            observations = []

            for item in history:

                observed = parse_time(
                    item.get(
                        "captured_at"
                    )
                )

                if observed is None:
                    continue

                age_hours = (
                    observed - published
                ).total_seconds() / 3600.0

                if age_hours < 0:
                    continue

                views = int(
                    item.get(
                        "views"
                    )
                    or 0
                )

                gained_raw = item.get(
                    "subscribers_gained"
                )

                lost_raw = item.get(
                    "subscribers_lost"
                )

                subscriber_metrics_available = (
                    gained_raw is not None
                    or lost_raw is not None
                )

                if subscriber_metrics_available:

                    gained = int(
                        gained_raw
                        or 0
                    )

                    lost = int(
                        lost_raw
                        or 0
                    )

                    net_subscribers = (
                        gained - lost
                    )

                    net_subscribers_per_1000 = (
                        net_subscribers
                        / views
                        * 1000.0
                        if views > 0
                        else None
                    )

                else:

                    net_subscribers = None

                    net_subscribers_per_1000 = None

                observations.append({
                    "captured_at":
                        observed.isoformat(),

                    "release_age_hours":
                        age_hours,

                    "views":
                        views,

                    "views_per_hour":
                        (
                            views / age_hours
                            if age_hours > 0
                            else None
                        ),

                    "average_view_duration_sec":
                        item.get(
                            "average_view_duration_sec"
                        ),

                    "average_view_percentage":
                        item.get(
                            "average_view_percentage"
                        ),

                    "net_subscribers":
                        net_subscribers,

                    "net_subscribers_per_1000":
                        net_subscribers_per_1000,

                    "subscriber_metrics_available":
                        subscriber_metrics_available,

                    "analytics_state":
                        item.get(
                            "analytics_state"
                        ),
                })

            checkpoints = {}

            checkpoint_quality = {}

            for checkpoint in checkpoint_hours:

                tolerance = (
                    checkpoint_tolerance_hours[
                        checkpoint
                    ]
                )

                eligible = [
                    item
                    for item in observations
                    if abs(
                        item[
                            "release_age_hours"
                        ]
                        - checkpoint
                    )
                    <= tolerance
                ]

                if not eligible:

                    checkpoints[
                        f"{checkpoint}h"
                    ] = None

                    checkpoint_quality[
                        f"{checkpoint}h"
                    ] = {
                        "state":
                            "NO_OBSERVATION_IN_WINDOW",

                        "target_hours":
                            checkpoint,

                        "tolerance_hours":
                            tolerance,
                    }

                    continue

                selected = min(
                    eligible,
                    key=lambda item:
                        abs(
                            item[
                                "release_age_hours"
                            ]
                            - checkpoint
                        ),
                )

                selected_copy = dict(
                    selected
                )

                selected_copy[
                    "checkpoint_target_hours"
                ] = checkpoint

                selected_copy[
                    "checkpoint_distance_hours"
                ] = abs(
                    selected[
                        "release_age_hours"
                    ]
                    - checkpoint
                )

                selected_copy[
                    "checkpoint_tolerance_hours"
                ] = tolerance

                checkpoints[
                    f"{checkpoint}h"
                ] = selected_copy

                checkpoint_quality[
                    f"{checkpoint}h"
                ] = {
                    "state":
                        "OBSERVATION_IN_WINDOW",

                    "target_hours":
                        checkpoint,

                    "source_age_hours":
                        selected[
                            "release_age_hours"
                        ],

                    "distance_hours":
                        abs(
                            selected[
                                "release_age_hours"
                            ]
                            - checkpoint
                        ),

                    "tolerance_hours":
                        tolerance,
                }

            velocity_windows = []

            for previous, current in zip(
                observations,
                observations[1:],
            ):

                delta_hours = (
                    current[
                        "release_age_hours"
                    ]
                    - previous[
                        "release_age_hours"
                    ]
                )

                delta_views = (
                    current[
                        "views"
                    ]
                    - previous[
                        "views"
                    ]
                )

                if delta_hours <= 0:
                    continue

                velocity_windows.append({
                    "start_age_hours":
                        previous[
                            "release_age_hours"
                        ],

                    "end_age_hours":
                        current[
                            "release_age_hours"
                        ],

                    "delta_hours":
                        delta_hours,

                    "delta_views":
                        delta_views,

                    "views_per_hour":
                        delta_views
                        / delta_hours,
                })

            latest_observation = (
                observations[-1]
                if observations
                else None
            )

            previous_velocity = (
                velocity_windows[-2][
                    "views_per_hour"
                ]
                if len(
                    velocity_windows
                ) >= 2
                else None
            )

            latest_velocity = (
                velocity_windows[-1][
                    "views_per_hour"
                ]
                if velocity_windows
                else None
            )

            acceleration_ratio = None

            if (
                previous_velocity
                not in (
                    None,
                    0,
                )
                and latest_velocity
                is not None
            ):

                acceleration_ratio = (
                    latest_velocity
                    / previous_velocity
                )

            release_age_now = max(
                0.0,
                (
                    now - published
                ).total_seconds()
                / 3600.0,
            )

            analytics_complete = bool(
                latest_observation
                and latest_observation.get(
                    "average_view_percentage"
                ) is not None
                and latest_observation.get(
                    "subscriber_metrics_available"
                )
            )

            videos.append({
                "video_id":
                    video_id,

                "project_id":
                    project_id,

                "title":
                    latest.get(
                        "title"
                    ),

                "published_at":
                    published.isoformat(),

                "release_age_hours":
                    release_age_now,

                "observation_count":
                    len(
                        observations
                    ),

                "state":
                    (
                        "TRAJECTORY_READY"
                        if observations
                        else
                        "INSUFFICIENT_DATA"
                    ),

                "analytics_complete":
                    analytics_complete,

                "latest":
                    latest_observation,

                "checkpoints":
                    checkpoints,

                "checkpoint_quality":
                    checkpoint_quality,

                "velocity_windows":
                    velocity_windows,

                "latest_velocity_views_per_hour":
                    latest_velocity,

                "acceleration_ratio":
                    acceleration_ratio,
            })

        ready = [
            item
            for item in videos
            if item.get(
                "state"
            )
            == "TRAJECTORY_READY"
        ]

        analytics_complete = [
            item
            for item in ready
            if item.get(
                "analytics_complete"
            )
        ]

        return {
            "schema":
                "atlas_zero.youtube_release_trajectory.rc2",

            "captured_at":
                now.isoformat(),

            "checkpoint_hours":
                list(
                    checkpoint_hours
                ),

            "checkpoint_tolerance_hours":
                checkpoint_tolerance_hours,

            "video_count":
                len(
                    videos
                ),

            "trajectory_ready_count":
                len(
                    ready
                ),

            "analytics_complete_count":
                len(
                    analytics_complete
                ),

            "videos":
                videos,
        }


    def build_channel_report(
        self,
        *,
        captured_at: str | None = None,
    ) -> dict[str, Any]:

        videos = (
            self.latest_video_snapshots()
        )

        release_trajectories = (
            self._build_release_trajectories(
                captured_at=captured_at,
            )
        )

        public_videos = [
            item
            for item in videos
            if item.get(
                "privacy_status"
            ) in (
                None,
                "public",
            )
        ]

        analytics_ready = [
            item
            for item in public_videos
            if item.get(
                "analytics_state"
            ) != "ANALYTICS_PENDING"
        ]

        views = [
            int(item["views"])
            for item in public_videos
            if item.get("views") is not None
        ]

        avg_duration = [
            float(
                item[
                    "average_view_duration_sec"
                ]
            )
            for item in analytics_ready
            if item.get(
                "average_view_duration_sec"
            ) is not None
        ]

        avg_percentage = [
            float(
                item[
                    "average_view_percentage"
                ]
            )
            for item in analytics_ready
            if item.get(
                "average_view_percentage"
            ) is not None
        ]

        subscriber_net = []

        for item in analytics_ready:

            gained = int(
                item.get(
                    "subscribers_gained"
                )
                or 0
            )

            lost = int(
                item.get(
                    "subscribers_lost"
                )
                or 0
            )

            subscriber_net.append(
                gained - lost
            )

        baseline = {
            "mean_views":
                mean(views)
                if views
                else 0.0,

            "median_views":
                median(views)
                if views
                else 0.0,

            "mean_average_view_duration_sec":
                mean(avg_duration)
                if avg_duration
                else None,

            "mean_average_view_percentage":
                mean(avg_percentage)
                if avg_percentage
                else None,

            "mean_subscriber_net":
                mean(subscriber_net)
                if subscriber_net
                else None,
        }

        ranked = []

        for item in public_videos:

            item_views = float(
                item.get("views")
                or 0
            )

            view_index = (
                item_views
                / baseline["mean_views"]
                if baseline["mean_views"] > 0
                else 0.0
            )

            analytics_pending = (
                item.get(
                    "analytics_state"
                )
                == "ANALYTICS_PENDING"
            )

            avp = (
                None
                if analytics_pending
                else item.get(
                    "average_view_percentage"
                )
            )

            if (
                avp is not None
                and baseline[
                    "mean_average_view_percentage"
                ] not in (
                    None,
                    0,
                )
            ):
                retention_index = (
                    float(avp)
                    / float(
                        baseline[
                            "mean_average_view_percentage"
                        ]
                    )
                )
            else:
                retention_index = None

            if analytics_pending:

                performance_score = (
                    view_index
                )

                score_mode = (
                    "views_only_pending_analytics"
                )

                net_subscribers = None

            else:

                gained = int(
                    item.get(
                        "subscribers_gained"
                    )
                    or 0
                )

                lost = int(
                    item.get(
                        "subscribers_lost"
                    )
                    or 0
                )

                net_subscribers = (
                    gained - lost
                )

                subscriber_component = 0.0

                mean_subscriber_net = (
                    baseline.get(
                        "mean_subscriber_net"
                    )
                )

                if (
                    mean_subscriber_net
                    not in (
                        None,
                        0,
                    )
                ):
                    subscriber_component = (
                        max(
                            0.0,
                            float(
                                net_subscribers
                            ),
                        )
                        / max(
                            1.0,
                            float(
                                mean_subscriber_net
                            ),
                        )
                    )

                performance_score = (
                    view_index * 0.50
                    + (
                        retention_index
                        or 0.0
                    )
                    * 0.35
                    + subscriber_component
                    * 0.15
                )

                score_mode = (
                    "full_analytics"
                )

            ranked.append({
                "video_id":
                    item["video_id"],

                "project_id":
                    item.get(
                        "project_id"
                    ),

                "title":
                    item.get("title"),

                "analytics_state":
                    item.get(
                        "analytics_state"
                    ),

                "views":
                    int(
                        item.get("views")
                        or 0
                    ),

                "average_view_duration_sec":
                    item.get(
                        "average_view_duration_sec"
                    ),

                "average_view_percentage":
                    item.get(
                        "average_view_percentage"
                    ),

                "subscriber_net":
                    net_subscribers,

                "view_index":
                    view_index,

                "retention_index":
                    retention_index,

                "performance_score":
                    performance_score,

                "score_mode":
                    score_mode,
            })

        ranked.sort(
            key=lambda item:
                item[
                    "performance_score"
                ],
            reverse=True,
        )

        for index, item in enumerate(
            ranked,
            1,
        ):
            item["rank"] = index

        return {
            "schema":
                "atlas_zero.youtube_channel_intelligence.rc1",

            "state":
                "YOUTUBE_CHANNEL_REPORT_READY",

            "captured_at":
                captured_at
                or self._now(),

            "video_count":
                len(public_videos),

            "analytics_ready_count":
                len(analytics_ready),

            "analytics_pending_count":
                len(
                    public_videos
                )
                - len(
                    analytics_ready
                ),

            "linked_project_count":
                sum(
                    1
                    for item
                    in public_videos
                    if item.get(
                        "project_id"
                    )
                ),

            "baseline":
                baseline,

            "release_trajectories":
                release_trajectories,

            "ranking":
                ranked,

            "top_video":
                ranked[0]
                if ranked
                else None,

            "learning_scope":
                self.CHANNEL_LEARNING_PROJECT,
        }

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    def _update_learning(
        self,
        report: dict[str, Any],
    ) -> None:

        learning = LearningCoreRC1(
            db=self.db,
            project_id=
                self.CHANNEL_LEARNING_PROJECT,
        )

        baseline = (
            report.get("baseline")
            or {}
        )

        evidence = {
            "source":
                "youtube_channel_intelligence",

            "captured_at":
                report.get(
                    "captured_at"
                ),

            "video_count":
                report.get(
                    "video_count"
                ),

            "analytics_ready_count":
                report.get(
                    "analytics_ready_count"
                ),

            "analytics_pending_count":
                report.get(
                    "analytics_pending_count"
                ),
        }

        confidence = self._confidence(
            report.get(
                "analytics_ready_count",
                0,
            )
        )

        learning.record_observation(
            scope="youtube:channel",
            key="mean_views",
            value=float(
                baseline.get(
                    "mean_views"
                )
                or 0.0
            ),
            confidence=confidence,
            evidence=evidence,
        )

        mean_avp = baseline.get(
            "mean_average_view_percentage"
        )

        if mean_avp is not None:

            learning.record_observation(
                scope="youtube:channel",
                key="mean_average_view_percentage",
                value=float(mean_avp),
                confidence=confidence,
                evidence=evidence,
            )

        ready_ranking = [
            item
            for item in (
                report.get("ranking")
                or []
            )
            if item.get(
                "analytics_state"
            ) != "ANALYTICS_PENDING"
        ]

        if ready_ranking:

            best_ready = max(
                ready_ranking,
                key=lambda item:
                    item[
                        "performance_score"
                    ],
            )

            learning.record_observation(
                scope="youtube:channel",
                key="best_performing_video",
                value={
                    "video_id":
                        best_ready.get(
                            "video_id"
                        ),

                    "project_id":
                        best_ready.get(
                            "project_id"
                        ),

                    "title":
                        best_ready.get(
                            "title"
                        ),

                    "performance_score":
                        best_ready.get(
                            "performance_score"
                        ),
                },
                confidence=confidence,
                evidence=evidence,
            )

    # ------------------------------------------------------------------

    def _save_report(
        self,
        report: dict[str, Any],
    ) -> None:

        self.db.conn.execute(
            """
            INSERT INTO youtube_channel_reports(
                captured_at,
                video_count,
                report_json
            )
            VALUES (?, ?, ?)
            """,
            (
                report["captured_at"],
                int(
                    report["video_count"]
                ),
                json.dumps(
                    report,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )

        self.db.conn.commit()

    @staticmethod
    def _confidence(
        video_count: int,
    ) -> float:

        count = max(
            0,
            int(video_count),
        )

        return min(
            0.95,
            0.40 + count * 0.08,
        )

    @staticmethod
    def _integer(
        value: Any,
    ) -> int | None:

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:

        if value is None:
            return None

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _now() -> str:

        return datetime.now(
            timezone.utc
        ).isoformat()
