from pathlib import Path
import sqlite3
import json
import shutil
import subprocess
import hashlib
from datetime import datetime

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID
DB = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"

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

OUT_DIR.mkdir(parents=True, exist_ok=True)

SYNC_REPORT = OUT_DIR / "FILM10_CANONICAL_CORPUS_SYNC_V1.json"
SEGMENT_REPORT = OUT_DIR / "FILM10_VIDEO_SEGMENT_INVENTORY_V1.json"

print("=" * 118)
print("ATLAS ZERO — FILM10 HUMAN-CURATED CORPUS SYNC + VIDEO SEGMENT INVENTORY V1.1")
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

recon = json.loads(RECON.read_text(encoding="utf-8"))

# ----------------------------------------------------------------------
# SAFETY GATES
# ----------------------------------------------------------------------

print()
print("=" * 118)
print("SAFETY GATES")
print("=" * 118)

expected = {
    "human_curated_files": 43,
    "matched": 43,
    "filesystem_only": 0,
    "db_physically_missing": 17,
    "db_exists_but_not_matched": 0,
}

for key, expected_value in expected.items():
    actual = recon.get(key)

    print(
        f"{key:<30} "
        f"expected={expected_value:<3} "
        f"actual={actual}"
    )

    if actual != expected_value:
        raise RuntimeError(
            f"Safety gate failed: {key}: "
            f"expected {expected_value}, got {actual}"
        )

missing_rows = recon.get("db_physically_missing_assets", [])

if len(missing_rows) != 17:
    raise RuntimeError(
        f"Expected 17 physically missing assets, got {len(missing_rows)}"
    )

missing_ids = [str(row["id"]) for row in missing_rows]

if len(set(missing_ids)) != 17:
    raise RuntimeError("Missing asset IDs are not unique.")

# ----------------------------------------------------------------------
# REVERIFY FILE DELETIONS
# ----------------------------------------------------------------------

print()
print("=" * 118)
print("REVERIFY PHYSICAL DELETIONS")
print("=" * 118)

for row in missing_rows:
    p = Path(str(row["path"]))

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
            f"Refusing DB sync: deleted file exists again: {p}"
        )

# ----------------------------------------------------------------------
# CHECK CURRENT DB STATE BEFORE MUTATION
# ----------------------------------------------------------------------

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

try:
    asset_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM assets
        WHERE project_id=?
        """,
        (PROJECT_ID,),
    ).fetchone()[0]

    assigned_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM shots
        WHERE project_id=?
          AND assigned_asset_id IS NOT NULL
        """,
        (PROJECT_ID,),
    ).fetchone()[0]

finally:
    conn.close()

print()
print("=" * 118)
print("CURRENT CANONICAL STATE")
print("=" * 118)

print("ASSETS   :", asset_count)
print("ASSIGNED :", assigned_count)

if asset_count != 60:
    raise RuntimeError(
        f"Expected pre-sync asset count 60, got {asset_count}. "
        "No DB changes performed."
    )

if assigned_count != 0:
    raise RuntimeError(
        f"Expected 0 current Film10 assignments, got {assigned_count}. "
        "No DB changes performed."
    )

# ----------------------------------------------------------------------
# BACKUP
# ----------------------------------------------------------------------

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = DB.with_name(
    f"{DB.stem}.before_film10_human_sync_{stamp}{DB.suffix}"
)

shutil.copy2(DB, BACKUP)

print()
print("=" * 118)
print("DATABASE BACKUP")
print("=" * 118)
print(BACKUP)

# ----------------------------------------------------------------------
# TRANSACTIONAL CANONICAL SYNC
# ----------------------------------------------------------------------

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

try:
    conn.execute("PRAGMA foreign_keys=ON")

    placeholders = ",".join("?" for _ in missing_ids)

    candidates = conn.execute(
        f"""
        SELECT id, filename
        FROM assets
        WHERE project_id=?
          AND id IN ({placeholders})
        ORDER BY filename
        """,
        [PROJECT_ID, *missing_ids],
    ).fetchall()

    if len(candidates) != 17:
        raise RuntimeError(
            f"Expected 17 DB deletion candidates, got {len(candidates)}"
        )

    references = conn.execute(
        f"""
        SELECT id, idx, assigned_asset_id
        FROM shots
        WHERE project_id=?
          AND assigned_asset_id IN ({placeholders})
        """,
        [PROJECT_ID, *missing_ids],
    ).fetchall()

    if references:
        raise RuntimeError(
            f"Found {len(references)} shot references to deletion candidates."
        )

    print()
    print("=" * 118)
    print("CANONICAL DELETE CANDIDATES")
    print("=" * 118)

    for row in candidates:
        print(f"{row['id']} | {row['filename']}")

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
        raise RuntimeError(f"Unexpected BEFORE count: {before}")

    if after != 43:
        raise RuntimeError(f"Unexpected AFTER count: {after}")

    remaining_deleted = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM assets
        WHERE project_id=?
          AND id IN ({placeholders})
        """,
        [PROJECT_ID, *missing_ids],
    ).fetchone()[0]

    if remaining_deleted != 0:
        raise RuntimeError(
            f"{remaining_deleted} deletion candidates remain."
        )

    conn.commit()

except Exception:
    conn.rollback()
    print("TRANSACTION ROLLED BACK.")
    raise

finally:
    conn.close()

print()
print("=" * 118)
print("CANONICAL SYNC")
print("=" * 118)
print("BEFORE :", before)
print("REMOVED:", before - after)
print("AFTER  :", after)
print("COMMIT : YES")

# ----------------------------------------------------------------------
# LOAD CLEAN CANONICAL CORPUS READ-ONLY
# ----------------------------------------------------------------------

uri = DB.resolve().as_uri() + "?mode=ro"

conn = sqlite3.connect(uri, uri=True)
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
    ]

finally:
    conn.close()

videos = [
    row
    for row in remaining
    if str(row["media_type"]).lower() == "video"
]

images = [
    row
    for row in remaining
    if str(row["media_type"]).lower() != "video"
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
        f"Expected 43 post-sync assets, got {len(remaining)}"
    )

if len(videos) != 27:
    raise RuntimeError(
        f"Expected 27 videos, got {len(videos)}"
    )

if len(images) != 16:
    raise RuntimeError(
        f"Expected 16 images, got {len(images)}"
    )

# ----------------------------------------------------------------------
# VIDEO SEGMENT INVENTORY
# ----------------------------------------------------------------------

def resolve_asset_path(row):
    p = Path(str(row["path"]))

    if not p.is_absolute():
        p = ROOT / p

    return p.resolve()


def probe_duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for {path}\n{result.stderr}"
        )

    return float(result.stdout.strip())


def make_windows(duration):
    """
    Temporal candidate inventory only.

    Windows are NOT semantic assignments.
    They simply make different source regions addressable
    by the next editorial stage.
    """

    if duration <= 12.0:
        return [(0.0, duration)]

    target = 10.0
    windows = []
    start = 0.0

    while start < duration:
        end = min(start + target, duration)

        # Merge a tiny final remainder into the current segment.
        if duration - end < 4.0:
            end = duration

        windows.append((start, end))

        if end >= duration:
            break

        start = end

    return windows


segments = []

print()
print("=" * 118)
print("VIDEO TEMPORAL SEGMENT INVENTORY")
print("=" * 118)

for asset_index, asset in enumerate(videos, 1):
    path = resolve_asset_path(asset)

    if not path.exists():
        raise FileNotFoundError(path)

    duration = probe_duration(path)
    windows = make_windows(duration)

    print(
        f"{asset_index:02d}/{len(videos):02d} | "
        f"{duration:8.3f}s | "
        f"{len(windows):3d} segments | "
        f"{asset['filename']}"
    )

    for segment_index, (start, end) in enumerate(windows, 1):
        identity = (
            f"{asset['id']}|"
            f"{start:.3f}|"
            f"{end:.3f}"
        )

        segment_id = (
            "seg_"
            + hashlib.sha1(
                identity.encode("utf-8")
            ).hexdigest()[:16]
        )

        segments.append(
            {
                "segment_id": segment_id,
                "segment_index": segment_index,
                "asset_id": asset["id"],
                "filename": asset["filename"],
                "path": str(path),
                "source_start": round(start, 3),
                "source_end": round(end, 3),
                "duration_sec": round(end - start, 3),
                "human_curated": True,
                "semantic_assignment": None,
                "editorial_status": "CANDIDATE",
            }
        )

total_source_time = sum(
    segment["duration_sec"]
    for segment in segments
)

minutes = int(total_source_time // 60)
seconds = total_source_time - minutes * 60

print()
print("=" * 118)
print("SEGMENT SUMMARY")
print("=" * 118)
print("SOURCE VIDEOS      :", len(videos))
print("CANDIDATE SEGMENTS :", len(segments))
print("SOURCE TIME        :", f"{total_source_time:.3f}s")
print("SOURCE TC          :", f"{minutes:02d}:{seconds:06.3f}")

# ----------------------------------------------------------------------
# REPORTS
# ----------------------------------------------------------------------

sync_payload = {
    "schema": "atlas_zero.film10.canonical_corpus_sync.v1",
    "project_id": PROJECT_ID,
    "backup": str(BACKUP),
    "before": before,
    "removed": before - after,
    "after": after,
    "videos": len(videos),
    "images": len(images),
    "removed_asset_ids": missing_ids,
    "transaction_committed": True,
    "assignment": False,
    "render": False,
    "live_api": False,
    "paid_calls": False,
}

segment_payload = {
    "schema": "atlas_zero.film10.video_segment_inventory.v1",
    "project_id": PROJECT_ID,
    "human_curated": True,
    "source_videos": len(videos),
    "source_images": len(images),
    "segments": len(segments),
    "source_duration_sec": round(total_source_time, 3),
    "segment_inventory": segments,
    "assignment": False,
    "render": False,
    "live_api": False,
    "paid_calls": False,
}

SYNC_REPORT.write_text(
    json.dumps(
        sync_payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

SEGMENT_REPORT.write_text(
    json.dumps(
        segment_payload,
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
print("FILM10 HUMAN-CURATED CORPUS SYNC V1.1: PASS")
print("=" * 118)
print("Canonical corpus now contains only the 43 human-retained assets.")
print("Temporal inventory created for all 27 videos.")
print("No semantic assignment.")
print("No render.")
print("No paid API calls.")
