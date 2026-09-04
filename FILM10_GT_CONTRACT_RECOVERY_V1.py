from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import json
import re
import shutil
import subprocess
import sys

ROOT = Path.cwd()

PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

GT_FILE = (
    PROJECT
    / "00_Production"
    / "human_editorial_ground_truth_v1"
    / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_V1.json"
)

V3_SCRIPT = (
    ROOT
    / "FILM10_HUMAN_EDITORIAL_ASSIGNMENT_V3.py"
)

V2_TIMELINE = (
    PROJECT
    / "00_Production"
    / "human_editorial_assignment_v2"
    / "FILM10_HUMAN_EDITORIAL_TIMELINE_V2.json"
)

print("=" * 120)
print("ATLAS ZERO - FILM10 GT CONTRACT AUTO-RECOVERY + V3 REBUILD")
print("=" * 120)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("RENDER     : NO")
print("CLIP       : NO")
print()

for p in (
    GT_FILE,
    V3_SCRIPT,
    V2_TIMELINE,
):
    if not p.exists():
        raise FileNotFoundError(p)


# =============================================================================
# LOAD
# =============================================================================

gt_raw = json.loads(
    GT_FILE.read_text(
        encoding="utf-8"
    )
)

v2_raw = json.loads(
    V2_TIMELINE.read_text(
        encoding="utf-8"
    )
)

timeline = v2_raw["timeline"]


def discover_lists(obj):
    out = []

    def walk(value, path="$"):
        if isinstance(value, list):
            if (
                value
                and isinstance(
                    value[0],
                    dict
                )
            ):
                out.append(
                    (
                        path,
                        value
                    )
                )

            for idx, item in enumerate(
                value[:3]
            ):
                if isinstance(
                    item,
                    (list, dict)
                ):
                    walk(
                        item,
                        f"{path}[{idx}]"
                    )

        elif isinstance(
            value,
            dict
        ):
            for key, child in value.items():
                if isinstance(
                    child,
                    (list, dict)
                ):
                    walk(
                        child,
                        f"{path}.{key}"
                    )

    walk(obj)

    return out


candidates = discover_lists(
    gt_raw
)

if not candidates:
    raise RuntimeError(
        "No GT record arrays found"
    )


def score_gt(rows):
    if not rows:
        return -1

    sample = rows[:min(
        20,
        len(rows)
    )]

    keys = set()

    for row in sample:
        keys.update(
            row.keys()
        )

    score = len(rows)

    vocabulary = (
        "fragment",
        "review",
        "status",
        "category",
        "semantic",
        "source",
        "asset",
        "path",
        "start",
        "end",
        "duration",
    )

    for key in keys:
        lk = key.lower()

        if any(
            word in lk
            for word in vocabulary
        ):
            score += 25

    if len(rows) == 153:
        score += 2000

    return score


ranked = sorted(
    (
        (
            score_gt(rows),
            path,
            rows,
        )
        for path, rows
        in candidates
    ),
    reverse=True,
    key=lambda x: x[0],
)

score, gt_path, gt_rows = ranked[0]

print("GT ARRAY PATH :", gt_path)
print("GT ROWS       :", len(gt_rows))
print()

if len(gt_rows) != 153:
    print(
        "WARNING: expected 153 human editorial fragments."
    )


# =============================================================================
# INSPECT ACTUAL FIELD CONTRACT
# =============================================================================

all_keys = Counter()

for row in gt_rows:
    all_keys.update(
        row.keys()
    )

print("=" * 120)
print("ACTUAL GT FIELD CONTRACT")
print("=" * 120)

for key, count in sorted(
    all_keys.items(),
    key=lambda x: (
        -x[1],
        x[0]
    )
):
    print(
        f"{key:40s} | "
        f"{count:3d}/{len(gt_rows)}"
    )

print()
print("FIRST THREE GT RECORDS:")

for i, row in enumerate(
    gt_rows[:3],
    1
):
    print("-" * 120)
    print(
        "RECORD",
        i
    )

    for key, value in row.items():

        text = repr(value)

        if len(text) > 240:
            text = (
                text[:237]
                + "..."
            )

        print(
            f"{key:32s}: "
            f"{text}"
        )


# =============================================================================
# FIELD DISCOVERY
# =============================================================================

KNOWN_STATUS = {
    "KEEP_STRONG",
    "KEEP_CONTEXT",
    "SPECIAL_USE",
    "DUPLICATE",
    "REJECT",
}

KNOWN_CATEGORIES = {
    "GYIRONG_PORT_MUDSLIDE",
    "LANGTANG_GLACIER_MOUNTAIN",
    "GLACIER_COLLAPSE",
    "RASUWA_FLOOD_TOWN",
    "RASUWA_AFTER_FLOOD",
    "GYIRONG_BEFORE",
    "BEFORE_AFTER_COMPARISON",
    "BORDER_DAMAGE",
    "FLOOD_DEBRIS",
    "FLOOD_AFTERMATH",
    "RIVER_VALLEY",
    "MAP_SATELLITE",
    "HIMALAYA_GEOGRAPHY",
    "GLACIER_COLLAPSE_CONTEXT",
    "RESCUE_RESPONSE",
    "RESCUE_DEBRIS",
    "RASUWA_AERIAL_DESTRUCTION",
    "ROAD_DESTRUCTION_RESCUE",
    "RESCUE_DRILLING",
    "FLOOD_VEHICLES",
    "FLOOD_BUILDINGS_IMPACT",
    "GROUND_SEARCH_DEBRIS",
    "RESCUE_TUNNEL_SEARCH",
    "TECHNICAL_ARTICLE_INSERT",
    "INTERFACE_SCREEN",
    "ADVERTISEMENT",
    "CHANNEL_IDENT",
    "IRRELEVANT_OR_LOW_VALUE",
    "INTERVIEW_OR_PRESENTER_INSERT",
}

MEDIA_EXT = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".m4v",
}


def norm(value):
    return str(
        value or ""
    ).strip()


def upper(value):
    return norm(
        value
    ).upper()


def number(value):
    try:
        return float(
            value
        )
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Score field candidates from ACTUAL values
# -----------------------------------------------------------------------------

field_scores = defaultdict(
    lambda: defaultdict(float)
)

for row in gt_rows:

    for key, value in row.items():

        lk = key.lower()
        sval = norm(value)
        uval = upper(value)

        # status
        if uval in KNOWN_STATUS:
            field_scores[
                "status"
            ][key] += 100

        if (
            "status" in lk
            or "decision" in lk
            or "review_status" in lk
        ):
            field_scores[
                "status"
            ][key] += 10

        # category
        if uval in KNOWN_CATEGORIES:
            field_scores[
                "category"
            ][key] += 100

        if (
            "category" in lk
            or "semantic" in lk
            or "editorial" in lk
        ):
            field_scores[
                "category"
            ][key] += 10

        # path / filename
        suffix = Path(
            sval
        ).suffix.lower()

        if suffix in MEDIA_EXT:
            field_scores[
                "path"
            ][key] += 80

        if (
            "path" in lk
            or "file" in lk
            or "source" in lk
            or "asset" in lk
        ):
            field_scores[
                "path"
            ][key] += 5

        # id
        if (
            "fragment" in lk
            and "id" in lk
        ):
            field_scores[
                "fragment_id"
            ][key] += 30

        if (
            lk == "id"
        ):
            field_scores[
                "fragment_id"
            ][key] += 10

        # start/end
        if number(
            value
        ) is not None:

            if (
                "start" in lk
                or "in_sec" in lk
                or lk.endswith("_in")
            ):
                field_scores[
                    "start"
                ][key] += 20

            if (
                "end" in lk
                or "out_sec" in lk
                or lk.endswith("_out")
            ):
                field_scores[
                    "end"
                ][key] += 20

            if "duration" in lk:
                field_scores[
                    "duration"
                ][key] += 20


def best_field(kind):
    values = field_scores.get(
        kind,
        {}
    )

    if not values:
        return None

    return max(
        values.items(),
        key=lambda x: x[1]
    )[0]


detected = {
    kind: best_field(kind)
    for kind in (
        "status",
        "category",
        "path",
        "fragment_id",
        "start",
        "end",
        "duration",
    )
}

print()
print("=" * 120)
print("AUTO-DETECTED GT FIELDS")
print("=" * 120)

for key, value in detected.items():
    print(
        f"{key:15s}: "
        f"{value}"
    )


# =============================================================================
# PATH RECOVERY
#
# Ground truth may store source filename rather than full path.
# Build basename index from current Film10 corpus and V2 timeline.
# =============================================================================

file_index = defaultdict(list)

for root in (
    PROJECT
    / "00_Research"
    / "visual_research"
    / "social_downloads",

    PROJECT
    / "02_Visuals"
    / "real"
    / "archive",
):

    if not root.exists():
        continue

    for p in root.rglob("*"):

        if (
            p.is_file()
            and p.suffix.lower()
            in MEDIA_EXT
        ):
            file_index[
                p.name.lower()
            ].append(
                p.resolve()
            )


for row in timeline:

    p_raw = norm(
        row.get(
            "asset_path"
        )
    )

    if not p_raw:
        continue

    p = Path(
        p_raw
    )

    if p.exists():
        file_index[
            p.name.lower()
        ].append(
            p.resolve()
        )


def resolve_media_path(value):

    if value is None:
        return None

    raw = norm(
        value
    )

    if not raw:
        return None

    p = Path(
        raw
    )

    if p.is_absolute():

        if p.exists():
            return p.resolve()

    else:

        direct = (
            ROOT
            / p
        )

        if direct.exists():
            return direct.resolve()

        direct2 = (
            PROJECT
            / p
        )

        if direct2.exists():
            return direct2.resolve()

    # basename lookup
    basename = p.name.lower()

    matches = file_index.get(
        basename,
        []
    )

    unique = []

    seen = set()

    for match in matches:

        key = str(
            match
        ).lower()

        if key not in seen:
            unique.append(
                match
            )
            seen.add(
                key
            )

    if len(unique) == 1:
        return unique[0]

    return None


# =============================================================================
# EXTRACT USABLE GT
# =============================================================================

status_field = detected[
    "status"
]

category_field = detected[
    "category"
]

path_field = detected[
    "path"
]

fragment_field = detected[
    "fragment_id"
]

start_field = detected[
    "start"
]

end_field = detected[
    "end"
]

duration_field = detected[
    "duration"
]


if not status_field:
    raise RuntimeError(
        "Could not detect GT status field"
    )

if not category_field:
    raise RuntimeError(
        "Could not detect GT category field"
    )

if not path_field:
    raise RuntimeError(
        "Could not detect GT media path/file field"
    )


eligible_status = {
    "KEEP_STRONG",
    "KEEP_CONTEXT",
    "SPECIAL_USE",
}

usable = []

reject_reasons = Counter()

for row in gt_rows:

    status = upper(
        row.get(
            status_field
        )
    )

    if status not in eligible_status:
        reject_reasons[
            "STATUS_NOT_ELIGIBLE"
        ] += 1
        continue

    category = upper(
        row.get(
            category_field
        )
    )

    media = resolve_media_path(
        row.get(
            path_field
        )
    )

    if media is None:
        reject_reasons[
            "MEDIA_PATH_NOT_RESOLVED"
        ] += 1
        continue

    start = (
        number(
            row.get(
                start_field
            )
        )
        if start_field
        else None
    )

    end = (
        number(
            row.get(
                end_field
            )
        )
        if end_field
        else None
    )

    dur = (
        number(
            row.get(
                duration_field
            )
        )
        if duration_field
        else None
    )

    if start is None:
        start = 0.0

    if end is None:

        if (
            dur is not None
            and dur > 0
        ):
            end = (
                start
                + dur
            )

    if (
        end is None
        or end <= start
    ):
        reject_reasons[
            "INVALID_RANGE"
        ] += 1
        continue

    fid = (
        norm(
            row.get(
                fragment_field
            )
        )
        if fragment_field
        else ""
    )

    usable.append({
        "fragment_id":
            fid,

        "status":
            status,

        "category":
            category,

        "asset_path":
            str(media),

        "source_start":
            float(start),

        "source_end":
            float(end),

        "duration_sec":
            float(
                end - start
            ),
    })


print()
print("=" * 120)
print("GT RECOVERY RESULT")
print("=" * 120)

print(
    "TOTAL GT ROWS       :",
    len(gt_rows)
)

print(
    "USABLE GT FRAGMENTS :",
    len(usable)
)

print(
    "USABLE RAW SEC      :",
    f"{sum(x['duration_sec'] for x in usable):.3f}"
)

print()

for reason, count in reject_reasons.items():
    print(
        f"{reason:28s}: "
        f"{count}"
    )


if len(usable) < 50:
    raise RuntimeError(
        "GT recovery produced fewer than 50 usable fragments. "
        "Refusing to patch V3 blindly."
    )


# =============================================================================
# WRITE NORMALIZED SIDE-CAR
#
# Important: we do NOT overwrite original human GT.
# =============================================================================

NORMALIZED = (
    PROJECT
    / "00_Production"
    / "human_editorial_ground_truth_v1"
    / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_NORMALIZED_V1.json"
)

NORMALIZED.write_text(
    json.dumps(
        {
            "schema":
                "atlas_zero.film10.human_editorial_ground_truth.normalized.v1",

            "generated_at":
                datetime.now().isoformat(),

            "source":
                str(
                    GT_FILE
                ),

            "detected_fields":
                detected,

            "fragment_count":
                len(
                    usable
                ),

            "fragments":
                usable,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print(
    "NORMALIZED GT:",
    NORMALIZED.relative_to(
        ROOT
    )
)


# =============================================================================
# PATCH COMPLETE V3 TO USE NORMALIZED GT
# =============================================================================

source = V3_SCRIPT.read_text(
    encoding="utf-8"
)

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup = V3_SCRIPT.with_name(
    V3_SCRIPT.name
    + f".before_gt_contract_fix_{stamp}.bak"
)

shutil.copy2(
    V3_SCRIPT,
    backup
)

print(
    "V3 BACKUP   :",
    backup.relative_to(
        ROOT
    )
)


old_gt = '''GT = PROJECT / "00_Production" / "human_editorial_ground_truth_v1" / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_V1.json"'''

new_gt = '''GT = PROJECT / "00_Production" / "human_editorial_ground_truth_v1" / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_NORMALIZED_V1.json"'''


if old_gt not in source:
    raise RuntimeError(
        "Expected GT declaration was not found in current V3 script."
    )

source = source.replace(
    old_gt,
    new_gt,
    1
)


# Normalized contract is explicitly {"fragments":[...]}
# Existing discovery already supports this key.

V3_SCRIPT.write_text(
    source,
    encoding="utf-8",
    newline="\n",
)


# =============================================================================
# COMPILE + RUN
# =============================================================================

print()
print("=" * 120)
print("V3 REBUILD")
print("=" * 120)

compile_result = subprocess.run(
    [
        sys.executable,
        "-m",
        "py_compile",
        str(
            V3_SCRIPT
        ),
    ],
    cwd=str(
        ROOT
    ),
)

if compile_result.returncode != 0:
    raise SystemExit(
        compile_result.returncode
    )

print(
    "PY_COMPILE : PASS"
)

print()
print(
    "RUNNING V3 WITH NORMALIZED HUMAN GT..."
)
print()

result = subprocess.run(
    [
        sys.executable,
        str(
            V3_SCRIPT
        ),
    ],
    cwd=str(
        ROOT
    ),
)

print()
print("=" * 120)

if result.returncode == 0:

    print(
        "FILM10 GT CONTRACT RECOVERY: PASS"
    )

    print(
        "V3 REBUILT WITH HUMAN-APPROVED VIDEO FRAGMENTS."
    )

else:

    print(
        "FILM10 GT CONTRACT RECOVERY: "
        f"DOWNSTREAM FAILURE ({result.returncode})"
    )

print("=" * 120)

raise SystemExit(
    result.returncode
)

