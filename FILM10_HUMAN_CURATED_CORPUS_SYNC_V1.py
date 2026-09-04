from __future__ import annotations

from pathlib import Path
import sqlite3
import json
import shutil
import subprocess
import hashlib
from datetime import datetime

ROOT = Path.cwd().resolve()

PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

DB = (
    ROOT
    / "workspace"
    / "atlas_zero_enterprise.sqlite3"
)

RECON = (
    PROJECT
    / "00_Production"
    / "human_curated_corpus_v1"
    / "FILM10_CANONICAL_CORPUS_RECONCILIATION_V1.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "human_curated_corpus_v2"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

SEGMENT_REPORT = (
    OUT_DIR
    / "FILM10_VIDEO_SEGMENT_INVENTORY_V1.json"
)

SYNC_REPORT = (
    OUT_DIR
    / "FILM10_CANONICAL_CORPUS_SYNC_V1.json"
)

print("=" * 118)
print("ATLAS ZERO — FILM10 HUMAN-CURATED CORPUS SYNC + VIDEO SEGMENT INVENTORY")
print("=" * 118)

print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

if not DB.exists():
    raise FileNotFoundError(DB)

if not RECON.exists():
    raise FileNotFoundError(RECON)

recon = json.loads(
    RECON.read_text(
        encoding="utf-8"
    )
)

# =============================================================================
# HARD SAFETY GATES
# =============================================================================

print()
print("=" * 118)
print("RECONCILIATION SAFETY GATES")
print("=" * 118)

expected = {
    "human_curated_files": 43,
    "matched": 43,
    "filesystem_only": 0,
    "db_physically_missing": 17,
    "db_exists_but_not_matched": 0,
}

for key, value in expected.items():

    actual = recon.get(key)

    print(
        f"{key:<30} "
        f"expected={value:<4} "
        f"actual={actual}"
    )

    if actual != value:
        raise RuntimeError(
            f"Safety gate failed: {key}"
        )

missing_rows = (
    recon.get(
        "db_physically_missing_assets",
        []
    )
)

if len(missing_rows) != 17:
    raise RuntimeError(
        "Expected exactly 17 missing DB assets."
    )

missing_ids = [
    str(row["id"])
    for row in missing_rows
]

if len(set(missing_ids)) != 17:
    raise RuntimeError(
        "Missing asset IDs are not unique."
    )

# =============================================================================
# VERIFY PHYSICAL ABSENCE AGAIN
# =============================================================================

print()
print("=" * 118)
print("REVERIFY PHYSICAL DELETIONS")
print("=" * 118)

for row in missing_rows:

    p = Path(
        str(row["path"])
    )

    if not p.is_absolute():
        p = ROOT / p

    exists = p.exists()

    print(
        f"{row['id']} | "
        f"{'EXISTS' if exists else 'MISSING':<7} | "
        f"{row['filename']}"
    )

    if exists:
        raise RuntimeError(
            "Refusing DB deletion because "
            f"file exists again: {p}"
        )

# =============================================================================
# DB BACKUP
# =============================================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = DB.with_name(
    f"{DB.stem}.before_film10_human_sync_{stamp}{DB.suffix}"
)

shutil.copy2(
    DB,
    BACKUP,
)

print()
print("=" * 118)
print("DATABASE BACKUP")
print("=" * 118)

print(BACKUP)

# =============================================================================
# INSPECT REFERENCES BEFORE DELETE
# =============================================================================

conn = sqlite3.connect(
    str(DB)
)

conn.row_factory = sqlite3.Row

try:

    conn.execute(
        "PRAGMA foreign_keys=ON"
    )

    placeholders = ",".join(
        "?"
        for _ in missing_ids
    )

    current_missing_rows = conn.execute(
        f"""
        SELECT id, filename, path
        FROM assets
        WHERE project_id=?
          AND id IN ({placeholders})
        """,
        [PROJECT_ID, *missing_ids],
    ).fetchall()

    if len(current_missing_rows) != 17:
        raise RuntimeError(
            "Canonical DB changed since reconciliation. "
            f"Expected 17 deletion candidates, "
            f"found {len(current_missing_rows)}."
        )

    assigned_refs = conn.execute(
        f"""
        SELECT
            id,
            idx,
            assigned_asset_id
        FROM shots
        WHERE project_id=?
          AND assigned_asset_id IN ({placeholders})
        ORDER BY idx
        """,
        [PROJECT_ID, *missing_ids],
    ).fetchall()

    print()
    print("=" * 118)
    print("REFERENCES BEFORE DELETE")
    print("=" * 118)

    print(
        "SHOT REFERENCES TO REMOVED ASSETS:",
        len(assigned_refs),
    )

    # Current Film10 canonical state is expected to have
    # no assignments. If that changed, stop rather than
    # silently rewriting editorial decisions.
    if assigned_refs:

        for row in assigned_refs[:20]:
            print(
                "SHOT",
                row["idx"],
                "->",
                row["assigned_asset_id"],
            )

        raise RuntimeError(
            "Removed assets are currently assigned. "
            "Aborting before mutation."
        )

    # =============================================================
    # TRANSACTIONAL DELETE
    # =============================================================

    print()
    print("=" * 118)
    print("CANONICAL SYNC")
    print("=" * 118)

    conn.execute("BEGIN IMMEDIATE")

    before = conn.execute(
        """
        SELECT COUNT(*)
        FROM assets
        WHERE project_id=?
        """,
        (PROJECT_ID,),
    ).fetchone()[0]

    conn.execute(
        f"""
        DELETE FROM assets
        WHERE project_id=?
          AND id IN ({placeholders})
        """,
        [PROJECT_ID, *missing_ids],
    )

    after = conn.execute(
        """
        SELECT COUNT(*)
        FROM assets
        WHERE project_id=?
        """,
        (PROJECT_ID,),
    ).fetchone()[0]

    if before != 60:
        raise RuntimeError(
            f"Expected 60 assets before sync, got {before}"
        )

    if after != 43:
        raise RuntimeError(
            f"Expected 43 assets after sync, got {after}"
        )

    remaining_missing = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM assets
        WHERE project_id=?
          AND id IN ({placeholders})
        """,
        [PROJECT_ID, *missing_ids],
    ).fetchone()[0]

    if remaining_missing != 0:
        raise RuntimeError(
            "Deletion verification failed."
        )

    conn.commit()

    print("BEFORE :", before)
    print("REMOVED:", before - after)
    print("AFTER  :", after)
    print("COMMIT : YES")

except Exception:

    conn.rollback()

    print()
    print("TRANSACTION ROLLED BACK.")

    raise

finally:

    conn.close()

# =============================================================================
# LOAD REMAINING VIDEO ASSETS
# =============================================================================

uri = (
    DB.resolve().as_uri()
    + "?mode=ro"
)

conn = sqlite3.connect(
    uri,
    uri=True,
)

conn.row_factory = sqlite3.Row

try:

    remaining = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                id,
                path,
                filename,
                media_type,
                duration_sec,
                max_use,
                sha256
            FROM assets
            WHERE project_id=?
            ORDER BY filename
            """,
            (PROJECT_ID,),
        ).fetchall()

finally:
    conn.close()

videos = [
    row
    for row in remaining
    if str(
        row["media_type"]
    ).lower() == "video"
]

images = [
    row
    for row in remaining
    if str(
        row["media_type"]
    ).lower() != "video"
]

print()
print("=" * 118)
print("POST-SYNC CANONICAL CORPUS")
print("=" * 118)

print("TOTAL :", len(remaining))
print("VIDEOS:", len(videos))
print("IMAGES:", len(images))

if len(remaining) != 43:
    raise RuntimeError(
        "Post-sync corpus != 43."
    )

if len(videos) != 27:
    raise RuntimeError(
        f"Expected 27 videos, got {len(videos)}"
    )

# =============================================================================
# VIDEO SEGMENT INVENTORY
#
# IMPORTANT:
# These are candidate temporal windows, NOT assignments.
#
# Long videos are divided into non-overlapping windows so later
# editorial logic can use different parts of one source rather than
# replaying the beginning repeatedly.
# =============================================================================

def resolve_path(row):

    p = Path(
        str(row["path"])
    )

    if not p.is_absolute():
        p = ROOT / p

    return p.resolve()


def probe_duration(path):

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed: {path}"
        )

    return float(
        result.stdout.strip()
    )


def make_windows(duration):

    # Candidate editorial windows.
    # No visual meaning is assigned here.
    #
    # 8–12 second chunks are practical for documentary rough cutting,
    # while avoiding micro-shot explosion.

    if duration <= 12:
        return [(0.0, duration)]

    target = 10.0

    windows = []

    start = 0.0

    while start < duration:

        end = min(
            start + target,
            duration,
        )

        remaining = (
            duration - end
        )

        # Avoid tiny tail.
        if (
            remaining > 0
            and remaining < 4.0
            and windows
        ):
            prev_start, _ = windows[-1]

            windows[-1] = (
                prev_start,
                duration,
            )

            break

        windows.append(
            (start, end)
        )

        start = end

    return windows


segments = []

print()
print("=" * 118)
print("VIDEO SEGMENT INVENTORY")
print("=" * 118)

for asset_index, asset in enumerate(
    videos,
    1,
):

    path = resolve_path(
        asset
    )

    if not path.exists():
        raise FileNotFoundError(
            path
        )

    duration = probe_duration(
        path
    )

    windows = make_windows(
        duration
    )

    print(
        f"{asset_index:02d}/"
        f"{len(videos):02d} | "
        f"{duration:8.3f}s | "
        f"{len(windows):3d} windows | "
        f"{asset['filename']}"
    )

    for segment_index, (
        start,
        end,
    ) in enumerate(
        windows,
        1,
    ):

        raw = (
            f"{asset['id']}|"
            f"{start:.3f}|"
            f"{end:.3f}"
        )

        segment_id = (
            "seg_"
            + hashlib.sha1(
                raw.encode(
                    "utf-8"
                )
            ).hexdigest()[:16]
        )

        segments.append({
            "segment_id":
                segment_id,

            "asset_id":
                asset["id"],

            "filename":
                asset["filename"],

            "path":
                str(path),

            "source_start":
                round(start, 3),

            "source_end":
                round(end, 3),

            "duration_sec":
                round(
                    end - start,
                    3,
                ),

            "human_curated":
                True,

            "semantic_assignment":
                None,

            "editorial_status":
                "CANDIDATE",
        })

total_segment_time = sum(
    row["duration_sec"]
    for row in segments
)

print()
print("=" * 118)
print("SEGMENT SUMMARY")
print("=" * 118)

print(
    "SOURCE VIDEOS       :",
    len(videos),
)

print(
    "CANDIDATE SEGMENTS  :",
    len(segments),
)

print(
    "SEGMENT SOURCE TIME :",
    f"{total_segment_time:.3f}s",
)

m = int(
    total_segment_time // 60
)

s = (
    total_segment_time
    - m * 60
)

print(
    "SEGMENT SOURCE TC   :",
    f"{m:02d}:{s:06.3f}",
)

# =============================================================================
# REPORTS
# =============================================================================

SEGMENT_REPORT.write_text(
    json.dumps(
        {
            "schema":
                "atlas_zero.film10.video_segment_inventory.v1",

            "project_id":
                PROJECT_ID,

            "human_curated":
                True,

            "source_videos":
                len(videos),

            "segments":
                len(segments),

            "source_duration_sec":
                total_segment_time,

            "segment_inventory":
                segments,

            "assignment":
                False,

            "render":
                False,

            "paid_calls":
                False,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

SYNC_REPORT.write_text(
    json.dumps(
        {
            "schema":
                "atlas_zero.film10.canonical_corpus_sync.v1",

            "project_id":
                PROJECT_ID,

            "backup":
                str(BACKUP),

            "before":
                60,

            "removed":
                17,

            "after":
                43,

            "videos":
                len(videos),

            "images":
                len(images),

            "removed_asset_ids":
                missing_ids,

            "transaction_committed":
                True,

            "assignment":
                False,

            "render":
                False,

            "live_api":
                False,

            "paid_calls":
                False,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("=" * 118)
print("OUTPUT")
print("=" * 118)

print("SYNC REPORT   :", SYNC_REPORT)
print("SEGMENT REPORT:", SEGMENT_REPORT)
print("DB BACKUP     :", BACKUP)

print()
print("=" * 118)
print("FILM10 HUMAN-CURATED CORPUS SYNC: PASS")
print("=" * 118)

print("Canonical corpus now contains only human-retained assets.")
print("Video temporal segment inventory created.")
print("No semantic assignment performed.")
print("No render performed.")
print("No paid API calls.")
