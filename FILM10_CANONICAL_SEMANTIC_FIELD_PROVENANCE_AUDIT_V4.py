from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
import json
import re
import sqlite3
import sys

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

DB_PATH = (
    ROOT
    / "workspace"
    / "atlas_zero_enterprise.sqlite3"
)

OUT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "semantic_context_v4_audit"
)

OUT.mkdir(parents=True, exist_ok=True)

print("=" * 120)
print("ATLAS ZERO — FILM10 CANONICAL SEMANTIC FIELD PROVENANCE AUDIT V4")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("DATABASE   :", DB_PATH)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("MODE       : READ ONLY")
print("CLIP RUN   : NO")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

if not DB_PATH.is_file():
    raise FileNotFoundError(DB_PATH)

# =============================================================================
# DATABASE SCHEMA + SCENE DATA
# =============================================================================

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

try:
    columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(story_scenes)"
        ).fetchall()
    ]

    print()
    print("=" * 120)
    print("STORY_SCENES COLUMNS")
    print("=" * 120)

    for col in columns:
        print(" -", col)

    preferred_fields = [
        "idx",
        "block",
        "title",
        "narrative_goal",
        "emotional_goal",
        "visual_strategy",
        "required_assets",
        "status",
        "coverage",
    ]

    selected_fields = [
        field
        for field in preferred_fields
        if field in columns
    ]

    if "idx" not in selected_fields:
        raise RuntimeError("story_scenes.idx not found")

    rows = conn.execute(
        f"""
        SELECT
            {", ".join(selected_fields)}
        FROM story_scenes
        WHERE project_id=?
        ORDER BY idx
        """,
        (PROJECT_ID,),
    ).fetchall()

finally:
    conn.close()

print()
print("SCENES:", len(rows))

if len(rows) != 86:
    raise RuntimeError(
        f"Expected 86 scenes, found {len(rows)}"
    )

# =============================================================================
# NORMALIZATION
# =============================================================================

def text(value):
    if value is None:
        return ""

    if isinstance(value, (list, tuple, dict)):
        return json.dumps(
            value,
            ensure_ascii=False,
        )

    return str(value).strip()


scene_records = []

for row in rows:
    record = {
        field: text(row[field])
        for field in selected_fields
    }
    scene_records.append(record)

# =============================================================================
# STRATEGIC SEMANTIC GROUPS — TESTS ONLY
# No production implementation is changed here.
# =============================================================================

strategic_groups = {
    "LANGTANG": (
        r"\bлангтанг",
        r"\blangtang",
    ),

    "GYIRONG": (
        r"\bгьиронг",
        r"\bгиронг",
        r"\bgyirong",
        r"\bkyirong",
    ),

    "TRISHULI": (
        r"\bтришули",
        r"\btrishuli",
    ),

    "NEPAL": (
        r"\bнепал",
        r"\bnepal",
    ),

    "USGS": (
        r"\busgs\b",
    ),

    "GLACIER": (
        r"\bледник",
        r"\bледника",
        r"\bледников",
        r"\bglacier",
    ),

    "SLOPE_COLLAPSE": (
        r"разрушени\w*\s+склон",
        r"обрушени\w*\s+склон",
        r"\bсклон",
        r"\bslope",
        r"\bcollapse",
    ),

    "FLOOD": (
        r"\bнаводнен",
        r"\bпавод",
        r"\bселев",
        r"\bпоток",
        r"\bгрязев",
        r"\bflood",
        r"\bdebris flow",
        r"\bflash flood",
    ),

    "SATELLITE": (
        r"\bспутник",
        r"\bспутников",
        r"\bsatellite",
        r"\bsentinel",
        r"\blandsat",
    ),

    "SCHOOL": (
        r"\bшкол",
        r"\bschool",
        r"\btribhuvan",
        r"\bученик",
        r"\bstudents?",
    ),

    "HYDROPOWER": (
        r"\bгидроэлект",
        r"\bгэс\b",
        r"\bэлектростан",
        r"\bhydropower",
        r"\bhydroelectric",
        r"\bpower plant",
    ),
}

# =============================================================================
# PRODUCTION / EDITORIAL CONTAMINATION SIGNALS
# =============================================================================

production_patterns = {
    "STRICT_SEMANTIC":
        r"\bstrict semantic\b",

    "MISSING_PREFERABLE":
        r"\bmissing preferable\b",

    "EVENT_RELEVANCE":
        r"\bevent relevance\b",

    "WRONG_VISUAL":
        r"\bwrong visual\b",

    "OPENING":
        r"\bopening\b",

    "SHOCK":
        r"\bshock\b",

    "HOOK":
        r"\bhook\b",

    "ATLAS_ZERO":
        r"\batlas\s+zero\b",

    "VISUAL_GAP":
        r"\bvisual[_\s-]*gap\b",

    "SEARCH_OR_GENERATE":
        r"\bsearch\s+or\s+generate\b",

    "LICENSE_REQUIRED":
        r"\blicense[_\s-]*required\b",

    "ACCEPT_REJECT":
        r"\baccept\b|\breject\b",

    "PRODUCTION_ELIGIBLE":
        r"\bproduction[_\s-]*eligible\b",
}

# =============================================================================
# FIELD COVERAGE
# =============================================================================

semantic_fields = [
    field
    for field in (
        "title",
        "narrative_goal",
        "emotional_goal",
        "visual_strategy",
        "required_assets",
    )
    if field in selected_fields
]

print()
print("=" * 120)
print("FIELD POPULATION")
print("=" * 120)

field_population = {}

for field in semantic_fields:
    count = sum(
        1
        for record in scene_records
        if record.get(field, "").strip()
    )

    field_population[field] = count

    print(
        f"{field:<22}: {count:>3} / {len(scene_records)}"
    )

# =============================================================================
# STRATEGIC TERM LOCATION BY FIELD
# =============================================================================

print()
print("=" * 120)
print("STRATEGIC TERM PROVENANCE")
print("=" * 120)

strategic_matrix = {}

for group, patterns in strategic_groups.items():
    strategic_matrix[group] = {}

    print()
    print(group)

    any_hit = False

    for field in semantic_fields:
        hits = []

        for record in scene_records:
            value = record.get(field, "")

            if not value:
                continue

            if any(
                re.search(
                    pattern,
                    value,
                    flags=re.I,
                )
                for pattern in patterns
            ):
                hits.append(
                    {
                        "idx": record.get("idx"),
                        "value": value,
                    }
                )

        strategic_matrix[group][field] = hits

        if hits:
            any_hit = True
            print(
                f"  {field:<20}: {len(hits)} scene(s)"
            )

            for item in hits[:5]:
                preview = re.sub(
                    r"\s+",
                    " ",
                    item["value"],
                )

                print(
                    f"      scene {str(item['idx']):>3}: "
                    + preview[:180]
                )
        else:
            print(
                f"  {field:<20}: 0"
            )

    if not any_hit:
        print("  >>> NOT FOUND IN ANY CANONICAL SCENE FIELD")

# =============================================================================
# PRODUCTION CONTAMINATION BY FIELD
# =============================================================================

print()
print("=" * 120)
print("PRODUCTION / EDITORIAL CONTAMINATION")
print("=" * 120)

contamination = {
    field: []
    for field in semantic_fields
}

for field in semantic_fields:
    print()
    print(field)

    for record in scene_records:
        value = record.get(field, "")

        if not value:
            continue

        labels = [
            name
            for name, pattern in production_patterns.items()
            if re.search(
                pattern,
                value,
                flags=re.I,
            )
        ]

        if not labels:
            continue

        contamination[field].append(
            {
                "idx": record.get("idx"),
                "labels": labels,
                "value": value,
            }
        )

    print(
        "  contaminated scenes:",
        len(contamination[field]),
    )

    for item in contamination[field][:12]:
        preview = re.sub(
            r"\s+",
            " ",
            item["value"],
        )

        print(
            f"    scene {str(item['idx']):>3} "
            f"| {','.join(item['labels'])} "
            f"| {preview[:200]}"
        )

# =============================================================================
# FIELD SEMANTIC QUALITY SCORE
# =============================================================================

print()
print("=" * 120)
print("FIELD QUALITY SUMMARY")
print("=" * 120)

field_quality = {}

for field in semantic_fields:

    strategic_groups_present = 0

    for group in strategic_groups:
        if strategic_matrix[group][field]:
            strategic_groups_present += 1

    contaminated_count = len(
        contamination[field]
    )

    populated_count = field_population[field]

    contamination_ratio = (
        contaminated_count / populated_count
        if populated_count
        else 0.0
    )

    field_quality[field] = {
        "populated":
            populated_count,

        "strategic_groups_present":
            strategic_groups_present,

        "strategic_groups_total":
            len(strategic_groups),

        "contaminated_scenes":
            contaminated_count,

        "contamination_ratio":
            round(
                contamination_ratio,
                6,
            ),
    }

    print(
        f"{field:<22} "
        f"| populated={populated_count:>3} "
        f"| strategic={strategic_groups_present:>2}/{len(strategic_groups)} "
        f"| contaminated={contaminated_count:>3} "
        f"| ratio={contamination_ratio:.3f}"
    )

# =============================================================================
# SCENES AROUND KEY STORY DOMAINS
# =============================================================================

print()
print("=" * 120)
print("KEY DOMAIN SCENES — FULL FIELD VIEW")
print("=" * 120)

key_domains = {
    "FLOOD": strategic_groups["FLOOD"],
    "SCHOOL": strategic_groups["SCHOOL"],
    "HYDROPOWER": strategic_groups["HYDROPOWER"],
    "SATELLITE": strategic_groups["SATELLITE"],
    "GYIRONG": strategic_groups["GYIRONG"],
}

domain_scene_ids = set()

for patterns in key_domains.values():
    for record in scene_records:
        haystack = " ".join(
            record.get(field, "")
            for field in semantic_fields
        )

        if any(
            re.search(
                pattern,
                haystack,
                flags=re.I,
            )
            for pattern in patterns
        ):
            try:
                domain_scene_ids.add(
                    int(record["idx"])
                )
            except Exception:
                pass

for idx in sorted(domain_scene_ids):

    record = next(
        item
        for item in scene_records
        if int(item["idx"]) == idx
    )

    print()
    print("-" * 120)
    print("SCENE:", idx)

    for field in semantic_fields:
        value = record.get(field, "")

        if value:
            print()
            print(field.upper() + ":")
            print(value)

# =============================================================================
# TOKEN / PHRASE DISCOVERY FROM CLEANER FIELDS
# =============================================================================

print()
print("=" * 120)
print("RECURRENT PHRASES BY FIELD")
print("=" * 120)

ru_en_token = re.compile(
    r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\-–—']+"
)

generic_stop = {
    "это", "этот", "эта", "эти", "что", "как", "где",
    "когда", "после", "перед", "через", "между",
    "один", "одна", "одно", "есть", "было", "были",
    "была", "будет", "уже", "еще", "ещё",
    "если", "такие", "иногда", "поэтому",
    "может", "могут", "который", "которая",
    "которые", "люди", "людей", "вода", "воды",
    "воду", "день", "утро", "время",
}

phrase_summary = {}

for field in semantic_fields:

    phrases = Counter()

    for record in scene_records:
        value = record.get(field, "")

        tokens = [
            token
            for token in ru_en_token.findall(value)
            if len(token) >= 3
        ]

        for n in (1, 2, 3):
            for i in range(
                0,
                len(tokens) - n + 1,
            ):
                seq = tokens[i:i+n]

                if all(
                    token.lower() in generic_stop
                    for token in seq
                ):
                    continue

                phrase = " ".join(seq)
                phrases[phrase] += 1

    top = [
        (phrase, count)
        for phrase, count in phrases.most_common(30)
        if count >= 2
    ]

    phrase_summary[field] = top

    print()
    print(field)

    for phrase, count in top[:20]:
        print(
            f"  {count:>3} | {phrase}"
        )

# =============================================================================
# RECOMMENDATION ENGINE
# =============================================================================

print()
print("=" * 120)
print("SOURCE SELECTION DIAGNOSTIC")
print("=" * 120)

ranked = sorted(
    field_quality.items(),
    key=lambda item: (
        item[1]["strategic_groups_present"],
        -item[1]["contamination_ratio"],
        item[1]["populated"],
    ),
    reverse=True,
)

for rank, (field, stats) in enumerate(
    ranked,
    1,
):
    print(
        f"{rank}. {field:<22} "
        f"strategic={stats['strategic_groups_present']}/{stats['strategic_groups_total']} "
        f"contamination={stats['contamination_ratio']:.3f} "
        f"populated={stats['populated']}"
    )

# =============================================================================
# REPORT
# =============================================================================

REPORT = (
    OUT
    / "FILM10_CANONICAL_SEMANTIC_FIELD_PROVENANCE_V4.json"
)

report = {
    "schema":
        "atlas_zero.film10.semantic_field_provenance.v4",

    "project_id":
        PROJECT_ID,

    "scene_count":
        len(scene_records),

    "story_scene_columns":
        columns,

    "semantic_fields":
        semantic_fields,

    "field_population":
        field_population,

    "field_quality":
        field_quality,

    "strategic_matrix": {
        group: {
            field: [
                {
                    "idx": item["idx"],
                    "value": item["value"],
                }
                for item in hits
            ]
            for field, hits in field_map.items()
        }
        for group, field_map
        in strategic_matrix.items()
    },

    "contamination":
        contamination,

    "recurrent_phrases": {
        field: [
            {
                "phrase": phrase,
                "count": count,
            }
            for phrase, count in values
        ]
        for field, values in phrase_summary.items()
    },

    "ranked_fields": [
        {
            "field": field,
            **stats,
        }
        for field, stats
        in ranked
    ],

    "clip_run":
        False,

    "db_writes":
        False,

    "assignments_written":
        False,

    "render_performed":
        False,

    "live_api":
        False,

    "paid_calls":
        False,
}

REPORT.write_text(
    json.dumps(
        report,
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
print("AUDIT COMPLETE")
print("=" * 120)

print("No source code modified.")
print("No CLIP inference performed.")
print("No DB writes performed.")
print("No assignments written.")
print("No render performed.")
print("No paid API calls.")
