from pathlib import Path
import json
from collections import Counter, defaultdict

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

QC_JSON = (
    PROJECT
    / "00_Production"
    / "editorial_fragment_qc_v1"
    / "FILM10_EDITORIAL_FRAGMENT_QC_V1.json"
)

FRAGMENT_JSON = (
    PROJECT
    / "00_Production"
    / "editorial_fragmenter_v2"
    / "FILM10_EDITORIAL_FRAGMENTS_V2.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "human_editorial_ground_truth_v1"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUT = (
    OUT_DIR
    / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_V1.json"
)

print("=" * 124)
print("ATLAS ZERO — FILM10 HUMAN EDITORIAL GROUND TRUTH V1")
print("=" * 124)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

# =============================================================================
# LOAD CANONICAL EDITORIAL FRAGMENTS
# =============================================================================

source = QC_JSON if QC_JSON.exists() else FRAGMENT_JSON

if not source.exists():
    raise FileNotFoundError(
        "Neither QC V1 nor Editorial Fragments V2 exists."
    )

payload = json.loads(
    source.read_text(
        encoding="utf-8"
    )
)

fragments = payload.get(
    "fragments",
    []
)

if len(fragments) != 153:
    raise RuntimeError(
        f"Expected 153 reviewed fragments, got {len(fragments)}"
    )

# Normalize review numbers.
for index, fragment in enumerate(
    fragments,
    1,
):
    fragment["review_number"] = int(
        fragment.get(
            "review_number",
            index,
        )
    )

by_number = {
    int(row["review_number"]): row
    for row in fragments
}

if set(by_number) != set(range(1, 154)):
    raise RuntimeError(
        "Review numbers are not exactly 1..153."
    )

# =============================================================================
# HUMAN EDITORIAL LABELS
#
# production_status:
#
# KEEP_STRONG   — high-value footage suitable for rough/final candidate
# KEEP_CONTEXT  — geography/before/context/explanation
# SPECIAL_USE   — usable only selectively; text/logo/mixed material
# DUPLICATE     — redundant copy; use preferred source instead
# REJECT        — technical insert, advertising, ident, irrelevant material
# =============================================================================

labels = {
    n: {
        "review_number": n,
        "production_status": "REVIEW",
        "semantic_category": "UNCLASSIFIED",
        "flags": [],
        "reason": None,
        "preferred_over": [],
        "preferred_fragment": None,
        "sequence_group": None,
        "max_sequence_uses": None,
    }
    for n in range(1, 154)
}


def apply(
    numbers,
    status,
    category,
    *,
    flags=None,
    reason=None,
    preferred_fragment=None,
    sequence_group=None,
    max_sequence_uses=None,
):
    for n in numbers:

        row = labels[n]

        row["production_status"] = status
        row["semantic_category"] = category
        row["flags"] = list(flags or [])
        row["reason"] = reason
        row["preferred_fragment"] = preferred_fragment
        row["sequence_group"] = sequence_group
        row["max_sequence_uses"] = max_sequence_uses


def rng(a, b):
    return range(a, b + 1)


# =============================================================================
# 001–005 — Gyirong port / mudslide CCTV — archive source
# =============================================================================

apply(
    rng(1, 5),
    "KEEP_STRONG",
    "GYIRONG_PORT_MUDSLIDE",
    flags=["REAL_EVENT", "CCTV_STYLE"],
    reason="Strong primary Gyirong mudslide sequence; preferred over repost copies.",
    sequence_group="GYIRONG_PORT_ARCHIVE_A",
    max_sequence_uses=4,
)

# =============================================================================
# 006–009 — glacier / mountain / collapse source
# =============================================================================

apply(
    rng(6, 8),
    "KEEP_CONTEXT",
    "LANGTANG_GLACIER_MOUNTAIN",
    flags=["MOUNTAIN", "GLACIER", "BEFORE_OR_CONTEXT"],
    reason="Useful establishing geography and glacier context.",
)

apply(
    [9],
    "KEEP_STRONG",
    "GLACIER_COLLAPSE",
    flags=["REAL_EVENT", "COLLAPSE"],
    reason="Strong collapse/collapse-cloud material.",
)

# =============================================================================
# 010–014 — Rasuwa town / flood
# =============================================================================

apply(
    rng(10, 13),
    "KEEP_STRONG",
    "RASUWA_FLOOD_TOWN",
    flags=["REAL_EVENT", "FLOOD", "SETTLEMENT"],
    reason="Strong wide and medium views of flood through populated area.",
    sequence_group="RASUWA_TOWN_A",
    max_sequence_uses=4,
)

apply(
    [14],
    "KEEP_CONTEXT",
    "RASUWA_AFTER_FLOOD",
    flags=["AFTERMATH", "SETTLEMENT"],
    reason="Useful aftermath/context transition.",
)

# =============================================================================
# 015–019 — second Gyirong CCTV/archive angle
# =============================================================================

apply(
    rng(15, 19),
    "KEEP_STRONG",
    "GYIRONG_PORT_MUDSLIDE",
    flags=["REAL_EVENT", "CCTV_STYLE"],
    reason="Second useful Gyirong sequence; distinct enough for selective use.",
    sequence_group="GYIRONG_PORT_ARCHIVE_B",
    max_sequence_uses=3,
)

# =============================================================================
# 020–023 — Gyirong before / geography
# =============================================================================

apply(
    rng(20, 23),
    "KEEP_CONTEXT",
    "GYIRONG_BEFORE",
    flags=["BEFORE", "GEOGRAPHY", "VERTICAL"],
    reason="Useful pre-disaster location context and border geography.",
    sequence_group="GYIRONG_BEFORE",
    max_sequence_uses=2,
)

# 024 — 4 sec before/after webm with failed preview
apply(
    [24],
    "SPECIAL_USE",
    "BEFORE_AFTER_COMPARISON",
    flags=["FRAME_EXTRACTION_ISSUE", "SHORT"],
    reason="Potentially useful before/after comparison; requires runtime decode check.",
)

# =============================================================================
# 025–026 — The Hindu repost of Gyirong CCTV
# =============================================================================

apply(
    rng(25, 26),
    "DUPLICATE",
    "GYIRONG_PORT_MUDSLIDE",
    flags=["VERTICAL", "TEXT_HEAVY", "BRAND_HEAVY", "REPOST"],
    reason="Same event already available from cleaner archive sources.",
    preferred_fragment="#001-005",
)

# =============================================================================
# 027–032 — GMA branded Gyirong copies
# =============================================================================

apply(
    rng(27, 32),
    "DUPLICATE",
    "GYIRONG_PORT_MUDSLIDE",
    flags=["BRAND_HEAVY", "NEWS_GRAPHICS", "REPOST"],
    reason="Branded duplicate/repackaging of cleaner Gyirong archive footage.",
    preferred_fragment="#001-005/#015-019",
)

# =============================================================================
# 033–035 — mixed flood/border report
# =============================================================================

apply(
    [33],
    "KEEP_CONTEXT",
    "BORDER_DAMAGE",
    flags=["VERTICAL", "AFTERMATH"],
    reason="Useful border/damage context.",
)

apply(
    [34],
    "SPECIAL_USE",
    "BORDER_DAMAGE",
    flags=["VERTICAL", "PRESENTER_INSERT", "MIXED_CONTENT"],
    reason="Useful first portion but fragment includes presenter/graphic material.",
)

apply(
    [35],
    "KEEP_CONTEXT",
    "FLOOD_DEBRIS",
    flags=["VERTICAL", "TEXT_OVERLAY"],
    reason="Potential debris/flood context with overlay.",
)

# =============================================================================
# 036–051 — CGTN America mixed explanatory report
# =============================================================================

apply(
    [36],
    "SPECIAL_USE",
    "GLACIER_COLLAPSE",
    flags=["VERTICAL", "TEXT_HEAVY"],
    reason="Relevant event but heavily formatted social/news presentation.",
)

apply(
    [37, 39, 40, 44, 46],
    "KEEP_CONTEXT",
    "FLOOD_AFTERMATH",
    flags=["VERTICAL", "NEWS_OVERLAY"],
    reason="Useful flood/aftermath explanatory shots.",
)

apply(
    [38],
    "KEEP_CONTEXT",
    "RIVER_VALLEY",
    flags=["VERTICAL", "NEWS_OVERLAY"],
    reason="Useful geography/river context.",
)

apply(
    [41],
    "REJECT",
    "IRRELEVANT_OR_LOW_VALUE",
    flags=["PEOPLE_INSERT", "LOW_EDITORIAL_VALUE"],
    reason="Low-value people/interior-style insert; not needed for Film10.",
)

apply(
    [42],
    "KEEP_CONTEXT",
    "MAP_SATELLITE",
    flags=["MAP", "VERTICAL"],
    reason="Useful route/geography/map explanation.",
)

apply(
    [43],
    "KEEP_STRONG",
    "GLACIER_COLLAPSE",
    flags=["REAL_EVENT", "COLLAPSE", "VERTICAL"],
    reason="Strong collapse imagery despite vertical/social framing.",
)

apply(
    [45],
    "REJECT",
    "TECHNICAL_ARTICLE_INSERT",
    flags=["ARTICLE_SCREEN", "TEXT_HEAVY"],
    reason="Article/webpage insert; not production footage.",
)

apply(
    [47, 48, 49, 50],
    "KEEP_CONTEXT",
    "HIMALAYA_GEOGRAPHY",
    flags=["VERTICAL", "NEWS_OVERLAY"],
    reason="Useful mountain/valley/geography context.",
)

apply(
    [51],
    "REJECT",
    "INTERVIEW_OR_PRESENTER_INSERT",
    flags=["INTERVIEW", "PRESENTER", "LOW_PRIORITY"],
    reason="Interview/presenter montage not required for current narration.",
)

# =============================================================================
# 052–056 — CNA
# =============================================================================

apply(
    rng(52, 54),
    "KEEP_CONTEXT",
    "GLACIER_COLLAPSE_CONTEXT",
    flags=["VERTICAL", "NEWS_TEXT"],
    reason="Relevant glacier/collapse sequence but with social/news overlays.",
)

apply(
    [55],
    "SPECIAL_USE",
    "RESCUE_RESPONSE",
    flags=["VERTICAL", "MIXED_CONTENT", "ENDS_WITH_INTERFACE"],
    reason="Rescue vehicle is useful but fragment transitions into call/interface screen.",
)

apply(
    [56],
    "REJECT",
    "INTERFACE_SCREEN",
    flags=["CALL_SCREEN", "TECHNICAL_INSERT"],
    reason="Phone/call interface; not production footage.",
)

# =============================================================================
# 057–058 — Straits Times glacier collapse
# =============================================================================

apply(
    rng(57, 58),
    "KEEP_STRONG",
    "GLACIER_COLLAPSE",
    flags=["REAL_EVENT", "VERTICAL", "TEXT_OVERLAY"],
    reason="Strong collapse footage; use selectively due to embedded graphics.",
    sequence_group="COLLAPSE_ST",
    max_sequence_uses=2,
)

# =============================================================================
# 059–066 — Lokmat Times explainer
# =============================================================================

apply(
    [59, 60],
    "SPECIAL_USE",
    "GLACIER_COLLAPSE",
    flags=["VERTICAL", "TEXT_HEAVY"],
    reason="Relevant but heavily overlaid collapse material.",
)

apply(
    rng(61, 65),
    "SPECIAL_USE",
    "MAP_SATELLITE_EXPLAINER",
    flags=["VERTICAL", "TEXT_HEAVY", "INFOGRAPHIC"],
    reason="Potentially useful for technical explanation, not generic visual filler.",
)

apply(
    [66],
    "KEEP_CONTEXT",
    "RESCUE_RESPONSE",
    flags=["VERTICAL", "NEWS_TEXT"],
    reason="Useful rescue/emergency response visual.",
)

# =============================================================================
# 067–068 — AsiaOne rescuers in debris
# =============================================================================

apply(
    rng(67, 68),
    "KEEP_STRONG",
    "RESCUE_DEBRIS",
    flags=["REAL_EVENT", "VERTICAL", "RESCUERS"],
    reason="Strong rescue/search footage in debris.",
    sequence_group="RESCUE_ASIAONE",
    max_sequence_uses=2,
)

# =============================================================================
# 069–070 — Bharatpost collapse repost
# =============================================================================

apply(
    [69],
    "KEEP_STRONG",
    "GLACIER_COLLAPSE",
    flags=["REAL_EVENT", "VERTICAL", "TEXT_OVERLAY"],
    reason="Useful collapse comparison footage.",
)

apply(
    [70],
    "SPECIAL_USE",
    "GLACIER_COLLAPSE",
    flags=["VERTICAL", "OUTRO_OR_UI", "MIXED_CONTENT"],
    reason="Useful first portion but fragment ends in non-event interface/outro.",
)

# =============================================================================
# 071–073 — Rasuwa aerial landslide/flood
# =============================================================================

apply(
    rng(71, 73),
    "KEEP_STRONG",
    "RASUWA_AERIAL_DESTRUCTION",
    flags=["REAL_EVENT", "AERIAL", "VERTICAL", "BRAND_OVERLAY"],
    reason="Strong aerial views of destruction and debris flow.",
    sequence_group="RASUWA_AERIAL_GMA",
    max_sequence_uses=3,
)

# =============================================================================
# 074–095 — Gyirong road reconstruction / devastation aerial
# =============================================================================

apply(
    rng(74, 95),
    "KEEP_STRONG",
    "ROAD_DESTRUCTION_RESCUE",
    flags=["REAL_EVENT", "AERIAL", "ROAD_DAMAGE", "HEAVY_MACHINERY"],
    reason="High-value sequence with distinct aerial views of destroyed road, debris, machinery and recovery.",
    sequence_group="GYIRONG_ROAD_AERIAL",
    max_sequence_uses=8,
)

# =============================================================================
# 096–111 — Varendra TV event montage
# =============================================================================

apply(
    rng(96, 103),
    "SPECIAL_USE",
    "GLACIER_COLLAPSE",
    flags=["BRAND_HEAVY", "LOWER_THIRD", "NEWS_REPACKAGE"],
    reason="Strong underlying collapse visuals but severe persistent branding.",
)

apply(
    rng(104, 109),
    "SPECIAL_USE",
    "RASUWA_FLOOD_TOWN",
    flags=["BRAND_HEAVY", "LOWER_THIRD", "NEWS_REPACKAGE"],
    reason="Useful flood/town visuals but better cleaner versions exist elsewhere.",
)

apply(
    rng(110, 111),
    "DUPLICATE",
    "GYIRONG_PORT_MUDSLIDE",
    flags=["BRAND_HEAVY", "LOWER_THIRD", "REPOST"],
    reason="Gyirong event already represented by cleaner archive footage.",
    preferred_fragment="#001-005/#015-019",
)

# =============================================================================
# 112–115 — advertisements / ident
# =============================================================================

apply(
    rng(112, 114),
    "REJECT",
    "ADVERTISEMENT",
    flags=["COMMERCIAL_AD", "IRRELEVANT"],
    reason="Real-estate advertising unrelated to Film10.",
)

apply(
    [115],
    "REJECT",
    "CHANNEL_IDENT",
    flags=["BRAND_STING", "CHANNEL_IDENT"],
    reason="TV channel ident/sting; not documentary content.",
)

# =============================================================================
# 116 — drilling / rescue
# =============================================================================

apply(
    [116],
    "KEEP_STRONG",
    "RESCUE_DRILLING",
    flags=["REAL_EVENT", "RESCUE", "HEAVY_MACHINERY", "VERTICAL"],
    reason="Strong specific rescue/drilling footage.",
)

# =============================================================================
# 117–126 — duplicated Gyirong copies from nepal-1 / nepal-2
# =============================================================================

apply(
    rng(117, 126),
    "DUPLICATE",
    "GYIRONG_PORT_MUDSLIDE",
    flags=["REPOST", "DUPLICATE_EVENT"],
    reason="Duplicate copies of Gyirong sequences already preserved from preferred archive sources.",
    preferred_fragment="#001-005/#015-019",
)

# =============================================================================
# 127–131 — Rasuwa town repost/alternate crop
# =============================================================================

apply(
    rng(127, 131),
    "DUPLICATE",
    "RASUWA_FLOOD_TOWN",
    flags=["REPOST", "VERTICAL_OR_CROP"],
    reason="Same Rasuwa town flood sequence available earlier in cleaner/wider source.",
    preferred_fragment="#010-014",
)

# =============================================================================
# 132–135 — flood with vehicles; two duplicate source pairs
# =============================================================================

apply(
    [132, 133],
    "KEEP_CONTEXT",
    "FLOOD_VEHICLES",
    flags=["REAL_EVENT", "VERTICAL"],
    reason="Useful alternate flood/vehicle view.",
    sequence_group="FLOOD_VEHICLES",
    max_sequence_uses=2,
)

apply(
    [134, 135],
    "DUPLICATE",
    "FLOOD_VEHICLES",
    flags=["DUPLICATE_EVENT"],
    reason="Duplicate of #132-133 pair.",
    preferred_fragment="#132-133",
)

# =============================================================================
# 136–145 — flood/debris surge around buildings
# =============================================================================

apply(
    rng(136, 145),
    "KEEP_STRONG",
    "FLOOD_BUILDINGS_IMPACT",
    flags=["REAL_EVENT", "FLOOD_SURGE", "BUILDINGS", "VERTICAL"],
    reason="Powerful continuous sequence showing flood/debris impact near buildings.",
    sequence_group="NEPAL6_FLOOD_BUILDINGS",
    max_sequence_uses=5,
)

# =============================================================================
# 146–147 — ground-level search / debris
# =============================================================================

apply(
    rng(146, 147),
    "KEEP_CONTEXT",
    "GROUND_SEARCH_DEBRIS",
    flags=["REAL_EVENT", "VERTICAL", "SEARCH"],
    reason="Useful close ground-level rescue/search context.",
)

# =============================================================================
# 148–153 — rescuers / tunnel / drilling/search
# =============================================================================

apply(
    rng(148, 153),
    "KEEP_STRONG",
    "RESCUE_TUNNEL_SEARCH",
    flags=["REAL_EVENT", "RESCUE", "TUNNEL", "VERTICAL"],
    reason="Strong rescue/search/tunnel sequence.",
    sequence_group="RESCUE_TUNNEL",
    max_sequence_uses=4,
)

# =============================================================================
# VALIDATION
# =============================================================================

unclassified = [
    n
    for n, row in labels.items()
    if row["production_status"] == "REVIEW"
]

if unclassified:
    raise RuntimeError(
        f"Unclassified fragments remain: {unclassified}"
    )

# Attach source details.
ground_truth = []

for n in range(1, 154):

    fragment = by_number[n]
    human = labels[n]

    ground_truth.append({
        "review_number": n,

        "fragment_id":
            fragment["fragment_id"],

        "filename":
            fragment.get("filename"),

        "source_path":
            fragment.get("source_path"),

        "source_start":
            fragment["source_start"],

        "source_end":
            fragment["source_end"],

        "duration_sec":
            fragment.get("duration_sec"),

        "production_status":
            human["production_status"],

        "semantic_category":
            human["semantic_category"],

        "flags":
            human["flags"],

        "reason":
            human["reason"],

        "preferred_fragment":
            human["preferred_fragment"],

        "sequence_group":
            human["sequence_group"],

        "max_sequence_uses":
            human["max_sequence_uses"],

        "human_review":
            True,

        "human_confidence":
            1.0,
    })

# =============================================================================
# SUMMARY
# =============================================================================

status_counts = Counter(
    row["production_status"]
    for row in ground_truth
)

category_counts = Counter(
    row["semantic_category"]
    for row in ground_truth
)

duration_by_status = defaultdict(float)

for row in ground_truth:
    duration_by_status[
        row["production_status"]
    ] += float(
        row["duration_sec"] or 0.0
    )

print()
print("=" * 124)
print("HUMAN EDITORIAL SUMMARY")
print("=" * 124)

for status in (
    "KEEP_STRONG",
    "KEEP_CONTEXT",
    "SPECIAL_USE",
    "DUPLICATE",
    "REJECT",
):
    print(
        f"{status:<15} "
        f"fragments={status_counts[status]:3d} "
        f"time={duration_by_status[status]:8.3f}s"
    )

production_pool = [
    row
    for row in ground_truth
    if row["production_status"]
    in {
        "KEEP_STRONG",
        "KEEP_CONTEXT",
        "SPECIAL_USE",
    }
]

production_time = sum(
    float(row["duration_sec"] or 0.0)
    for row in production_pool
)

print()
print("PRODUCTION-ELIGIBLE FRAGMENTS :", len(production_pool))
print("PRODUCTION-ELIGIBLE RAW TIME  :", f"{production_time:.3f}s")

minutes = int(
    production_time // 60
)

seconds = (
    production_time
    - minutes * 60
)

print(
    "PRODUCTION-ELIGIBLE RAW TC    :",
    f"{minutes:02d}:{seconds:06.3f}",
)

print()
print("TOP CATEGORIES:")

for category, count in category_counts.most_common():
    print(
        f"{category:<32} {count:3d}"
    )

# =============================================================================
# OUTPUT
# =============================================================================

output_payload = {
    "schema":
        "atlas_zero.film10.human_editorial_ground_truth.v1",

    "project_id":
        PROJECT_ID,

    "source_review":
        "FILM10_EDITORIAL_QC_FULL_REVIEW_V1.pdf",

    "reviewed_fragments":
        153,

    "human_confidence":
        1.0,

    "status_counts":
        dict(status_counts),

    "duration_by_status_sec":
        {
            key: round(value, 3)
            for key, value
            in duration_by_status.items()
        },

    "production_pool": {
        "statuses": [
            "KEEP_STRONG",
            "KEEP_CONTEXT",
            "SPECIAL_USE",
        ],

        "fragment_count":
            len(production_pool),

        "raw_duration_sec":
            round(
                production_time,
                3,
            ),
    },

    "sequence_policy": {
        "same_fragment_exact_reuse":
            "FORBIDDEN",

        "same_sequence_reuse":
            "LIMITED_BY_MAX_SEQUENCE_USES",

        "duplicate_status":
            "NOT_PRODUCTION_ELIGIBLE",

        "reject_status":
            "NOT_PRODUCTION_ELIGIBLE",

        "special_use":
            "ONLY_WHEN_NARRATION_SPECIFICALLY_JUSTIFIES_IT",
    },

    "fragments":
        ground_truth,

    "db_writes":
        False,

    "assignment":
        False,

    "render":
        False,

    "paid_calls":
        False,
}

OUT.write_text(
    json.dumps(
        output_payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("=" * 124)
print("OUTPUT")
print("=" * 124)
print(OUT)

print()
print("=" * 124)
print("FILM10 HUMAN EDITORIAL GROUND TRUTH V1: PASS")
print("=" * 124)

print("153/153 fragments classified.")
print("No DB writes.")
print("No assignment.")
print("No render.")
print("No paid API calls.")
