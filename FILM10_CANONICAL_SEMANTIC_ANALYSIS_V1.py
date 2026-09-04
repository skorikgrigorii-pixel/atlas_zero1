from __future__ import annotations

import inspect
import json
import os
import sqlite3
import sys
import traceback
from pathlib import Path


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
    / "semantic_analysis_v1"
)

OUT.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================================
# HARD SAFETY
# ============================================================================

os.environ["AZ_ENABLE_LIVE_API"] = "0"
os.environ["AZ_ALLOW_PAID_CALLS"] = "0"

print("=" * 120)
print("ATLAS ZERO — FILM10 CANONICAL SEMANTIC ANALYSIS V1")
print("=" * 120)

print("ROOT       :", ROOT)
print("PROJECT    :", PROJECT_ID)
print("DATABASE   :", DB_PATH)
print("LIVE API   :", os.environ["AZ_ENABLE_LIVE_API"])
print("PAID CALLS :", os.environ["AZ_ALLOW_PAID_CALLS"])


if not DB_PATH.exists():
    raise FileNotFoundError(DB_PATH)


# ============================================================================
# IMPORT EXISTING OS — NO NEW ANALYZER
# ============================================================================

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from az_enterprise.core.database import Database
from az_enterprise.core.visual_semantic_analyzer_rc2 import (
    VisualSemanticAnalyzerRC2,
)


print()
print("=" * 120)
print("EXISTING ANALYZER")
print("=" * 120)

print(
    "CLASS      :",
    VisualSemanticAnalyzerRC2.__module__
    + "."
    + VisualSemanticAnalyzerRC2.__name__,
)

print(
    "INIT       :",
    inspect.signature(
        VisualSemanticAnalyzerRC2
    ),
)

print(
    "ANALYZE    :",
    inspect.signature(
        VisualSemanticAnalyzerRC2.analyze
    ),
)


source_file = Path(
    inspect.getsourcefile(
        VisualSemanticAnalyzerRC2
    )
).resolve()

print(
    "SOURCE     :",
    source_file,
)


# ============================================================================
# READ SOURCE TO DETERMINE BACKEND / LIVE-API BEHAVIOUR
# ============================================================================

source = source_file.read_text(
    encoding="utf-8-sig",
    errors="replace",
)

source_lower = source.lower()

live_markers = [
    "openai",
    "anthropic",
    "gemini",
    "google.generativeai",
    "requests.post",
    "httpx",
    "urllib.request",
    "api_key",
    "az_enable_live_api",
    "az_allow_paid_calls",
]

found_live_markers = [
    marker
    for marker in live_markers
    if marker in source_lower
]

print()
print("=" * 120)
print("BACKEND SAFETY INSPECTION")
print("=" * 120)

print(
    "LIVE/API MARKERS:",
    found_live_markers
    if found_live_markers
    else "NONE",
)


# ============================================================================
# CANONICAL STATE BEFORE ANALYSIS
# ============================================================================

conn = sqlite3.connect(
    str(DB_PATH)
)

conn.row_factory = sqlite3.Row

try:
    rows = conn.execute(
        """
        SELECT
            id,
            filename,
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
print("CANONICAL ASSET STATE — BEFORE")
print("=" * 120)

print(
    "ASSETS:",
    len(rows),
)

if len(rows) != 60:
    raise RuntimeError(
        "Expected 60 canonical Film10 assets; "
        "found {}".format(
            len(rows)
        )
    )


already_semantic = sum(
    1
    for row in rows
    if (
        row["semantic_class"]
        or row["semantic_description"]
        or float(
            row["semantic_confidence"]
            or 0
        ) > 0
    )
)

print(
    "ALREADY SEMANTIC:",
    already_semantic,
)


# ============================================================================
# CONSTRUCT EXISTING DATABASE OBJECT
# ============================================================================

print()
print("=" * 120)
print("DATABASE CONTRACT")
print("=" * 120)

print(
    "Database signature:",
    inspect.signature(Database),
)


db = None
db_errors = []


constructors = [
    lambda: Database(
        str(DB_PATH)
    ),

    lambda: Database(
        DB_PATH
    ),

    lambda: Database(),
]


for constructor in constructors:
    try:
        db = constructor()
        break

    except Exception as exc:
        db_errors.append(
            repr(exc)
        )


if db is None:
    raise RuntimeError(
        "Unable to construct existing Database object. "
        "Attempts: "
        + " | ".join(
            db_errors
        )
    )


print(
    "DATABASE OBJECT:",
    type(db).__name__,
)


# ============================================================================
# CONSTRUCT ANALYZER WITH backend=None
# ============================================================================

analyzer = VisualSemanticAnalyzerRC2(
    db,
    PROJECT_ID,
    backend=None,
    video_frames=4,
)


print()
print("=" * 120)
print("ANALYZER RUNTIME STATE")
print("=" * 120)


interesting_attrs = [
    "backend",
    "_backend",
    "provider",
    "_provider",
    "client",
    "_client",
    "model",
    "_model",
]


runtime_state = {}

for name in interesting_attrs:
    if hasattr(
        analyzer,
        name,
    ):
        try:
            value = getattr(
                analyzer,
                name,
            )

            runtime_state[name] = repr(
                value
            )

        except Exception as exc:
            runtime_state[name] = (
                "<ERROR {}>".format(
                    exc
                )
            )


for name, value in runtime_state.items():
    print(
        "{:<16}: {}".format(
            name,
            value,
        )
    )


# ============================================================================
# DETERMINE WHETHER backend=None IS SAFE
# ============================================================================

backend_value = None

for name in (
    "backend",
    "_backend",
):
    if hasattr(
        analyzer,
        name,
    ):
        backend_value = getattr(
            analyzer,
            name,
        )

        break


backend_repr = repr(
    backend_value
).lower()


dangerous_backend = any(
    marker in backend_repr
    for marker in (
        "openai",
        "anthropic",
        "gemini",
        "remote",
        "api",
    )
)


env_live_enabled = (
    os.environ.get(
        "AZ_ENABLE_LIVE_API",
        "0",
    ) == "1"
)

env_paid_enabled = (
    os.environ.get(
        "AZ_ALLOW_PAID_CALLS",
        "0",
    ) == "1"
)


if env_live_enabled or env_paid_enabled:
    raise RuntimeError(
        "API safety environment unexpectedly enabled."
    )


if dangerous_backend:
    print()
    print("=" * 120)
    print("SEMANTIC ANALYSIS: HOLD")
    print("=" * 120)

    print(
        "backend=None resolved to a potentially "
        "remote/live backend:"
    )

    print(
        repr(
            backend_value
        )
    )

    print()
    print(
        "No analyzer call performed."
    )

    raise SystemExit(20)


# ============================================================================
# RUN EXISTING ANALYZER
# ============================================================================

asset_ids = [
    row["id"]
    for row in rows
]


print()
print("=" * 120)
print("RUNNING EXISTING VisualSemanticAnalyzerRC2")
print("=" * 120)

print(
    "ASSET IDS    :",
    len(asset_ids),
)

print(
    "VIDEO FRAMES : 4",
)

print(
    "RENDER       : NO",
)

print(
    "PAID API     : NO",
)


try:
    result = analyzer.analyze(
        asset_ids=asset_ids
    )

except Exception as exc:
    print()
    print("=" * 120)
    print("ANALYZER ERROR")
    print("=" * 120)

    print(
        type(exc).__name__
        + ": "
        + str(exc)
    )

    traceback.print_exc()

    raise


print()
print("=" * 120)
print("ANALYZER RETURN")
print("=" * 120)

print(
    repr(result)
)


# ============================================================================
# VERIFY DATABASE AFTER ANALYSIS
# ============================================================================

conn = sqlite3.connect(
    str(DB_PATH)
)

conn.row_factory = sqlite3.Row

try:
    after = conn.execute(
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


    metadata_count = None

    exists = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM sqlite_master
        WHERE type='table'
          AND name='cv_asset_metadata'
        """
    ).fetchone()["n"]

    if exists:
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(cv_asset_metadata)"
            )
        }

        if "project_id" in columns:
            metadata_count = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM cv_asset_metadata
                WHERE project_id=?
                """,
                (PROJECT_ID,),
            ).fetchone()["n"]

        elif "asset_id" in columns:
            placeholders = ",".join(
                "?"
                for _ in asset_ids
            )

            metadata_count = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM cv_asset_metadata
                WHERE asset_id IN ({})
                """.format(
                    placeholders
                ),
                asset_ids,
            ).fetchone()["n"]

finally:
    conn.close()


classified = sum(
    1
    for row in after
    if row["semantic_class"]
)

described = sum(
    1
    for row in after
    if row["semantic_description"]
)

confident = sum(
    1
    for row in after
    if float(
        row["semantic_confidence"]
        or 0
    ) > 0
)


print()
print("=" * 120)
print("CANONICAL ASSET STATE — AFTER")
print("=" * 120)

print(
    "ASSETS                :",
    len(after),
)

print(
    "SEMANTIC CLASS        :",
    classified,
)

print(
    "SEMANTIC DESCRIPTION  :",
    described,
)

print(
    "CONFIDENCE > 0        :",
    confident,
)

print(
    "CV ASSET METADATA     :",
    metadata_count
    if metadata_count is not None
    else "N/A",
)


# ============================================================================
# DISTRIBUTION
# ============================================================================

from collections import Counter


class_distribution = Counter(
    str(
        row["semantic_class"]
        or "<NONE>"
    )
    for row in after
)


print()
print("=" * 120)
print("SEMANTIC CLASS DISTRIBUTION")
print("=" * 120)

for name, count in class_distribution.most_common():
    print(
        "{:<40}: {}".format(
            name,
            count,
        )
    )


# ============================================================================
# LOW-CONFIDENCE / SUSPICIOUS CANDIDATES
# ============================================================================

suspicious_terms = (
    "insect",
    "specimen",
    "butterfly",
    "beetle",
    "museum",
    "panel",
    "diagram",
    "chart",
    "unrelated",
)


suspicious = []

for row in after:
    combined = (
        str(
            row["filename"]
            or ""
        )
        + " "
        + str(
            row["semantic_class"]
            or ""
        )
        + " "
        + str(
            row["semantic_description"]
            or ""
        )
    ).lower()

    hits = [
        term
        for term in suspicious_terms
        if term in combined
    ]

    confidence = float(
        row["semantic_confidence"]
        or 0
    )

    if hits or confidence < 0.20:
        suspicious.append(
            {
                "id":
                    row["id"],

                "filename":
                    row["filename"],

                "semantic_class":
                    row["semantic_class"],

                "semantic_description":
                    row["semantic_description"],

                "semantic_confidence":
                    confidence,

                "suspicious_terms":
                    hits,
            }
        )


print()
print("=" * 120)
print("SUSPICIOUS / LOW-CONFIDENCE ASSETS")
print("=" * 120)

print(
    "COUNT:",
    len(suspicious),
)

for item in suspicious[:30]:
    print()
    print(
        json.dumps(
            item,
            ensure_ascii=False,
            indent=2,
        )
    )


# ============================================================================
# SAVE EVIDENCE
# ============================================================================

snapshot = [
    {
        "id":
            row["id"],

        "filename":
            row["filename"],

        "path":
            row["path"],

        "media_type":
            row["media_type"],

        "sha256":
            row["sha256"],

        "duplicate_of":
            row["duplicate_of"],

        "semantic_class":
            row["semantic_class"],

        "semantic_description":
            row["semantic_description"],

        "semantic_confidence":
            row["semantic_confidence"],
    }
    for row in after
]


(OUT / "FILM10_SEMANTIC_ASSET_SNAPSHOT_V1.json").write_text(
    json.dumps(
        snapshot,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


report = {
    "schema":
        "atlas_zero.film10_semantic_analysis.v1",

    "project_id":
        PROJECT_ID,

    "analyzer":
        (
            VisualSemanticAnalyzerRC2.__module__
            + "."
            + VisualSemanticAnalyzerRC2.__name__
        ),

    "source_file":
        str(
            source_file
        ),

    "live_api":
        False,

    "paid_calls":
        False,

    "asset_count":
        len(after),

    "classified":
        classified,

    "described":
        described,

    "confidence_gt_zero":
        confident,

    "cv_asset_metadata":
        metadata_count,

    "class_distribution":
        dict(
            class_distribution
        ),

    "suspicious_count":
        len(suspicious),

    "suspicious":
        suspicious,

    "analyzer_return":
        repr(
            result
        ),
}


(OUT / "FILM10_SEMANTIC_ANALYSIS_REPORT_V1.json").write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


print()
print("=" * 120)

if classified == 0 and described == 0:
    print(
        "FILM10 SEMANTIC ANALYSIS V1: "
        "EXECUTED BUT NO SEMANTIC DATA PRODUCED"
    )

else:
    print(
        "FILM10 SEMANTIC ANALYSIS V1: PASS"
    )

print("=" * 120)

print(
    "SNAPSHOT:",
    OUT / "FILM10_SEMANTIC_ASSET_SNAPSHOT_V1.json",
)

print(
    "REPORT  :",
    OUT / "FILM10_SEMANTIC_ANALYSIS_REPORT_V1.json",
)

print()
print(
    "NO RENDER PERFORMED."
)
