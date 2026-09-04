from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import html
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

GAPS_V3 = (
    PROJECT
    / "00_Production"
    / "human_editorial_assignment_v3"
    / "FILM10_HUMAN_EDITORIAL_GAPS_V3.json"
)

OUT = (
    PROJECT
    / "00_Production"
    / "visual_production_pack_v1"
)

OUT.mkdir(
    parents=True,
    exist_ok=True
)

JSON_OUT = (
    OUT
    / "FILM10_VISUAL_PRODUCTION_PACK_V1.json"
)

TXT_OUT = (
    OUT
    / "FILM10_VISUAL_PRODUCTION_PACK_V1.txt"
)

HTML_OUT = (
    OUT
    / "FILM10_VISUAL_PRODUCTION_PACK_V1.html"
)

PDF_OUT = (
    OUT
    / "FILM10_VISUAL_PRODUCTION_PACK_V1.pdf"
)


print("=" * 120)
print("ATLAS ZERO - FILM10 VISUAL PRODUCTION PACK V1")
print("=" * 120)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("RENDER     : NO")
print("CLIP       : NO")
print()


if not GAPS_V3.exists():
    raise FileNotFoundError(
        GAPS_V3
    )


raw = json.loads(
    GAPS_V3.read_text(
        encoding="utf-8"
    )
)

gaps = raw["gaps"]


print(
    "INPUT GAPS  :",
    len(gaps)
)

print(
    "INPUT SEC   :",
    f"{sum(float(x.get('duration_sec', 0)) for x in gaps):.3f}"
)


# =============================================================================
# HELPERS
# =============================================================================

def num(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def norm(value):
    return " ".join(
        str(value or "")
        .lower()
        .replace("ё", "е")
        .split()
    )


def idx(row):

    value = row.get(
        "shot_index"
    )

    if value is not None:
        try:
            return int(value)
        except Exception:
            pass

    m = re.findall(
        r"\d+",
        str(
            row.get(
                "shot_id",
                ""
            )
        )
    )

    return int(
        m[-1]
    ) if m else None


def start(row):
    return num(
        row.get(
            "timeline_start",
            row.get(
                "start_sec",
                0
            )
        )
    )


def end(row):
    return num(
        row.get(
            "timeline_end",
            row.get(
                "end_sec",
                start(row)
            )
        )
    )


def duration(row):
    return num(
        row.get(
            "duration_sec"
        ),
        max(
            0,
            end(row) - start(row)
        )
    )


# =============================================================================
# PRODUCTION POLICY
#
# Important:
# We are NOT generating fake archival evidence.
#
# SEARCH_REAL:
# exact historical/event-specific real material preferred.
#
# GENERATE_EDITORIAL:
# clearly editorial reconstruction / illustrative sequence.
#
# BUILD_GRAPHIC:
# map, seismic diagram, explanatory science graphic.
#
# REUSE_OR_SEARCH:
# first try current corpus; if unavailable/non-overlapping,
# acquire another rights-clean source.
# =============================================================================

POLICY = {

    "SCHOOL_BIDUR": {
        "mode":
            "SEARCH_REAL_OR_GENERATE_EDITORIAL",

        "max_unit_sec":
            18.0,

        "visual_brief":
            (
                "Tribhuvan Trishuli Secondary School in Bidur; "
                "students and teachers evacuating after upstream warning; "
                "school buses, old bridge, children moving uphill. "
                "Prefer real rights-cleared images/video. "
                "If unavailable, use clearly editorial reconstruction, "
                "never present generated imagery as archival footage."
            ),

        "search_brief":
            (
                "Tribhuvan Trishuli Secondary School Bidur Nepal flood "
                "evacuation August 26 2026 school bus old bridge "
                "Rajendra Dawadi Rasuwa warning"
            ),

        "generation_style":
            (
                "photorealistic documentary editorial reconstruction, "
                "Nepal, 2026, natural overcast daylight, authentic school "
                "environment, children and teachers evacuating calmly but "
                "urgently, no logos, no captions, no fake news graphics, "
                "16:9 cinematic documentary frame"
            ),
    },


    "WARNING_COMMUNICATION": {
        "mode":
            "GENERATE_EDITORIAL",

        "max_unit_sec":
            14.0,

        "visual_brief":
            (
                "Human warning chain: upstream relative calls accountant, "
                "school staff receive warning, phones ringing, teacher "
                "moving through corridor, people pointing toward river, "
                "rapid word-of-mouth evacuation. Symbolic/editorial."
            ),

        "search_brief":
            "",

        "generation_style":
            (
                "photorealistic documentary editorial reconstruction in Nepal, "
                "phone warning during natural disaster, realistic people and "
                "environment, restrained urgency, no readable phone text, "
                "no logos, no captions, 16:9"
            ),
    },


    "USGS_SEISMIC_SCIENCE": {
        "mode":
            "BUILD_GRAPHIC",

        "max_unit_sec":
            12.0,

        "visual_brief":
            (
                "Scientific visual explaining unusual seismic signal initially "
                "resembling approximately M5.2 and later another signal around "
                "M4.2; waveform, Himalayan terrain/map context, mass movement "
                "rather than a conventional earthquake."
            ),

        "search_brief":
            (
                "USGS Nepal August 26 2026 debris avalanche seismic signal "
                "Langtang Lirung M5.2 M4.2"
            ),

        "generation_style":
            (
                "clean scientific documentary graphic, seismic waveform, "
                "Himalayan relief map, restrained labels added later in edit, "
                "16:9, no invented agency logo"
            ),
    },


    "HYDROPOWER_INFRASTRUCTURE": {
        "mode":
            "SEARCH_REAL_OR_GENERATE_EDITORIAL",

        "max_unit_sec":
            12.0,

        "visual_brief":
            (
                "Hydropower infrastructure in the affected Nepal river valley: "
                "intake, powerhouse, tunnel portal, muddy flood damage, "
                "workers/rescuers. Prefer exact real infrastructure."
            ),

        "search_brief":
            (
                "Nepal August 26 2026 flood hydropower plant damage "
                "Rasuwa Trishuli Bhote Koshi tunnel workers"
            ),

        "generation_style":
            (
                "photorealistic documentary editorial reconstruction of Nepal "
                "hydropower infrastructure after catastrophic debris flood, "
                "mud, tunnel entrance, emergency workers, realistic engineering, "
                "no logos, no captions, 16:9"
            ),
    },


    "TUNNEL_WORKER_RESCUE": {
        "mode":
            "REUSE_OR_SEARCH",

        "max_unit_sec":
            14.0,

        "visual_brief":
            (
                "Rescuers searching/drilling near tunnel or hydropower "
                "infrastructure for trapped workers. Use existing approved "
                "RESCUE_TUNNEL_SEARCH / RESCUE_DRILLING if an unused source "
                "range exists; otherwise acquire rights-clean equivalent."
            ),

        "search_brief":
            (
                "Nepal flood August 26 2026 tunnel trapped workers rescue "
                "hydropower Rasuwa drilling"
            ),

        "generation_style":
            "",
    },


    "LANGTANG_2015_ARCHIVE_CONTEXT": {
        "mode":
            "REUSE_OR_SEARCH",

        "max_unit_sec":
            15.0,

        "visual_brief":
            (
                "Langtang valley historical context around the 2015 earthquake "
                "and avalanche destruction. Do not pass 2026 footage off as "
                "2015 archival material. Geography/context footage is acceptable "
                "where narration is general."
            ),

        "search_brief":
            (
                "Langtang Nepal 2015 earthquake avalanche village "
                "public domain Creative Commons archive"
            ),

        "generation_style":
            "",
    },


    "GLACIER_COLLAPSE_REAL": {
        "mode":
            "REUSE_OR_SEARCH",

        "max_unit_sec":
            8.0,

        "visual_brief":
            (
                "Actual Langtang Lirung slope/glacier collapse or the closest "
                "rights-cleared real evidence. Existing approved collapse "
                "fragment first. Generated imagery must not masquerade as "
                "actual drone footage."
            ),

        "search_brief":
            (
                "Langtang Lirung collapse drone August 26 2026 Nepal"
            ),

        "generation_style":
            "",
    },


    "FLOOD_AFTERMATH": {
        "mode":
            "REUSE_OR_SEARCH",

        "max_unit_sec":
            10.0,

        "visual_brief":
            (
                "Real aftermath: debris field, damaged roads, river valley, "
                "mud, destroyed infrastructure. Existing human-approved "
                "Film10 footage preferred."
            ),

        "search_brief":
            "",
        "generation_style":
            "",
    },


    "EDITORIAL_REVIEW_REQUIRED": {
        "mode":
            "GENERATE_EDITORIAL",

        "max_unit_sec":
            10.0,

        "visual_brief":
            (
                "Create a neutral documentary visual based directly on the "
                "individual shot narration and visual_need. No random Himalaya "
                "beauty shot. No fake archival framing."
            ),

        "search_brief":
            "",
        "generation_style":
            (
                "photorealistic documentary editorial illustration, Nepal "
                "Himalayan disaster context, restrained realism, no captions, "
                "no logos, 16:9"
            ),
    },
}


# =============================================================================
# SUBTYPE
#
# Used to prevent one large SCHOOL unit from combining:
# - school building
# - warning
# - bus
# - bridge collapse
# =============================================================================

def subtype(row):

    target = str(
        row.get(
            "new_target",
            ""
        )
    )

    text = norm(
        str(
            row.get(
                "narration",
                ""
            )
        )
        + " "
        + str(
            row.get(
                "visual_need",
                ""
            )
        )
    )

    if target == "SCHOOL_BIDUR":

        if any(
            x in text
            for x in (
                "автобус",
                "bus",
                "последний автобус",
            )
        ):
            return "SCHOOL_BUS"

        if any(
            x in text
            for x in (
                "мост",
                "bridge",
                "пересек",
                "пересёк",
            )
        ):
            return "OLD_BRIDGE"

        if any(
            x in text
            for x in (
                "14 минут",
                "четырнадцать минут",
                "эваку",
                "ученик",
                "коридор",
                "класс",
            )
        ):
            return "EVACUATION"

        return "SCHOOL_ESTABLISHING"

    if target == "WARNING_COMMUNICATION":

        if any(
            x in text
            for x in (
                "телефон",
                "позвон",
                "звонок",
                "сообщен",
            )
        ):
            return "PHONE_WARNING"

        return "HUMAN_WARNING_CHAIN"

    if target == "USGS_SEISMIC_SCIENCE":

        if any(
            x in text
            for x in (
                "m5.2",
                "5,2",
                "5.2",
            )
        ):
            return "USGS_SIGNAL_1"

        if any(
            x in text
            for x in (
                "m4.2",
                "4,2",
                "4.2",
                "три часа",
            )
        ):
            return "USGS_SIGNAL_2"

        return "USGS_EXPLANATION"

    if target == "HYDROPOWER_INFRASTRUCTURE":

        if any(
            x in text
            for x in (
                "туннел",
                "tunnel",
            )
        ):
            return "HPP_TUNNEL"

        return "HPP_DAMAGE"

    if target == "TUNNEL_WORKER_RESCUE":
        return "TUNNEL_RESCUE"

    if target == "LANGTANG_2015_ARCHIVE_CONTEXT":
        return "LANGTANG_2015"

    if target == "GLACIER_COLLAPSE_REAL":
        return "COLLAPSE"

    if target == "FLOOD_AFTERMATH":
        return "AFTERMATH"

    return "GENERAL"


# =============================================================================
# CONSOLIDATE CONSECUTIVE GAPS INTO EDITORIAL UNITS
#
# New unit when:
# - target changes
# - subtype changes
# - action changes
# - timeline discontinuity > 0.15 sec
# - max useful unit length exceeded
# =============================================================================

ordered = sorted(
    gaps,
    key=lambda x: (
        start(x),
        idx(x) or 0,
    )
)

units = []
current = None


for row in ordered:

    target = str(
        row.get(
            "new_target",
            "UNKNOWN"
        )
    )

    action = str(
        row.get(
            "next_action",
            "UNKNOWN"
        )
    )

    stype = subtype(
        row
    )

    policy = POLICY.get(
        target,
        {
            "mode":
                action,
            "max_unit_sec":
                10.0,
            "visual_brief":
                "",
            "search_brief":
                "",
            "generation_style":
                "",
        }
    )

    max_sec = float(
        policy[
            "max_unit_sec"
        ]
    )

    must_break = False

    if current is None:
        must_break = True

    else:

        if (
            current["target"]
            != target
        ):
            must_break = True

        elif (
            current["subtype"]
            != stype
        ):
            must_break = True

        elif (
            current["source_action"]
            != action
        ):
            must_break = True

        elif (
            abs(
                start(row)
                - current["end_sec"]
            )
            > 0.15
        ):
            must_break = True

        elif (
            end(row)
            - current["start_sec"]
            > max_sec
        ):
            must_break = True

    if must_break:

        if current:
            units.append(
                current
            )

        current = {
            "unit_id":
                None,

            "target":
                target,

            "subtype":
                stype,

            "production_mode":
                policy["mode"],

            "source_action":
                action,

            "start_sec":
                start(row),

            "end_sec":
                end(row),

            "duration_sec":
                duration(row),

            "shot_indices": [
                idx(row)
            ],

            "shot_ids": [
                row.get(
                    "shot_id"
                )
            ],

            "narration_parts": [
                str(
                    row.get(
                        "narration",
                        ""
                    )
                )
            ],

            "visual_needs": [
                str(
                    row.get(
                        "visual_need",
                        ""
                    )
                )
            ],

            "priority":
                row.get(
                    "priority",
                    "HIGH"
                ),

            "visual_brief":
                policy[
                    "visual_brief"
                ],

            "search_brief":
                policy[
                    "search_brief"
                ],

            "generation_style":
                policy[
                    "generation_style"
                ],
        }

    else:

        current[
            "end_sec"
        ] = end(row)

        current[
            "duration_sec"
        ] = (
            current[
                "end_sec"
            ]
            - current[
                "start_sec"
            ]
        )

        current[
            "shot_indices"
        ].append(
            idx(row)
        )

        current[
            "shot_ids"
        ].append(
            row.get(
                "shot_id"
            )
        )

        current[
            "narration_parts"
        ].append(
            str(
                row.get(
                    "narration",
                    ""
                )
            )
        )

        current[
            "visual_needs"
        ].append(
            str(
                row.get(
                    "visual_need",
                    ""
                )
            )
        )


if current:
    units.append(
        current
    )


# =============================================================================
# FINALIZE UNITS
# =============================================================================

for i, unit in enumerate(
    units,
    1
):

    unit[
        "unit_id"
    ] = (
        f"F10_VIS_{i:03d}"
    )

    narration = " ".join(
        x.strip()
        for x in unit[
            "narration_parts"
        ]
        if x.strip()
    )

    visual_need = " | ".join(
        dict.fromkeys(
            x.strip()
            for x in unit[
                "visual_needs"
            ]
            if x.strip()
        )
    )

    unit[
        "narration"
    ] = narration

    unit[
        "visual_need"
    ] = visual_need

    unit.pop(
        "narration_parts",
        None
    )

    unit.pop(
        "visual_needs",
        None
    )

    # -------------------------------------------------------------
    # Concrete generation prompt
    # -------------------------------------------------------------

    if unit[
        "production_mode"
    ] in {
        "GENERATE_EDITORIAL",
        "SEARCH_REAL_OR_GENERATE_EDITORIAL",
    }:

        unit[
            "generation_prompt"
        ] = (
            unit[
                "generation_style"
            ]
            + ". Editorial objective: "
            + unit[
                "visual_brief"
            ]
            + ". Narration context: "
            + narration[:1200]
        ).strip()

        unit[
            "negative_prompt"
        ] = (
            "text, captions, subtitles, watermark, logo, news lower third, "
            "fantasy mountains, surreal disaster, exaggerated destruction, "
            "Hollywood explosion, duplicated people, deformed hands, "
            "modern Western school architecture, fake archival timestamp"
        )

    elif unit[
        "production_mode"
    ] == "BUILD_GRAPHIC":

        unit[
            "generation_prompt"
        ] = (
            "16:9 scientific documentary graphic. "
            + unit[
                "visual_brief"
            ]
            + " Clean neutral layout, dark terrain/map background, "
              "clear waveform and geographic structure. "
              "Do not invent measurements or agency branding. "
              "Leave precise text labels for later compositing."
        )

        unit[
            "negative_prompt"
        ] = (
            "fake USGS logo, invented numbers, decorative infographic, "
            "3D fantasy globe, watermark, paragraph text"
        )

    else:

        unit[
            "generation_prompt"
        ] = ""

        unit[
            "negative_prompt"
        ] = ""


# =============================================================================
# SUMMARIES
# =============================================================================

mode_count = Counter()
mode_sec = Counter()

target_count = Counter()
target_sec = Counter()

shot_seen = []


for unit in units:

    mode = unit[
        "production_mode"
    ]

    target = unit[
        "target"
    ]

    sec = unit[
        "duration_sec"
    ]

    mode_count[
        mode
    ] += 1

    mode_sec[
        mode
    ] += sec

    target_count[
        target
    ] += 1

    target_sec[
        target
    ] += sec

    shot_seen.extend(
        unit[
            "shot_indices"
        ]
    )


input_shots = sorted(
    idx(x)
    for x in gaps
)

output_shots = sorted(
    x
    for x in shot_seen
    if x is not None
)


if input_shots != output_shots:

    missing = sorted(
        set(input_shots)
        - set(output_shots)
    )

    duplicates = [
        x
        for x, count
        in Counter(
            output_shots
        ).items()
        if count > 1
    ]

    raise RuntimeError(
        "Shot coverage failure. "
        f"missing={missing} "
        f"duplicates={duplicates}"
    )


total_gap_sec = sum(
    duration(x)
    for x in gaps
)

total_unit_sec = sum(
    x["duration_sec"]
    for x in units
)


report = {

    "schema":
        "atlas_zero.film10.visual_production_pack.v1",

    "generated_at":
        datetime.now().isoformat(),

    "project_id":
        PROJECT_ID,

    "policy": {
        "random_fallback":
            False,

        "fake_archive":
            False,

        "generated_visuals_must_be_editorial":
            True,

        "rights_clearance_separate":
            True,

        "clip_used":
            False,

        "api_used":
            False,

        "db_writes":
            False,

        "render":
            False,
    },

    "summary": {
        "input_gap_shots":
            len(
                gaps
            ),

        "input_gap_duration_sec":
            round(
                total_gap_sec,
                3
            ),

        "production_units":
            len(
                units
            ),

        "production_unit_duration_sec":
            round(
                total_unit_sec,
                3
            ),

        "shot_coverage":
            len(
                output_shots
            ),

        "shot_coverage_pass":
            (
                input_shots
                == output_shots
            ),
    },

    "by_mode": {
        key: {
            "units":
                mode_count[
                    key
                ],

            "duration_sec":
                round(
                    mode_sec[
                        key
                    ],
                    3
                ),
        }
        for key in sorted(
            mode_count
        )
    },

    "by_target": {
        key: {
            "units":
                target_count[
                    key
                ],

            "duration_sec":
                round(
                    target_sec[
                        key
                    ],
                    3
                ),
        }
        for key in sorted(
            target_count
        )
    },

    "units":
        units,
}


# =============================================================================
# JSON
# =============================================================================

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
    "ATLAS ZERO - FILM10 VISUAL PRODUCTION PACK V1"
)

lines.append(
    "=" * 100
)

lines.append("")

lines.append(
    f"INPUT GAP SHOTS       : {len(gaps)}"
)

lines.append(
    f"INPUT GAP SEC         : {total_gap_sec:.3f}"
)

lines.append(
    f"PRODUCTION UNITS      : {len(units)}"
)

lines.append(
    f"UNIT SEC              : {total_unit_sec:.3f}"
)

lines.append("")

lines.append(
    "BY PRODUCTION MODE"
)

lines.append(
    "-" * 100
)

for key in sorted(
    mode_count,
    key=lambda k:
        -mode_sec[k]
):

    lines.append(
        f"{key:34s} "
        f"{mode_count[key]:3d} units | "
        f"{mode_sec[key]:8.3f} sec"
    )


lines.append("")
lines.append(
    "BY TARGET"
)
lines.append(
    "-" * 100
)

for key in sorted(
    target_count,
    key=lambda k:
        -target_sec[k]
):

    lines.append(
        f"{key:34s} "
        f"{target_count[key]:3d} units | "
        f"{target_sec[key]:8.3f} sec"
    )


lines.append("")
lines.append(
    "PRODUCTION UNITS"
)
lines.append(
    "=" * 100
)


for unit in units:

    lines.append("")
    lines.append(
        f"{unit['unit_id']} | "
        f"{unit['target']} | "
        f"{unit['subtype']}"
    )

    lines.append(
        f"TC       : "
        f"{unit['start_sec']:.3f} - "
        f"{unit['end_sec']:.3f}"
    )

    lines.append(
        f"DURATION : "
        f"{unit['duration_sec']:.3f}"
    )

    lines.append(
        f"SHOTS    : "
        + ", ".join(
            str(x)
            for x in unit[
                "shot_indices"
            ]
        )
    )

    lines.append(
        f"MODE     : "
        f"{unit['production_mode']}"
    )

    lines.append(
        f"PRIORITY : "
        f"{unit['priority']}"
    )

    lines.append(
        f"VISUAL   : "
        f"{unit['visual_brief']}"
    )

    if unit[
        "search_brief"
    ]:

        lines.append(
            f"SEARCH   : "
            f"{unit['search_brief']}"
        )

    if unit[
        "generation_prompt"
    ]:

        lines.append(
            f"PROMPT   : "
            f"{unit['generation_prompt']}"
        )

        lines.append(
            f"NEGATIVE : "
            f"{unit['negative_prompt']}"
        )

    lines.append(
        f"NARRATION: "
        f"{unit['narration']}"
    )


TXT_OUT.write_text(
    "\n".join(
        lines
    ),
    encoding="utf-8"
)


# =============================================================================
# HTML
# =============================================================================

def esc(value):
    return html.escape(
        str(
            value or ""
        )
    )


parts = [
    """
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>Film10 Visual Production Pack V1</title>
    <style>
    body {
        font-family: Arial, sans-serif;
        margin: 30px;
        line-height: 1.4;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 25px;
    }
    th, td {
        border: 1px solid #aaa;
        padding: 6px;
        vertical-align: top;
    }
    th { background: #eee; }
    .unit {
        border: 1px solid #aaa;
        margin: 15px 0;
        padding: 12px;
        page-break-inside: avoid;
    }
    </style>
    </head>
    <body>
    """
]

parts.append(
    "<h1>ATLAS ZERO — Film10 Visual Production Pack V1</h1>"
)

parts.append(
    f"<p>72-shot gap set consolidated into "
    f"<b>{len(units)}</b> editorial production units.</p>"
)

parts.append(
    "<h2>Production modes</h2>"
)

parts.append(
    "<table><tr>"
    "<th>Mode</th>"
    "<th>Units</th>"
    "<th>Seconds</th>"
    "</tr>"
)

for key in sorted(
    mode_count,
    key=lambda k:
        -mode_sec[k]
):

    parts.append(
        "<tr>"
        f"<td>{esc(key)}</td>"
        f"<td>{mode_count[key]}</td>"
        f"<td>{mode_sec[key]:.3f}</td>"
        "</tr>"
    )

parts.append(
    "</table>"
)


for unit in units:

    parts.append(
        "<div class='unit'>"
    )

    parts.append(
        f"<h3>{esc(unit['unit_id'])} — "
        f"{esc(unit['target'])} / "
        f"{esc(unit['subtype'])}</h3>"
    )

    parts.append(
        f"<p><b>Time:</b> "
        f"{unit['start_sec']:.3f}–"
        f"{unit['end_sec']:.3f} "
        f"({unit['duration_sec']:.3f}s)<br>"
        f"<b>Shots:</b> "
        f"{esc(', '.join(str(x) for x in unit['shot_indices']))}<br>"
        f"<b>Mode:</b> "
        f"{esc(unit['production_mode'])}</p>"
    )

    parts.append(
        f"<p><b>Visual brief:</b><br>"
        f"{esc(unit['visual_brief'])}</p>"
    )

    if unit[
        "search_brief"
    ]:

        parts.append(
            f"<p><b>Search:</b><br>"
            f"{esc(unit['search_brief'])}</p>"
        )

    if unit[
        "generation_prompt"
    ]:

        parts.append(
            f"<p><b>Generation prompt:</b><br>"
            f"{esc(unit['generation_prompt'])}</p>"
        )

    parts.append(
        f"<p><b>Narration:</b><br>"
        f"{esc(unit['narration'])}</p>"
    )

    parts.append(
        "</div>"
    )


parts.append(
    "</body></html>"
)

HTML_OUT.write_text(
    "\n".join(
        parts
    ),
    encoding="utf-8"
)


# =============================================================================
# PDF
# =============================================================================

try:

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import (
        getSampleStyleSheet,
        ParagraphStyle,
    )
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
    )

except Exception as exc:

    raise RuntimeError(
        f"ReportLab import failed: {exc}"
    )


font_candidates = [
    Path(
        r"C:\Windows\Fonts\arial.ttf"
    ),
    Path(
        r"C:\Windows\Fonts\segoeui.ttf"
    ),
    Path(
        r"C:\Windows\Fonts\calibri.ttf"
    ),
]


font_path = next(
    (
        x
        for x in font_candidates
        if x.exists()
    ),
    None
)


if font_path is None:

    raise RuntimeError(
        "Unicode Windows font not found."
    )


pdfmetrics.registerFont(
    TTFont(
        "AZUnicode",
        str(
            font_path
        )
    )
)


styles = getSampleStyleSheet()


title_style = ParagraphStyle(
    "AZTitle",
    parent=styles[
        "Title"
    ],
    fontName="AZUnicode",
    fontSize=16,
    leading=20,
)


heading_style = ParagraphStyle(
    "AZHeading",
    parent=styles[
        "Heading2"
    ],
    fontName="AZUnicode",
    fontSize=11,
    leading=14,
)


body_style = ParagraphStyle(
    "AZBody",
    parent=styles[
        "BodyText"
    ],
    fontName="AZUnicode",
    fontSize=8.5,
    leading=11,
)


small_style = ParagraphStyle(
    "AZSmall",
    parent=body_style,
    fontSize=7.4,
    leading=9,
)


doc = SimpleDocTemplate(
    str(
        PDF_OUT
    ),
    pagesize=A4,
    leftMargin=14 * mm,
    rightMargin=14 * mm,
    topMargin=14 * mm,
    bottomMargin=14 * mm,
)


story = []


story.append(
    Paragraph(
        "ATLAS ZERO — Film10 Visual Production Pack V1",
        title_style
    )
)


story.append(
    Paragraph(
        (
            f"Remaining {len(gaps)} technical gaps are consolidated into "
            f"{len(units)} editorial visual production units."
        ),
        body_style
    )
)


story.append(
    Spacer(
        1,
        8
    )
)


summary_table = [[
    Paragraph(
        "Mode",
        small_style
    ),
    Paragraph(
        "Units",
        small_style
    ),
    Paragraph(
        "Seconds",
        small_style
    ),
]]


for key in sorted(
    mode_count,
    key=lambda k:
        -mode_sec[k]
):

    summary_table.append([
        Paragraph(
            esc(key),
            small_style
        ),
        str(
            mode_count[key]
        ),
        f"{mode_sec[key]:.3f}",
    ])


tbl = Table(
    summary_table,
    colWidths=[
        105 * mm,
        25 * mm,
        35 * mm,
    ],
    repeatRows=1,
)


tbl.setStyle(
    TableStyle([
        (
            "GRID",
            (0, 0),
            (-1, -1),
            0.25,
            colors.grey
        ),
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.lightgrey
        ),
        (
            "FONTNAME",
            (0, 0),
            (-1, -1),
            "AZUnicode"
        ),
        (
            "VALIGN",
            (0, 0),
            (-1, -1),
            "TOP"
        ),
    ])
)


story.append(
    tbl
)

story.append(
    PageBreak()
)


for unit in units:

    story.append(
        Paragraph(
            (
                f"{esc(unit['unit_id'])} — "
                f"{esc(unit['target'])} / "
                f"{esc(unit['subtype'])}"
            ),
            heading_style
        )
    )

    meta = [
        [
            "Time",
            (
                f"{unit['start_sec']:.3f}–"
                f"{unit['end_sec']:.3f} "
                f"({unit['duration_sec']:.3f}s)"
            ),
        ],
        [
            "Shots",
            ", ".join(
                str(x)
                for x in unit[
                    "shot_indices"
                ]
            ),
        ],
        [
            "Mode",
            unit[
                "production_mode"
            ],
        ],
        [
            "Priority",
            unit[
                "priority"
            ],
        ],
    ]


    table_rows = []

    for a, b in meta:

        table_rows.append([
            Paragraph(
                f"<b>{esc(a)}</b>",
                small_style
            ),
            Paragraph(
                esc(b),
                small_style
            ),
        ])


    table = Table(
        table_rows,
        colWidths=[
            30 * mm,
            140 * mm,
        ]
    )


    table.setStyle(
        TableStyle([
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.2,
                colors.grey
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, -1),
                "AZUnicode"
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP"
            ),
        ])
    )


    story.append(
        table
    )

    story.append(
        Spacer(
            1,
            4
        )
    )


    story.append(
        Paragraph(
            "<b>Visual brief:</b> "
            + esc(
                unit[
                    "visual_brief"
                ]
            ),
            body_style
        )
    )


    if unit[
        "search_brief"
    ]:

        story.append(
            Spacer(
                1,
                3
            )
        )

        story.append(
            Paragraph(
                "<b>Search:</b> "
                + esc(
                    unit[
                        "search_brief"
                    ]
                ),
                body_style
            )
        )


    if unit[
        "generation_prompt"
    ]:

        story.append(
            Spacer(
                1,
                3
            )
        )

        story.append(
            Paragraph(
                "<b>Generation prompt:</b> "
                + esc(
                    unit[
                        "generation_prompt"
                    ]
                ),
                body_style
            )
        )


    story.append(
        Spacer(
            1,
            3
        )
    )

    story.append(
        Paragraph(
            "<b>Narration:</b> "
            + esc(
                unit[
                    "narration"
                ]
            ),
            body_style
        )
    )


    story.append(
        Spacer(
            1,
            10
        )
    )


doc.build(
    story
)


# =============================================================================
# VALIDATION
# =============================================================================

outputs = [
    JSON_OUT,
    TXT_OUT,
    HTML_OUT,
    PDF_OUT,
]


for p in outputs:

    if not p.exists():
        raise RuntimeError(
            f"Missing output: {p}"
        )

    if p.stat().st_size <= 0:
        raise RuntimeError(
            f"Empty output: {p}"
        )


if PDF_OUT.stat().st_size < 10000:
    raise RuntimeError(
        "PDF suspiciously small."
    )


print()
print("=" * 120)
print("PRODUCTION PACK SUMMARY")
print("=" * 120)

print(
    "INPUT GAP SHOTS     :",
    len(
        gaps
    )
)

print(
    "INPUT GAP SEC       :",
    f"{total_gap_sec:.3f}"
)

print(
    "PRODUCTION UNITS    :",
    len(
        units
    )
)

print(
    "UNIT SEC            :",
    f"{total_unit_sec:.3f}"
)

print(
    "SHOT COVERAGE       :",
    f"{len(output_shots)}/{len(input_shots)}"
)

print()

print(
    "BY MODE:"
)

for key in sorted(
    mode_count,
    key=lambda k:
        -mode_sec[k]
):

    print(
        f"  {key:34s} "
        f"{mode_count[key]:3d} units | "
        f"{mode_sec[key]:8.3f} sec"
    )


print()

print(
    "BY TARGET:"
)

for key in sorted(
    target_count,
    key=lambda k:
        -target_sec[k]
):

    print(
        f"  {key:34s} "
        f"{target_count[key]:3d} units | "
        f"{target_sec[key]:8.3f} sec"
    )


print()
print("=" * 120)
print("OUTPUTS")
print("=" * 120)


for p in outputs:

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
print("FILM10 VISUAL PRODUCTION PACK V1: PASS")
print("=" * 120)
print(
    "NEXT: produce SEARCH_REAL / GENERATE_EDITORIAL / BUILD_GRAPHIC units and feed them into render-ready timeline."
)
print("=" * 120)

