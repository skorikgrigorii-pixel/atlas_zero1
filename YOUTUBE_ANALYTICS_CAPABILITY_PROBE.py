from inspect import signature
import json

import src.az_enterprise.core.youtube_channel_runtime_rc1 as ytr
from src.az_enterprise.core.youtube_channel_collector_rc1 import (
    YouTubeChannelCollectorRC1,
)

START = "2026-06-01"
END   = "2026-08-25"

print("=" * 100)
print("ATLAS ZERO — YOUTUBE ANALYTICS CAPABILITY PROBE V2")
print("=" * 100)

# ------------------------------------------------------------------
# 1. CURRENT PRODUCTION METRICS
# ------------------------------------------------------------------

print("\n===== CURRENT COLLECTOR METRICS =====")
print(YouTubeChannelCollectorRC1.ANALYTICS_METRICS)

# ------------------------------------------------------------------
# 2. INITIALIZE EXACTLY LIKE THE CANONICAL CLI
# ------------------------------------------------------------------

db = ytr.Database()
db.init()

runtime = ytr.YouTubeChannelRuntimeRC1(
    db=db,
)

connector = runtime._build_live_connector()

print("\n===== CONNECTOR =====")
print("analytics_report signature:")
print(signature(connector.analytics_report))

print("\ncredential status:")
print(
    json.dumps(
        connector.credential_status(),
        ensure_ascii=False,
        indent=2,
    )
)

# ------------------------------------------------------------------
# 3. AUTHENTICATED CHANNEL
#
# Use the already initialized canonical collector from Runtime.
# ------------------------------------------------------------------

channel = runtime.collector.discover_channel()

channel_id = channel["channel_id"]

print("\n===== AUTHENTICATED CHANNEL =====")
print("channel_id :", channel_id)
print("title      :", channel.get("title"))

# ------------------------------------------------------------------
# 4. ADAPT TO THE REAL analytics_report SIGNATURE
# ------------------------------------------------------------------

sig = signature(connector.analytics_report)
params = set(sig.parameters.keys())

print("\nanalytics_report params:")
print(sorted(params))

def analytics_query(
    *,
    metrics,
    dimensions=None,
    filters=None,
):
    kwargs = {}

    candidates = {
        "channel_id": channel_id,
        "ids": f"channel=={channel_id}",
        "start_date": START,
        "end_date": END,
        "metrics": metrics,
        "dimensions": dimensions,
        "filters": filters,
    }

    for key, value in candidates.items():
        if key in params and value is not None:
            kwargs[key] = value

    print("CALL KWARGS:", kwargs)

    return connector.analytics_report(
        **kwargs
    )

# ------------------------------------------------------------------
# 5. LIVE CAPABILITY TESTS
# ------------------------------------------------------------------

tests = [
    {
        "name": "BASELINE_CHANNEL",
        "metrics": (
            "views,"
            "estimatedMinutesWatched,"
            "averageViewDuration,"
            "averageViewPercentage,"
            "likes,"
            "comments,"
            "shares,"
            "subscribersGained,"
            "subscribersLost"
        ),
    },

    {
        "name": "THUMBNAIL_IMPRESSIONS_CTR",
        "metrics": (
            "videoThumbnailImpressions,"
            "videoThumbnailImpressionsClickRate"
        ),
    },

    {
        "name": "TRAFFIC_SOURCE",
        "metrics": (
            "views,"
            "estimatedMinutesWatched"
        ),
        "dimensions": "insightTrafficSourceType",
    },

    {
        "name": "VIDEOS",
        "metrics": (
            "views,"
            "estimatedMinutesWatched,"
            "averageViewDuration,"
            "averageViewPercentage,"
            "subscribersGained,"
            "subscribersLost"
        ),
        "dimensions": "video",
    },

    {
        "name": "DEVICE_TYPE",
        "metrics": (
            "views,"
            "estimatedMinutesWatched"
        ),
        "dimensions": "deviceType",
    },

    {
        "name": "GEOGRAPHY",
        "metrics": (
            "views,"
            "estimatedMinutesWatched"
        ),
        "dimensions": "country",
    },

    {
        "name": "SUBSCRIBED_STATUS",
        "metrics": (
            "views,"
            "estimatedMinutesWatched"
        ),
        "dimensions": "subscribedStatus",
    },

    {
        "name": "DAY_TIMESERIES",
        "metrics": (
            "views,"
            "estimatedMinutesWatched,"
            "subscribersGained,"
            "subscribersLost"
        ),
        "dimensions": "day",
    },
]

results = {}

print("\n" + "=" * 100)
print("LIVE ANALYTICS PROBES")
print("=" * 100)

for test in tests:

    name = test["name"]

    print("\n" + "-" * 100)
    print(name)
    print("-" * 100)

    try:
        response = analytics_query(
            metrics=test["metrics"],
            dimensions=test.get("dimensions"),
            filters=test.get("filters"),
        )

        results[name] = {
            "supported": True,
            "response": response,
        }

        print("SUPPORTED: YES")

        if isinstance(response, dict):

            print("keys:", list(response.keys()))

            headers = response.get(
                "columnHeaders"
            )

            rows = response.get("rows")

            if headers:
                print("headers:")
                for h in headers:
                    print(" ", h)

            if rows is not None:
                print(
                    "row_count:",
                    len(rows)
                )

                print("first_rows:")

                for row in rows[:10]:
                    print(" ", row)

        else:
            print(str(response)[:2000])

    except Exception as exc:

        results[name] = {
            "supported": False,
            "error_type":
                type(exc).__name__,
            "error":
                str(exc),
        }

        print("SUPPORTED: NO")
        print(
            type(exc).__name__,
            str(exc)[:2000]
        )

# ------------------------------------------------------------------
# 6. SUMMARY
# ------------------------------------------------------------------

print("\n" + "=" * 100)
print("CAPABILITY SUMMARY")
print("=" * 100)

for name, result in results.items():
    print(
        f"{name:30} : "
        f"{'YES' if result['supported'] else 'NO'}"
    )

print("=" * 100)

