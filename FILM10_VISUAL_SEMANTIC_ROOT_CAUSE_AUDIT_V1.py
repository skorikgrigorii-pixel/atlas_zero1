from pathlib import Path
import sys
import inspect
import sqlite3
import json
import re

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"
DB_PATH = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"
SRC_ROOT = ROOT / "src"

sys.path.insert(0, str(SRC_ROOT))

from az_enterprise.core.visual_semantic_analyzer_rc2 import (
    VisualSemanticAnalyzerRC2,
    HuggingFaceClipBackendRC2,
)

print("=" * 120)
print("ATLAS ZERO — VISUAL SEMANTIC ANALYZER ROOT-CAUSE AUDIT V1")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("MODE       : READ ONLY")


# =============================================================================
# SOURCE
# =============================================================================

analyzer_file = Path(
    inspect.getsourcefile(VisualSemanticAnalyzerRC2)
).resolve()

print()
print("=" * 120)
print("SOURCE")
print("=" * 120)
print(analyzer_file)


source = analyzer_file.read_text(
    encoding="utf-8-sig",
    errors="replace",
)

lines = source.splitlines()


# =============================================================================
# CLASS SIGNATURES
# =============================================================================

print()
print("=" * 120)
print("CLASS CONTRACTS")
print("=" * 120)

print(
    "VisualSemanticAnalyzerRC2:",
    inspect.signature(VisualSemanticAnalyzerRC2)
)

print(
    "HuggingFaceClipBackendRC2:",
    inspect.signature(HuggingFaceClipBackendRC2)
)


for cls in (
    VisualSemanticAnalyzerRC2,
    HuggingFaceClipBackendRC2,
):
    print()
    print("CLASS:", cls.__name__)

    for name, member in inspect.getmembers(cls):
        if name.startswith("__"):
            continue

        if inspect.isfunction(member):
            try:
                sig = inspect.signature(member)
            except Exception:
                sig = "?"

            print("  {:<36} {}".format(name, sig))


# =============================================================================
# FIND SEMANTIC VOCABULARIES / PROMPTS
# =============================================================================

print()
print("=" * 120)
print("SEMANTIC VOCABULARY / PROMPT DEFINITIONS")
print("=" * 120)

patterns = [
    r"documentary_context",
    r"unrelated_private_content",
    r"event",
    r"topic",
    r"prompt",
    r"label",
    r"class",
    r"relevant",
    r"off_topic",
    r"time_period",
    r"morning",
    r"night",
]

interesting_lines = set()

for i, line in enumerate(lines, 1):
    low = line.lower()

    if any(re.search(p, low) for p in patterns):
        for j in range(max(1, i - 3), min(len(lines), i + 3) + 1):
            interesting_lines.add(j)


for i in sorted(interesting_lines):
    print(
        "{:04d}: {}".format(
            i,
            lines[i - 1]
        )
    )


# =============================================================================
# CLASS CONSTANTS
# =============================================================================

print()
print("=" * 120)
print("CLASS CONSTANTS / VOCABULARIES")
print("=" * 120)

for cls in (
    VisualSemanticAnalyzerRC2,
    HuggingFaceClipBackendRC2,
):
    print()
    print("CLASS:", cls.__name__)

    for name, value in vars(cls).items():

        if name.startswith("__"):
            continue

        if callable(value):
            continue

        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
                list,
                tuple,
                set,
                dict,
                type(None),
            )
        ):
            try:
                rendered = repr(value)

                if len(rendered) > 4000:
                    rendered = rendered[:4000] + "...<TRUNCATED>"

                print(
                    "  {} = {}".format(
                        name,
                        rendered
                    )
                )

            except Exception:
                pass


# =============================================================================
# METHOD SOURCE
# =============================================================================

candidate_methods = [
    "__init__",
    "analyze",
    "_analyze_asset",
    "_analyze_image",
    "_analyze_video",
    "_classify",
    "classify",
    "_score",
    "score",
    "_encode_text",
    "_encode_image",
    "_event_scores",
    "_topic_scores",
]

print()
print("=" * 120)
print("RELEVANT METHOD SOURCE")
print("=" * 120)

for cls in (
    HuggingFaceClipBackendRC2,
    VisualSemanticAnalyzerRC2,
):
    for name in candidate_methods:

        if not hasattr(cls, name):
            continue

        member = getattr(cls, name)

        if not callable(member):
            continue

        print()
        print("-" * 120)
        print("{} . {}".format(cls.__name__, name))
        print("-" * 120)

        try:
            text = inspect.getsource(member)

            if len(text) > 16000:
                text = text[:16000] + "\n...<TRUNCATED>"

            print(text)

        except Exception as exc:
            print(
                "SOURCE ERROR:",
                repr(exc)
            )


# =============================================================================
# DATABASE SCHEMA
# =============================================================================

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

try:

    print()
    print("=" * 120)
    print("SEMANTIC-RELATED TABLES")
    print("=" * 120)

    tables = [
        r["name"]
        for r in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            ORDER BY name
            """
        )
    ]

    semantic_tables = [
        t for t in tables
        if any(
            word in t.lower()
            for word in (
                "semantic",
                "asset",
                "visual",
                "cv_",
                "embedding",
            )
        )
    ]

    for table in semantic_tables:

        print()
        print("TABLE:", table)

        cols = conn.execute(
            "PRAGMA table_info({})".format(table)
        ).fetchall()

        print(
            "COLUMNS:",
            [
                c["name"]
                for c in cols
            ]
        )

        try:
            total = conn.execute(
                "SELECT COUNT(*) n FROM {}".format(table)
            ).fetchone()["n"]

            print("ROWS:", total)

        except Exception as exc:
            print("COUNT ERROR:", exc)


    # =========================================================================
    # CURRENT FILM10 ASSET SEMANTICS
    # =========================================================================

    print()
    print("=" * 120)
    print("FILM10 CURRENT SEMANTIC STATE")
    print("=" * 120)

    rows = conn.execute(
        """
        SELECT
            id,
            filename,
            media_type,
            semantic_class,
            semantic_description,
            semantic_confidence,
            duplicate_of
        FROM assets
        WHERE project_id=?
        ORDER BY filename
        """,
        (PROJECT_ID,),
    ).fetchall()

    print("ASSETS:", len(rows))

    classes = {}

    for r in rows:
        key = r["semantic_class"] or "<NONE>"
        classes[key] = classes.get(key, 0) + 1

    print("CLASSES:")
    for k, v in sorted(
        classes.items(),
        key=lambda x: (-x[1], x[0])
    ):
        print("  {:<40}: {}".format(k, v))


    print()
    print("=" * 120)
    print("KNOWN BAD ASSET CHECK")
    print("=" * 120)

    bad = conn.execute(
        """
        SELECT
            id,
            filename,
            semantic_class,
            semantic_description,
            semantic_confidence,
            path
        FROM assets
        WHERE project_id=?
          AND filename LIKE '%10.5852%'
        """,
        (PROJECT_ID,),
    ).fetchall()

    for row in bad:
        print(
            json.dumps(
                dict(row),
                ensure_ascii=False,
                indent=2
            )
        )


finally:
    conn.close()


# =============================================================================
# SOURCE-LEVEL ROOT CAUSE HEURISTICS
# =============================================================================

print()
print("=" * 120)
print("ROOT-CAUSE HEURISTICS")
print("=" * 120)

checks = {
    "contains_documentary_context":
        "documentary_context" in source,

    "contains_unrelated_private_content":
        "unrelated_private_content" in source,

    "contains_relevant":
        "relevant" in source.lower(),

    "contains_off_topic":
        "off_topic" in source.lower(),

    "contains_location_hint":
        "location_hint" in source,

    "contains_detected_objects":
        "detected_objects" in source,

    "contains_detected_actions":
        "detected_actions" in source,
}

for name, value in checks.items():
    print(
        "{:<44}: {}".format(
            name,
            "YES" if value else "NO"
        )
    )


# =============================================================================
# SEARCH NEIGHBOURING MODULES
# =============================================================================

print()
print("=" * 120)
print("NEIGHBOURING EXISTING SEMANTIC MODULES")
print("=" * 120)

hits = []

for path in (
    ROOT / "src" / "az_enterprise" / "core"
).glob("*.py"):

    try:
        txt = path.read_text(
            encoding="utf-8-sig",
            errors="replace"
        )

    except Exception:
        continue

    low = txt.lower()

    score = sum(
        1
        for term in (
            "clip",
            "semantic_class",
            "semantic_description",
            "visual_need",
            "event_type",
            "relevance_status",
            "detected_objects",
            "detected_actions",
        )
        if term in low
    )

    if score:
        hits.append(
            (
                score,
                path.name,
            )
        )


for score, name in sorted(
    hits,
    reverse=True
):
    print(
        "{:>2}  {}".format(
            score,
            name
        )
    )


print()
print("=" * 120)
print("AUDIT COMPLETE — READ ONLY")
print("=" * 120)

print(
    "No source files modified."
)

print(
    "No database rows modified."
)

print(
    "No API calls made."
)

print(
    "No render performed."
)
