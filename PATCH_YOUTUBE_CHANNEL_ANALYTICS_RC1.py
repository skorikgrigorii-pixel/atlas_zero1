from pathlib import Path
from datetime import datetime
import ast
import shutil
import re

ROOT = Path.cwd()

COLLECTOR = ROOT / "src/az_enterprise/core/youtube_channel_collector_rc1.py"
INTEL = ROOT / "src/az_enterprise/core/youtube_channel_intelligence_rc1.py"

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

for path in (COLLECTOR, INTEL):
    if not path.exists():
        raise FileNotFoundError(path)

    backup = path.with_name(
        path.name + f".before_channel_analytics_{stamp}.bak"
    )
    shutil.copy2(path, backup)
    print("BACKUP:", backup)

# ======================================================================
# COLLECTOR
# ======================================================================

text = COLLECTOR.read_text(encoding="utf-8-sig")

COLLECTOR_MARKER = "AZ_CHANNEL_ANALYTICS_RC1"

if COLLECTOR_MARKER not in text:

    anchor = """    # ------------------------------------------------------------------
    # Full channel collection
    # ------------------------------------------------------------------
"""

    if anchor not in text:
        raise RuntimeError(
            "Collector anchor not found. No changes applied."
        )

    method = r'''
    # ------------------------------------------------------------------
    # AZ_CHANNEL_ANALYTICS_RC1
    # Channel-level Analytics API breakdowns
    # ------------------------------------------------------------------

    @staticmethod
    def _analytics_rows(
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:

        columns = [
            str(
                column.get(
                    "name",
                    "",
                )
            )
            for column in (
                payload.get(
                    "columnHeaders"
                )
                or []
            )
        ]

        result = []

        for row in (
            payload.get("rows")
            or []
        ):

            result.append({
                columns[index]:
                    row[index]

                for index
                in range(
                    min(
                        len(columns),
                        len(row),
                    )
                )
            })

        return result


    def fetch_channel_analytics(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> tuple[
        dict[str, Any],
        list[dict[str, str]],
    ]:

        specs = {
            "traffic_source": {
                "metrics":
                    "views,estimatedMinutesWatched",
                "dimensions":
                    "insightTrafficSourceType",
            },

            "device_type": {
                "metrics":
                    "views,estimatedMinutesWatched",
                "dimensions":
                    "deviceType",
            },

            "geography": {
                "metrics":
                    "views,estimatedMinutesWatched",
                "dimensions":
                    "country",
            },

            "subscribed_status": {
                "metrics":
                    "views,estimatedMinutesWatched",
                "dimensions":
                    "subscribedStatus",
            },

            "day_timeseries": {
                "metrics": (
                    "views,"
                    "estimatedMinutesWatched,"
                    "subscribersGained,"
                    "subscribersLost"
                ),
                "dimensions":
                    "day",
            },
        }

        result = {}
        failures = []

        for name, spec in specs.items():

            try:

                payload = (
                    self.connector
                    .analytics_report(
                        start_date=start_date,
                        end_date=end_date,
                        metrics=spec["metrics"],
                        dimensions=
                            spec["dimensions"],
                    )
                )

                result[name] = (
                    self._analytics_rows(
                        payload
                    )
                )

            except Exception as exc:

                result[name] = []

                failures.append({
                    "breakdown":
                        name,

                    "error":
                        str(exc),
                })

        return (
            result,
            failures,
        )


'''

    text = text.replace(
        anchor,
        method + anchor,
        1,
    )

    # Insert collection call after analytics_failures initialization.
    old = """        analytics_failures = []

        for video_id in video_ids:
"""

    new = """        analytics_failures = []

        (
            channel_analytics,
            channel_analytics_failures,
        ) = self.fetch_channel_analytics(
            start_date=start_date,
            end_date=end_date,
        )

        for video_id in video_ids:
"""

    if old not in text:
        raise RuntimeError(
            "Collector analytics_failures anchor not found."
        )

    text = text.replace(
        old,
        new,
        1,
    )

    # Add fields to snapshot.
    old = """            "analytics_failures":
                analytics_failures,
        }
"""

    new = """            "analytics_failures":
                analytics_failures,

            "channel_analytics":
                channel_analytics,

            "channel_analytics_failures":
                channel_analytics_failures,
        }
"""

    if old not in text:
        raise RuntimeError(
            "Collector result anchor not found."
        )

    text = text.replace(
        old,
        new,
        1,
    )

    COLLECTOR.write_text(
        text,
        encoding="utf-8",
    )

    print("PATCHED:", COLLECTOR)

else:
    print("ALREADY PATCHED:", COLLECTOR)


# ======================================================================
# INTELLIGENCE
# ======================================================================

text = INTEL.read_text(encoding="utf-8-sig")

INTEL_MARKER = "AZ_CHANNEL_SIGNALS_RC1"

if INTEL_MARKER not in text:

    anchor = """    # ------------------------------------------------------------------
    # Channel report
    # ------------------------------------------------------------------
"""

    if anchor not in text:
        raise RuntimeError(
            "Intelligence channel report anchor not found."
        )

    helper = r'''
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


'''

    text = text.replace(
        anchor,
        helper + anchor,
        1,
    )

    # Parse source and find build_channel_report() call inside
    # ingest_channel_snapshot. Inject enrichment immediately after
    # its assignment, before save/report/learning code.
    tree = ast.parse(text)

    ingest = None

    for node in ast.walk(tree):
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == "ingest_channel_snapshot"
        ):
            ingest = node
            break

    if ingest is None:
        raise RuntimeError(
            "ingest_channel_snapshot not found."
        )

    target_assign = None
    target_var = None

    for node in ast.walk(ingest):

        if not isinstance(
            node,
            (
                ast.Assign,
                ast.AnnAssign,
            ),
        ):
            continue

        value = node.value

        if not isinstance(
            value,
            ast.Call,
        ):
            continue

        func = value.func

        if (
            isinstance(
                func,
                ast.Attribute,
            )
            and func.attr
            == "build_channel_report"
        ):
            target_assign = node

            if isinstance(
                node,
                ast.Assign,
            ):
                target = (
                    node.targets[0]
                )
            else:
                target = node.target

            if isinstance(
                target,
                ast.Name,
            ):
                target_var = (
                    target.id
                )

            break

    if (
        target_assign is None
        or target_var is None
    ):
        raise RuntimeError(
            "Could not resolve build_channel_report assignment "
            "inside ingest_channel_snapshot."
        )

    lines = text.splitlines()

    insert_at = (
        target_assign.end_lineno
    )

    indent = " " * 8

    injection = [
        "",
        indent
        + "# Channel-level analytics discovered by Collector.",
        indent
        + f"{target_var}['channel_analytics'] = dict(",
        indent
        + "    snapshot.get('channel_analytics') or {}",
        indent
        + ")",
        "",
        indent
        + f"{target_var}['channel_analytics_failures'] = list(",
        indent
        + "    snapshot.get('channel_analytics_failures') or []",
        indent
        + ")",
        "",
        indent
        + f"{target_var}['channel_signals'] = (",
        indent
        + "    self._build_channel_signals(",
        indent
        + f"        {target_var}['channel_analytics']",
        indent
        + "    )",
        indent
        + ")",
    ]

    lines[
        insert_at:insert_at
    ] = injection

    text = "\n".join(lines) + "\n"

    # Syntax validation before writing.
    ast.parse(text)

    INTEL.write_text(
        text,
        encoding="utf-8",
    )

    print("PATCHED:", INTEL)

else:
    print("ALREADY PATCHED:", INTEL)


# ======================================================================
# FINAL STATIC VALIDATION
# ======================================================================

for path in (
    COLLECTOR,
    INTEL,
):
    source = path.read_text(
        encoding="utf-8-sig"
    )

    ast.parse(source)

    print(
        "SYNTAX OK:",
        path,
    )

print()
print("=" * 78)
print("YOUTUBE CHANNEL ANALYTICS PATCH COMPLETE")
print("=" * 78)
