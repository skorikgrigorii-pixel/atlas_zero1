from pathlib import Path
import sqlite3
import json
import re
from collections import Counter, defaultdict

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

V1 = (
    PROJECT
    / "00_Production"
    / "human_editorial_assignment_v1"
    / "FILM10_HUMAN_EDITORIAL_TIMELINE_V1.json"
)

GT = (
    PROJECT
    / "00_Production"
    / "human_editorial_ground_truth_v1"
    / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_V1.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "human_editorial_assignment_v2"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TIMELINE_OUT = (
    OUT_DIR
    / "FILM10_HUMAN_EDITORIAL_TIMELINE_V2.json"
)

GAPS_OUT = (
    OUT_DIR
    / "FILM10_HUMAN_EDITORIAL_GAPS_V2.json"
)

REPORT_OUT = (
    OUT_DIR
    / "FILM10_HUMAN_EDITORIAL_ASSIGNMENT_REPORT_V2.json"
)

print("=" * 126)
print("ATLAS ZERO — FILM10 HUMAN EDITORIAL ASSIGNMENT V2")
print("=" * 126)

print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("CLIP       : NO")
print("DB WRITES  : NO")
print("RENDER     : NO")

for path in (
    DB,
    V1,
    GT,
):
    if not path.exists():
        raise FileNotFoundError(path)

# =============================================================================
# LOAD V1
# =============================================================================

v1_payload = json.loads(
    V1.read_text(
        encoding="utf-8"
    )
)

timeline = v1_payload.get(
    "timeline",
    []
)

if len(timeline) != 260:
    raise RuntimeError(
        f"Expected 260 V1 rows, got {len(timeline)}"
    )

# =============================================================================
# HUMAN GROUND TRUTH
# =============================================================================

gt = json.loads(
    GT.read_text(
        encoding="utf-8"
    )
)

fragments = {
    int(row["review_number"]): row
    for row in gt.get(
        "fragments",
        []
    )
}

if len(fragments) != 153:
    raise RuntimeError(
        f"Expected 153 reviewed fragments, got {len(fragments)}"
    )

# =============================================================================
# LOAD CANONICAL IMAGES
# =============================================================================

uri = DB.resolve().as_uri() + "?mode=ro"

conn = sqlite3.connect(
    uri,
    uri=True,
)

conn.row_factory = sqlite3.Row

try:

    images = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                id,
                path,
                filename,
                media_type,
                category,
                tags,
                semantic_class,
                semantic_description,
                width,
                height,
                max_use
            FROM assets
            WHERE project_id=?
              AND LOWER(media_type) != 'video'
            ORDER BY filename
            """,
            (PROJECT_ID,),
        ).fetchall()
    ]

finally:
    conn.close()

print()
print("=" * 126)
print("CANONICAL STATIC VISUALS")
print("=" * 126)

print("IMAGES:", len(images))

for idx, image in enumerate(
    images,
    1,
):

    print(
        f"{idx:02d} | "
        f"{image['filename']} | "
        f"category={image.get('category')} | "
        f"class={image.get('semantic_class')}"
    )

# =============================================================================
# SAFE IMAGE CLASSIFICATION
#
# Filename/category based.
# We deliberately DO NOT trust old CLIP relevance here.
# =============================================================================

def norm(value):

    return re.sub(
        r"[^a-zа-я0-9]+",
        " ",
        str(value or "").lower()
    ).strip()


def image_text(image):

    return " ".join(
        norm(
            image.get(key)
        )
        for key in (
            "filename",
            "category",
            "tags",
            "semantic_description",
        )
    )


def has(
    text,
    *terms,
):

    return any(
        term in text
        for term in terms
    )


def image_category(image):

    text = image_text(
        image
    )

    if has(
        text,
        "satellite",
        "sentinel",
        "landsat",
        "nasa",
        "iss",
        "earth observ",
    ):
        return "MAP_SATELLITE"

    if has(
        text,
        "map",
        "location",
        "route",
        "basin",
    ):
        return "MAP_SATELLITE"

    if has(
        text,
        "before after",
        "before_after",
        "comparison",
    ):
        return "BEFORE_AFTER"

    if has(
        text,
        "langtang",
        "lirung",
        "glacier",
        "himalaya",
        "mountain",
    ):
        return "GLACIER_CONTEXT"

    if has(
        text,
        "gyirong",
        "kyirong",
        "border",
    ):
        return "GYIRONG_CONTEXT"

    if has(
        text,
        "trishuli",
        "bhote",
        "koshi",
        "river",
        "valley",
    ):
        return "RIVER_VALLEY"

    return None


image_pool = []

for image in images:

    category = image_category(
        image
    )

    if not category:
        continue

    p = Path(
        str(image["path"])
    )

    if not p.is_absolute():
        p = ROOT / p

    if not p.exists():
        continue

    item = dict(
        image
    )

    item["_category"] = category
    item["_path"] = str(
        p.resolve()
    )

    item["_uses"] = 0

    # Static images may safely appear multiple times,
    # but we still limit repetition.
    item["_limit"] = min(
        int(
            image.get(
                "max_use"
            )
            or 3
        ),
        3,
    )

    image_pool.append(
        item
    )

print()
print("SAFE CLASSIFIED IMAGES:", len(image_pool))

for image in image_pool:

    print(
        f"  {image['_category']:<18} | "
        f"{image['filename']}"
    )

# =============================================================================
# HELPERS
# =============================================================================

def make_gap(
    row,
    reason,
    action="SEARCH_OR_GENERATE",
):

    return {
        "shot_id":
            row["shot_id"],

        "shot_index":
            row["shot_index"],

        "timeline_start":
            row["timeline_start"],

        "timeline_end":
            row["timeline_end"],

        "duration_sec":
            row["duration_sec"],

        "narration":
            row.get(
                "narration"
            ),

        "visual_need":
            row.get(
                "visual_need"
            ),

        "story_goal":
            row.get(
                "story_goal"
            ),

        "target_category":
            row.get(
                "target_category"
            ),

        "reason":
            reason,

        "recommended_action":
            action,

        "status":
            "VISUAL_GAP",
    }


def select_image(
    target,
    previous_path,
):

    allowed = []

    if target == "MAP_SATELLITE":

        allowed = [
            "MAP_SATELLITE",
            "BEFORE_AFTER",
        ]

    elif target == "GLACIER_CONTEXT":

        allowed = [
            "GLACIER_CONTEXT",
        ]

    elif target == "RIVER_VALLEY":

        allowed = [
            "RIVER_VALLEY",
            "GYIRONG_CONTEXT",
            "GLACIER_CONTEXT",
        ]

    elif target == "GYIRONG_MUDSLIDE":

        allowed = [
            "GYIRONG_CONTEXT",
        ]

    else:

        return None

    candidates = [
        x
        for x in image_pool
        if x["_category"] in allowed
        and x["_uses"] < x["_limit"]
    ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x["_uses"],
            x["_path"] == previous_path,
            allowed.index(
                x["_category"]
            ),
            x["filename"],
        )
    )

    return candidates[0]

# =============================================================================
# FIX OPENING HOOK
#
# Five separate sources/events.
# Exact source ranges taken from human-reviewed ground truth.
# =============================================================================

HOOK_FRAGMENT_NUMBERS = [
    136,  # flood hitting buildings
    1,    # Gyirong CCTV
    71,   # Rasuwa aerial destruction
    57,   # glacier collapse
    74,   # destroyed road / recovery aerial
]

print()
print("=" * 126)
print("REBUILDING OPENING HOOK")
print("=" * 126)

used_hook_sources = set()

for i in range(5):

    row = timeline[i]

    fragment_number = (
        HOOK_FRAGMENT_NUMBERS[i]
    )

    fragment = fragments[
        fragment_number
    ]

    source = Path(
        fragment["source_path"]
    ).resolve()

    start = float(
        fragment["source_start"]
    )

    end = float(
        fragment["source_end"]
    )

    shot_duration = float(
        row["timeline_end"]
        - row["timeline_start"]
    )

    available = (
        end
        - start
    )

    if available < shot_duration:
        raise RuntimeError(
            f"Hook fragment #{fragment_number} "
            f"is too short: {available:.3f}s"
        )

    source_end = (
        start
        + shot_duration
    )

    if str(source) in used_hook_sources:
        raise RuntimeError(
            "Hook source file repeated."
        )

    used_hook_sources.add(
        str(source)
    )

    row.update({
        "status":
            "HUMAN_EDITORIAL_MATCH",

        "fragment_id":
            fragment["fragment_id"],

        "fragment_review_number":
            fragment_number,

        "human_status":
            fragment[
                "production_status"
            ],

        "semantic_category":
            fragment[
                "semantic_category"
            ],

        "asset_path":
            str(source),

        "asset_type":
            "video",

        "source_start":
            round(
                start,
                6,
            ),

        "source_end":
            round(
                source_end,
                6,
            ),

        "source_in_sec":
            round(
                start,
                6,
            ),

        "source_out_sec":
            round(
                source_end,
                6,
            ),

        "selection_reason":
            (
                "HUMAN_CURATED_SHOCK_HOOK"
                f" | fragment=#{fragment_number:03d}"
            ),
    })

    print(
        f"SHOT {i+1:03d} | "
        f"#{fragment_number:03d} | "
        f"{source.name} | "
        f"{start:.3f}-{source_end:.3f}"
    )

# =============================================================================
# FILL APPROPRIATE V1 GAPS WITH SAFE STATIC IMAGES
# =============================================================================

previous_path = None

image_fill_count = 0
image_fill_sec = 0.0

for row in timeline:

    if row.get(
        "asset_path"
    ):

        previous_path = (
            row["asset_path"]
        )

        continue

    target = str(
        row.get(
            "target_category"
        )
        or ""
    )

    # These remain STRICT gaps.
    if target in {
        "SCHOOL",
        "HYDROPOWER",
        "TUNNEL_RESCUE",
        "RESCUE",
    }:

        previous_path = None
        continue

    image = select_image(
        target,
        previous_path,
    )

    if image is None:

        previous_path = None
        continue

    image["_uses"] += 1

    duration = float(
        row["timeline_end"]
        - row["timeline_start"]
    )

    row.update({
        "status":
            "HUMAN_STATIC_EDITORIAL_MATCH",

        "fragment_id":
            None,

        "fragment_review_number":
            None,

        "human_status":
            "CANONICAL_STATIC_SAFE_MATCH",

        "semantic_category":
            image["_category"],

        "asset_id":
            image["id"],

        "asset_path":
            image["_path"],

        "asset_type":
            "image",

        "source_start":
            None,

        "source_end":
            None,

        "source_in_sec":
            None,

        "source_out_sec":
            None,

        "selection_reason":
            (
                "SAFE_STATIC_CONTEXT"
                f" | target={target}"
                f" | image_category={image['_category']}"
                f" | {image['filename']}"
            ),
    })

    image_fill_count += 1
    image_fill_sec += duration

    previous_path = (
        image["_path"]
    )

# =============================================================================
# REBUILD HONEST GAPS
# =============================================================================

gaps = []

video_sec = 0.0
image_sec = 0.0
gap_sec = 0.0

assigned_rows = 0

for row in timeline:

    duration = float(
        row["timeline_end"]
        - row["timeline_start"]
    )

    if row.get(
        "asset_path"
    ):

        assigned_rows += 1

        if row.get(
            "asset_type"
        ) == "image":

            image_sec += duration

        else:

            video_sec += duration

    else:

        gap_sec += duration

        target = (
            row.get(
                "target_category"
            )
            or "UNRESOLVED"
        )

        if target == "SCHOOL":

            reason = (
                "EXACT_SCHOOL_VISUAL_REQUIRED"
            )

        elif target == "HYDROPOWER":

            reason = (
                "EXACT_HYDROPOWER_VISUAL_REQUIRED"
            )

        elif target == "MAP_SATELLITE":

            reason = (
                "MAP_OR_SATELLITE_STILL_MISSING"
            )

        else:

            reason = (
                "NO_SAFE_HUMAN_APPROVED_VISUAL"
            )

        gaps.append(
            make_gap(
                row,
                reason,
            )
        )

# =============================================================================
# SOURCE RANGE OVERLAP CHECK
#
# Hook replacement may overlap ranges already selected deeper in V1.
# Detect this now rather than render it.
# =============================================================================

ranges_by_source = defaultdict(
    list
)

for row in timeline:

    if (
        row.get(
            "asset_type"
        ) != "video"
        or row.get(
            "source_start"
        )
        is None
    ):
        continue

    ranges_by_source[
        row["asset_path"]
    ].append(
        (
            float(
                row["source_start"]
            ),
            float(
                row["source_end"]
            ),
            int(
                row["shot_index"]
            ),
        )
    )

overlaps = []

for source, ranges in (
    ranges_by_source.items()
):

    ordered = sorted(
        ranges
    )

    for a, b in zip(
        ordered,
        ordered[1:],
    ):

        if b[0] < a[1] - 0.01:

            overlaps.append({
                "source":
                    source,

                "a":
                    a,

                "b":
                    b,
            })

# If hook introduced overlap with later use, remove later duplicate use
# rather than sacrificing the curated opening.

if overlaps:

    hook_indices = {
        1, 2, 3, 4, 5
    }

    shots_to_clear = set()

    for overlap in overlaps:

        a_shot = overlap[
            "a"
        ][2]

        b_shot = overlap[
            "b"
        ][2]

        if a_shot in hook_indices:

            shots_to_clear.add(
                b_shot
            )

        elif b_shot in hook_indices:

            shots_to_clear.add(
                a_shot
            )

        else:

            raise RuntimeError(
                "Non-hook source overlap detected "
                f"between shots {a_shot} and {b_shot}"
            )

    for row in timeline:

        if int(
            row["shot_index"]
        ) not in shots_to_clear:

            continue

        row.update({
            "status":
                "VISUAL_GAP",

            "fragment_id":
                None,

            "fragment_review_number":
                None,

            "human_status":
                None,

            "semantic_category":
                None,

            "asset_id":
                None,

            "asset_path":
                None,

            "asset_type":
                None,

            "source_start":
                None,

            "source_end":
                None,

            "source_in_sec":
                None,

            "source_out_sec":
                None,

            "selection_reason":
                "CLEARED_TO_PROTECT_CURATED_HOOK",
        })

    print()
    print(
        "HOOK OVERLAP COLLISIONS CLEARED:",
        len(
            shots_to_clear
        )
    )

# =============================================================================
# FINAL RECALCULATION
# =============================================================================

gaps = []

video_sec = 0.0
image_sec = 0.0
gap_sec = 0.0
assigned_rows = 0

for row in timeline:

    duration = float(
        row["timeline_end"]
        - row["timeline_start"]
    )

    if row.get(
        "asset_path"
    ):

        assigned_rows += 1

        if row.get(
            "asset_type"
        ) == "image":

            image_sec += duration

        else:

            video_sec += duration

    else:

        gap_sec += duration

        gaps.append(
            make_gap(
                row,
                row.get(
                    "selection_reason"
                )
                or "NO_SAFE_HUMAN_APPROVED_VISUAL",
            )
        )

VOICE_DURATION = 1607.517

covered_sec = (
    video_sec
    + image_sec
)

coverage = (
    covered_sec
    / VOICE_DURATION
)

gap_targets = Counter(
    gap[
        "target_category"
    ]
    for gap in gaps
)

image_usage = Counter()

for image in image_pool:

    if image["_uses"]:

        image_usage[
            image["filename"]
        ] = image["_uses"]

# =============================================================================
# PRINT
# =============================================================================

print()
print("=" * 126)
print("ASSIGNMENT V2 SUMMARY")
print("=" * 126)

print(
    "TIMELINE ROWS       :",
    len(timeline),
)

print(
    "ASSIGNED ROWS       :",
    assigned_rows,
)

print(
    "VIDEO SEC           :",
    f"{video_sec:.3f}",
)

print(
    "STATIC IMAGE SEC    :",
    f"{image_sec:.3f}",
)

print(
    "TOTAL COVERED SEC   :",
    f"{covered_sec:.3f}",
)

print(
    "GAP SEC             :",
    f"{gap_sec:.3f}",
)

print(
    "COVERAGE            :",
    f"{coverage:.2%}",
)

print(
    "STATIC FILLS        :",
    image_fill_count,
)

print(
    "GAPS                :",
    len(gaps),
)

print()
print("REMAINING GAP TARGETS:")

for key, value in (
    gap_targets.most_common()
):

    print(
        f"{key:<26} {value:4d}"
    )

print()
print("STATIC IMAGE USAGE:")

if not image_usage:

    print("NONE")

else:

    for name, count in (
        image_usage.most_common()
    ):

        print(
            f"{count:2d}x | {name}"
        )

print()
print("=" * 126)
print("FINAL HOOK")
print("=" * 126)

for row in timeline[:5]:

    print(
        f"{row['shot_index']:03d} | "
        f"#{int(row['fragment_review_number']):03d} | "
        f"{Path(row['asset_path']).name} | "
        f"{row['source_start']:.3f}-"
        f"{row['source_end']:.3f}"
    )

# =============================================================================
# SAVE
# =============================================================================

TIMELINE_OUT.write_text(
    json.dumps(
        {
            "schema":
                "atlas_zero.film10.human_editorial_timeline.v2",

            "project_id":
                PROJECT_ID,

            "voice_duration_sec":
                VOICE_DURATION,

            "timeline":
                timeline,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

GAPS_OUT.write_text(
    json.dumps(
        {
            "schema":
                "atlas_zero.film10.human_editorial_gaps.v2",

            "project_id":
                PROJECT_ID,

            "gap_count":
                len(gaps),

            "gap_duration_sec":
                round(
                    gap_sec,
                    3,
                ),

            "gaps":
                gaps,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

REPORT_OUT.write_text(
    json.dumps(
        {
            "schema":
                "atlas_zero.film10.human_editorial_assignment_report.v2",

            "project_id":
                PROJECT_ID,

            "timeline_rows":
                len(timeline),

            "assigned_rows":
                assigned_rows,

            "video_sec":
                round(
                    video_sec,
                    3,
                ),

            "static_image_sec":
                round(
                    image_sec,
                    3,
                ),

            "covered_sec":
                round(
                    covered_sec,
                    3,
                ),

            "gap_sec":
                round(
                    gap_sec,
                    3,
                ),

            "coverage":
                round(
                    coverage,
                    6,
                ),

            "gap_targets":
                dict(
                    gap_targets
                ),

            "static_image_usage":
                dict(
                    image_usage
                ),

            "hook_fragments":
                HOOK_FRAGMENT_NUMBERS,

            "hook_source_files_unique":
                len(
                    used_hook_sources
                )
                == 5,

            "db_writes":
                False,

            "clip":
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

print()
print("=" * 126)
print("OUTPUT")
print("=" * 126)

print(
    "TIMELINE :",
    TIMELINE_OUT,
)

print(
    "GAPS     :",
    GAPS_OUT,
)

print(
    "REPORT   :",
    REPORT_OUT,
)

print()
print("=" * 126)
print("FILM10 HUMAN EDITORIAL ASSIGNMENT V2: PASS")
print("=" * 126)

print("Hook diversified across five source files.")
print("Canonical static visuals used only when safely classifiable.")
print("School/hydropower remain honest gaps.")
print("No random fallback.")
print("No DB writes.")
print("No render.")
print("No paid API calls.")
