from __future__ import annotations

from pathlib import Path
from collections import Counter
import json
import os
import sqlite3
import sys
import traceback


ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

DB_PATH = (
    ROOT
    / "workspace"
    / "atlas_zero_enterprise.sqlite3"
)

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

OUT = (
    PROJECT
    / "00_Production"
    / "semantic_analysis_v2"
)

OUT.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================================
# SAFETY
# ============================================================================

os.environ["AZ_ENABLE_LIVE_API"] = "0"
os.environ["AZ_ALLOW_PAID_CALLS"] = "0"
os.environ["ATLAS_ZERO_SEMANTIC_RESET"] = "1"

os.environ[
    "ATLAS_ZERO_SEMANTIC_CHECKPOINT_PATH"
] = str(
    OUT / "visual_semantic_checkpoint_v2.json"
)

os.environ[
    "ATLAS_ZERO_SEMANTIC_PARTIAL_REPORT_PATH"
] = str(
    OUT / "visual_semantic_report_v2.partial.json"
)

os.environ[
    "ATLAS_ZERO_SEMANTIC_REPORT_PATH"
] = str(
    OUT / "visual_semantic_report_v2.json"
)


print("=" * 120)
print("ATLAS ZERO — FILM10 SEMANTIC REANALYSIS V2")
print("=" * 120)

print("ROOT       :", ROOT)
print("PROJECT    :", PROJECT_ID)
print("DATABASE   :", DB_PATH)
print("LIVE API   :", os.environ["AZ_ENABLE_LIVE_API"])
print("PAID CALLS :", os.environ["AZ_ALLOW_PAID_CALLS"])
print("RENDER     : NO")
print("ASSIGNMENT : NO")


if not DB_PATH.is_file():
    raise FileNotFoundError(DB_PATH)


# ============================================================================
# IMPORT EXISTING OS
# ============================================================================

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from az_enterprise.core.database import Database

from az_enterprise.core.project_semantic_context_rc2 import (
    ProjectSemanticContextBuilderRC2,
)

from az_enterprise.core.visual_semantic_analyzer_rc2 import (
    VisualSemanticAnalyzerRC2,
)


# ============================================================================
# VERIFY NEW PROJECT SEMANTIC CONTEXT
# ============================================================================

print()
print("=" * 120)
print("SEMANTIC CONTEXT PREFLIGHT")
print("=" * 120)


context = ProjectSemanticContextBuilderRC2(
    project_id=PROJECT_ID,
    root_dir=ROOT,
).build()


scene_labels = [
    key
    for key in context.event_labels
    if key.startswith("scene_")
]


print("TITLE        :", context.title)
print("SOURCE       :", context.source_path)
print("EVENT LABELS :", len(context.event_labels))
print("SCENE LABELS :", len(scene_labels))
print("CONCEPTS     :", len(context.concepts))


if context.source_path != "canonical_db:story_scenes":
    raise RuntimeError(
        "Canonical story semantic context is not active."
    )


if len(scene_labels) != 86:
    raise RuntimeError(
        "Expected 86 canonical semantic scene labels; "
        f"found {len(scene_labels)}"
    )


if "documentary_context" in context.event_labels:
    raise RuntimeError(
        "Generic fallback semantic context is active."
    )


print("CONTEXT GATE : PASS")


# ============================================================================
# LOAD PREVIOUS V1 RESULT BEFORE NEW ANALYSIS
# ============================================================================

old_report_candidates = [
    OUT.parent
    / "semantic_analysis_v1"
    / "FILM10_SEMANTIC_ANALYSIS_REPORT_V1.json",

    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "rc2"
    / "story"
    / "visual_semantic_report.json",
]


old_report = None
old_report_path = None


for candidate in old_report_candidates:

    if not candidate.is_file():
        continue

    try:
        payload = json.loads(
            candidate.read_text(
                encoding="utf-8-sig",
                errors="replace",
            )
        )

    except Exception:
        continue

    # We prefer a report containing individual results.
    if isinstance(payload, dict):
        if isinstance(
            payload.get("results"),
            list,
        ):
            old_report = payload
            old_report_path = candidate
            break


print()
print("=" * 120)
print("V1 BASELINE")
print("=" * 120)

if old_report is None:

    print(
        "Detailed V1 result report not found."
    )

    print(
        "Comparison will use known V1 baseline: "
        "60/60 documentary_context."
    )

    old_results = []

else:

    old_results = old_report.get(
        "results",
        []
    )

    print(
        "V1 REPORT:",
        old_report_path,
    )

    print(
        "V1 RESULTS:",
        len(old_results),
    )

    # Preserve exact old report before V2.
    baseline_copy = (
        OUT
        / "FILM10_SEMANTIC_BASELINE_V1.json"
    )

    baseline_copy.write_text(
        json.dumps(
            old_report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "BASELINE COPY:",
        baseline_copy,
    )


old_by_id = {
    str(item.get("asset_id")):
        item
    for item in old_results
    if item.get("asset_id")
}


# ============================================================================
# LOAD EXACT CANONICAL 60 ASSETS
# ============================================================================

conn = sqlite3.connect(
    str(DB_PATH)
)

conn.row_factory = sqlite3.Row

try:

    asset_rows = conn.execute(
        """
        SELECT
            id,
            filename,
            path,
            media_type,
            sha256,
            duplicate_of,
            semantic_class,
            semantic_description,
            semantic_confidence
        FROM assets
        WHERE project_id=?
        ORDER BY filename
        """,
        (PROJECT_ID,),
    ).fetchall()

finally:
    conn.close()


print()
print("=" * 120)
print("CANONICAL ASSETS")
print("=" * 120)

print(
    "ASSETS:",
    len(asset_rows),
)


if len(asset_rows) != 60:
    raise RuntimeError(
        "Expected 60 Film10 assets, found "
        + str(len(asset_rows))
    )


asset_ids = [
    str(row["id"])
    for row in asset_rows
]


# ============================================================================
# RUN EXISTING ANALYZER
# ============================================================================

print()
print("=" * 120)
print("RUNNING VisualSemanticAnalyzerRC2 — V2 CONTEXT")
print("=" * 120)

print(
    "This should reanalyse all 60 assets."
)

print(
    "Existing local HuggingFace CLIP backend only."
)


db = Database(DB_PATH)


analyzer = VisualSemanticAnalyzerRC2(
    db,
    PROJECT_ID,
    backend=None,
    video_frames=4,
)


print(
    "BACKEND:",
    getattr(
        analyzer.backend,
        "name",
        type(analyzer.backend).__name__,
    )
)


try:

    result = analyzer.analyze(
        asset_ids=asset_ids
    )

except Exception:

    print()
    print("=" * 120)
    print("SEMANTIC V2 ANALYSIS FAILED")
    print("=" * 120)

    traceback.print_exc()

    raise


print()
print("=" * 120)
print("ANALYZER COMPLETE")
print("=" * 120)

print(
    "STATUS    :",
    result.get("status"),
)

print(
    "REQUESTED :",
    result.get("assets_requested"),
)

print(
    "ANALYZED  :",
    result.get("assets_analyzed"),
)

print(
    "FAILED    :",
    result.get("assets_failed"),
)


if result.get("assets_analyzed") != 60:
    raise RuntimeError(
        "V2 did not analyze all 60 assets."
    )


if result.get("assets_failed"):
    raise RuntimeError(
        "V2 semantic analysis contains failures."
    )


results = result.get(
    "results",
    []
)


# ============================================================================
# V2 DISTRIBUTIONS
# ============================================================================

event_distribution = Counter(
    str(
        item.get(
            "event_type",
            "<NONE>",
        )
    )
    for item in results
)


relevance_distribution = Counter(
    str(
        item.get(
            "relevance_status",
            "<NONE>",
        )
    )
    for item in results
)


print()
print("=" * 120)
print("V2 EVENT CLASS DISTRIBUTION")
print("=" * 120)

for key, count in event_distribution.most_common():
    print(
        f"{key:<45}: {count}"
    )


print()
print("=" * 120)
print("V2 RELEVANCE DISTRIBUTION")
print("=" * 120)

for key, count in relevance_distribution.most_common():
    print(
        f"{key:<20}: {count}"
    )


unique_scene_classes = {
    item.get("event_type")
    for item in results
    if str(
        item.get("event_type") or ""
    ).startswith("scene_")
}


print()
print(
    "UNIQUE scene_* CLASSES USED:",
    len(unique_scene_classes),
)


# ============================================================================
# KNOWN BAD CONTROL ASSET
# ============================================================================

BAD_FRAGMENT = (
    "10.5852-ejt.2022.834.1905_Figure_1"
)


bad_items = [
    item
    for item in results
    if BAD_FRAGMENT.lower()
    in str(
        item.get("filename") or ""
    ).lower()
]


print()
print("=" * 120)
print("KNOWN BAD CONTROL ASSET")
print("=" * 120)


if len(bad_items) != 1:

    print(
        "CONTROL ASSET COUNT:",
        len(bad_items),
    )

    raise RuntimeError(
        "Known bad control asset could not be "
        "identified uniquely."
    )


bad = bad_items[0]


print(
    "FILE       :",
    bad.get("filename"),
)

print(
    "EVENT      :",
    bad.get("event_type"),
)

print(
    "EVENT CONF :",
    bad.get("event_confidence"),
)

print(
    "RELEVANCE  :",
    bad.get("relevance_status"),
)

print(
    "REL SCORE  :",
    bad.get("relevance_score"),
)

print(
    "OFF TOPIC  :",
    bad.get("off_topic_score"),
)

print(
    "DESCRIPTION:",
    bad.get("description"),
)


# ============================================================================
# STRATEGIC KNOWN-ASSET CHECKS
# ============================================================================

print()
print("=" * 120)
print("STRATEGIC KNOWN-ASSET CHECKS")
print("=" * 120)


strategic_patterns = {
    "LANGTANG":
        (
            "Langtang_Lirung",
            "glacier_collapse",
        ),

    "GYIRONG":
        (
            "Gyirong",
            "Nepal-China_border",
        ),

    "SATELLITE":
        (
            "Sentinel",
            "Landsat",
            "satellite",
        ),

    "RASUWA":
        (
            "Rasuwa",
        ),

    "RESCUE":
        (
            "drilling",
        ),
}


strategic_summary = {}


for group, patterns in strategic_patterns.items():

    matched = [
        item
        for item in results
        if any(
            pattern.lower()
            in str(
                item.get("filename") or ""
            ).lower()
            for pattern in patterns
        )
    ]

    strategic_summary[group] = []

    print()
    print(
        group,
        "—",
        len(matched),
        "assets",
    )

    for item in matched[:12]:

        row = {
            "filename":
                item.get("filename"),

            "event_type":
                item.get("event_type"),

            "event_confidence":
                item.get("event_confidence"),

            "relevance_status":
                item.get("relevance_status"),

            "relevance_score":
                item.get("relevance_score"),

            "off_topic_score":
                item.get("off_topic_score"),
        }

        strategic_summary[group].append(
            row
        )

        print(
            "  {:<75} => {:<12} {:<12} rel={:.3f} off={:.3f}".format(
                str(item.get("filename"))[:75],
                str(item.get("event_type")),
                str(item.get("relevance_status")),
                float(
                    item.get(
                        "relevance_score",
                        0.0,
                    )
                ),
                float(
                    item.get(
                        "off_topic_score",
                        0.0,
                    )
                ),
            )
        )


# ============================================================================
# V1 -> V2 COMPARISON
# ============================================================================

print()
print("=" * 120)
print("V1 -> V2 COMPARISON")
print("=" * 120)


comparison = []


for item in results:

    asset_id = str(
        item.get("asset_id")
    )

    previous = old_by_id.get(
        asset_id,
        {},
    )

    comparison.append(
        {
            "asset_id":
                asset_id,

            "filename":
                item.get("filename"),

            "v1_event":
                previous.get(
                    "event_type",
                    "documentary_context"
                    if not old_by_id
                    else None,
                ),

            "v1_relevance":
                previous.get(
                    "relevance_status"
                ),

            "v1_relevance_score":
                previous.get(
                    "relevance_score"
                ),

            "v2_event":
                item.get(
                    "event_type"
                ),

            "v2_event_confidence":
                item.get(
                    "event_confidence"
                ),

            "v2_relevance":
                item.get(
                    "relevance_status"
                ),

            "v2_relevance_score":
                item.get(
                    "relevance_score"
                ),

            "v2_off_topic_score":
                item.get(
                    "off_topic_score"
                ),
        }
    )


changed_from_documentary = sum(
    1
    for row in comparison
    if row["v2_event"]
    != "documentary_context"
)


print(
    "V2 NOT documentary_context:",
    changed_from_documentary,
    "/",
    len(comparison),
)


print(
    "UNIQUE V2 EVENTS:",
    len(event_distribution),
)


# ============================================================================
# DATABASE VERIFICATION
# ============================================================================

conn = sqlite3.connect(
    str(DB_PATH)
)

conn.row_factory = sqlite3.Row

try:

    db_rows = conn.execute(
        """
        SELECT
            id,
            filename,
            semantic_class,
            semantic_description,
            semantic_confidence
        FROM assets
        WHERE project_id=?
        ORDER BY filename
        """,
        (PROJECT_ID,),
    ).fetchall()

finally:
    conn.close()


db_classes = Counter(
    str(
        row["semantic_class"]
        or "<NONE>"
    )
    for row in db_rows
)


print()
print("=" * 120)
print("CANONICAL DB AFTER V2")
print("=" * 120)

print(
    "ROWS:",
    len(db_rows),
)

print(
    "SEMANTIC CLASSES:",
    len(db_classes),
)

for key, count in db_classes.most_common():
    print(
        f"{key:<45}: {count}"
    )


# ============================================================================
# DIAGNOSTIC GATES
# ============================================================================

control_rejected = (
    str(
        bad.get("relevance_status")
    )
    == "OFF_TOPIC"
)


control_not_scene = (
    not str(
        bad.get("event_type") or ""
    ).startswith("scene_")
)


semantic_diversity = (
    len(event_distribution) >= 4
)


scene_semantics_used = (
    len(unique_scene_classes) >= 3
)


all_60 = (
    len(results) == 60
)


checks = {
    "ALL_60_ANALYZED":
        all_60,

    "NO_ANALYSIS_FAILURES":
        not result.get("failures"),

    "GENERIC_COLLAPSE_BROKEN":
        changed_from_documentary >= 50,

    "SEMANTIC_DIVERSITY_GE_4":
        semantic_diversity,

    "SCENE_CLASSES_USED_GE_3":
        scene_semantics_used,

    "KNOWN_BAD_CONTROL_OFF_TOPIC":
        control_rejected,

    "KNOWN_BAD_CONTROL_NOT_SCENE":
        control_not_scene,
}


print()
print("=" * 120)
print("V2 DIAGNOSTIC GATES")
print("=" * 120)


for key, passed in checks.items():

    print(
        f"{key:<42}: "
        + (
            "PASS"
            if passed
            else "FAIL"
        )
    )


# ============================================================================
# SAVE COMPARISON
# ============================================================================

comparison_path = (
    OUT
    / "FILM10_SEMANTIC_V1_V2_COMPARISON.json"
)


comparison_path.write_text(
    json.dumps(
        comparison,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


summary_path = (
    OUT
    / "FILM10_SEMANTIC_REANALYSIS_V2_SUMMARY.json"
)


summary = {
    "schema":
        "atlas_zero.film10_semantic_reanalysis.v2",

    "project_id":
        PROJECT_ID,

    "semantic_context_source":
        context.source_path,

    "event_label_count":
        len(context.event_labels),

    "scene_label_count":
        len(scene_labels),

    "concept_count":
        len(context.concepts),

    "assets_analyzed":
        len(results),

    "event_distribution":
        dict(event_distribution),

    "relevance_distribution":
        dict(relevance_distribution),

    "unique_scene_classes_used":
        len(unique_scene_classes),

    "known_bad_control":
        {
            "filename":
                bad.get("filename"),

            "event_type":
                bad.get("event_type"),

            "event_confidence":
                bad.get("event_confidence"),

            "relevance_status":
                bad.get("relevance_status"),

            "relevance_score":
                bad.get("relevance_score"),

            "off_topic_score":
                bad.get("off_topic_score"),
        },

    "strategic_assets":
        strategic_summary,

    "gates":
        checks,

    "render_performed":
        False,

    "assignments_written":
        False,

    "live_api":
        False,

    "paid_calls":
        False,
}


summary_path.write_text(
    json.dumps(
        summary,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


print()
print("=" * 120)
print("OUTPUT")
print("=" * 120)

print(
    "V2 REPORT :",
    OUT / "visual_semantic_report_v2.json",
)

print(
    "COMPARE   :",
    comparison_path,
)

print(
    "SUMMARY   :",
    summary_path,
)


print()
print("=" * 120)

if all(checks.values()):

    print(
        "FILM10 SEMANTIC REANALYSIS V2: PASS"
    )

    print(
        "Semantic layer is ready for "
        "AssignmentPolicy integration testing."
    )

else:

    print(
        "FILM10 SEMANTIC REANALYSIS V2: "
        "DIAGNOSTIC FAILURE"
    )

    print(
        "Do NOT run AssignmentPolicy yet."
    )

print("=" * 120)

print()
print("No render performed.")
print("No assignments written.")
print("No paid API calls.")
