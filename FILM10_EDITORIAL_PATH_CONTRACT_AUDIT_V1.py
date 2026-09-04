from pathlib import Path
import inspect
import json
import sqlite3
import sys

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

sys.path.insert(0, str(ROOT / "src"))

print("=" * 120)
print("ATLAS ZERO — FILM10 FINAL EDITORIAL PATH CONTRACT AUDIT")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")
print("CLIP       : NO")

# =============================================================================
# IMPORT EXISTING CORE
# =============================================================================

from az_enterprise.core.assignment_policy_rc2 import AssignmentPolicyRC2
from az_enterprise.core.render_engine_rc2 import RenderEngineRC2

print()
print("=" * 120)
print("ASSIGNMENT POLICY")
print("=" * 120)

print("CLASS FILE :", inspect.getsourcefile(AssignmentPolicyRC2))
print("SIGNATURE  :", inspect.signature(AssignmentPolicyRC2))

for name in (
    "__init__",
    "run",
):
    method = getattr(AssignmentPolicyRC2, name, None)

    print()
    print("-" * 120)
    print(name)
    print("-" * 120)

    if method is None:
        print("NOT FOUND")
        continue

    print("SIGNATURE:", inspect.signature(method))

    try:
        print(inspect.getsource(method))
    except Exception as exc:
        print(
            "SOURCE UNAVAILABLE:",
            type(exc).__name__,
            str(exc),
        )

# =============================================================================
# SEARCH IMPORTANT ASSIGNMENT METHODS
# =============================================================================

print()
print("=" * 120)
print("ASSIGNMENT POLICY METHOD MAP")
print("=" * 120)

for name, member in inspect.getmembers(
    AssignmentPolicyRC2,
    predicate=inspect.isfunction,
):
    low = name.lower()

    if any(
        token in low
        for token in (
            "assign",
            "score",
            "asset",
            "shot",
            "candidate",
            "semantic",
            "fallback",
            "write",
        )
    ):
        try:
            sig = inspect.signature(member)
        except Exception:
            sig = "?"

        print(
            f"{name:<40} {sig}"
        )

# =============================================================================
# RENDER ENGINE
# =============================================================================

print()
print("=" * 120)
print("RENDER ENGINE")
print("=" * 120)

print("CLASS FILE :", inspect.getsourcefile(RenderEngineRC2))
print("SIGNATURE  :", inspect.signature(RenderEngineRC2))

for name in (
    "__init__",
    "load_timeline",
    "build_render_model",
    "validate_render_model",
    "run",
):
    method = getattr(RenderEngineRC2, name, None)

    print()
    print("-" * 120)
    print(name)
    print("-" * 120)

    if method is None:
        print("NOT FOUND")
        continue

    print("SIGNATURE:", inspect.signature(method))

    try:
        src = inspect.getsource(method)
        print(src)
    except Exception as exc:
        print(
            "SOURCE UNAVAILABLE:",
            type(exc).__name__,
            str(exc),
        )

# =============================================================================
# DB CURRENT FILM10 STATE
# =============================================================================

DB = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"

uri = DB.resolve().as_uri() + "?mode=ro"

conn = sqlite3.connect(
    uri,
    uri=True,
)

conn.row_factory = sqlite3.Row

try:
    shot_columns = [
        dict(row)
        for row in conn.execute(
            "PRAGMA table_info(shots)"
        ).fetchall()
    ]

    asset_columns = [
        dict(row)
        for row in conn.execute(
            "PRAGMA table_info(assets)"
        ).fetchall()
    ]

    shots = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM shots
            WHERE project_id=?
            ORDER BY idx
            """,
            (PROJECT_ID,),
        ).fetchall()
    ]

    assets = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM assets
            WHERE project_id=?
            ORDER BY filename
            """,
            (PROJECT_ID,),
        ).fetchall()
    ]

finally:
    conn.close()

print()
print("=" * 120)
print("CANONICAL FILM10 STATE")
print("=" * 120)

print("SHOTS       :", len(shots))
print("ASSETS      :", len(assets))

assigned = [
    row
    for row in shots
    if row.get("assigned_asset_id")
]

print("ASSIGNED    :", len(assigned))
print("UNASSIGNED  :", len(shots) - len(assigned))

print()
print("SHOT COLUMNS:")
for row in shot_columns:
    print(
        f"  {row['name']:<24} "
        f"{row['type']}"
    )

print()
print("ASSET COLUMNS:")
for row in asset_columns:
    print(
        f"  {row['name']:<24} "
        f"{row['type']}"
    )

print()
print("=" * 120)
print("FIRST 5 SHOTS")
print("=" * 120)

for row in shots[:5]:
    print(
        json.dumps(
            row,
            ensure_ascii=False,
            default=str,
            indent=2,
        )
    )

# =============================================================================
# SEGMENT INVENTORY
# =============================================================================

SEGMENTS = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "human_curated_corpus_v2"
    / "FILM10_VIDEO_SEGMENT_INVENTORY_V1.json"
)

if not SEGMENTS.exists():
    raise FileNotFoundError(SEGMENTS)

segment_data = json.loads(
    SEGMENTS.read_text(
        encoding="utf-8"
    )
)

segments = segment_data.get(
    "segment_inventory",
    []
)

print()
print("=" * 120)
print("HUMAN-CURATED VIDEO SEGMENTS")
print("=" * 120)

print("SEGMENTS:", len(segments))

if len(segments) != 181:
    raise RuntimeError(
        f"Expected 181 segments, got {len(segments)}"
    )

print()
print("FIRST 5 SEGMENTS:")

for row in segments[:5]:
    print(
        json.dumps(
            row,
            ensure_ascii=False,
            indent=2,
        )
    )

# =============================================================================
# SOURCE CODE KEYWORD SEARCH
# =============================================================================

print()
print("=" * 120)
print("RENDER SOURCE RANGE SUPPORT")
print("=" * 120)

render_source = inspect.getsource(
    inspect.getmodule(RenderEngineRC2)
)

for token in (
    "source_start",
    "source_end",
    "assigned_asset_id",
    "timeline",
    "asset_path",
):
    count = render_source.count(token)

    print(
        f"{token:<24}: {count}"
    )

print()
print("=" * 120)
print("ASSIGNMENT SOURCE RANGE SUPPORT")
print("=" * 120)

assignment_source = inspect.getsource(
    inspect.getmodule(AssignmentPolicyRC2)
)

for token in (
    "source_start",
    "source_end",
    "assigned_asset_id",
    "fallback_semantic",
    "story_explicit",
    "max_use",
):
    count = assignment_source.count(token)

    print(
        f"{token:<24}: {count}"
    )

# =============================================================================
# REPORT
# =============================================================================

OUT_DIR = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "editorial_assignment_v4"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

REPORT = (
    OUT_DIR
    / "FILM10_EDITORIAL_PATH_CONTRACT_AUDIT_V1.json"
)

payload = {
    "project_id":
        PROJECT_ID,

    "assignment_policy_signature":
        str(
            inspect.signature(
                AssignmentPolicyRC2
            )
        ),

    "render_engine_signature":
        str(
            inspect.signature(
                RenderEngineRC2
            )
        ),

    "shots":
        len(shots),

    "assets":
        len(assets),

    "assigned":
        len(assigned),

    "segments":
        len(segments),

    "shot_columns":
        shot_columns,

    "asset_columns":
        asset_columns,

    "render_source_range_tokens": {
        token: render_source.count(token)
        for token in (
            "source_start",
            "source_end",
            "assigned_asset_id",
            "timeline",
            "asset_path",
        )
    },

    "assignment_source_range_tokens": {
        token: assignment_source.count(token)
        for token in (
            "source_start",
            "source_end",
            "assigned_asset_id",
            "fallback_semantic",
            "story_explicit",
            "max_use",
        )
    },

    "db_writes":
        False,

    "assignment":
        False,

    "render":
        False,

    "clip":
        False,

    "paid_calls":
        False,
}

REPORT.write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("=" * 120)
print("REPORT")
print("=" * 120)
print(REPORT)

print()
print("=" * 120)
print("EDITORIAL PATH CONTRACT AUDIT: COMPLETE")
print("=" * 120)
print("No DB writes.")
print("No assignment.")
print("No render.")
print("No CLIP.")
print("No paid API calls.")
