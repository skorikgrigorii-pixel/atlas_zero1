from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import json
import re

ROOT = Path.cwd()
PROJECT_ID = "film_10_nepal_tibet_aftershock"
PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID

V2 = PROJECT / "00_Production" / "human_editorial_assignment_v2" / "FILM10_HUMAN_EDITORIAL_TIMELINE_V2.json"
V4 = PROJECT / "00_Production" / "shot_semantic_correction_v4" / "FILM10_SHOT_SEMANTIC_CORRECTION_V4.json"
GT = PROJECT / "00_Production" / "human_editorial_ground_truth_v1" / "FILM10_HUMAN_EDITORIAL_GROUND_TRUTH_NORMALIZED_V1.json"

OUT = PROJECT / "00_Production" / "human_editorial_assignment_v3"
OUT.mkdir(parents=True, exist_ok=True)

TIMELINE_OUT = OUT / "FILM10_HUMAN_EDITORIAL_TIMELINE_V3.json"
GAPS_OUT = OUT / "FILM10_HUMAN_EDITORIAL_GAPS_V3.json"
REPORT_OUT = OUT / "FILM10_HUMAN_EDITORIAL_ASSIGNMENT_REPORT_V3.json"

print("=" * 120)
print("ATLAS ZERO - FILM10 HUMAN EDITORIAL ASSIGNMENT V3")
print("=" * 120)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("RENDER     : NO")
print("CLIP       : NO")
print()


def load(path):
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


v2_raw = load(V2)
v4_raw = load(V4)
gt_raw = load(GT)

timeline = v2_raw["timeline"]
corrections = v4_raw["gaps"]

# GT contract can have different wrapper names.
if isinstance(gt_raw, list):
    gt_rows = gt_raw
else:
    gt_rows = None
    for key in ("fragments", "records", "ground_truth", "items"):
        value = gt_raw.get(key)
        if isinstance(value, list):
            gt_rows = value
            break

    if gt_rows is None:
        # deterministic discovery
        candidates = [
            value for value in gt_raw.values()
            if isinstance(value, list)
            and value
            and isinstance(value[0], dict)
        ]
        if not candidates:
            raise RuntimeError("Ground-truth fragment list not found")
        gt_rows = max(candidates, key=len)


print("TIMELINE ROWS :", len(timeline))
print("V4 GAPS       :", len(corrections))
print("GT ROWS       :", len(gt_rows))

if len(timeline) != 260:
    raise RuntimeError(f"Expected 260 timeline rows, got {len(timeline)}")

if len(corrections) != 81:
    raise RuntimeError(f"Expected 81 corrected gaps, got {len(corrections)}")


def number(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def shot_idx(row):
    for key in ("shot_index", "shot_idx", "idx"):
        if row.get(key) is not None:
            try:
                return int(row[key])
            except Exception:
                pass

    m = re.findall(r"\d+", str(row.get("shot_id", "")))
    return int(m[-1]) if m else None


def duration(row):
    if row.get("duration_sec") is not None:
        return number(row["duration_sec"])

    return max(
        0.0,
        number(row.get("timeline_end"))
        - number(row.get("timeline_start")),
    )


corr = {
    shot_idx(row): row
    for row in corrections
    if shot_idx(row) is not None
}


# ----------------------------------------------------------------------
# Human-approved fragment normalization
# ----------------------------------------------------------------------

def first(row, *keys):
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


eligible_status = {
    "KEEP_STRONG",
    "KEEP_CONTEXT",
    "SPECIAL_USE",
}

fragments = []

for row in gt_rows:

    status = str(
        first(
            row,
            "human_status",
            "status",
            "editorial_status",
            "decision",
        ) or ""
    ).upper()

    if status not in eligible_status:
        continue

    category = str(
        first(
            row,
            "semantic_category",
            "category",
            "editorial_category",
            "target_category",
        ) or ""
    ).upper()

    path_raw = first(
        row,
        "asset_path",
        "source_path",
        "file_path",
        "path",
        "source_file",
    )

    if not path_raw:
        continue

    p = Path(str(path_raw))

    if not p.is_absolute():
        p = ROOT / p

    if not p.exists():
        continue

    start = number(
        first(
            row,
            "source_start",
            "source_in_sec",
            "start_sec",
            "fragment_start_sec",
            "start",
        )
    )

    end_raw = first(
        row,
        "source_end",
        "source_out_sec",
        "end_sec",
        "fragment_end_sec",
        "end",
    )

    if end_raw is None:
        end = start + number(
            first(row, "duration_sec", "duration")
        )
    else:
        end = number(end_raw)

    if end <= start:
        continue

    fragments.append({
        "fragment_id": str(
            first(row, "fragment_id", "id", "fragment") or ""
        ),
        "status": status,
        "category": category,
        "path": str(p),
        "start": start,
        "end": end,
        "duration": end - start,
    })


print("USABLE GT FRAGMENTS:", len(fragments))


# ----------------------------------------------------------------------
# Existing V2 ranges
# ----------------------------------------------------------------------

used_ranges = defaultdict(list)
used_fragments = set()

for row in timeline:

    path = str(row.get("asset_path") or "")

    if not path:
        continue

    if str(row.get("asset_type") or "").lower() == "video":

        a = number(
            row.get(
                "source_start",
                row.get("source_in_sec", 0)
            )
        )

        b = number(
            row.get(
                "source_end",
                row.get("source_out_sec", a)
            )
        )

        if b > a:
            used_ranges[path].append((a, b))

    fid = str(row.get("fragment_id") or "")
    if fid:
        used_fragments.add(fid)


def overlaps(path, a, b):

    for x, y in used_ranges.get(path, []):
        if max(a, x) < min(b, y) - 0.001:
            return True

    return False


# ----------------------------------------------------------------------
# Strict semantic reuse pools.
# No generic/random fallback.
# ----------------------------------------------------------------------

VIDEO_POOLS = {
    "TUNNEL_WORKER_RESCUE": {
        "RESCUE_TUNNEL_SEARCH",
        "RESCUE_DRILLING",
        "RESCUE_RESPONSE",
    },
    "GLACIER_COLLAPSE_REAL": {
        "GLACIER_COLLAPSE",
    },
    "FLOOD_AFTERMATH": {
        "FLOOD_AFTERMATH",
        "RASUWA_AFTER_FLOOD",
        "FLOOD_DEBRIS",
    },
    "LANGTANG_2015_ARCHIVE_CONTEXT": {
        "LANGTANG_GLACIER_MOUNTAIN",
        "GLACIER_COLLAPSE_CONTEXT",
        "HIMALAYA_GEOGRAPHY",
    },
}


# ----------------------------------------------------------------------
# Static visuals already in Film10
# ----------------------------------------------------------------------

static_files = []

for base in (
    PROJECT / "02_Visuals",
    PROJECT / "00_Research",
):

    if not base.exists():
        continue

    static_files.extend(
        p for p in base.rglob("*")
        if p.is_file()
        and p.suffix.lower() in {
            ".jpg", ".jpeg", ".png", ".webp"
        }
    )


def static_kind(p):

    s = p.name.lower()

    if any(x in s for x in (
        "usgs",
        "seismic",
        "earthquake",
        "magnitude",
    )):
        return "USGS"

    if any(x in s for x in (
        "landsat",
        "sentinel",
        "satellite",
        "iss0",
        "iss061",
        "before_and_after",
        "before_2026",
    )):
        return "MAP"

    if any(x in s for x in (
        "bhote_koshi",
        "valley",
        "phurte",
        "trail",
    )):
        return "RIVER"

    if any(x in s for x in (
        "langtang",
        "glacier",
        "himalaya",
        "lirung",
    )):
        return "MOUNTAIN"

    return "OTHER"


static_pool = defaultdict(list)

for p in static_files:
    static_pool[static_kind(p)].append(p)

for key in static_pool:
    static_pool[key].sort(key=lambda p: p.name.lower())


STATIC_POOLS = {
    "LANGTANG_MOUNTAIN_CONTEXT": (
        "MOUNTAIN",
    ),
    "RIVER_SYSTEM_MAP": (
        "MAP",
        "RIVER",
    ),
    # Important: generic satellite != seismic evidence.
    "USGS_SEISMIC_SCIENCE": (
        "USGS",
    ),
}


print("STATIC:")
for key in sorted(static_pool):
    print(f"  {key:10s}: {len(static_pool[key])}")


# ----------------------------------------------------------------------
# Selection
# ----------------------------------------------------------------------

static_usage = Counter()


def choose_static(target):

    candidates = []

    for kind in STATIC_POOLS.get(target, ()):

        for p in static_pool.get(kind, []):

            candidates.append(
                (
                    static_usage[str(p)],
                    p.name.lower(),
                    p,
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (x[0], x[1])
    )

    return candidates[0][2]


def choose_video(target, need, previous_path):

    allowed = VIDEO_POOLS.get(target, set())
    candidates = []

    for f in fragments:

        if f["category"] not in allowed:
            continue

        if f["fragment_id"] in used_fragments:
            continue

        if f["duration"] < need - 0.02:
            continue

        if overlaps(
            f["path"],
            f["start"],
            f["start"] + need,
        ):
            continue

        score = 0

        if f["status"] == "KEEP_STRONG":
            score += 100
        elif f["status"] == "KEEP_CONTEXT":
            score += 60
        else:
            score += 30

        if f["path"] == previous_path:
            score -= 200

        candidates.append((score, f))

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return candidates[0][1]


# ----------------------------------------------------------------------
# Build V3
# ----------------------------------------------------------------------

new_timeline = []

new_video = []
new_static = []
remaining = []

previous_path = None

for pos, original in enumerate(timeline, 1):

    row = dict(original)
    idx = shot_idx(row) or pos

    # Preserve every already assigned V2 shot.
    if row.get("asset_path"):
        new_timeline.append(row)
        previous_path = str(row["asset_path"])
        continue

    c = corr.get(idx)

    if not c:
        row["asset_path"] = None
        row["asset_id"] = None
        row["status"] = "VISUAL_GAP"
        new_timeline.append(row)

        remaining.append({
            "shot_id": row.get("shot_id"),
            "shot_index": idx,
            "timeline_start": row.get("timeline_start"),
            "timeline_end": row.get("timeline_end"),
            "duration_sec": duration(row),
            "narration": row.get("narration"),
            "visual_need": row.get("visual_need"),
            "new_target": "UNKNOWN",
            "next_action": "EDITORIAL_REVIEW",
            "priority": "HIGH",
            "reason": "No V4 correction record.",
        })

        previous_path = None
        continue

    target = str(c.get("new_target") or "")
    action = str(c.get("next_action") or "")
    need = duration(row)

    assigned = False

    if action == "REUSE_EXISTING":

        f = choose_video(
            target,
            need,
            previous_path,
        )

        if f:

            a = f["start"]
            b = a + need

            row.update({
                "fragment_id": f["fragment_id"],
                "human_status": f["status"],
                "semantic_category": f["category"],
                "asset_path": f["path"],
                "asset_type": "video",
                "source_start": a,
                "source_end": b,
                "source_in_sec": a,
                "source_out_sec": b,
                "status": "ASSIGNED",
                "selection_reason":
                    "HUMAN_EDITORIAL_V3_REUSE_EXISTING:"
                    + target,
            })

            used_ranges[f["path"]].append((a, b))

            if f["fragment_id"]:
                used_fragments.add(f["fragment_id"])

            new_video.append({
                "shot_index": idx,
                "duration_sec": need,
                "target": target,
                "fragment_id": f["fragment_id"],
                "asset_path": f["path"],
                "source_start": a,
                "source_end": b,
            })

            previous_path = f["path"]
            assigned = True

    elif action == "STATIC_EXISTING":

        p = choose_static(target)

        if p:

            row.update({
                "fragment_id": None,
                "human_status": "STATIC_EXISTING",
                "semantic_category": target,
                "asset_path": str(p),
                "asset_type": "image",
                "source_start": 0.0,
                "source_end": need,
                "source_in_sec": 0.0,
                "source_out_sec": need,
                "status": "ASSIGNED",
                "selection_reason":
                    "HUMAN_EDITORIAL_V3_STATIC_EXISTING:"
                    + target,
            })

            static_usage[str(p)] += 1

            new_static.append({
                "shot_index": idx,
                "duration_sec": need,
                "target": target,
                "asset_path": str(p),
            })

            previous_path = str(p)
            assigned = True

    if not assigned:

        row["asset_path"] = None
        row["asset_id"] = None
        row["status"] = "VISUAL_GAP"
        row["selection_reason"] = (
            "HUMAN_EDITORIAL_V3_UNRESOLVED:"
            + target
            + ":"
            + action
        )

        remaining.append({
            "shot_id": row.get("shot_id"),
            "shot_index": idx,
            "timeline_start": row.get("timeline_start"),
            "timeline_end": row.get("timeline_end"),
            "duration_sec": need,
            "narration": row.get("narration"),
            "visual_need": row.get("visual_need"),
            "new_target": target,
            "next_action": action,
            "priority": c.get("priority"),
            "reason": c.get("reason"),
        })

        previous_path = None

    new_timeline.append(row)


# ----------------------------------------------------------------------
# Validate no source range collision
# ----------------------------------------------------------------------

ranges = defaultdict(list)

for row in new_timeline:

    if (
        not row.get("asset_path")
        or str(row.get("asset_type") or "").lower() != "video"
    ):
        continue

    a = number(
        row.get(
            "source_start",
            row.get("source_in_sec", 0)
        )
    )

    b = number(
        row.get(
            "source_end",
            row.get("source_out_sec", a)
        )
    )

    if b > a:
        ranges[str(row["asset_path"])].append(
            (a, b, shot_idx(row))
        )


overlap_errors = []

for path, rr in ranges.items():

    rr.sort()

    for i in range(1, len(rr)):

        pa, pb, ps = rr[i - 1]
        a, b, s = rr[i]

        if a < pb - 0.001:
            overlap_errors.append({
                "asset_path": path,
                "shot_a": ps,
                "shot_b": s,
                "range_a": [pa, pb],
                "range_b": [a, b],
            })


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------

assigned_rows = [
    r for r in new_timeline
    if r.get("asset_path")
]

gap_rows = [
    r for r in new_timeline
    if not r.get("asset_path")
]

assigned_sec = sum(
    duration(r)
    for r in assigned_rows
)

gap_sec = sum(
    duration(r)
    for r in gap_rows
)

new_video_sec = sum(
    x["duration_sec"]
    for x in new_video
)

new_static_sec = sum(
    x["duration_sec"]
    for x in new_static
)

action_count = Counter()
action_sec = Counter()
target_count = Counter()
target_sec = Counter()

for g in remaining:

    action = str(g["next_action"])
    target = str(g["new_target"])
    sec = number(g["duration_sec"])

    action_count[action] += 1
    action_sec[action] += sec

    target_count[target] += 1
    target_sec[target] += sec


report = {
    "schema":
        "atlas_zero.film10.human_editorial_assignment.v3",

    "generated_at":
        datetime.now().isoformat(),

    "project_id":
        PROJECT_ID,

    "summary": {
        "timeline_rows": len(new_timeline),
        "assigned_rows": len(assigned_rows),
        "gap_rows": len(gap_rows),
        "assigned_duration_sec": round(assigned_sec, 3),
        "gap_duration_sec": round(gap_sec, 3),
        "new_video_fills": len(new_video),
        "new_video_fill_sec": round(new_video_sec, 3),
        "new_static_fills": len(new_static),
        "new_static_fill_sec": round(new_static_sec, 3),
        "source_overlap_errors": len(overlap_errors),
    },

    "remaining_by_action": {
        key: {
            "count": action_count[key],
            "duration_sec": round(action_sec[key], 3),
        }
        for key in sorted(action_count)
    },

    "remaining_by_target": {
        key: {
            "count": target_count[key],
            "duration_sec": round(target_sec[key], 3),
        }
        for key in sorted(target_count)
    },

    "new_video_assignments": new_video,
    "new_static_assignments": new_static,
    "remaining_gaps": remaining,
    "overlap_errors": overlap_errors,
}


TIMELINE_OUT.write_text(
    json.dumps({
        "schema":
            "atlas_zero.film10.human_editorial_timeline.v3",
        "project_id": PROJECT_ID,
        "voice_duration_sec":
            number(v2_raw.get("voice_duration_sec"), 1607.517),
        "timeline": new_timeline,
    }, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

GAPS_OUT.write_text(
    json.dumps({
        "schema":
            "atlas_zero.film10.human_editorial_gaps.v3",
        "project_id": PROJECT_ID,
        "gap_count": len(remaining),
        "gap_duration_sec": round(gap_sec, 3),
        "gaps": remaining,
    }, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

REPORT_OUT.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


print()
print("=" * 120)
print("V3 ASSIGNMENT SUMMARY")
print("=" * 120)

for key, value in report["summary"].items():
    print(f"{key:30s}: {value}")

print()
print("REMAINING BY ACTION:")

for key in sorted(
    action_count,
    key=lambda k: -action_sec[k]
):
    print(
        f"  {key:24s} "
        f"{action_count[key]:3d} | "
        f"{action_sec[key]:8.3f} sec"
    )

print()
print("REMAINING BY TARGET:")

for key in sorted(
    target_count,
    key=lambda k: -target_sec[k]
):
    print(
        f"  {key:34s} "
        f"{target_count[key]:3d} | "
        f"{target_sec[key]:8.3f} sec"
    )

print()
print("OUTPUTS:")
for p in (
    TIMELINE_OUT,
    GAPS_OUT,
    REPORT_OUT,
):
    print(
        " ",
        p.relative_to(ROOT),
        "|",
        p.stat().st_size,
        "bytes"
    )

print()

if overlap_errors:
    print("FILM10 HUMAN EDITORIAL ASSIGNMENT V3: BLOCKED")
    print("SOURCE RANGE OVERLAPS:", len(overlap_errors))
    raise SystemExit(2)

print("FILM10 HUMAN EDITORIAL ASSIGNMENT V3: PASS")
print("NEXT: exact acquisition/generation list.")
print("=" * 120)
