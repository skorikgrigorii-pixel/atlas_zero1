from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path


# =============================================================================
# ATLAS ZERO — FILM10 CANONICAL IMPORT V1.3
# =============================================================================

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID
DB_PATH = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"

TIMELINE_JSON = (
    PROJECT
    / "00_Production"
    / "rough_cut_v2"
    / "FILM10_ROUGH_CUT_TIMELINE_V2.json"
)

GAPS_JSON = (
    PROJECT
    / "00_Production"
    / "rough_cut_v2"
    / "FILM10_VISUAL_GAPS_V2.json"
)

OUT_ROOT = (
    PROJECT
    / "00_Production"
    / "canonical_import_v1"
)

OUT_ROOT.mkdir(parents=True, exist_ok=True)

REPORT_JSON = OUT_ROOT / "FILM10_CANONICAL_IMPORT_REPORT_V1_3.json"
SHOT_JSON = OUT_ROOT / "FILM10_CANONICAL_SHOTS_V1_3.json"
SCENE_JSON = OUT_ROOT / "FILM10_CANONICAL_SCENES_V1_3.json"
ASSET_JSON = OUT_ROOT / "FILM10_CANONICAL_ASSETS_V1_3.json"

VOICE_DURATION = 1607.517

VISUAL_ROOTS = [
    PROJECT
    / "00_Research"
    / "visual_research"
    / "social_downloads",

    PROJECT
    / "02_Visuals"
    / "real"
    / "archive",
]

VIDEO_EXT = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".m4v",
}

IMAGE_EXT = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
}

MEDIA_EXT = VIDEO_EXT | IMAGE_EXT


# =============================================================================
# HELPERS
# =============================================================================

def load_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def extract_records(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in (
        "shots",
        "timeline",
        "segments",
        "items",
        "records",
        "gaps",
    ):
        value = payload.get(key)

        if isinstance(value, list):
            return value

    for key in ("result", "data"):
        value = payload.get(key)

        if isinstance(value, dict):
            nested = extract_records(value)

            if nested:
                return nested

    return []


def first(obj, keys, default=None):
    if not isinstance(obj, dict):
        return default

    for key in keys:
        if key in obj:
            value = obj[key]

            if value not in (None, ""):
                return value

    return default


def as_float(value, default=0.0):
    try:
        return float(value)

    except (TypeError, ValueError):
        return float(default)


def sha256_file(path: Path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def asset_id_from_hash(digest: str):
    raw = PROJECT_ID + "\0" + digest

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]


def ffprobe_media(path: Path):
    result = {
        "width": 0,
        "height": 0,
        "duration_sec": 0.0,
    }

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,duration",
        "-of",
        "json",
        str(path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        if proc.returncode != 0:
            return result

        payload = json.loads(
            proc.stdout or "{}"
        )

        for stream in payload.get("streams") or []:
            if stream.get("codec_type") != "video":
                continue

            result["width"] = int(
                stream.get("width") or 0
            )

            result["height"] = int(
                stream.get("height") or 0
            )

            stream_duration = as_float(
                stream.get("duration"),
                0.0,
            )

            if stream_duration > 0:
                result["duration_sec"] = stream_duration

            break

        format_duration = as_float(
            (payload.get("format") or {}).get(
                "duration"
            ),
            0.0,
        )

        if format_duration > 0:
            result["duration_sec"] = format_duration

    except Exception:
        pass

    return result


def normalize_category(value):
    text = str(
        value or ""
    ).strip().upper()

    known = {
        "DRONE_COLLAPSE",
        "SCHOOL",
        "GYIRONG",
        "HYDROPOWER",
        "FLOOD_DESTRUCTION",
        "MAP_SCIENCE",
        "RIVER",
        "SECONDARY_LAKE",
        "GENERAL_CONTEXT",
    }

    if text in known:
        return text

    return "GENERAL_CONTEXT"


def infer_visual_need(narration: str, category: str):
    n = str(
        narration or ""
    ).lower()

    rules = [
        (
            (
                "школ",
                "ученик",
                "учител",
                "автобус",
            ),
            "SCHOOL_EVACUATION_BIDUR",
        ),

        (
            (
                "дрон",
                "съёмк",
                "обруш",
                "ледник",
            ),
            "DRONE_COLLAPSE_LANGTANG_LIRUNG",
        ),

        (
            (
                "гиронг",
                "gyirong",
                "kyirong",
                "тибет",
                "границ",
            ),
            "GYIRONG_TIBET_BORDER_DISASTER",
        ),

        (
            (
                "гэс",
                "гидроэлект",
                "электростанц",
                "туннел",
            ),
            "HYDROPOWER_TUNNEL_RESCUE",
        ),

        (
            (
                "озер",
                "плотин",
                "дамб",
            ),
            "SECONDARY_LAKE_NATURAL_DAM",
        ),

        (
            (
                "карта",
                "100 км",
                "сто килом",
                "маршрут",
            ),
            "MAP_DISASTER_PROPAGATION_ROUTE",
        ),

        (
            (
                "спутник",
                "landsat",
                "sentinel",
                "usgs",
            ),
            "SATELLITE_SCIENCE_EVIDENCE",
        ),

        (
            (
                "река",
                "кхола",
                "bhote",
                "trishuli",
                "тришули",
            ),
            "RIVER_CHANNEL_DEBRIS_FLOW",
        ),

        (
            (
                "поток",
                "наводнен",
                "сел",
                "гряз",
                "разруш",
            ),
            "FLOOD_DEBRIS_DESTRUCTION",
        ),

        (
            (
                "лангтанг",
                "лирунг",
                "склон",
                "ледник",
                "скал",
                "гора",
            ),
            "LANGTANG_LIRUNG_MOUNTAIN_CONTEXT",
        ),
    ]

    for needles, visual_need in rules:
        if any(
            needle in n
            for needle in needles
        ):
            return visual_need

    mapping = {
        "DRONE_COLLAPSE":
            "DRONE_COLLAPSE_LANGTANG_LIRUNG",

        "SCHOOL":
            "SCHOOL_EVACUATION_BIDUR",

        "GYIRONG":
            "GYIRONG_TIBET_BORDER_DISASTER",

        "HYDROPOWER":
            "HYDROPOWER_TUNNEL_RESCUE",

        "FLOOD_DESTRUCTION":
            "FLOOD_DEBRIS_DESTRUCTION",

        "MAP_SCIENCE":
            "MAP_SATELLITE_SCIENCE",

        "RIVER":
            "RIVER_CHANNEL_DEBRIS_FLOW",

        "SECONDARY_LAKE":
            "SECONDARY_LAKE_NATURAL_DAM",

        "GENERAL_CONTEXT":
            "NEPAL_TIBET_DISASTER_CONTEXT",
    }

    return mapping[category]


def visual_group_from_path(path: Path):
    low = str(path).lower()

    if "social_downloads" in low:
        parts = list(path.parts)

        parts_low = [
            p.lower()
            for p in parts
        ]

        try:
            idx = parts_low.index(
                "social_downloads"
            )

            if idx + 1 < len(parts):
                return (
                    "social:"
                    + parts[idx + 1]
                )

        except ValueError:
            pass

        return "social_research"

    if (
        "\\archive\\" in low
        or "/archive/" in low
    ):
        return "archive"

    return "film10_corpus"


def table_exists(conn, table):
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        """,
        (table,),
    ).fetchone()

    return int(row["n"]) == 1


def project_count(conn, table):
    if not table_exists(conn, table):
        return None

    columns = {
        row["name"]
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }

    if "project_id" not in columns:
        return None

    row = conn.execute(
        f"""
        SELECT COUNT(*) AS n
        FROM {table}
        WHERE project_id=?
        """,
        (PROJECT_ID,),
    ).fetchone()

    return int(row["n"])


# =============================================================================
# PREFLIGHT
# =============================================================================

print("=" * 120)
print("ATLAS ZERO — FILM10 CANONICAL IMPORT V1.3")
print("=" * 120)

print("ROOT       :", ROOT)
print("PROJECT    :", PROJECT)
print("DATABASE   :", DB_PATH)
print("LIVE API   : 0")
print("PAID CALLS : 0")

print()
print("=" * 120)
print("PREFLIGHT")
print("=" * 120)

required_paths = [
    ("DATABASE", DB_PATH),
    ("TIMELINE", TIMELINE_JSON),
    ("GAPS", GAPS_JSON),
]

for label, path in required_paths:
    state = (
        "OK"
        if path.exists()
        else "MISSING"
    )

    print(
        "{:<14}: {} | {}".format(
            label,
            state,
            path,
        )
    )

    if not path.exists():
        raise FileNotFoundError(path)


for root in VISUAL_ROOTS:
    state = (
        "OK"
        if root.exists()
        else "MISSING"
    )

    print(
        "{:<14}: {} | {}".format(
            "VISUAL ROOT",
            state,
            root,
        )
    )

    if not root.exists():
        raise FileNotFoundError(root)


# =============================================================================
# LOAD V2 EDITORIAL TIMELINE
# =============================================================================

timeline_payload = load_json(
    TIMELINE_JSON
)

gaps_payload = load_json(
    GAPS_JSON
)

timeline = extract_records(
    timeline_payload
)

gaps = extract_records(
    gaps_payload
)

print()
print("TIMELINE RECORDS :", len(timeline))
print("GAP RECORDS      :", len(gaps))

if len(timeline) != 260:
    print()
    print("FIRST TIMELINE RECORD KEYS:")

    if timeline:
        print(
            sorted(
                timeline[0].keys()
            )
        )

    raise RuntimeError(
        "Expected 260 timeline records; "
        "found {}".format(
            len(timeline)
        )
    )


# =============================================================================
# NORMALIZE SHOTS
# =============================================================================

shots = []

for idx, row in enumerate(
    timeline,
    start=1,
):
    start_sec = as_float(
        first(
            row,
            (
                "start_sec",
                "start",
                "timeline_start_sec",
                "in_sec",
            ),
            0.0,
        )
    )

    end_sec = as_float(
        first(
            row,
            (
                "end_sec",
                "end",
                "timeline_end_sec",
                "out_sec",
            ),
            start_sec,
        )
    )

    narration = str(
        first(
            row,
            (
                "narration",
                "narration_text",
                "text",
                "voice_text",
                "script_text",
                "story_goal",
            ),
            "",
        )
        or ""
    ).strip()

    category = normalize_category(
        first(
            row,
            (
                "semantic_category",
                "category",
                "visual_category",
                "need_category",
            ),
            "GENERAL_CONTEXT",
        )
    )

    beat_id = str(
        first(
            row,
            (
                "beat_id",
                "semantic_beat_id",
                "source_beat_id",
                "block",
            ),
            "",
        )
        or ""
    ).strip()

    if end_sec <= start_sec:
        raise RuntimeError(
            "Invalid shot timing #{}: "
            "{} -> {}".format(
                idx,
                start_sec,
                end_sec,
            )
        )

    shots.append(
        {
            "id":
                "{}_shot_{:04d}".format(
                    PROJECT_ID,
                    idx,
                ),

            "idx":
                idx,

            "start_sec":
                round(
                    start_sec,
                    6,
                ),

            "end_sec":
                round(
                    end_sec,
                    6,
                ),

            "duration_sec":
                round(
                    end_sec - start_sec,
                    6,
                ),

            "beat_id":
                beat_id,

            "story_goal":
                narration,

            "narration":
                narration,

            "semantic_category":
                category,

            "visual_need":
                infer_visual_need(
                    narration,
                    category,
                ),

            "status":
                "missing",

            "assigned_asset_id":
                None,

            "transition":
                "dissolve",

            "camera_motion":
                "slow push-in",
        }
    )


nonempty_story_goals = sum(
    1
    for shot in shots
    if shot["story_goal"].strip()
)

visual_duration = sum(
    shot["duration_sec"]
    for shot in shots
)

duration_delta = abs(
    visual_duration
    - VOICE_DURATION
)

print()
print("=" * 120)
print("SHOT NORMALIZATION")
print("=" * 120)

print("SHOTS                 :", len(shots))
print("NONEMPTY STORY GOALS  :", nonempty_story_goals)
print(
    "VISUAL DURATION       : {:.6f}".format(
        visual_duration
    )
)
print(
    "VOICE DURATION        : {:.6f}".format(
        VOICE_DURATION
    )
)
print(
    "DURATION DELTA        : {:.6f}".format(
        duration_delta
    )
)


if nonempty_story_goals < 250:
    print()
    print("FIRST TIMELINE RECORD:")
    print(
        json.dumps(
            timeline[0],
            ensure_ascii=False,
            indent=2,
        )
    )

    raise RuntimeError(
        "Narration/story_goal extraction failed. "
        "Only {} of 260 shots contain text.".format(
            nonempty_story_goals
        )
    )


if duration_delta > 0.03:
    raise RuntimeError(
        "Duration gate failed. "
        "Delta={:.6f}".format(
            duration_delta
        )
    )


# =============================================================================
# BUILD STORY SCENES FROM BEATS
# =============================================================================

scene_groups = []
current = None

for shot in shots:
    if shot["beat_id"]:
        group_key = (
            "BEAT::"
            + shot["beat_id"]
        )

    else:
        group_key = (
            "NARRATION::"
            + shot["narration"][:180]
        )

    if (
        current is None
        or current["group_key"] != group_key
    ):
        current = {
            "group_key": group_key,
            "shots": [],
        }

        scene_groups.append(
            current
        )

    current["shots"].append(
        shot
    )


scenes = []

for scene_idx, group in enumerate(
    scene_groups,
    start=1,
):
    scene_shots = group["shots"]

    first_shot = scene_shots[0]
    last_shot = scene_shots[-1]

    category_counts = Counter(
        shot["semantic_category"]
        for shot in scene_shots
    )

    dominant_category = (
        category_counts
        .most_common(1)[0][0]
    )

    narration_parts = []

    for shot in scene_shots:
        text = shot["narration"].strip()

        if (
            text
            and text not in narration_parts
        ):
            narration_parts.append(
                text
            )

    narration = " ".join(
        narration_parts
    )

    scenes.append(
        {
            "id":
                "{}_SC{:03d}".format(
                    PROJECT_ID,
                    scene_idx,
                ),

            "idx":
                scene_idx,

            "block":
                first_shot["beat_id"]
                or "BEAT_{:03d}".format(
                    scene_idx
                ),

            "title":
                dominant_category,

            "start_sec":
                first_shot["start_sec"],

            "end_sec":
                last_shot["end_sec"],

            "duration_sec":
                round(
                    last_shot["end_sec"]
                    - first_shot["start_sec"],
                    6,
                ),

            "target_shots":
                len(scene_shots),

            "narrative_goal":
                narration,

            "emotional_goal":
                "documentary",

            "visual_strategy":
                (
                    "Strict narration-to-image semantic alignment. "
                    "If no valid event-relevant visual exists, "
                    "preserve a missing visual gap."
                ),

            "required_assets":
                json.dumps(
                    {
                        "asset_ids": [],
                        "cluster_ids": [],
                        "use_existing_assets_only":
                            False,
                    },
                    ensure_ascii=False,
                ),

            "status":
                "planned",

            "coverage":
                0.0,
        }
    )


print("CANONICAL SCENES      :", len(scenes))

if not (
    50
    <= len(scenes)
    <= 120
):
    raise RuntimeError(
        "Scene count sanity gate failed. "
        "Expected approximately semantic beats "
        "(50..120); got {}".format(
            len(scenes)
        )
    )


# =============================================================================
# BUILD EXACT FILM10 CORPUS
# =============================================================================

media_paths = []

for root in VISUAL_ROOTS:
    for path in root.rglob("*"):
        if (
            path.is_file()
            and path.suffix.lower()
            in MEDIA_EXT
        ):
            media_paths.append(
                path.resolve()
            )


media_paths = sorted(
    set(media_paths),
    key=lambda p: str(p).lower(),
)

print()
print("=" * 120)
print("FILM10 VISUAL CORPUS")
print("=" * 120)

print("MEDIA FILES          :", len(media_paths))

if len(media_paths) != 60:
    print()

    for root in VISUAL_ROOTS:
        count = sum(
            1
            for p in root.rglob("*")
            if (
                p.is_file()
                and p.suffix.lower()
                in MEDIA_EXT
            )
        )

        print(
            "{} -> {}".format(
                root,
                count,
            )
        )

    raise RuntimeError(
        "Expected exactly 60 Film10 corpus media files; "
        "found {}".format(
            len(media_paths)
        )
    )


assets = []
hash_seen = {}

for asset_index, path in enumerate(
    media_paths,
    start=1,
):
    digest = sha256_file(
        path
    )

    asset_id = asset_id_from_hash(
        digest
    )

    duplicate_of = hash_seen.get(
        digest
    )

    if duplicate_of is None:
        hash_seen[digest] = asset_id

    media_type = (
        "video"
        if path.suffix.lower()
        in VIDEO_EXT
        else "image"
    )

    meta = ffprobe_media(
        path
    )

    assets.append(
        {
            "id":
                asset_id,

            "project_id":
                PROJECT_ID,

            "path":
                str(path),

            "filename":
                path.name,

            "media_type":
                media_type,

            "sha256":
                digest,

            "category":
                "film10_candidate",

            "tags":
                "[]",

            "emotion":
                "neutral",

            "quality":
                0.55,

            "width":
                int(
                    meta["width"]
                ),

            "height":
                int(
                    meta["height"]
                ),

            "duration_sec":
                round(
                    float(
                        meta["duration_sec"]
                    ),
                    6,
                ),

            "duplicate_of":
                duplicate_of,

            "semantic_class":
                None,

            "semantic_description":
                None,

            "visual_group":
                visual_group_from_path(
                    path
                ),

            "perceptual_hash":
                None,

            "semantic_confidence":
                0.0,

            "max_use":
                3,
        }
    )


duplicates = [
    asset
    for asset in assets
    if asset["duplicate_of"]
]

asset_ids = [
    asset["id"]
    for asset in assets
]

if len(set(asset_ids)) != len(asset_ids):
    raise RuntimeError(
        "Project-scoped asset ID collision detected."
    )


print("ASSETS BUILT         :", len(assets))
print("HASH DUPLICATES      :", len(duplicates))
print("PROJECT-SCOPED IDS   : PASS")


# =============================================================================
# SAVE NORMALIZED SNAPSHOTS BEFORE DB MUTATION
# =============================================================================

SHOT_JSON.write_text(
    json.dumps(
        shots,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

SCENE_JSON.write_text(
    json.dumps(
        scenes,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

ASSET_JSON.write_text(
    json.dumps(
        assets,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


# =============================================================================
# DATABASE IMPORT
# =============================================================================

conn = sqlite3.connect(
    str(DB_PATH)
)

conn.row_factory = sqlite3.Row


try:
    # -------------------------------------------------------------------------
    # Check production state
    # -------------------------------------------------------------------------

    existing = {}

    existing["projects"] = int(
        conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM projects
            WHERE id=?
            """,
            (PROJECT_ID,),
        ).fetchone()["n"]
    )

    for table in (
        "shots",
        "story_scenes",
        "assets",
    ):
        existing[table] = int(
            conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM {}
                WHERE project_id=?
                """.format(table),
                (PROJECT_ID,),
            ).fetchone()["n"]
        )


    print()
    print("=" * 120)
    print("PRE-IMPORT DATABASE STATE")
    print("=" * 120)

    for table, count in existing.items():
        print(
            "{:<20}: {}".format(
                table,
                count,
            )
        )


    completely_empty = (
        existing["projects"] == 0
        and existing["shots"] == 0
        and existing["story_scenes"] == 0
        and existing["assets"] == 0
    )

    already_complete = (
        existing["projects"] == 1
        and existing["shots"] == 260
        and existing["story_scenes"] == len(scenes)
        and existing["assets"] == 60
    )


    if already_complete:
        print()
        print(
            "Canonical Film10 production state "
            "already exists."
        )
        print(
            "No production mutation performed."
        )

    elif not completely_empty:
        raise RuntimeError(
            "PARTIAL_FILM10_CANONICAL_STATE detected: "
            + json.dumps(
                existing,
                ensure_ascii=False,
            )
            + ". No mutation performed."
        )

    else:
        # ---------------------------------------------------------------------
        # Collision check before BEGIN
        # ---------------------------------------------------------------------

        placeholders = ",".join(
            "?"
            for _ in asset_ids
        )

        collision_rows = conn.execute(
            """
            SELECT
                id,
                project_id,
                sha256
            FROM assets
            WHERE id IN ({})
            """.format(
                placeholders
            ),
            asset_ids,
        ).fetchall()

        bad_collisions = [
            dict(row)
            for row in collision_rows
            if row["project_id"] != PROJECT_ID
        ]

        if bad_collisions:
            raise RuntimeError(
                "Global asset ID collision detected before import: "
                + json.dumps(
                    bad_collisions,
                    ensure_ascii=False,
                )
            )


        # ---------------------------------------------------------------------
        # Atomic transaction
        # ---------------------------------------------------------------------

        conn.execute(
            "BEGIN IMMEDIATE"
        )

        try:
            conn.execute(
                """
                INSERT INTO projects(
                    id,
                    title,
                    status,
                    duration_sec
                )
                VALUES(
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    PROJECT_ID,
                    "Film 10 — Nepal/Tibet Aftershock",
                    "active",
                    VOICE_DURATION,
                ),
            )


            conn.executemany(
                """
                INSERT INTO story_scenes(
                    id,
                    project_id,
                    idx,
                    block,
                    title,
                    start_sec,
                    end_sec,
                    duration_sec,
                    target_shots,
                    narrative_goal,
                    emotional_goal,
                    visual_strategy,
                    required_assets,
                    status,
                    coverage
                )
                VALUES(
                    ?,?,?,?,?,?,
                    ?,?,?,?,?,?,
                    ?,?,?
                )
                """,
                [
                    (
                        scene["id"],
                        PROJECT_ID,
                        scene["idx"],
                        scene["block"],
                        scene["title"],
                        scene["start_sec"],
                        scene["end_sec"],
                        scene["duration_sec"],
                        scene["target_shots"],
                        scene["narrative_goal"],
                        scene["emotional_goal"],
                        scene["visual_strategy"],
                        scene["required_assets"],
                        scene["status"],
                        scene["coverage"],
                    )
                    for scene in scenes
                ],
            )


            conn.executemany(
                """
                INSERT INTO shots(
                    id,
                    project_id,
                    idx,
                    start_sec,
                    end_sec,
                    block,
                    story_goal,
                    visual_need,
                    emotion,
                    status,
                    assigned_asset_id,
                    transition,
                    camera_motion
                )
                VALUES(
                    ?,?,?,?,?,?,
                    ?,?,?,?,?,?,
                    ?
                )
                """,
                [
                    (
                        shot["id"],
                        PROJECT_ID,
                        shot["idx"],
                        shot["start_sec"],
                        shot["end_sec"],
                        shot["beat_id"],
                        shot["story_goal"],
                        shot["visual_need"],
                        "documentary",
                        "missing",
                        None,
                        shot["transition"],
                        shot["camera_motion"],
                    )
                    for shot in shots
                ],
            )


            conn.executemany(
                """
                INSERT INTO assets(
                    id,
                    project_id,
                    path,
                    filename,
                    media_type,
                    sha256,
                    category,
                    tags,
                    emotion,
                    quality,
                    width,
                    height,
                    duration_sec,
                    duplicate_of,
                    semantic_class,
                    semantic_description,
                    visual_group,
                    perceptual_hash,
                    semantic_confidence,
                    max_use
                )
                VALUES(
                    ?,?,?,?,?,?,
                    ?,?,?,?,?,?,
                    ?,?,?,?,?,?,
                    ?,?
                )
                """,
                [
                    (
                        asset["id"],
                        PROJECT_ID,
                        asset["path"],
                        asset["filename"],
                        asset["media_type"],
                        asset["sha256"],
                        asset["category"],
                        asset["tags"],
                        asset["emotion"],
                        asset["quality"],
                        asset["width"],
                        asset["height"],
                        asset["duration_sec"],
                        asset["duplicate_of"],
                        asset["semantic_class"],
                        asset["semantic_description"],
                        asset["visual_group"],
                        asset["perceptual_hash"],
                        asset["semantic_confidence"],
                        asset["max_use"],
                    )
                    for asset in assets
                ],
            )


            conn.commit()

        except Exception:
            conn.rollback()
            raise


        print()
        print("DATABASE TRANSACTION : COMMITTED")


    # =========================================================================
    # VERIFY CANONICAL STATE
    # =========================================================================

    counts = {}

    counts["projects"] = int(
        conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM projects
            WHERE id=?
            """,
            (PROJECT_ID,),
        ).fetchone()["n"]
    )

    for table in (
        "shots",
        "story_scenes",
        "assets",
    ):
        counts[table] = int(
            conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM {}
                WHERE project_id=?
                """.format(table),
                (PROJECT_ID,),
            ).fetchone()["n"]
        )


    assigned_count = int(
        conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM shots
            WHERE project_id=?
              AND assigned_asset_id IS NOT NULL
            """,
            (PROJECT_ID,),
        ).fetchone()["n"]
    )


    missing_count = int(
        conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM shots
            WHERE project_id=?
              AND status='missing'
            """,
            (PROJECT_ID,),
        ).fetchone()["n"]
    )


    empty_story_goals_db = int(
        conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM shots
            WHERE project_id=?
              AND (
                    story_goal IS NULL
                    OR TRIM(story_goal)=''
                  )
            """,
            (PROJECT_ID,),
        ).fetchone()["n"]
    )


    # =========================================================================
    # VERIFY LEARNING STATE WITHOUT ASSUMING SCHEMA
    # =========================================================================

    learning_counts = {}

    for table in (
        "learning_observations",
        "learning_profiles",
        "director_learning_advisories",
        "director_learning_cycles",
    ):
        value = project_count(
            conn,
            table,
        )

        learning_counts[table] = value


    print()
    print("=" * 120)
    print("CANONICAL STATE")
    print("=" * 120)

    for name, value in counts.items():
        print(
            "{:<34}: {}".format(
                name,
                value,
            )
        )

    print(
        "{:<34}: {}".format(
            "assigned shots",
            assigned_count,
        )
    )

    print(
        "{:<34}: {}".format(
            "missing shots",
            missing_count,
        )
    )

    print(
        "{:<34}: {}".format(
            "empty story goals",
            empty_story_goals_db,
        )
    )


    print()
    print("=" * 120)
    print("LEARNING STATE")
    print("=" * 120)

    for name, value in learning_counts.items():
        print(
            "{:<34}: {}".format(
                name,
                (
                    value
                    if value is not None
                    else "NO_PROJECT_ID_COLUMN"
                ),
            )
        )


    # =========================================================================
    # GATES
    # =========================================================================

    gates = {
        "project_registered":
            counts["projects"] == 1,

        "shots_260":
            counts["shots"] == 260,

        "assets_60":
            counts["assets"] == 60,

        "scene_count_matches":
            counts["story_scenes"] == len(scenes),

        "scene_count_sane":
            50 <= counts["story_scenes"] <= 120,

        "zero_fake_assignments":
            assigned_count == 0,

        "all_shots_missing":
            missing_count == 260,

        "story_goals_present":
            empty_story_goals_db == 0,

        "duration_exact":
            duration_delta <= 0.03,

        "learning_observations_preserved":
            (
                learning_counts["learning_observations"]
                is None
                or learning_counts["learning_observations"] >= 5
            ),

        "learning_profiles_preserved":
            (
                learning_counts["learning_profiles"]
                is None
                or learning_counts["learning_profiles"] >= 5
            ),

        "advisory_preserved":
            (
                learning_counts["director_learning_advisories"]
                is None
                or learning_counts["director_learning_advisories"] >= 1
            ),

        "learning_cycle_preserved":
            (
                learning_counts["director_learning_cycles"]
                is None
                or learning_counts["director_learning_cycles"] >= 1
            ),
    }


    print()
    print("=" * 120)
    print("IMPORT GATES")
    print("=" * 120)

    failed = []

    for name, ok in gates.items():
        state = (
            "PASS"
            if ok
            else "FAIL"
        )

        print(
            "{:<42}: {}".format(
                name,
                state,
            )
        )

        if not ok:
            failed.append(
                name
            )


    report = {
        "schema":
            "atlas_zero.film10_canonical_import.v1.3",

        "state":
            (
                "PASS"
                if not failed
                else "FAIL"
            ),

        "project_id":
            PROJECT_ID,

        "database":
            str(DB_PATH),

        "voice_duration_sec":
            VOICE_DURATION,

        "visual_duration_sec":
            visual_duration,

        "duration_delta_sec":
            duration_delta,

        "timeline_records":
            len(timeline),

        "gap_records":
            len(gaps),

        "nonempty_story_goals":
            nonempty_story_goals,

        "scene_count":
            len(scenes),

        "asset_count":
            len(assets),

        "hash_duplicates":
            len(duplicates),

        "counts":
            counts,

        "learning_counts":
            learning_counts,

        "assigned_shots":
            assigned_count,

        "missing_shots":
            missing_count,

        "empty_story_goals_db":
            empty_story_goals_db,

        "gates":
            gates,

        "policy":
            {
                "v2_fallback_assignments_imported":
                    False,

                "all_canonical_shots_begin_missing":
                    True,

                "random_fallback_allowed":
                    False,

                "semantic_analysis_pending":
                    True,

                "assignment_pending":
                    True,

                "render_pending":
                    True,

                "paid_api_calls":
                    False,
            },
    }


    REPORT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


    if failed:
        raise RuntimeError(
            "CANONICAL IMPORT GATES FAILED: "
            + ", ".join(
                failed
            )
        )


finally:
    conn.close()


# =============================================================================
# SUCCESS
# =============================================================================

print()
print("=" * 120)
print("FILM10 CANONICAL IMPORT V1.3: PASS")
print("=" * 120)

print("SHOTS  :", SHOT_JSON)
print("SCENES :", SCENE_JSON)
print("ASSETS :", ASSET_JSON)
print("REPORT :", REPORT_JSON)

print()
print(
    "NEXT: canonical VisualSemanticAnalyzerRC2 "
    "on Film10 60-asset corpus. NO RENDER."
)
