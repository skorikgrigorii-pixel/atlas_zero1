from __future__ import annotations

from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
import json
import re

ROOT = Path.cwd()

PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

PACK = (
    PROJECT
    / "00_Production"
    / "visual_production_pack_v1"
    / "FILM10_VISUAL_PRODUCTION_PACK_V1.json"
)

GT = (
    PROJECT
    / "00_Production"
    / "human_editorial_ground_truth_v1"
    / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_NORMALIZED_V1.json"
)

TIMELINE = (
    PROJECT
    / "00_Production"
    / "human_editorial_assignment_v3"
    / "FILM10_HUMAN_EDITORIAL_TIMELINE_V3.json"
)

OUT = (
    PROJECT
    / "00_Production"
    / "production_decision_v1"
)

OUT.mkdir(
    parents=True,
    exist_ok=True
)

JSON_OUT = (
    OUT
    / "FILM10_PRODUCTION_DECISION_V1.json"
)

TXT_OUT = (
    OUT
    / "FILM10_PRODUCTION_DECISION_V1.txt"
)


print("=" * 120)
print("ATLAS ZERO - FILM10 PRODUCTION DECISION V1")
print("=" * 120)

print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("RENDER     : NO")
print("CLIP       : NO")
print()


for p in (
    PACK,
    GT,
    TIMELINE,
):
    if not p.exists():
        raise FileNotFoundError(p)


pack = json.loads(
    PACK.read_text(
        encoding="utf-8"
    )
)

gt = json.loads(
    GT.read_text(
        encoding="utf-8"
    )
)

timeline_raw = json.loads(
    TIMELINE.read_text(
        encoding="utf-8"
    )
)


units = pack["units"]
fragments = gt["fragments"]
timeline = timeline_raw["timeline"]


print("PRODUCTION UNITS :", len(units))
print("GT FRAGMENTS     :", len(fragments))
print("TIMELINE ROWS    :", len(timeline))


if len(units) != 44:
    raise RuntimeError(
        f"Expected 44 production units, got {len(units)}"
    )

if len(fragments) != 118:
    raise RuntimeError(
        f"Expected 118 normalized GT fragments, got {len(fragments)}"
    )


# =============================================================================
# HELPERS
# =============================================================================

def num(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def norm(v):
    return " ".join(
        str(v or "")
        .lower()
        .replace("ё", "е")
        .split()
    )


def basename(path):
    try:
        return Path(
            str(path)
        ).name
    except Exception:
        return ""


# =============================================================================
# CURRENTLY USED SOURCE RANGES
# =============================================================================

used_ranges = defaultdict(list)

for row in timeline:

    if not row.get("asset_path"):
        continue

    if str(
        row.get(
            "asset_type",
            ""
        )
    ).lower() != "video":
        continue

    path = str(
        row["asset_path"]
    )

    a = num(
        row.get(
            "source_start",
            row.get(
                "source_in_sec",
                0
            )
        )
    )

    b = num(
        row.get(
            "source_end",
            row.get(
                "source_out_sec",
                a
            )
        )
    )

    if b > a:
        used_ranges[path].append(
            (
                a,
                b
            )
        )


def free_seconds(fragment):

    path = str(
        fragment[
            "asset_path"
        ]
    )

    start = num(
        fragment[
            "source_start"
        ]
    )

    end = num(
        fragment[
            "source_end"
        ]
    )

    intervals = [
        (
            start,
            end
        )
    ]

    for ua, ub in sorted(
        used_ranges.get(
            path,
            []
        )
    ):

        next_intervals = []

        for a, b in intervals:

            if (
                ub <= a
                or ua >= b
            ):
                next_intervals.append(
                    (
                        a,
                        b
                    )
                )
                continue

            if ua > a:
                next_intervals.append(
                    (
                        a,
                        min(
                            ua,
                            b
                        )
                    )
                )

            if ub < b:
                next_intervals.append(
                    (
                        max(
                            ub,
                            a
                        ),
                        b
                    )
                )

        intervals = next_intervals

    return [
        (
            a,
            b
        )
        for a, b in intervals
        if b - a > 0.25
    ]


# =============================================================================
# EXISTING CATEGORY MATCH
# =============================================================================

TARGET_CATEGORIES = {

    "LANGTANG_2015_ARCHIVE_CONTEXT": {
        "LANGTANG_GLACIER_MOUNTAIN",
        "GLACIER_COLLAPSE_CONTEXT",
        "HIMALAYA_GEOGRAPHY",
        "RIVER_VALLEY",
    },

    "TUNNEL_WORKER_RESCUE": {
        "RESCUE_TUNNEL_SEARCH",
        "RESCUE_DRILLING",
        "RESCUE_RESPONSE",
        "GROUND_SEARCH_DEBRIS",
    },

    "GLACIER_COLLAPSE_REAL": {
        "GLACIER_COLLAPSE",
    },

    "FLOOD_AFTERMATH": {
        "FLOOD_AFTERMATH",
        "RASUWA_AFTER_FLOOD",
        "FLOOD_DEBRIS",
        "ROAD_DESTRUCTION_RESCUE",
    },

    "HYDROPOWER_INFRASTRUCTURE": {
        "RESCUE_TUNNEL_SEARCH",
        "RESCUE_DRILLING",
    },
}


# =============================================================================
# STATIC INDEX
# =============================================================================

STATIC_EXT = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

static_files = []

for root in (
    PROJECT / "00_Research",
    PROJECT / "02_Visuals",
):

    if not root.exists():
        continue

    for p in root.rglob("*"):

        if (
            p.is_file()
            and p.suffix.lower()
            in STATIC_EXT
        ):
            static_files.append(
                p.resolve()
            )


def static_score(
    target,
    path
):

    text = norm(
        path.name
    )

    score = 0

    if target == "USGS_SEISMIC_SCIENCE":

        if "usgs" in text:
            score += 100

        if any(
            x in text
            for x in (
                "seismic",
                "earthquake",
                "waveform",
                "magnitude",
            )
        ):
            score += 80

    elif target == "LANGTANG_2015_ARCHIVE_CONTEXT":

        if "langtang" in text:
            score += 80

        if any(
            x in text
            for x in (
                "2015",
                "glacier",
                "himalaya",
            )
        ):
            score += 50

    elif target == "HYDROPOWER_INFRASTRUCTURE":

        if any(
            x in text
            for x in (
                "hydro",
                "power",
                "tunnel",
                "trishuli",
                "bhote",
            )
        ):
            score += 80

    return score


# =============================================================================
# UNIT ANALYSIS
# =============================================================================

decisions = []

reserved_ranges = defaultdict(list)


def conflicts_reserved(
    path,
    a,
    b
):

    for x, y in reserved_ranges[
        path
    ]:

        if max(
            a,
            x
        ) < min(
            b,
            y
        ) - 0.001:
            return True

    return False


def find_existing_video(
    unit
):

    target = unit[
        "target"
    ]

    allowed = TARGET_CATEGORIES.get(
        target,
        set()
    )

    if not allowed:
        return None

    need = num(
        unit[
            "duration_sec"
        ]
    )

    candidates = []

    for fragment in fragments:

        category = str(
            fragment[
                "category"
            ]
        ).upper()

        if category not in allowed:
            continue

        path = str(
            fragment[
                "asset_path"
            ]
        )

        if not Path(
            path
        ).exists():
            continue

        for a, b in free_seconds(
            fragment
        ):

            if (
                b - a
                < need - 0.02
            ):
                continue

            candidate_end = (
                a
                + need
            )

            if conflicts_reserved(
                path,
                a,
                candidate_end
            ):
                continue

            status = str(
                fragment[
                    "status"
                ]
            )

            strength = {
                "KEEP_STRONG":
                    300,

                "KEEP_CONTEXT":
                    200,

                "SPECIAL_USE":
                    100,

            }.get(
                status,
                0
            )

            surplus = (
                b
                - a
                - need
            )

            score = (
                strength
                - surplus
            )

            candidates.append(
                (
                    score,
                    fragment,
                    a,
                    candidate_end
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x:
            x[0],
        reverse=True
    )

    _, fragment, a, b = (
        candidates[0]
    )

    return {
        "fragment_id":
            fragment[
                "fragment_id"
            ],

        "asset_path":
            fragment[
                "asset_path"
            ],

        "category":
            fragment[
                "category"
            ],

        "source_start":
            round(
                a,
                3
            ),

        "source_end":
            round(
                b,
                3
            ),

        "duration_sec":
            round(
                b - a,
                3
            ),
    }


def find_static(
    unit
):

    target = unit[
        "target"
    ]

    candidates = []

    for path in static_files:

        score = static_score(
            target,
            path
        )

        if score > 0:
            candidates.append(
                (
                    score,
                    path
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            -x[0],
            x[1].name.lower()
        )
    )

    score, path = candidates[0]

    return {
        "asset_path":
            str(
                path
            ),

        "score":
            score,
    }


# =============================================================================
# SHARED EDITORIAL VISUAL GROUPS
#
# One generated/real visual may serve multiple units,
# but ONLY inside same semantic subtype.
# =============================================================================

share_groups = {}

share_counter = Counter()


def shared_key(
    unit
):

    target = unit[
        "target"
    ]

    subtype = unit[
        "subtype"
    ]

    if target in {
        "SCHOOL_BIDUR",
        "WARNING_COMMUNICATION",
    }:
        return (
            target,
            subtype
        )

    return None


for unit in units:

    target = unit[
        "target"
    ]

    mode = unit[
        "production_mode"
    ]

    decision = {
        "unit_id":
            unit[
                "unit_id"
            ],

        "target":
            target,

        "subtype":
            unit[
                "subtype"
            ],

        "duration_sec":
            num(
                unit[
                    "duration_sec"
                ]
            ),

        "shot_indices":
            unit[
                "shot_indices"
            ],

        "narration":
            unit[
                "narration"
            ],

        "visual_need":
            unit[
                "visual_need"
            ],

        "original_mode":
            mode,

        "production_decision":
            None,

        "existing_assignment":
            None,

        "shared_visual_group":
            None,

        "search_brief":
            unit.get(
                "search_brief",
                ""
            ),

        "generation_prompt":
            unit.get(
                "generation_prompt",
                ""
            ),

        "negative_prompt":
            unit.get(
                "negative_prompt",
                ""
            ),
    }


    # -----------------------------------------------------------------
    # First priority: existing approved video
    # -----------------------------------------------------------------

    existing = find_existing_video(
        unit
    )

    if existing:

        decision[
            "production_decision"
        ] = "FOUND_EXISTING_VIDEO"

        decision[
            "existing_assignment"
        ] = existing

        reserved_ranges[
            existing[
                "asset_path"
            ]
        ].append(
            (
                existing[
                    "source_start"
                ],
                existing[
                    "source_end"
                ]
            )
        )

        decisions.append(
            decision
        )

        continue


    # -----------------------------------------------------------------
    # Second priority: exact existing static/science asset
    # -----------------------------------------------------------------

    static = find_static(
        unit
    )

    if (
        static
        and target
        == "USGS_SEISMIC_SCIENCE"
    ):

        decision[
            "production_decision"
        ] = "FOUND_EXISTING_STATIC"

        decision[
            "existing_assignment"
        ] = static

        decisions.append(
            decision
        )

        continue


    # -----------------------------------------------------------------
    # Shared school / warning production
    # -----------------------------------------------------------------

    key = shared_key(
        unit
    )

    if key:

        if key not in share_groups:

            share_counter[
                target
            ] += 1

            share_groups[
                key
            ] = (
                f"{target}_"
                f"{unit['subtype']}_"
                f"{share_counter[target]:02d}"
            )

        decision[
            "shared_visual_group"
        ] = share_groups[
            key
        ]


    # -----------------------------------------------------------------
    # Final production decision
    # -----------------------------------------------------------------

    if mode == "BUILD_GRAPHIC":

        decision[
            "production_decision"
        ] = "BUILD_GRAPHIC_NOW"


    elif mode == "GENERATE_EDITORIAL":

        decision[
            "production_decision"
        ] = "GENERATE_NOW"


    elif mode == "SEARCH_REAL_OR_GENERATE_EDITORIAL":

        decision[
            "production_decision"
        ] = "EXTERNAL_REAL_PRIORITY"


    elif mode == "REUSE_OR_SEARCH":

        decision[
            "production_decision"
        ] = "EXTERNAL_REAL_REQUIRED"


    else:

        decision[
            "production_decision"
        ] = "EDITORIAL_REVIEW"


    decisions.append(
        decision
    )


# =============================================================================
# CONSOLIDATE NEW FILE REQUIREMENTS
# =============================================================================

file_requirements = []

seen_shared = set()


for d in decisions:

    kind = d[
        "production_decision"
    ]

    if kind in {
        "FOUND_EXISTING_VIDEO",
        "FOUND_EXISTING_STATIC",
    }:
        continue

    shared = d.get(
        "shared_visual_group"
    )

    if (
        shared
        and shared
        in seen_shared
    ):
        continue

    if shared:
        seen_shared.add(
            shared
        )

    related = [
        x
        for x in decisions
        if (
            shared
            and x.get(
                "shared_visual_group"
            ) == shared
        )
    ]

    if not related:
        related = [
            d
        ]

    requirement = {
        "requirement_id":
            (
                f"F10_NEW_"
                f"{len(file_requirements)+1:03d}"
            ),

        "decision":
            kind,

        "target":
            d[
                "target"
            ],

        "subtype":
            d[
                "subtype"
            ],

        "shared_visual_group":
            shared,

        "covers_units": [
            x[
                "unit_id"
            ]
            for x in related
        ],

        "covers_shots":
            sorted({
                shot
                for x in related
                for shot in x[
                    "shot_indices"
                ]
            }),

        "total_timeline_sec":
            round(
                sum(
                    x[
                        "duration_sec"
                    ]
                    for x in related
                ),
                3
            ),

        "search_brief":
            d[
                "search_brief"
            ],

        "generation_prompt":
            d[
                "generation_prompt"
            ],

        "negative_prompt":
            d[
                "negative_prompt"
            ],
    }

    file_requirements.append(
        requirement
    )


# =============================================================================
# SUMMARY
# =============================================================================

decision_count = Counter()
decision_sec = Counter()


for d in decisions:

    key = d[
        "production_decision"
    ]

    decision_count[
        key
    ] += 1

    decision_sec[
        key
    ] += d[
        "duration_sec"
    ]


found_existing_sec = sum(
    d[
        "duration_sec"
    ]
    for d in decisions
    if d[
        "production_decision"
    ] in {
        "FOUND_EXISTING_VIDEO",
        "FOUND_EXISTING_STATIC",
    }
)


new_sec = sum(
    d[
        "duration_sec"
    ]
    for d in decisions
    if d[
        "production_decision"
    ] not in {
        "FOUND_EXISTING_VIDEO",
        "FOUND_EXISTING_STATIC",
    }
)


report = {
    "schema":
        "atlas_zero.film10.production_decision.v1",

    "generated_at":
        datetime.now().isoformat(),

    "project_id":
        PROJECT_ID,

    "summary": {
        "production_units":
            len(
                decisions
            ),

        "found_existing_units":
            sum(
                1
                for x in decisions
                if x[
                    "production_decision"
                ] in {
                    "FOUND_EXISTING_VIDEO",
                    "FOUND_EXISTING_STATIC",
                }
            ),

        "found_existing_sec":
            round(
                found_existing_sec,
                3
            ),

        "new_material_units":
            sum(
                1
                for x in decisions
                if x[
                    "production_decision"
                ] not in {
                    "FOUND_EXISTING_VIDEO",
                    "FOUND_EXISTING_STATIC",
                }
            ),

        "new_material_timeline_sec":
            round(
                new_sec,
                3
            ),

        "unique_new_file_requirements":
            len(
                file_requirements
            ),
    },

    "by_decision": {
        key: {
            "units":
                decision_count[
                    key
                ],

            "duration_sec":
                round(
                    decision_sec[
                        key
                    ],
                    3
                ),
        }
        for key in sorted(
            decision_count
        )
    },

    "decisions":
        decisions,

    "new_file_requirements":
        file_requirements,
}


JSON_OUT.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


# =============================================================================
# TXT
# =============================================================================

lines = []

lines.append(
    "ATLAS ZERO - FILM10 PRODUCTION DECISION V1"
)

lines.append(
    "=" * 100
)

lines.append("")

for key, value in report[
    "summary"
].items():

    lines.append(
        f"{key:32s}: {value}"
    )


lines.append("")
lines.append(
    "BY DECISION"
)
lines.append(
    "-" * 100
)


for key in sorted(
    decision_count,
    key=lambda k:
        -decision_sec[k]
):

    lines.append(
        f"{key:30s} "
        f"{decision_count[key]:3d} units | "
        f"{decision_sec[key]:8.3f} sec"
    )


lines.append("")
lines.append(
    "NEW FILE REQUIREMENTS"
)
lines.append(
    "=" * 100
)


for req in file_requirements:

    lines.append("")
    lines.append(
        f"{req['requirement_id']} | "
        f"{req['decision']} | "
        f"{req['target']} / "
        f"{req['subtype']}"
    )

    lines.append(
        "COVERS UNITS : "
        + ", ".join(
            req[
                "covers_units"
            ]
        )
    )

    lines.append(
        "COVERS SHOTS : "
        + ", ".join(
            str(x)
            for x in req[
                "covers_shots"
            ]
        )
    )

    lines.append(
        f"TIMELINE SEC : "
        f"{req['total_timeline_sec']:.3f}"
    )

    if req[
        "search_brief"
    ]:

        lines.append(
            "SEARCH       : "
            + req[
                "search_brief"
            ]
        )

    if req[
        "generation_prompt"
    ]:

        lines.append(
            "PROMPT       : "
            + req[
                "generation_prompt"
            ]
        )

        lines.append(
            "NEGATIVE     : "
            + req[
                "negative_prompt"
            ]
        )


TXT_OUT.write_text(
    "\n".join(
        lines
    ),
    encoding="utf-8"
)


# =============================================================================
# VALIDATION
# =============================================================================

if len(
    decisions
) != 44:

    raise RuntimeError(
        "Not all production units received decisions."
    )


if not JSON_OUT.exists():
    raise RuntimeError(
        "JSON output missing."
    )


if not TXT_OUT.exists():
    raise RuntimeError(
        "TXT output missing."
    )


print()
print("=" * 120)
print("PRODUCTION DECISION SUMMARY")
print("=" * 120)

print(
    "PRODUCTION UNITS       :",
    len(
        decisions
    )
)

print(
    "FOUND EXISTING UNITS   :",
    report[
        "summary"
    ][
        "found_existing_units"
    ]
)

print(
    "FOUND EXISTING SEC     :",
    f"{found_existing_sec:.3f}"
)

print(
    "NEW MATERIAL UNITS     :",
    report[
        "summary"
    ][
        "new_material_units"
    ]
)

print(
    "NEW MATERIAL SEC       :",
    f"{new_sec:.3f}"
)

print(
    "UNIQUE NEW FILES NEEDED:",
    len(
        file_requirements
    )
)


print()
print("BY DECISION:")


for key in sorted(
    decision_count,
    key=lambda k:
        -decision_sec[k]
):

    print(
        f"  {key:30s} "
        f"{decision_count[key]:3d} | "
        f"{decision_sec[key]:8.3f} sec"
    )


print()
print("NEW FILE REQUIREMENTS BY TARGET:")


req_target = Counter(
    x[
        "target"
    ]
    for x in file_requirements
)


for key, count in req_target.most_common():

    print(
        f"  {key:34s}: "
        f"{count}"
    )


print()
print("=" * 120)
print("OUTPUTS")
print("=" * 120)

for p in (
    JSON_OUT,
    TXT_OUT,
):

    print(
        p.relative_to(
            ROOT
        ),
        "|",
        p.stat().st_size,
        "bytes"
    )


print()
print("=" * 120)
print("FILM10 PRODUCTION DECISION V1: PASS")
print("=" * 120)
print(
    "NEXT: acquire/generate the UNIQUE NEW FILE REQUIREMENTS, then build render-ready timeline."
)
print("=" * 120)

