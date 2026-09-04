from pathlib import Path
import sqlite3
import hashlib
import json

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT / "workspace" / "projects" / PROJECT_ID
)

DB_PATH = (
    ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"
)

CORPUS_REPORT = (
    PROJECT
    / "00_Production"
    / "human_curated_corpus_v1"
    / "FILM10_HUMAN_CURATED_CORPUS_V1.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "human_curated_corpus_v1"
)

OUT = (
    OUT_DIR
    / "FILM10_CANONICAL_CORPUS_RECONCILIATION_V1.json"
)

print("=" * 118)
print("ATLAS ZERO — FILM10 CANONICAL CORPUS RECONCILIATION V1")
print("=" * 118)

print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("MODE       : READ-ONLY")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

if not DB_PATH.exists():
    raise FileNotFoundError(DB_PATH)

if not CORPUS_REPORT.exists():
    raise FileNotFoundError(CORPUS_REPORT)

corpus = json.loads(
    CORPUS_REPORT.read_text(
        encoding="utf-8"
    )
)

fs_assets = corpus["assets"]

print()
print("=" * 118)
print("FILESYSTEM / HUMAN CURATED CORPUS")
print("=" * 118)

print("TOTAL :", len(fs_assets))
print(
    "VIDEO :",
    sum(
        1 for a in fs_assets
        if a["media_type"] == "video"
    )
)
print(
    "IMAGE :",
    sum(
        1 for a in fs_assets
        if a["media_type"] == "image"
    )
)

# =============================================================================
# CANONICAL DB — READ ONLY
# =============================================================================

uri = (
    DB_PATH.resolve().as_uri()
    + "?mode=ro"
)

conn = sqlite3.connect(
    uri,
    uri=True,
)

conn.row_factory = sqlite3.Row

try:

    rows = conn.execute(
        """
        SELECT
            id,
            project_id,
            path,
            filename,
            media_type,
            sha256,
            category,
            semantic_class,
            semantic_description,
            semantic_confidence,
            max_use,
            duplicate_of,
            duration_sec
        FROM assets
        WHERE project_id=?
        ORDER BY filename
        """,
        (PROJECT_ID,),
    ).fetchall()

finally:
    conn.close()

db_assets = [
    dict(row)
    for row in rows
]

print()
print("=" * 118)
print("CANONICAL DB")
print("=" * 118)

print("ASSETS:", len(db_assets))

# =============================================================================
# NORMALIZATION
# =============================================================================

def norm_path(value):

    try:
        p = Path(str(value))

        if not p.is_absolute():
            p = ROOT / p

        return str(
            p.resolve()
        ).lower()

    except Exception:
        return str(value).lower()


def sha256_file(path: Path):

    h = hashlib.sha256()

    with path.open("rb") as f:

        while True:

            chunk = f.read(
                1024 * 1024
            )

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


db_by_path = {
    norm_path(a["path"]): a
    for a in db_assets
}

db_by_sha = {}

for asset in db_assets:

    sha = asset.get("sha256")

    if sha:
        db_by_sha.setdefault(
            str(sha).lower(),
            [],
        ).append(asset)

# =============================================================================
# MATCH CURRENT FILESYSTEM -> DB
# =============================================================================

matched = []
filesystem_only = []

print()
print("=" * 118)
print("CURRENT FILES -> CANONICAL DB")
print("=" * 118)

for idx, fs in enumerate(
    fs_assets,
    1,
):

    path = Path(
        fs["path"]
    ).resolve()

    if not path.exists():

        filesystem_only.append({
            "filesystem":
                fs,

            "reason":
                "REPORT_PATH_NO_LONGER_EXISTS",
        })

        print(
            f"{idx:02d}/{len(fs_assets):02d} "
            f"MISSING_AFTER_REPORT | "
            f"{fs['filename']}"
        )

        continue

    key = norm_path(path)

    db = db_by_path.get(key)

    method = None
    calculated_sha = None

    if db is not None:

        method = "PATH"

    else:

        calculated_sha = (
            sha256_file(path)
        )

        candidates = db_by_sha.get(
            calculated_sha.lower(),
            [],
        )

        if len(candidates) == 1:

            db = candidates[0]
            method = "SHA256"

    if db is None:

        filesystem_only.append({
            "filesystem":
                fs,

            "sha256":
                calculated_sha,

            "reason":
                "NOT_IN_CANONICAL_DB",
        })

        print(
            f"{idx:02d}/{len(fs_assets):02d} "
            f"FS_ONLY            | "
            f"{fs['filename']}"
        )

    else:

        matched.append({
            "filesystem":
                fs,

            "db":
                db,

            "match_method":
                method,
        })

        print(
            f"{idx:02d}/{len(fs_assets):02d} "
            f"MATCH {method:<6} | "
            f"{fs['filename']} "
            f"| id={db['id']} "
            f"| max_use={db['max_use']}"
        )

# =============================================================================
# DB ASSETS WHOSE PHYSICAL FILE IS GONE
# =============================================================================

matched_db_ids = {
    str(row["db"]["id"])
    for row in matched
}

db_not_current = [
    asset
    for asset in db_assets
    if str(asset["id"])
    not in matched_db_ids
]

physically_missing_db = []

still_existing_but_not_matched = []

for asset in db_not_current:

    p = Path(
        str(asset["path"])
    )

    if not p.is_absolute():
        p = ROOT / p

    if p.exists():

        still_existing_but_not_matched.append(
            asset
        )

    else:

        physically_missing_db.append(
            asset
        )

print()
print("=" * 118)
print("RECONCILIATION SUMMARY")
print("=" * 118)

print(
    "CURRENT HUMAN-CURATED FILES :",
    len(fs_assets),
)

print(
    "MATCHED TO CANONICAL DB     :",
    len(matched),
)

print(
    "FILESYSTEM ONLY             :",
    len(filesystem_only),
)

print(
    "DB NOT IN CURRENT CORPUS    :",
    len(db_not_current),
)

print(
    "DB PHYSICALLY MISSING       :",
    len(physically_missing_db),
)

print(
    "DB EXISTS BUT NOT MATCHED   :",
    len(still_existing_but_not_matched),
)

print()
print("=" * 118)
print("REMOVED / PHYSICALLY MISSING CANONICAL ASSETS")
print("=" * 118)

if not physically_missing_db:

    print("NONE")

else:

    for asset in physically_missing_db:

        print(
            f"{asset['id']} | "
            f"{asset['media_type']:<6} | "
            f"{asset['filename']}"
        )

print()
print("=" * 118)
print("FILESYSTEM-ONLY ASSETS")
print("=" * 118)

if not filesystem_only:

    print("NONE")

else:

    for row in filesystem_only:

        fs = row["filesystem"]

        print(
            f"{fs['media_type']:<6} | "
            f"{fs['filename']} | "
            f"{row['reason']}"
        )

print()
print("=" * 118)
print("MAX_USE DISTRIBUTION — MATCHED ASSETS")
print("=" * 118)

distribution = {}

for row in matched:

    value = row["db"].get(
        "max_use"
    )

    distribution[
        str(value)
    ] = (
        distribution.get(
            str(value),
            0,
        )
        + 1
    )

for key in sorted(distribution):

    print(
        f"max_use={key:<8} "
        f"assets={distribution[key]}"
    )

# =============================================================================
# REPORT
# =============================================================================

report = {
    "schema":
        "atlas_zero.film10.canonical_corpus_reconciliation.v1",

    "project_id":
        PROJECT_ID,

    "human_curated_files":
        len(fs_assets),

    "canonical_db_assets":
        len(db_assets),

    "matched":
        len(matched),

    "filesystem_only":
        len(filesystem_only),

    "db_not_current":
        len(db_not_current),

    "db_physically_missing":
        len(physically_missing_db),

    "db_exists_but_not_matched":
        len(
            still_existing_but_not_matched
        ),

    "max_use_distribution":
        distribution,

    "matches":
        matched,

    "filesystem_only_assets":
        filesystem_only,

    "db_physically_missing_assets":
        physically_missing_db,

    "db_exists_but_not_matched_assets":
        still_existing_but_not_matched,

    "db_writes":
        False,

    "assignment":
        False,

    "render":
        False,

    "live_api":
        False,

    "paid_calls":
        False,
}

OUT.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)

print()
print("=" * 118)
print("REPORT")
print("=" * 118)

print(OUT)

print()
print("=" * 118)
print("RECONCILIATION V1 COMPLETE")
print("=" * 118)

print("No canonical DB writes.")
print("No semantic analysis.")
print("No assignments.")
print("No render.")
print("No paid API calls.")
