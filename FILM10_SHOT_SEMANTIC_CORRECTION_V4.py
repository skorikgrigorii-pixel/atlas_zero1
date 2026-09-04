from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import html
import json
import re
import sqlite3
import sys

ROOT = Path.cwd()

PROJECT_ID = "film_10_nepal_tibet_aftershock"
PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID

TIMELINE = (
    PROJECT / "00_Production" / "human_editorial_assignment_v2"
    / "FILM10_HUMAN_EDITORIAL_TIMELINE_V2.json"
)

GAPS = (
    PROJECT / "00_Production" / "human_editorial_assignment_v2"
    / "FILM10_HUMAN_EDITORIAL_GAPS_V2.json"
)

OUT = (
    PROJECT / "00_Production"
    / "shot_semantic_correction_v4"
)

OUT.mkdir(parents=True, exist_ok=True)

JSON_OUT = OUT / "FILM10_SHOT_SEMANTIC_CORRECTION_V4.json"
TXT_OUT  = OUT / "FILM10_SHOT_SEMANTIC_CORRECTION_V4.txt"
HTML_OUT = OUT / "FILM10_SHOT_SEMANTIC_CORRECTION_V4.html"
PDF_OUT  = OUT / "FILM10_SHOT_SEMANTIC_CORRECTION_V4.pdf"


print("=" * 120)
print("ATLAS ZERO - FILM10 SHOT SEMANTIC CORRECTION V4")
print("=" * 120)
print("ROOT       :", ROOT)
print("PROJECT    :", PROJECT)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")
print()


# =============================================================================
# LOAD
# =============================================================================

if not TIMELINE.exists():
    raise FileNotFoundError(TIMELINE)

if not GAPS.exists():
    raise FileNotFoundError(GAPS)

timeline_raw = json.loads(
    TIMELINE.read_text(encoding="utf-8")
)

gaps_raw = json.loads(
    GAPS.read_text(encoding="utf-8")
)


def _record_list_score(rows, kind):
    if not isinstance(rows, list) or not rows:
        return -1

    sample = [
        x for x in rows[:10]
        if isinstance(x, dict)
    ]

    if not sample:
        return -1

    keys = set()

    for row in sample:
        keys.update(row.keys())

    score = len(rows)

    if kind == "timeline":
        wanted = {
            "shot_id",
            "timeline_start",
            "timeline_end",
            "asset_path",
            "narration",
            "duration_sec",
        }

        score += 100 * len(
            wanted.intersection(keys)
        )

        if len(rows) >= 200:
            score += 1000

    else:
        wanted = {
            "shot_id",
            "start_sec",
            "end_sec",
            "narration",
            "category",
            "target_category",
        }

        score += 100 * len(
            wanted.intersection(keys)
        )

        if 50 <= len(rows) <= 150:
            score += 1000

    return score


def _discover_record_lists(obj, path="$"):
    found = []

    if isinstance(obj, list):
        found.append((path, obj))

        for i, item in enumerate(obj[:3]):
            if isinstance(item, (dict, list)):
                found.extend(
                    _discover_record_lists(
                        item,
                        f"{path}[{i}]"
                    )
                )

    elif isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                found.extend(
                    _discover_record_lists(
                        value,
                        f"{path}.{key}"
                    )
                )

    return found


def _select_record_list(obj, kind):
    ranked = []

    for path, rows in _discover_record_lists(obj):
        score = _record_list_score(
            rows,
            kind
        )

        if score >= 0:
            ranked.append(
                (score, path, rows)
            )

    if not ranked:
        raise RuntimeError(
            f"No usable {kind} records found "
            f"in V2 JSON contract"
        )

    ranked.sort(
        key=lambda x: x[0],
        reverse=True
    )

    score, path, rows = ranked[0]

    print(
        f"{kind.upper()} JSON PATH:",
        path
    )

    return rows


timeline = _select_record_list(
    timeline_raw,
    "timeline"
)

gaps = _select_record_list(
    gaps_raw,
    "gaps"
)

if len(timeline) < 200:
    raise RuntimeError(
        f"Timeline V2 record extraction suspicious: "
        f"{len(timeline)} rows"
    )

if not (50 <= len(gaps) <= 150):
    raise RuntimeError(
        f"Gap V2 record extraction suspicious: "
        f"{len(gaps)} rows"
    )

print("TIMELINE ROWS :", len(timeline))
print("GAP RECORDS   :", len(gaps))

if len(gaps) != 81:
    print(
        "WARNING: expected 81 V2 gaps from previous audit, "
        f"actual={len(gaps)}"
    )


# =============================================================================
# GENERIC HELPERS
# =============================================================================

def fnum(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def shot_number(value):
    if isinstance(value, int):
        return value

    s = str(value or "")

    nums = re.findall(r"\d+", s)

    if not nums:
        return None

    return int(nums[-1])


def norm(text):
    text = str(text or "").lower()
    text = text.replace("ё", "е")
    return " ".join(text.split())


def has(text, *terms):
    t = norm(text)
    return any(norm(term) in t for term in terms)


def duration_of(row):
    for key in ("duration_sec", "duration"):
        if key in row:
            v = fnum(row.get(key), -1)
            if v >= 0:
                return v

    start = fnum(
        row.get(
            "timeline_start",
            row.get(
                "start_sec",
                row.get("start", 0)
            )
        )
    )

    end = fnum(
        row.get(
            "timeline_end",
            row.get(
                "end_sec",
                row.get("end", start)
            )
        )
    )

    return max(0.0, end - start)


def interval_of(row):
    start = fnum(
        row.get(
            "timeline_start",
            row.get(
                "start_sec",
                row.get("start", 0)
            )
        )
    )

    end = fnum(
        row.get(
            "timeline_end",
            row.get(
                "end_sec",
                row.get("end", start)
            )
        )
    )

    return start, end


# =============================================================================
# TIMELINE LOOKUPS
# =============================================================================

timeline_by_shot_id = {}
timeline_by_idx = {}

for pos, row in enumerate(timeline, 1):

    sid = str(
        row.get("shot_id")
        or row.get("id")
        or ""
    )

    idx = (
        shot_number(row.get("shot_id"))
        or shot_number(row.get("idx"))
        or pos
    )

    if sid:
        timeline_by_shot_id[sid] = row

    timeline_by_idx[idx] = row


# =============================================================================
# VISUAL NEED DISCOVERY
#
# Priority:
# 1. existing JSON reports containing visual_need;
# 2. canonical SQLite shots table, READ ONLY.
# =============================================================================

visual_need_by_idx = {}
visual_need_source = {}


def harvest_visual_needs(obj, source_name):

    if isinstance(obj, dict):

        vn = obj.get("visual_need")

        idx = (
            shot_number(obj.get("shot_id"))
            or shot_number(obj.get("shot_idx"))
            or shot_number(obj.get("idx"))
        )

        if vn and idx:

            vn = str(vn).strip()

            if vn:
                visual_need_by_idx.setdefault(idx, vn)
                visual_need_source.setdefault(idx, source_name)

        for value in obj.values():
            harvest_visual_needs(value, source_name)

    elif isinstance(obj, list):

        for value in obj:
            harvest_visual_needs(value, source_name)


candidate_jsons = []

for p in PROJECT.rglob("*.json"):

    name = p.name.upper()

    if (
        "GAP" in name
        or "AUDIT" in name
        or "TIMELINE" in name
        or "ASSIGNMENT" in name
    ):
        candidate_jsons.append(p)


for p in candidate_jsons:

    try:
        payload = json.loads(
            p.read_text(
                encoding="utf-8",
                errors="replace"
            )
        )

        harvest_visual_needs(
            payload,
            str(p.relative_to(ROOT))
        )

    except Exception:
        pass


# -----------------------------------------------------------------------------
# READ ONLY DB fallback
# -----------------------------------------------------------------------------

db_used = None

if len(visual_need_by_idx) < len(gaps):

    db_candidates = []

    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):

        for p in ROOT.rglob(pattern):

            lower_parts = {x.lower() for x in p.parts}

            if any(
                x in lower_parts
                for x in {
                    ".git",
                    ".venv",
                    "venv",
                    "__pycache__",
                    "node_modules",
                }
            ):
                continue

            db_candidates.append(p)

    for db_path in db_candidates:

        try:
            uri = db_path.resolve().as_uri() + "?mode=ro"

            con = sqlite3.connect(
                uri,
                uri=True
            )

            con.row_factory = sqlite3.Row

            table_rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()

            tables = {
                row["name"]
                for row in table_rows
            }

            if "shots" not in tables:
                con.close()
                continue

            cols = {
                row["name"]
                for row in con.execute(
                    "PRAGMA table_info(shots)"
                ).fetchall()
            }

            needed = {
                "project_id",
                "idx",
                "visual_need",
            }

            if not needed.issubset(cols):
                con.close()
                continue

            rows = con.execute(
                """
                SELECT idx, visual_need
                FROM shots
                WHERE project_id = ?
                ORDER BY idx
                """,
                (PROJECT_ID,)
            ).fetchall()

            if not rows:
                con.close()
                continue

            for row in rows:

                idx = int(row["idx"])

                vn = str(
                    row["visual_need"] or ""
                ).strip()

                if vn:

                    visual_need_by_idx[idx] = vn
                    visual_need_source[idx] = (
                        "canonical_db:"
                        + str(db_path.relative_to(ROOT))
                    )

            db_used = db_path

            con.close()
            break

        except Exception:
            try:
                con.close()
            except Exception:
                pass


print(
    "VISUAL NEEDS  :",
    len(visual_need_by_idx)
)

if db_used:
    print(
        "READ-ONLY DB  :",
        db_used.relative_to(ROOT)
    )
else:
    print("READ-ONLY DB  : not required / not found")


# =============================================================================
# SEMANTIC CORRECTION
#
# Critical precedence rule:
#
# 1. concrete shot narration
# 2. concrete visual_need
# 3. inherited V2 target only as weak context
#
# Never reverse this order.
# =============================================================================

def classify_semantic(
    idx,
    narration,
    visual_need,
    old_target
):

    n = norm(narration)
    v = norm(visual_need)
    combined = n + " " + v

    reasons = []

    # -----------------------------------------------------------------
    # SCHOOL - only when concrete school story is actually present
    # -----------------------------------------------------------------

    if has(
        combined,
        "tribhuvan",
        "школ",
        "ученик",
        "учител",
        "директор школы",
        "бидур",
        "bidur",
        "school_evacu",
        "school evacuation",
        "школьн"
    ):

        reasons.append(
            "Concrete school/Bidur/evacuation evidence in narration or visual_need."
        )

        return (
            "SCHOOL_BIDUR",
            "SEARCH_REQUIRED",
            "CRITICAL",
            reasons
        )

    # -----------------------------------------------------------------
    # USGS / SEISMIC SCIENCE
    # -----------------------------------------------------------------

    if has(
        combined,
        "usgs",
        "сейсм",
        "m5.2",
        "m4.2",
        "магнитуд",
        "сейсмостан",
        "сигнал землетрясения",
        "seismic",
        "satellite_science_evidence"
    ):

        reasons.append(
            "Narration requires scientific/seismic evidence, not inherited block imagery."
        )

        return (
            "USGS_SEISMIC_SCIENCE",
            "STATIC_EXISTING",
            "HIGH",
            reasons
        )

    # -----------------------------------------------------------------
    # WARNING / HUMAN COMMUNICATION
    # -----------------------------------------------------------------

    if has(
        n,
        "предупреж",
        "сообщен",
        "позвони",
        "звонок",
        "телефон",
        "крик",
        "полицейск",
        "голос",
        "указал",
        "указыва",
        "связь",
        "раннее оповещение",
        "система оповещения"
    ):

        reasons.append(
            "Narration is about transmission of warning between people."
        )

        return (
            "WARNING_COMMUNICATION",
            "GENERATE_REQUIRED",
            "HIGH",
            reasons
        )

    # -----------------------------------------------------------------
    # RECOVERY / FINAL MONTAGE
    # -----------------------------------------------------------------

    if has(
        n,
        "восстановлен",
        "восстановили",
        "снова откры",
        "вернулись в школ",
        "возвращались в школ",
        "свет",
        "дорога снова",
        "пограничный переход",
        "гидроэлектростанц",
        "жизнь возвращ",
        "восстановление"
    ) and idx >= 230:

        reasons.append(
            "Late-film recovery narration requires a mixed recovery montage."
        )

        return (
            "RECOVERY_FINAL_MONTAGE",
            "REUSE_EXISTING",
            "HIGH",
            reasons
        )

    # -----------------------------------------------------------------
    # 2015 LANGTANG HISTORICAL CONTEXT
    # -----------------------------------------------------------------

    if has(
        n,
        "2015",
        "лангтанг был погреб",
        "поселение",
        "погребен",
        "погребён",
        "лавина 2015",
        "землетрясение 2015",
        "погибли"
    ):

        reasons.append(
            "Narration is historical Langtang destruction context."
        )

        return (
            "LANGTANG_2015_ARCHIVE_CONTEXT",
            "REUSE_EXISTING",
            "HIGH",
            reasons
        )

    # -----------------------------------------------------------------
    # HYDROPOWER / TUNNEL RESCUE
    # -----------------------------------------------------------------

    if has(
        combined,
        "туннел",
        "рабоч",
        "заблокирован",
        "спасател",
        "tunnel",
        "worker",
        "rescue"
    ) and has(
        combined,
        "гидро",
        "hydro",
        "электростан",
        "станц",
        "плотин",
        "дамб"
    ):

        reasons.append(
            "Narration combines hydropower infrastructure with trapped-worker rescue."
        )

        return (
            "TUNNEL_WORKER_RESCUE",
            "REUSE_EXISTING",
            "CRITICAL",
            reasons
        )

    if has(
        combined,
        "гидроэлектростан",
        "гэс",
        "hydropower",
        "hydro_power",
        "hydroelectric",
        "электростан",
        "плотин",
        "дамб"
    ):

        reasons.append(
            "Exact hydropower infrastructure is required."
        )

        return (
            "HYDROPOWER_INFRASTRUCTURE",
            "SEARCH_REQUIRED",
            "CRITICAL",
            reasons
        )

    # -----------------------------------------------------------------
    # MAP / RIVER SYSTEM
    # -----------------------------------------------------------------

    if has(
        n,
        "уберите названия стран",
        "оставьте высот",
        "приток",
        "реки",
        "река",
        "долин",
        "сто километров",
        "100 километров",
        "маршрут воды",
        "путь воды"
    ) and has(
        combined,
        "карт",
        "map",
        "satellite",
        "спутник",
        "высот",
        "приток"
    ):

        reasons.append(
            "Narration describes geography/river propagation and needs a map."
        )

        return (
            "RIVER_SYSTEM_MAP",
            "STATIC_EXISTING",
            "HIGH",
            reasons
        )

    # -----------------------------------------------------------------
    # SATELLITE / MAP EVIDENCE
    # -----------------------------------------------------------------

    if has(
        combined,
        "satellite",
        "спутник",
        "sentinel",
        "landsat",
        "iss",
        "map",
        "карт",
        "before_after"
    ):

        reasons.append(
            "Concrete satellite/map evidence requested."
        )

        return (
            "SATELLITE_MAP_EVIDENCE",
            "STATIC_EXISTING",
            "MEDIUM",
            reasons
        )

    # -----------------------------------------------------------------
    # REAL GLACIER COLLAPSE
    # -----------------------------------------------------------------

    if has(
        combined,
        "drone_collapse",
        "дрон",
        "обрушен",
        "обвал",
        "collapse",
        "ледово",
        "ледник рух",
        "склон рух",
        "langtang_lirung"
    ) and has(
        combined,
        "обруш",
        "collapse",
        "дрон",
        "drone"
    ):

        reasons.append(
            "Narration requires the Langtang Lirung collapse itself."
        )

        return (
            "GLACIER_COLLAPSE_REAL",
            "REUSE_EXISTING",
            "CRITICAL",
            reasons
        )

    # -----------------------------------------------------------------
    # GYIRONG / KYIRONG
    # -----------------------------------------------------------------

    if has(
        combined,
        "gyirong",
        "kyirong",
        "гиронг",
        "кьиронг",
        "киронг",
        "порт",
        "port"
    ):

        reasons.append(
            "Narration or visual_need explicitly points to Gyirong/Kyirong."
        )

        return (
            "GYIRONG_DISASTER",
            "REUSE_EXISTING",
            "HIGH",
            reasons
        )

    # -----------------------------------------------------------------
    # BORDER
    # -----------------------------------------------------------------

    if has(
        combined,
        "границ",
        "погранич",
        "border"
    ):

        reasons.append(
            "Border geography / border impact is explicit."
        )

        return (
            "BORDER_CONTEXT",
            "REUSE_EXISTING",
            "MEDIUM",
            reasons
        )

    # -----------------------------------------------------------------
    # FLOOD / DEBRIS / AFTERMATH
    # -----------------------------------------------------------------

    if has(
        combined,
        "flood_debris",
        "наводнен",
        "поток",
        "грязев",
        "селев",
        "разруш",
        "debris",
        "mudslide",
        "aftermath",
        "снес"
    ):

        reasons.append(
            "Narration describes debris-flow destruction or aftermath."
        )

        return (
            "FLOOD_AFTERMATH",
            "REUSE_EXISTING",
            "MEDIUM",
            reasons
        )

    # -----------------------------------------------------------------
    # LANGTANG MOUNTAIN / GLACIER CONTEXT
    # -----------------------------------------------------------------

    if has(
        combined,
        "langtang",
        "лангтанг",
        "glacier",
        "ледник",
        "гора",
        "склон",
        "вершин",
        "himalaya",
        "гимала"
    ):

        reasons.append(
            "Narration genuinely needs Langtang/Himalaya mountain context."
        )

        return (
            "LANGTANG_MOUNTAIN_CONTEXT",
            "STATIC_EXISTING",
            "MEDIUM",
            reasons
        )

    # -----------------------------------------------------------------
    # SAFE FALLBACK
    #
    # Important: fallback DOES NOT mean random footage.
    # It stays visible for human editorial review.
    # -----------------------------------------------------------------

    reasons.append(
        "No reliable shot-specific deterministic rule matched; kept for explicit editorial review."
    )

    return (
        "EDITORIAL_REVIEW_REQUIRED",
        "GENERATE_REQUIRED",
        "HIGH",
        reasons
    )


# =============================================================================
# OLD TARGET COMPATIBILITY
# =============================================================================

compatible = {

    "SCHOOL": {
        "SCHOOL_BIDUR",
    },

    "GLACIER_CONTEXT": {
        "LANGTANG_MOUNTAIN_CONTEXT",
        "LANGTANG_2015_ARCHIVE_CONTEXT",
    },

    "GYIRONG_MUDSLIDE": {
        "GYIRONG_DISASTER",
        "BORDER_CONTEXT",
    },

    "HYDROPOWER": {
        "HYDROPOWER_INFRASTRUCTURE",
        "TUNNEL_WORKER_RESCUE",
    },

    "GLACIER_COLLAPSE": {
        "GLACIER_COLLAPSE_REAL",
    },

    "AFTERMATH": {
        "FLOOD_AFTERMATH",
        "RECOVERY_FINAL_MONTAGE",
    },
}


# =============================================================================
# CORRECT ALL GAP RECORDS
# =============================================================================

corrected = []

for pos, gap in enumerate(gaps, 1):

    sid = str(
        gap.get("shot_id")
        or gap.get("id")
        or ""
    )

    idx = (
        shot_number(gap.get("shot_id"))
        or shot_number(gap.get("idx"))
        or shot_number(gap.get("beat_id"))
    )

    timeline_row = None

    if sid and sid in timeline_by_shot_id:
        timeline_row = timeline_by_shot_id[sid]

    if timeline_row is None and idx in timeline_by_idx:
        timeline_row = timeline_by_idx[idx]

    if timeline_row is None:
        timeline_row = {}

    if idx is None:
        idx = shot_number(
            timeline_row.get("shot_id")
        )

    narration = str(
        gap.get("narration")
        or timeline_row.get("narration")
        or ""
    ).strip()

    visual_need = str(
        gap.get("visual_need")
        or timeline_row.get("visual_need")
        or visual_need_by_idx.get(idx, "")
    ).strip()

    old_target = str(
        gap.get("target_category")
        or gap.get("category")
        or gap.get("target")
        or ""
    ).strip().upper()

    start = fnum(
        gap.get(
            "start_sec",
            gap.get(
                "timeline_start",
                timeline_row.get(
                    "timeline_start",
                    0
                )
            )
        )
    )

    end = fnum(
        gap.get(
            "end_sec",
            gap.get(
                "timeline_end",
                timeline_row.get(
                    "timeline_end",
                    start
                )
            )
        )
    )

    dur = fnum(
        gap.get("duration_sec"),
        max(0.0, end - start)
    )

    (
        new_target,
        next_action,
        priority,
        reasons
    ) = classify_semantic(
        idx,
        narration,
        visual_need,
        old_target
    )

    expected = compatible.get(
        old_target,
        set()
    )

    contradiction = (
        bool(old_target)
        and bool(expected)
        and new_target not in expected
    )

    changed = (
        bool(old_target)
        and new_target != old_target
    )

    corrected.append({
        "shot_id": (
            gap.get("shot_id")
            or timeline_row.get("shot_id")
            or f"SHOT_{idx:03d}"
            if idx is not None
            else sid
        ),
        "shot_idx": idx,
        "start_sec": start,
        "end_sec": end,
        "duration_sec": dur,
        "narration": narration,
        "visual_need": visual_need,
        "visual_need_source": visual_need_source.get(
            idx,
            "timeline_or_gap_json"
        ),
        "old_target": old_target,
        "new_target": new_target,
        "next_action": next_action,
        "priority": priority,
        "old_target_contradiction": contradiction,
        "target_changed": changed,
        "reason": " ".join(reasons),
    })


# =============================================================================
# DURATION ACCOUNTING RECONCILIATION
# =============================================================================

timeline_starts = []
timeline_ends = []

timeline_row_sum = 0.0
assigned_row_sum = 0.0
unassigned_row_sum = 0.0
assigned_rows = 0
unassigned_rows = 0

for row in timeline:

    start, end = interval_of(row)

    timeline_starts.append(start)
    timeline_ends.append(end)

    dur = duration_of(row)
    timeline_row_sum += dur

    path = str(
        row.get("asset_path")
        or row.get("path")
        or ""
    ).strip()

    asset_id = str(
        row.get("asset_id")
        or ""
    ).strip()

    assigned = bool(path or asset_id)

    if assigned:
        assigned_rows += 1
        assigned_row_sum += dur
    else:
        unassigned_rows += 1
        unassigned_row_sum += dur


timeline_start = min(timeline_starts) if timeline_starts else 0
timeline_end = max(timeline_ends) if timeline_ends else 0
timeline_span = max(0.0, timeline_end - timeline_start)

gap_sum = sum(
    x["duration_sec"]
    for x in corrected
)

accounted_by_asset_plus_gaps = (
    assigned_row_sum + gap_sum
)

accounting_delta = (
    timeline_span
    - accounted_by_asset_plus_gaps
)

row_sum_vs_span_delta = (
    timeline_row_sum - timeline_span
)


# =============================================================================
# SUMMARIES
# =============================================================================

by_target_count = Counter()
by_target_sec = Counter()

by_action_count = Counter()
by_action_sec = Counter()

by_priority_count = Counter()
by_priority_sec = Counter()

old_to_new = Counter()

contradictions = []

for row in corrected:

    dur = row["duration_sec"]

    by_target_count[row["new_target"]] += 1
    by_target_sec[row["new_target"]] += dur

    by_action_count[row["next_action"]] += 1
    by_action_sec[row["next_action"]] += dur

    by_priority_count[row["priority"]] += 1
    by_priority_sec[row["priority"]] += dur

    old_to_new[
        (row["old_target"], row["new_target"])
    ] += 1

    if row["old_target_contradiction"]:
        contradictions.append(row)


changed_count = sum(
    1
    for row in corrected
    if row["target_changed"]
)

contradiction_count = len(contradictions)

review_required = sum(
    1
    for row in corrected
    if row["new_target"] == "EDITORIAL_REVIEW_REQUIRED"
)


report = {

    "schema": "atlas_zero.film10.shot_semantic_correction.v4",

    "generated_at": datetime.now().isoformat(),

    "project_id": PROJECT_ID,

    "policy": {
        "precedence": [
            "shot_narration",
            "visual_need",
            "inherited_target_as_weak_context_only",
        ],
        "rule": (
            "Concrete visual_need and shot narration override "
            "large-block inherited gap category."
        ),
        "clip_used": False,
        "api_used": False,
        "db_writes": False,
        "assignment_performed": False,
        "render_performed": False,
    },

    "source": {
        "timeline": str(TIMELINE),
        "gaps": str(GAPS),
        "visual_need_records": len(
            visual_need_by_idx
        ),
        "read_only_db": (
            str(db_used)
            if db_used
            else None
        ),
    },

    "accounting": {
        "timeline_rows": len(timeline),
        "gap_records": len(gaps),
        "timeline_start_sec": timeline_start,
        "timeline_end_sec": timeline_end,
        "timeline_span_sec": timeline_span,
        "timeline_row_duration_sum_sec": timeline_row_sum,
        "timeline_row_sum_minus_span_sec": row_sum_vs_span_delta,
        "assigned_rows_by_asset_path_or_id": assigned_rows,
        "unassigned_rows_by_asset_path_or_id": unassigned_rows,
        "assigned_row_duration_sec": assigned_row_sum,
        "unassigned_row_duration_sec": unassigned_row_sum,
        "gap_record_duration_sec": gap_sum,
        "assigned_plus_gap_sec": accounted_by_asset_plus_gaps,
        "timeline_span_minus_assigned_plus_gap_sec": accounting_delta,
    },

    "summary": {
        "corrected_gaps": len(corrected),
        "changed_target_records": changed_count,
        "old_target_contradictions": contradiction_count,
        "editorial_review_required": review_required,
        "by_target": {
            key: {
                "count": by_target_count[key],
                "duration_sec": round(
                    by_target_sec[key],
                    3
                ),
            }
            for key in sorted(by_target_count)
        },
        "by_action": {
            key: {
                "count": by_action_count[key],
                "duration_sec": round(
                    by_action_sec[key],
                    3
                ),
            }
            for key in sorted(by_action_count)
        },
        "by_priority": {
            key: {
                "count": by_priority_count[key],
                "duration_sec": round(
                    by_priority_sec[key],
                    3
                ),
            }
            for key in sorted(by_priority_count)
        },
    },

    "old_to_new": [
        {
            "old_target": old,
            "new_target": new,
            "count": count,
        }
        for (old, new), count
        in sorted(
            old_to_new.items(),
            key=lambda x: (
                x[0][0],
                x[0][1]
            )
        )
    ],

    "gaps": corrected,
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
# TXT REPORT
# =============================================================================

lines = []

lines.append(
    "ATLAS ZERO - FILM10 SHOT SEMANTIC CORRECTION V4"
)

lines.append("=" * 100)
lines.append("")

lines.append(
    "RULE: visual_need + shot narration override inherited block target."
)

lines.append("")

lines.append(
    f"TIMELINE ROWS              : {len(timeline)}"
)

lines.append(
    f"GAP RECORDS                : {len(gaps)}"
)

lines.append(
    f"CORRECTED GAPS             : {len(corrected)}"
)

lines.append(
    f"OLD TARGET CONTRADICTIONS  : {contradiction_count}"
)

lines.append(
    f"EDITORIAL REVIEW REQUIRED  : {review_required}"
)

lines.append("")

lines.append("DURATION ACCOUNTING")
lines.append("-" * 100)

lines.append(
    f"Timeline span              : {timeline_span:.3f} sec"
)

lines.append(
    f"Timeline row sum           : {timeline_row_sum:.3f} sec"
)

lines.append(
    f"Assigned row duration      : {assigned_row_sum:.3f} sec"
)

lines.append(
    f"Unassigned row duration    : {unassigned_row_sum:.3f} sec"
)

lines.append(
    f"Gap record duration        : {gap_sum:.3f} sec"
)

lines.append(
    f"Assigned + gap             : {accounted_by_asset_plus_gaps:.3f} sec"
)

lines.append(
    f"Span - (assigned + gap)    : {accounting_delta:+.3f} sec"
)

lines.append("")

lines.append("NEW TARGETS")
lines.append("-" * 100)

for key in sorted(
    by_target_count,
    key=lambda k: -by_target_sec[k]
):
    lines.append(
        f"{key:34s} "
        f"{by_target_count[key]:3d} gaps | "
        f"{by_target_sec[key]:8.3f} sec"
    )

lines.append("")
lines.append("NEXT ACTIONS")
lines.append("-" * 100)

for key in sorted(
    by_action_count,
    key=lambda k: -by_action_sec[k]
):
    lines.append(
        f"{key:24s} "
        f"{by_action_count[key]:3d} gaps | "
        f"{by_action_sec[key]:8.3f} sec"
    )

lines.append("")
lines.append("OLD -> NEW TARGET")
lines.append("-" * 100)

for item in report["old_to_new"]:
    lines.append(
        f"{item['old_target']:22s} -> "
        f"{item['new_target']:34s} "
        f"{item['count']:3d}"
    )

lines.append("")
lines.append("SHOT CARDS")
lines.append("=" * 100)

for row in corrected:

    lines.append("")
    lines.append(
        f"SHOT {row['shot_idx']} | "
        f"{row['start_sec']:.3f}-{row['end_sec']:.3f} | "
        f"{row['duration_sec']:.3f}s"
    )

    lines.append(
        f"OLD     : {row['old_target']}"
    )

    lines.append(
        f"NEW     : {row['new_target']}"
    )

    lines.append(
        f"ACTION  : {row['next_action']}"
    )

    lines.append(
        f"PRIORITY: {row['priority']}"
    )

    lines.append(
        "CONFLICT: "
        + (
            "YES"
            if row["old_target_contradiction"]
            else "NO"
        )
    )

    lines.append(
        f"VISUAL NEED: {row['visual_need']}"
    )

    lines.append(
        f"NARRATION: {row['narration']}"
    )

    lines.append(
        f"WHY: {row['reason']}"
    )


TXT_OUT.write_text(
    "\n".join(lines),
    encoding="utf-8"
)


# =============================================================================
# HTML
# =============================================================================

def esc(x):
    return html.escape(
        str(x or "")
    )


html_parts = []

html_parts.append("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Film10 Shot Semantic Correction V4</title>
<style>
body {
    font-family: Arial, sans-serif;
    margin: 30px;
    line-height: 1.4;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 25px;
}
th, td {
    border: 1px solid #bbb;
    padding: 6px 8px;
    vertical-align: top;
}
th {
    background: #eee;
}
.card {
    border: 1px solid #aaa;
    padding: 12px;
    margin: 15px 0;
    page-break-inside: avoid;
}
code {
    white-space: pre-wrap;
}
</style>
</head>
<body>
""")

html_parts.append(
    "<h1>ATLAS ZERO — Film10 Shot Semantic Correction V4</h1>"
)

html_parts.append(
    "<p><b>Rule:</b> concrete shot narration + visual_need "
    "override inherited block category.</p>"
)

html_parts.append("<h2>Accounting</h2>")
html_parts.append("<table>")

for k, v in report["accounting"].items():
    html_parts.append(
        f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>"
    )

html_parts.append("</table>")

html_parts.append("<h2>Action summary</h2>")
html_parts.append(
    "<table><tr><th>Action</th><th>Gaps</th><th>Seconds</th></tr>"
)

for action in sorted(by_action_count):
    html_parts.append(
        "<tr>"
        f"<td>{esc(action)}</td>"
        f"<td>{by_action_count[action]}</td>"
        f"<td>{by_action_sec[action]:.3f}</td>"
        "</tr>"
    )

html_parts.append("</table>")

html_parts.append("<h2>Target summary</h2>")
html_parts.append(
    "<table><tr><th>Target</th><th>Gaps</th><th>Seconds</th></tr>"
)

for target in sorted(
    by_target_count,
    key=lambda k: -by_target_sec[k]
):
    html_parts.append(
        "<tr>"
        f"<td>{esc(target)}</td>"
        f"<td>{by_target_count[target]}</td>"
        f"<td>{by_target_sec[target]:.3f}</td>"
        "</tr>"
    )

html_parts.append("</table>")

html_parts.append("<h2>Gap cards</h2>")

for row in corrected:

    conflict = (
        "YES"
        if row["old_target_contradiction"]
        else "NO"
    )

    html_parts.append(
        f"""
        <div class="card">
        <h3>Shot {esc(row['shot_idx'])} —
        {row['duration_sec']:.3f}s</h3>

        <p>
        <b>Old:</b> {esc(row['old_target'])}<br>
        <b>New:</b> {esc(row['new_target'])}<br>
        <b>Action:</b> {esc(row['next_action'])}<br>
        <b>Priority:</b> {esc(row['priority'])}<br>
        <b>Old target contradiction:</b> {conflict}
        </p>

        <p>
        <b>Visual need:</b><br>
        {esc(row['visual_need'])}
        </p>

        <p>
        <b>Narration:</b><br>
        {esc(row['narration'])}
        </p>

        <p>
        <b>Why:</b><br>
        {esc(row['reason'])}
        </p>
        </div>
        """
    )

html_parts.append("</body></html>")

HTML_OUT.write_text(
    "\n".join(html_parts),
    encoding="utf-8"
)


# =============================================================================
# PDF
# =============================================================================

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
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
        "ReportLab is required for the mandatory PDF report. "
        f"Import failed: {exc}"
    )


font_candidates = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
]

font_path = next(
    (
        p
        for p in font_candidates
        if p.exists()
    ),
    None
)

if font_path is None:
    raise RuntimeError(
        "No Unicode Windows font found for Russian PDF."
    )

pdfmetrics.registerFont(
    TTFont(
        "AZUnicode",
        str(font_path)
    )
)

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "AZTitle",
    parent=styles["Title"],
    fontName="AZUnicode",
    fontSize=17,
    leading=21,
    spaceAfter=10,
)

h_style = ParagraphStyle(
    "AZHeading",
    parent=styles["Heading2"],
    fontName="AZUnicode",
    fontSize=12,
    leading=15,
    spaceBefore=8,
    spaceAfter=6,
)

body_style = ParagraphStyle(
    "AZBody",
    parent=styles["BodyText"],
    fontName="AZUnicode",
    fontSize=8.7,
    leading=11,
)

small_style = ParagraphStyle(
    "AZSmall",
    parent=body_style,
    fontSize=7.6,
    leading=9.4,
)

doc = SimpleDocTemplate(
    str(PDF_OUT),
    pagesize=A4,
    leftMargin=15 * mm,
    rightMargin=15 * mm,
    topMargin=15 * mm,
    bottomMargin=15 * mm,
)

story = []

story.append(
    Paragraph(
        "ATLAS ZERO — Film10 Shot Semantic Correction V4",
        title_style
    )
)

story.append(
    Paragraph(
        "Canonical editorial rule: concrete shot narration and visual_need "
        "override a category inherited from a larger narrative block.",
        body_style
    )
)

story.append(Spacer(1, 6))

story.append(
    Paragraph(
        "Duration Accounting",
        h_style
    )
)

account_table = [
    [
        Paragraph("Metric", small_style),
        Paragraph("Value", small_style),
    ]
]

for k, v in report["accounting"].items():
    account_table.append([
        Paragraph(esc(k), small_style),
        Paragraph(esc(v), small_style),
    ])

tbl = Table(
    account_table,
    colWidths=[95 * mm, 75 * mm],
    repeatRows=1,
)

tbl.setStyle(
    TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), "AZUnicode"),
    ])
)

story.append(tbl)

story.append(
    Paragraph(
        "Next Action Summary",
        h_style
    )
)

action_table = [[
    Paragraph("Action", small_style),
    Paragraph("Gaps", small_style),
    Paragraph("Seconds", small_style),
]]

for action in sorted(
    by_action_count,
    key=lambda k: -by_action_sec[k]
):
    action_table.append([
        Paragraph(action, small_style),
        str(by_action_count[action]),
        f"{by_action_sec[action]:.3f}",
    ])

tbl = Table(
    action_table,
    colWidths=[
        100 * mm,
        25 * mm,
        35 * mm
    ],
    repeatRows=1,
)

tbl.setStyle(
    TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), "AZUnicode"),
    ])
)

story.append(tbl)

story.append(
    Paragraph(
        "New Semantic Targets",
        h_style
    )
)

target_table = [[
    Paragraph("Target", small_style),
    Paragraph("Gaps", small_style),
    Paragraph("Seconds", small_style),
]]

for target in sorted(
    by_target_count,
    key=lambda k: -by_target_sec[k]
):
    target_table.append([
        Paragraph(target, small_style),
        str(by_target_count[target]),
        f"{by_target_sec[target]:.3f}",
    ])

tbl = Table(
    target_table,
    colWidths=[
        100 * mm,
        25 * mm,
        35 * mm
    ],
    repeatRows=1,
)

tbl.setStyle(
    TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), "AZUnicode"),
    ])
)

story.append(tbl)

story.append(PageBreak())

story.append(
    Paragraph(
        "Shot-level Audit Cards",
        title_style
    )
)

for i, row in enumerate(corrected, 1):

    conflict = (
        "YES"
        if row["old_target_contradiction"]
        else "NO"
    )

    story.append(
        Paragraph(
            (
                f"Shot {row['shot_idx']} | "
                f"{row['start_sec']:.3f}–{row['end_sec']:.3f} | "
                f"{row['duration_sec']:.3f} sec"
            ),
            h_style
        )
    )

    meta = [
        ["OLD", row["old_target"]],
        ["NEW", row["new_target"]],
        ["ACTION", row["next_action"]],
        ["PRIORITY", row["priority"]],
        ["CONTRADICTION", conflict],
        ["VISUAL NEED", row["visual_need"]],
    ]

    meta_table = []

    for a, b in meta:
        meta_table.append([
            Paragraph(
                f"<b>{esc(a)}</b>",
                small_style
            ),
            Paragraph(
                esc(b),
                small_style
            )
        ])

    tbl = Table(
        meta_table,
        colWidths=[36 * mm, 134 * mm]
    )

    tbl.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, -1), "AZUnicode"),
        ])
    )

    story.append(tbl)
    story.append(Spacer(1, 3))

    story.append(
        Paragraph(
            "<b>Narration:</b> "
            + esc(row["narration"]),
            body_style
        )
    )

    story.append(Spacer(1, 3))

    story.append(
        Paragraph(
            "<b>Why:</b> "
            + esc(row["reason"]),
            body_style
        )
    )

    story.append(Spacer(1, 7))


doc.build(story)


# =============================================================================
# OUTPUT VALIDATION
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

if PDF_OUT.stat().st_size < 10_000:
    raise RuntimeError(
        f"PDF suspiciously small: {PDF_OUT.stat().st_size} bytes"
    )


# =============================================================================
# CONSOLE SUMMARY
# =============================================================================

print()
print("=" * 120)
print("SEMANTIC CORRECTION SUMMARY")
print("=" * 120)

print(
    "CORRECTED GAPS             :",
    len(corrected)
)

print(
    "CHANGED TARGET RECORDS     :",
    changed_count
)

print(
    "OLD TARGET CONTRADICTIONS  :",
    contradiction_count
)

print(
    "EDITORIAL REVIEW REQUIRED  :",
    review_required
)

print()
print("NEW TARGETS:")

for target in sorted(
    by_target_count,
    key=lambda k: -by_target_sec[k]
):
    print(
        f"  {target:34s} "
        f"{by_target_count[target]:3d} | "
        f"{by_target_sec[target]:8.3f} sec"
    )

print()
print("NEXT ACTIONS:")

for action in sorted(
    by_action_count,
    key=lambda k: -by_action_sec[k]
):
    print(
        f"  {action:24s} "
        f"{by_action_count[action]:3d} | "
        f"{by_action_sec[action]:8.3f} sec"
    )

print()
print("=" * 120)
print("DURATION ACCOUNTING")
print("=" * 120)

print(
    f"TIMELINE SPAN              : {timeline_span:.3f}"
)

print(
    f"TIMELINE ROW SUM           : {timeline_row_sum:.3f}"
)

print(
    f"ASSIGNED ROW SEC           : {assigned_row_sum:.3f}"
)

print(
    f"UNASSIGNED ROW SEC         : {unassigned_row_sum:.3f}"
)

print(
    f"GAP RECORD SEC             : {gap_sum:.3f}"
)

print(
    f"ASSIGNED + GAP SEC         : {accounted_by_asset_plus_gaps:.3f}"
)

print(
    f"ACCOUNTING DELTA           : {accounting_delta:+.3f}"
)

print()
print("=" * 120)
print("OUTPUTS")
print("=" * 120)

for p in outputs:
    print(
        p.relative_to(ROOT),
        "|",
        p.stat().st_size,
        "bytes"
    )

print()
print("=" * 120)
print("FILM10 SHOT SEMANTIC CORRECTION V4: PASS")
print("=" * 120)

print(
    "NEXT: immediately close REUSE_EXISTING + STATIC_EXISTING, "
    "then generate/search only the true remaining gaps."
)
print("=" * 120)

