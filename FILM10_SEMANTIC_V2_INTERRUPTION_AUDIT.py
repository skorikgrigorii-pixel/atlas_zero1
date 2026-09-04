from pathlib import Path
import json
import os
import sqlite3
import traceback

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

OUT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "semantic_analysis_v2"
)

CHECKPOINT = OUT / "visual_semantic_checkpoint_v2.json"
PARTIAL    = OUT / "visual_semantic_report_v2.partial.json"
FINAL      = OUT / "visual_semantic_report_v2.json"
SUMMARY    = OUT / "FILM10_SEMANTIC_REANALYSIS_V2_SUMMARY.json"
COMPARE    = OUT / "FILM10_SEMANTIC_V1_V2_COMPARISON.json"

DB_PATH = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"

print("=" * 120)
print("ATLAS ZERO — FILM10 SEMANTIC V2 INTERRUPTION AUDIT")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("MODE       : READ ONLY")
print()

for name, path in [
    ("CHECKPOINT", CHECKPOINT),
    ("PARTIAL", PARTIAL),
    ("FINAL", FINAL),
    ("SUMMARY", SUMMARY),
    ("COMPARE", COMPARE),
]:
    print(f"{name:<12}: {'EXISTS' if path.is_file() else 'MISSING'} | {path}")

def load_json(path):
    if not path.is_file():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8-sig",
                errors="replace",
            )
        )
    except Exception as exc:
        print()
        print("JSON READ ERROR:", path)
        print(type(exc).__name__, str(exc))
        return None

checkpoint = load_json(CHECKPOINT)
partial = load_json(PARTIAL)
final = load_json(FINAL)

print()
print("=" * 120)
print("CHECKPOINT")
print("=" * 120)

if checkpoint is None:
    print("NO CHECKPOINT DATA")
else:
    print("TYPE:", type(checkpoint).__name__)

    if isinstance(checkpoint, dict):
        print("KEYS:", sorted(checkpoint.keys()))

        for key in (
            "saved",
            "failed",
            "processed",
            "completed",
            "current_index",
            "total",
            "status",
        ):
            if key in checkpoint:
                print(f"{key:<20}: {checkpoint[key]}")

        for candidate_key in (
            "results",
            "items",
            "completed_assets",
            "assets",
        ):
            value = checkpoint.get(candidate_key)

            if isinstance(value, list):
                print(
                    f"{candidate_key:<20}: {len(value)} records"
                )

                if value:
                    print()
                    print("LAST 5 CHECKPOINT RECORDS:")

                    for item in value[-5:]:
                        if isinstance(item, dict):
                            print(
                                "  asset_id=",
                                item.get("asset_id"),
                                "| filename=",
                                item.get("filename"),
                                "| event=",
                                item.get("event_type"),
                                "| relevance=",
                                item.get("relevance_status"),
                            )
                        else:
                            print(" ", item)

    elif isinstance(checkpoint, list):
        print("RECORDS:", len(checkpoint))

        print()
        print("LAST 5 CHECKPOINT RECORDS:")

        for item in checkpoint[-5:]:
            print(item)

print()
print("=" * 120)
print("PARTIAL REPORT")
print("=" * 120)

if partial is None:
    print("NO PARTIAL REPORT DATA")
else:
    print("TYPE:", type(partial).__name__)

    if isinstance(partial, dict):
        print("KEYS:", sorted(partial.keys()))

        results = partial.get("results")

        if isinstance(results, list):
            print("RESULTS:", len(results))

            if results:
                print()
                print("LAST 5 PARTIAL RESULTS:")

                for item in results[-5:]:
                    print(
                        "  {:<70} | event={:<18} | relevance={}".format(
                            str(item.get("filename"))[:70],
                            str(item.get("event_type")),
                            str(item.get("relevance_status")),
                        )
                    )

        failures = partial.get("failures")

        if isinstance(failures, list):
            print("FAILURES:", len(failures))

            if failures:
                print()
                print("FAILURE DETAILS:")

                for item in failures[-10:]:
                    print(json.dumps(
                        item,
                        ensure_ascii=False,
                        indent=2,
                    ))

print()
print("=" * 120)
print("FINAL REPORT")
print("=" * 120)

if final is None:
    print("FINAL REPORT NOT WRITTEN")
else:
    print("FINAL REPORT EXISTS")

    if isinstance(final, dict):
        results = final.get("results", [])
        failures = final.get("failures", [])

        print(
            "RESULTS :",
            len(results) if isinstance(results, list) else "N/A",
        )

        print(
            "FAILURES:",
            len(failures) if isinstance(failures, list) else "N/A",
        )

print()
print("=" * 120)
print("CANONICAL DB CURRENT SEMANTIC STATE")
print("=" * 120)

if DB_PATH.is_file():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            """
            SELECT
                filename,
                semantic_class,
                semantic_confidence
            FROM assets
            WHERE project_id=?
            ORDER BY filename
            """,
            (PROJECT_ID,),
        ).fetchall()
    finally:
        conn.close()

    print("ASSETS:", len(rows))

    classified = [
        row
        for row in rows
        if str(row["semantic_class"] or "").strip()
    ]

    print("WITH SEMANTIC CLASS:", len(classified))

    print()
    print("FIRST 25 CURRENT DB CLASSES:")

    for row in rows[:25]:
        print(
            "  {:<75} => {:<20} conf={}".format(
                str(row["filename"])[:75],
                str(row["semantic_class"]),
                row["semantic_confidence"],
            )
        )

else:
    print("DATABASE MISSING")

print()
print("=" * 120)
print("PROCESS STATUS")
print("=" * 120)

print("No Python process is running now.")
print("No restart performed.")
print("No render performed.")
print("No assignments written.")
print("No API calls made.")
