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

GROUND_TRUTH = (
    PROJECT
    / "00_Production"
    / "human_editorial_ground_truth_v1"
    / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_V1.json"
)

OLD_TIMELINE = (
    PROJECT
    / "00_Production"
    / "rough_cut_v2"
    / "FILM10_ROUGH_CUT_TIMELINE_V2.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "human_editorial_assignment_v1"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TIMELINE_OUT = (
    OUT_DIR
    / "FILM10_HUMAN_EDITORIAL_TIMELINE_V1.json"
)

GAPS_OUT = (
    OUT_DIR
    / "FILM10_HUMAN_EDITORIAL_GAPS_V1.json"
)

REPORT_OUT = (
    OUT_DIR
    / "FILM10_HUMAN_EDITORIAL_ASSIGNMENT_REPORT_V1.json"
)

print("=" * 126)
print("ATLAS ZERO — FILM10 HUMAN EDITORIAL ASSIGNMENT V1")
print("=" * 126)

print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("CLIP       : NO")
print("DB WRITES  : NO")
print("RENDER     : NO")

if not DB.exists():
    raise FileNotFoundError(DB)

if not GROUND_TRUTH.exists():
    raise FileNotFoundError(GROUND_TRUTH)

if not OLD_TIMELINE.exists():
    raise FileNotFoundError(OLD_TIMELINE)

# =============================================================================
# LOAD CANONICAL SHOTS
# =============================================================================

uri = DB.resolve().as_uri() + "?mode=ro"

conn = sqlite3.connect(
    uri,
    uri=True,
)

conn.row_factory = sqlite3.Row

try:

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

finally:

    conn.close()

if len(shots) != 260:
    raise RuntimeError(
        f"Expected 260 canonical shots, got {len(shots)}"
    )

# =============================================================================
# LOAD OLD TIMELINE ONLY AS NARRATION/TIMING SOURCE
# =============================================================================

old_payload = json.loads(
    OLD_TIMELINE.read_text(
        encoding="utf-8"
    )
)

if isinstance(old_payload, list):

    old_rows = old_payload

elif isinstance(old_payload, dict):

    for candidate in (
        "timeline",
        "shots",
        "rows",
        "clips",
    ):

        if isinstance(
            old_payload.get(candidate),
            list,
        ):

            old_rows = old_payload[candidate]
            break

    else:
        raise RuntimeError(
            "Could not locate rows inside V2 timeline."
        )

else:

    raise RuntimeError(
        "Unexpected V2 timeline format."
    )

if len(old_rows) != 260:
    raise RuntimeError(
        f"Expected 260 V2 rows, got {len(old_rows)}"
    )

# narration by shot id / position

old_by_shot = {}

for index, row in enumerate(
    old_rows,
    1,
):

    shot_id = str(
        row.get("shot_id")
        or ""
    )

    if shot_id:
        old_by_shot[
            shot_id
        ] = row

# =============================================================================
# HUMAN GROUND TRUTH
# =============================================================================

gt = json.loads(
    GROUND_TRUTH.read_text(
        encoding="utf-8"
    )
)

all_fragments = gt.get(
    "fragments",
    []
)

if len(all_fragments) != 153:
    raise RuntimeError(
        f"Expected 153 human-reviewed fragments, got {len(all_fragments)}"
    )

eligible_statuses = {
    "KEEP_STRONG",
    "KEEP_CONTEXT",
    "SPECIAL_USE",
}

eligible = [
    dict(row)
    for row in all_fragments
    if row.get(
        "production_status"
    ) in eligible_statuses
]

if len(eligible) != 118:
    raise RuntimeError(
        f"Expected 118 production candidates, got {len(eligible)}"
    )

# Runtime cursors:
# Each human-approved fragment can be consumed progressively.
# No source range may be used twice.

for row in eligible:

    row["_cursor"] = float(
        row["source_start"]
    )

    row["_end"] = float(
        row["source_end"]
    )

    row["_used_sec"] = 0.0

    row["_slice_count"] = 0

# =============================================================================
# CATEGORY COMPATIBILITY
# =============================================================================

COMPATIBILITY = {

    "GLACIER_COLLAPSE": [
        "GLACIER_COLLAPSE",
        "GLACIER_COLLAPSE_CONTEXT",
        "LANGTANG_GLACIER_MOUNTAIN",
    ],

    "GLACIER_CONTEXT": [
        "LANGTANG_GLACIER_MOUNTAIN",
        "HIMALAYA_GEOGRAPHY",
        "GLACIER_COLLAPSE_CONTEXT",
    ],

    "GYIRONG_MUDSLIDE": [
        "GYIRONG_PORT_MUDSLIDE",
        "FLOOD_BUILDINGS_IMPACT",
    ],

    "GYIRONG_BEFORE": [
        "GYIRONG_BEFORE",
        "HIMALAYA_GEOGRAPHY",
    ],

    "RASUWA_FLOOD": [
        "RASUWA_FLOOD_TOWN",
        "RASUWA_AERIAL_DESTRUCTION",
        "FLOOD_BUILDINGS_IMPACT",
        "FLOOD_DEBRIS",
        "FLOOD_AFTERMATH",
    ],

    "FLOOD_DESTRUCTION": [
        "FLOOD_BUILDINGS_IMPACT",
        "RASUWA_AERIAL_DESTRUCTION",
        "RASUWA_FLOOD_TOWN",
        "GYIRONG_PORT_MUDSLIDE",
        "FLOOD_DEBRIS",
        "FLOOD_VEHICLES",
    ],

    "ROAD_DESTRUCTION": [
        "ROAD_DESTRUCTION_RESCUE",
        "FLOOD_AFTERMATH",
        "GROUND_SEARCH_DEBRIS",
    ],

    "RESCUE": [
        "RESCUE_DEBRIS",
        "RESCUE_DRILLING",
        "RESCUE_TUNNEL_SEARCH",
        "RESCUE_RESPONSE",
        "ROAD_DESTRUCTION_RESCUE",
        "GROUND_SEARCH_DEBRIS",
    ],

    "TUNNEL_RESCUE": [
        "RESCUE_TUNNEL_SEARCH",
        "RESCUE_DRILLING",
        "RESCUE_DEBRIS",
    ],

    "MAP_SATELLITE": [
        "MAP_SATELLITE",
        "MAP_SATELLITE_EXPLAINER",
    ],

    "RIVER_VALLEY": [
        "RIVER_VALLEY",
        "HIMALAYA_GEOGRAPHY",
        "RASUWA_AFTER_FLOOD",
        "FLOOD_AFTERMATH",
    ],

    "AFTERMATH": [
        "ROAD_DESTRUCTION_RESCUE",
        "FLOOD_AFTERMATH",
        "RASUWA_AFTER_FLOOD",
        "GROUND_SEARCH_DEBRIS",
        "BORDER_DAMAGE",
    ],

    "GEOGRAPHY": [
        "HIMALAYA_GEOGRAPHY",
        "LANGTANG_GLACIER_MOUNTAIN",
        "RIVER_VALLEY",
        "GYIRONG_BEFORE",
    ],
}

# SPECIAL_USE may ONLY be selected for categories where it is
# specifically useful.
SPECIAL_ALLOWED_TARGETS = {
    "GLACIER_COLLAPSE",
    "MAP_SATELLITE",
    "RESCUE",
    "TUNNEL_RESCUE",
}

# =============================================================================
# SHOT CLASSIFIER — editorial, deterministic, no CLIP
# =============================================================================

def norm(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or "").lower()
    ).strip()


def contains(
    text,
    *terms,
):

    return any(
        term in text
        for term in terms
    )


def classify_shot(
    shot,
    narration,
):

    need = norm(
        shot.get("visual_need")
    )

    goal = norm(
        shot.get("story_goal")
    )

    text = (
        need
        + " "
        + goal
        + " "
        + norm(narration)
    )

    idx = int(
        shot["idx"]
    )

    # ---------------------------------------------------------
    # OPENING HOOK
    # ---------------------------------------------------------

    if idx <= 5:
        return (
            "FLOOD_DESTRUCTION",
            True,
            "OPENING_SHOCK_HOOK",
        )

    # ---------------------------------------------------------
    # SCHOOL — exact footage absent -> GAP
    # ---------------------------------------------------------

    if contains(
        text,
        "school",
        "школ",
        "student",
        "учен",
        "teacher",
        "учител",
        "principal",
        "директор школ",
        "school bus",
        "автобус",
    ):

        return (
            "SCHOOL",
            True,
            "EXACT_SCHOOL_VISUAL_REQUIRED",
        )

    # ---------------------------------------------------------
    # HYDROPOWER — do not fake with road footage
    # ---------------------------------------------------------

    if contains(
        text,
        "hydropower",
        "гидроэлект",
        "гэс",
        "power station",
        "электростан",
        "powerhouse",
    ):

        return (
            "HYDROPOWER",
            True,
            "EXACT_HYDROPOWER_VISUAL_REQUIRED",
        )

    # ---------------------------------------------------------
    # SATELLITE / MAP / DISTANCE
    # ---------------------------------------------------------

    if contains(
        text,
        "satellite",
        "спутник",
        "map",
        "карта",
        "100 km",
        "100 км",
        "сто килом",
        "километр downstream",
        "маршрут потока",
    ):

        return (
            "MAP_SATELLITE",
            True,
            "MAP_OR_SATELLITE_SPECIFIC",
        )

    # ---------------------------------------------------------
    # TUNNEL / DRILLING / TRAPPED
    # ---------------------------------------------------------

    if contains(
        text,
        "tunnel",
        "туннел",
        "drill",
        "бурен",
        "бурил",
        "trapped worker",
        "заблокирован",
        "рабоч",
    ):

        return (
            "TUNNEL_RESCUE",
            True,
            "RESCUE_SPECIFIC",
        )

    # ---------------------------------------------------------
    # RESCUE
    # ---------------------------------------------------------

    if contains(
        text,
        "rescue",
        "спас",
        "search",
        "поиск",
        "rescuer",
        "emergency",
        "эваку",
    ):

        return (
            "RESCUE",
            True,
            "RESCUE_SPECIFIC",
        )

    # ---------------------------------------------------------
    # GYIRONG BEFORE
    # ---------------------------------------------------------

    if (
        contains(
            text,
            "gyirong",
            "гиронг",
            "кирьонг",
            "kyirong",
        )
        and
        contains(
            text,
            "before",
            "до катастроф",
            "до потока",
            "раньше",
            "до события",
        )
    ):

        return (
            "GYIRONG_BEFORE",
            True,
            "LOCATION_BEFORE",
        )

    # ---------------------------------------------------------
    # GYIRONG EVENT / BORDER
    # ---------------------------------------------------------

    if contains(
        text,
        "gyirong",
        "гиронг",
        "кирьонг",
        "kyirong",
        "border crossing",
        "погранпереход",
        "границ",
        "tibet",
        "тибет",
    ):

        return (
            "GYIRONG_MUDSLIDE",
            True,
            "GYIRONG_EVENT",
        )

    # ---------------------------------------------------------
    # LANGTANG / COLLAPSE / GLACIER
    # ---------------------------------------------------------

    collapse = contains(
        text,
        "collapse",
        "обруш",
        "обвал",
        "landslide",
        "ополз",
        "avalanche",
        "лавин",
    )

    glacier = contains(
        text,
        "glacier",
        "ледник",
        "langtang",
        "лангтанг",
        "lirung",
        "лирунг",
    )

    if collapse and glacier:

        return (
            "GLACIER_COLLAPSE",
            True,
            "COLLAPSE_SPECIFIC",
        )

    if glacier:

        return (
            "GLACIER_CONTEXT",
            False,
            "GLACIER_CONTEXT",
        )

    # ---------------------------------------------------------
    # RASUWA
    # ---------------------------------------------------------

    if contains(
        text,
        "rasuwa",
        "расува",
        "расув",
    ):

        return (
            "RASUWA_FLOOD",
            True,
            "RASUWA_SPECIFIC",
        )

    # ---------------------------------------------------------
    # ROAD DAMAGE / MACHINERY
    # ---------------------------------------------------------

    if contains(
        text,
        "road",
        "дорог",
        "highway",
        "шоссе",
        "excavator",
        "экскаватор",
        "machinery",
        "техник",
        "repair",
        "ремонт",
    ):

        return (
            "ROAD_DESTRUCTION",
            False,
            "ROAD_DAMAGE",
        )

    # ---------------------------------------------------------
    # RIVER / VALLEY
    # ---------------------------------------------------------

    if contains(
        text,
        "river",
        "река",
        "trishuli",
        "тришули",
        "bhote koshi",
        "бхоте",
        "lhende",
        "ленде",
        "valley",
        "долин",
    ):

        return (
            "RIVER_VALLEY",
            False,
            "RIVER_GEOGRAPHY",
        )

    # ---------------------------------------------------------
    # AFTERMATH
    # ---------------------------------------------------------

    if contains(
        text,
        "aftermath",
        "последств",
        "destroyed",
        "разруш",
        "damage",
        "ущерб",
        "debris",
        "облом",
    ):

        return (
            "AFTERMATH",
            False,
            "AFTERMATH",
        )

    # ---------------------------------------------------------
    # FLOOD
    # ---------------------------------------------------------

    if contains(
        text,
        "flood",
        "поток",
        "наводнен",
        "mudflow",
        "грязев",
        "debris flow",
        "селев",
    ):

        return (
            "FLOOD_DESTRUCTION",
            False,
            "FLOOD_GENERIC",
        )

    # ---------------------------------------------------------
    # GENERIC MOUNTAIN / GEOGRAPHY
    # ---------------------------------------------------------

    if contains(
        text,
        "mountain",
        "гора",
        "himalaya",
        "гимала",
        "geography",
        "географ",
        "landscape",
        "ландшафт",
    ):

        return (
            "GEOGRAPHY",
            False,
            "GEOGRAPHY_CONTEXT",
        )

    # ---------------------------------------------------------
    # No random fallback
    # ---------------------------------------------------------

    return (
        "UNRESOLVED",
        True,
        "NO_SAFE_EDITORIAL_CATEGORY",
    )

# =============================================================================
# FRAGMENT RANKING
# =============================================================================

def compatible_categories(
    target,
):

    return COMPATIBILITY.get(
        target,
        []
    )


def remaining_sec(
    fragment,
):

    return max(
        0.0,
        fragment["_end"]
        - fragment["_cursor"]
    )


def fragment_priority(
    fragment,
    target,
    category_rank,
):

    status = fragment[
        "production_status"
    ]

    status_rank = {
        "KEEP_STRONG": 0,
        "KEEP_CONTEXT": 1,
        "SPECIAL_USE": 2,
    }.get(
        status,
        9,
    )

    # Specific special-use only.
    if (
        status == "SPECIAL_USE"
        and target not in SPECIAL_ALLOWED_TARGETS
    ):
        status_rank += 50

    # Prefer unused fragments before returning to same source.
    slice_penalty = int(
        fragment["_slice_count"]
    )

    # Prefer fragments with enough remaining material.
    remaining = remaining_sec(
        fragment
    )

    return (
        category_rank,
        status_rank,
        slice_penalty,
        -remaining,
        int(
            fragment[
                "review_number"
            ]
        ),
    )


def select_fragment(
    target,
    shot_duration,
    previous_fragment_id,
):

    categories = compatible_categories(
        target
    )

    if not categories:
        return None

    candidates = []

    for category_rank, category in enumerate(
        categories
    ):

        for fragment in eligible:

            if (
                fragment[
                    "semantic_category"
                ]
                != category
            ):
                continue

            # Never use an exhausted fragment.
            available = remaining_sec(
                fragment
            )

            if available < min(
                shot_duration,
                2.0,
            ):
                continue

            # SPECIAL_USE restrictions.
            if (
                fragment[
                    "production_status"
                ]
                == "SPECIAL_USE"
                and target not in SPECIAL_ALLOWED_TARGETS
            ):
                continue

            priority = fragment_priority(
                fragment,
                target,
                category_rank,
            )

            # Avoid same fragment in immediately adjacent shot
            # when another valid option exists.
            adjacency_penalty = (
                5
                if fragment[
                    "fragment_id"
                ] == previous_fragment_id
                else 0
            )

            priority = (
                priority[0],
                priority[1],
                adjacency_penalty,
                priority[2],
                priority[3],
                priority[4],
            )

            candidates.append(
                (
                    priority,
                    fragment,
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda row: row[0]
    )

    return candidates[0][1]

# =============================================================================
# OPENING HOOK MANUAL ORDER
#
# First 25 sec must be strongest event imagery.
# No calm Himalaya opening.
# =============================================================================

HOOK_CATEGORIES = [
    "FLOOD_BUILDINGS_IMPACT",
    "GYIRONG_PORT_MUDSLIDE",
    "RASUWA_AERIAL_DESTRUCTION",
    "GLACIER_COLLAPSE",
    "RASUWA_FLOOD_TOWN",
]

hook_pool = []

for category in HOOK_CATEGORIES:

    for fragment in eligible:

        if (
            fragment[
                "semantic_category"
            ]
            == category
            and fragment[
                "production_status"
            ]
            == "KEEP_STRONG"
        ):

            hook_pool.append(
                fragment
            )

# =============================================================================
# BUILD TIMELINE
# =============================================================================

timeline = []
gaps = []

category_counts = Counter()
reason_counts = Counter()
fragment_slice_counts = Counter()

covered_sec = 0.0
gap_sec = 0.0

previous_fragment_id = None

for position, shot in enumerate(
    shots,
    1,
):

    shot_id = str(
        shot["id"]
    )

    old = (
        old_by_shot.get(
            shot_id
        )
        or old_rows[
            position - 1
        ]
    )

    narration = str(
        old.get(
            "narration"
        )
        or ""
    )

    start = float(
        shot["start_sec"]
    )

    end = float(
        shot["end_sec"]
    )

    duration = (
        end
        - start
    )

    if duration <= 0:
        raise RuntimeError(
            f"Invalid shot duration at shot {position}"
        )

    target, strict, target_reason = classify_shot(
        shot,
        narration,
    )

    category_counts[
        target
    ] += 1

    selected = None

    # ---------------------------------------------------------
    # Hook = deliberately strongest diverse imagery
    # ---------------------------------------------------------

    if position <= 5:

        # Each hook shot should start from a different fragment
        # whenever possible.
        hook_candidates = [
            f
            for f in hook_pool
            if remaining_sec(f) >= min(duration, 2.0)
            and f["fragment_id"] != previous_fragment_id
        ]

        hook_candidates.sort(
            key=lambda f: (
                f["_slice_count"],
                HOOK_CATEGORIES.index(
                    f["semantic_category"]
                )
                if f["semantic_category"]
                in HOOK_CATEGORIES
                else 99,
                int(f["review_number"]),
            )
        )

        if hook_candidates:
            selected = hook_candidates[0]

    else:

        selected = select_fragment(
            target,
            duration,
            previous_fragment_id,
        )

    # ---------------------------------------------------------
    # Honest gap
    # ---------------------------------------------------------

    if selected is None:

        gap = {
            "shot_id":
                shot_id,

            "shot_index":
                int(
                    shot["idx"]
                ),

            "timeline_start":
                round(
                    start,
                    6,
                ),

            "timeline_end":
                round(
                    end,
                    6,
                ),

            "duration_sec":
                round(
                    duration,
                    6,
                ),

            "visual_need":
                shot.get(
                    "visual_need"
                ),

            "story_goal":
                shot.get(
                    "story_goal"
                ),

            "narration":
                narration,

            "target_category":
                target,

            "strict":
                strict,

            "reason":
                target_reason,

            "recommended_action":
                (
                    "SEARCH_OR_GENERATE"
                    if strict
                    else "SEARCH"
                ),

            "status":
                "VISUAL_GAP",
        }

        gaps.append(
            gap
        )

        gap_sec += duration

        timeline.append({
            "shot_id":
                shot_id,

            "shot_index":
                int(
                    shot["idx"]
                ),

            "timeline_start":
                round(
                    start,
                    6,
                ),

            "timeline_end":
                round(
                    end,
                    6,
                ),

            "duration_sec":
                round(
                    duration,
                    6,
                ),

            "narration":
                narration,

            "visual_need":
                shot.get(
                    "visual_need"
                ),

            "story_goal":
                shot.get(
                    "story_goal"
                ),

            "target_category":
                target,

            "status":
                "VISUAL_GAP",

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

            "selection_reason":
                target_reason,

            "transition":
                shot.get(
                    "transition"
                )
                or "cut",

            "camera_motion":
                shot.get(
                    "camera_motion"
                )
                or "static",
        })

        previous_fragment_id = None

        continue

    # ---------------------------------------------------------
    # Consume NON-OVERLAPPING source range
    # ---------------------------------------------------------

    source_in = float(
        selected[
            "_cursor"
        ]
    )

    available = remaining_sec(
        selected
    )

    use_duration = min(
        duration,
        available,
    )

    # If selected source fragment is shorter than timeline shot,
    # use the available part. The remainder becomes a gap.
    source_out = (
        source_in
        + use_duration
    )

    selected[
        "_cursor"
    ] = source_out

    selected[
        "_used_sec"
    ] += use_duration

    selected[
        "_slice_count"
    ] += 1

    fragment_slice_counts[
        selected[
            "fragment_id"
        ]
    ] += 1

    # ---------------------------------------------------------
    # Full shot covered
    # ---------------------------------------------------------

    if (
        use_duration
        >= duration - 0.02
    ):

        row_status = (
            "HUMAN_EDITORIAL_MATCH"
        )

        row_end = end

        covered_sec += duration

    else:

        row_status = (
            "PARTIAL_HUMAN_EDITORIAL_MATCH"
        )

        row_end = (
            start
            + use_duration
        )

        covered_sec += use_duration

        missing_duration = (
            duration
            - use_duration
        )

        gap_sec += missing_duration

        gaps.append({
            "shot_id":
                shot_id,

            "shot_index":
                int(
                    shot["idx"]
                ),

            "timeline_start":
                round(
                    row_end,
                    6,
                ),

            "timeline_end":
                round(
                    end,
                    6,
                ),

            "duration_sec":
                round(
                    missing_duration,
                    6,
                ),

            "visual_need":
                shot.get(
                    "visual_need"
                ),

            "story_goal":
                shot.get(
                    "story_goal"
                ),

            "narration":
                narration,

            "target_category":
                target,

            "reason":
                "APPROVED_FRAGMENT_EXHAUSTED",

            "recommended_action":
                "SEARCH_OR_GENERATE",

            "status":
                "VISUAL_GAP",
        })

    selection_reason = (
        "HUMAN_GROUND_TRUTH"
        f" | target={target}"
        f" | category={selected['semantic_category']}"
        f" | status={selected['production_status']}"
        f" | fragment=#{int(selected['review_number']):03d}"
    )

    timeline.append({
        "shot_id":
            shot_id,

        "shot_index":
            int(
                shot["idx"]
            ),

        "timeline_start":
            round(
                start,
                6,
            ),

        "timeline_end":
            round(
                row_end,
                6,
            ),

        "duration_sec":
            round(
                use_duration,
                6,
            ),

        "narration":
            narration,

        "visual_need":
            shot.get(
                "visual_need"
            ),

        "story_goal":
            shot.get(
                "story_goal"
            ),

        "target_category":
            target,

        "status":
            row_status,

        "fragment_id":
            selected[
                "fragment_id"
            ],

        "fragment_review_number":
            int(
                selected[
                    "review_number"
                ]
            ),

        "human_status":
            selected[
                "production_status"
            ],

        "semantic_category":
            selected[
                "semantic_category"
            ],

        "asset_id":
            None,

        "asset_path":
            selected[
                "source_path"
            ],

        "asset_type":
            "video",

        "source_start":
            round(
                source_in,
                6,
            ),

        "source_end":
            round(
                source_out,
                6,
            ),

        # aliases expected by RenderEngine variants
        "source_in_sec":
            round(
                source_in,
                6,
            ),

        "source_out_sec":
            round(
                source_out,
                6,
            ),

        "selection_reason":
            selection_reason,

        "transition":
            shot.get(
                "transition"
            )
            or "cut",

        "camera_motion":
            shot.get(
                "camera_motion"
            )
            or "static",
    })

    reason_counts[
        selected[
            "semantic_category"
        ]
    ] += 1

    previous_fragment_id = (
        selected[
            "fragment_id"
        ]
    )

# =============================================================================
# VALIDATE SOURCE RANGE NON-OVERLAP
# =============================================================================

ranges_by_source = defaultdict(
    list
)

for row in timeline:

    if (
        not row.get(
            "asset_path"
        )
        or row.get(
            "source_start"
        )
        is None
    ):
        continue

    ranges_by_source[
        row[
            "asset_path"
        ]
    ].append(
        (
            float(
                row[
                    "source_start"
                ]
            ),
            float(
                row[
                    "source_end"
                ]
            ),
            int(
                row[
                    "shot_index"
                ]
            ),
        )
    )

source_overlap_errors = []

for source_path, ranges in (
    ranges_by_source.items()
):

    ranges.sort()

    for previous, current in zip(
        ranges,
        ranges[1:],
    ):

        if (
            current[0]
            < previous[1]
            - 0.01
        ):

            source_overlap_errors.append({
                "source_path":
                    source_path,

                "previous":
                    previous,

                "current":
                    current,
            })

if source_overlap_errors:

    raise RuntimeError(
        f"Detected {len(source_overlap_errors)} source-range overlaps."
    )

# =============================================================================
# SUMMARY
# =============================================================================

VOICE_DURATION = 1607.517

coverage = (
    covered_sec
    / VOICE_DURATION
    if VOICE_DURATION
    else 0.0
)

assigned_rows = [
    row
    for row in timeline
    if row.get(
        "asset_path"
    )
]

gap_shots = {
    row[
        "shot_index"
    ]
    for row in gaps
}

used_fragments = {
    row[
        "fragment_id"
    ]
    for row in timeline
    if row.get(
        "fragment_id"
    )
}

used_source_paths = {
    row[
        "asset_path"
    ]
    for row in timeline
    if row.get(
        "asset_path"
    )
}

print()
print("=" * 126)
print("ASSIGNMENT SUMMARY")
print("=" * 126)

print(
    "CANONICAL SHOTS     :",
    len(shots),
)

print(
    "TIMELINE ROWS       :",
    len(timeline),
)

print(
    "ASSIGNED ROWS       :",
    len(assigned_rows),
)

print(
    "SHOTS WITH GAPS     :",
    len(gap_shots),
)

print(
    "GAP RECORDS         :",
    len(gaps),
)

print(
    "USED FRAGMENTS      :",
    len(used_fragments),
    "/",
    len(eligible),
)

print(
    "USED SOURCE FILES   :",
    len(used_source_paths),
)

print(
    "VIDEO COVERAGE SEC  :",
    f"{covered_sec:.3f}",
)

print(
    "VISUAL GAP SEC      :",
    f"{gap_sec:.3f}",
)

print(
    "VIDEO COVERAGE      :",
    f"{coverage:.2%}",
)

print(
    "SOURCE RANGE OVERLAP:",
    len(
        source_overlap_errors
    ),
)

print()
print("TARGET CATEGORY DISTRIBUTION")

for key, value in (
    category_counts.most_common()
):

    print(
        f"{key:<28} {value:4d}"
    )

print()
print("USED VISUAL CATEGORY DISTRIBUTION")

for key, value in (
    reason_counts.most_common()
):

    print(
        f"{key:<32} {value:4d}"
    )

print()
print("=" * 126)
print("FIRST 25 SHOTS")
print("=" * 126)

for row in timeline[:25]:

    if row.get(
        "asset_path"
    ):

        print(
            f"{row['shot_index']:03d} | "
            f"{row['status']:<30} | "
            f"{row['target_category']:<20} | "
            f"#{row['fragment_review_number']:03d} | "
            f"{row['source_start']:7.3f}-"
            f"{row['source_end']:7.3f} | "
            f"{Path(row['asset_path']).name}"
        )

    else:

        print(
            f"{row['shot_index']:03d} | "
            f"VISUAL_GAP                     | "
            f"{row['target_category']:<20} | "
            f"{row['selection_reason']}"
        )

# =============================================================================
# WRITE REPORTS
# =============================================================================

timeline_payload = {
    "schema":
        "atlas_zero.film10.human_editorial_timeline.v1",

    "project_id":
        PROJECT_ID,

    "voice_duration_sec":
        VOICE_DURATION,

    "human_ground_truth":
        str(
            GROUND_TRUTH
        ),

    "source_range_policy":
        "NON_OVERLAPPING_EXACT_RANGES",

    "gap_policy":
        "NO_RANDOM_FALLBACK",

    "timeline":
        timeline,
}

gaps_payload = {
    "schema":
        "atlas_zero.film10.human_editorial_gaps.v1",

    "project_id":
        PROJECT_ID,

    "gap_count":
        len(gaps),

    "shots_with_gap":
        len(gap_shots),

    "gap_duration_sec":
        round(
            gap_sec,
            3,
        ),

    "gaps":
        gaps,
}

report_payload = {
    "schema":
        "atlas_zero.film10.human_editorial_assignment_report.v1",

    "project_id":
        PROJECT_ID,

    "shots":
        len(shots),

    "timeline_rows":
        len(timeline),

    "assigned_rows":
        len(assigned_rows),

    "shots_with_gap":
        len(gap_shots),

    "gap_records":
        len(gaps),

    "used_fragments":
        len(used_fragments),

    "eligible_fragments":
        len(eligible),

    "used_source_files":
        len(used_source_paths),

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

    "voice_duration_sec":
        VOICE_DURATION,

    "coverage":
        round(
            coverage,
            6,
        ),

    "source_range_overlap_errors":
        source_overlap_errors,

    "target_category_counts":
        dict(
            category_counts
        ),

    "used_visual_category_counts":
        dict(
            reason_counts
        ),

    "fragment_slice_counts":
        dict(
            fragment_slice_counts
        ),

    "db_writes":
        False,

    "clip":
        False,

    "render":
        False,

    "paid_calls":
        False,
}

TIMELINE_OUT.write_text(
    json.dumps(
        timeline_payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

GAPS_OUT.write_text(
    json.dumps(
        gaps_payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

REPORT_OUT.write_text(
    json.dumps(
        report_payload,
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
print("FILM10 HUMAN EDITORIAL ASSIGNMENT V1: PASS")
print("=" * 126)

print(
    "Human-reviewed video only."
)

print(
    "No duplicate/reject fragments eligible."
)

print(
    "No exact source range reused."
)

print(
    "No random fallback."
)

print(
    "No DB writes."
)

print(
    "No render."
)

print(
    "No paid API calls."
)
