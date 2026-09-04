from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = Path.cwd()

SCRIPT = ROOT / "FILM10_SHOT_SEMANTIC_CORRECTION_V4.py"

PROJECT = (
    ROOT / "workspace" / "projects"
    / "film_10_nepal_tibet_aftershock"
)

TIMELINE = (
    PROJECT / "00_Production"
    / "human_editorial_assignment_v2"
    / "FILM10_HUMAN_EDITORIAL_TIMELINE_V2.json"
)

GAPS = (
    PROJECT / "00_Production"
    / "human_editorial_assignment_v2"
    / "FILM10_HUMAN_EDITORIAL_GAPS_V2.json"
)

print("=" * 120)
print("ATLAS ZERO - FILM10 V4 JSON CONTRACT RECOVERY")
print("=" * 120)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("RENDER     : NO")
print()

for p in (SCRIPT, TIMELINE, GAPS):
    if not p.exists():
        raise FileNotFoundError(p)

# =============================================================================
# 1. Inspect ACTUAL JSON contracts
# =============================================================================

def describe(value, name, depth=0):
    pad = "  " * depth

    if isinstance(value, dict):
        print(f"{pad}{name}: dict | keys={list(value.keys())[:30]}")

        for key, child in list(value.items())[:20]:
            if isinstance(child, list):
                print(
                    f"{pad}  {key}: list | len={len(child)}"
                )
                if child:
                    first = child[0]
                    if isinstance(first, dict):
                        print(
                            f"{pad}    first keys="
                            f"{list(first.keys())[:30]}"
                        )

            elif isinstance(child, dict):
                print(
                    f"{pad}  {key}: dict | "
                    f"keys={list(child.keys())[:20]}"
                )

    elif isinstance(value, list):
        print(f"{pad}{name}: list | len={len(value)}")

        if value and isinstance(value[0], dict):
            print(
                f"{pad}  first keys="
                f"{list(value[0].keys())[:30]}"
            )

    else:
        print(f"{pad}{name}: {type(value).__name__}")


timeline_raw = json.loads(
    TIMELINE.read_text(encoding="utf-8")
)

gaps_raw = json.loads(
    GAPS.read_text(encoding="utf-8")
)

print("ACTUAL JSON CONTRACTS")
print("-" * 120)
describe(timeline_raw, "TIMELINE ROOT")
describe(gaps_raw, "GAPS ROOT")
print()

# =============================================================================
# 2. Find best record list automatically
# =============================================================================

def score_list(lst, kind):
    if not isinstance(lst, list) or not lst:
        return -1

    dict_rows = [
        x for x in lst
        if isinstance(x, dict)
    ]

    if not dict_rows:
        return -1

    sample = dict_rows[:min(10, len(dict_rows))]

    keys = set()

    for row in sample:
        keys.update(row.keys())

    score = len(dict_rows)

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

        if len(lst) >= 200:
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

        if 50 <= len(lst) <= 150:
            score += 1000

    return score


def discover_lists(obj, path="$"):
    found = []

    if isinstance(obj, list):
        found.append((path, obj))

        for i, item in enumerate(obj[:3]):
            if isinstance(item, (dict, list)):
                found.extend(
                    discover_lists(
                        item,
                        f"{path}[{i}]"
                    )
                )

    elif isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                found.extend(
                    discover_lists(
                        value,
                        f"{path}.{key}"
                    )
                )

    return found


def select_records(obj, kind):
    candidates = discover_lists(obj)

    ranked = sorted(
        (
            (score_list(lst, kind), path, lst)
            for path, lst in candidates
        ),
        key=lambda x: x[0],
        reverse=True,
    )

    ranked = [
        x for x in ranked
        if x[0] >= 0
    ]

    if not ranked:
        raise RuntimeError(
            f"No usable {kind} record list discovered"
        )

    score, path, records = ranked[0]

    return path, records, ranked[:10]


timeline_path, timeline_records, timeline_ranked = (
    select_records(timeline_raw, "timeline")
)

gaps_path, gap_records, gaps_ranked = (
    select_records(gaps_raw, "gaps")
)

print("=" * 120)
print("AUTO-DISCOVERED RECORD ARRAYS")
print("=" * 120)

print(
    "TIMELINE PATH :",
    timeline_path
)
print(
    "TIMELINE ROWS :",
    len(timeline_records)
)

print(
    "GAPS PATH     :",
    gaps_path
)
print(
    "GAP ROWS      :",
    len(gap_records)
)

print()

print("TOP TIMELINE CANDIDATES:")
for score, path, rows in timeline_ranked:
    print(
        f"  score={score:5d} | "
        f"rows={len(rows):4d} | {path}"
    )

print()

print("TOP GAP CANDIDATES:")
for score, path, rows in gaps_ranked:
    print(
        f"  score={score:5d} | "
        f"rows={len(rows):4d} | {path}"
    )

print()

# Hard production sanity gates.

if len(timeline_records) < 200:
    raise RuntimeError(
        f"Timeline discovery suspicious: "
        f"{len(timeline_records)} rows"
    )

if not (50 <= len(gap_records) <= 150):
    raise RuntimeError(
        f"Gap discovery suspicious: "
        f"{len(gap_records)} rows"
    )

# =============================================================================
# 3. Patch ONLY the loader contract in the existing complete V4 script
# =============================================================================

source = SCRIPT.read_text(
    encoding="utf-8"
)

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup = SCRIPT.with_name(
    SCRIPT.name
    + f".before_json_contract_fix_{stamp}.bak"
)

shutil.copy2(
    SCRIPT,
    backup
)

print(
    "BACKUP       :",
    backup.relative_to(ROOT)
)

old_block = '''timeline = json.loads(TIMELINE.read_text(encoding="utf-8"))
gaps = json.loads(GAPS.read_text(encoding="utf-8"))

if not isinstance(timeline, list):
    raise RuntimeError("Timeline V2 must be a JSON list")

if not isinstance(gaps, list):
    raise RuntimeError("Gaps V2 must be a JSON list")
'''

new_block = r'''timeline_raw = json.loads(
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
'''

if old_block not in source:
    raise RuntimeError(
        "Audited V4 loader block was not found. "
        "No blind source modification performed."
    )

source = source.replace(
    old_block,
    new_block,
    1
)

SCRIPT.write_text(
    source,
    encoding="utf-8",
    newline="\n"
)

print("LOADER PATCH : WRITTEN")

# =============================================================================
# 4. Syntax check
# =============================================================================

print()
print("=" * 120)
print("SYNTAX CHECK")
print("=" * 120)

compile_result = subprocess.run(
    [
        sys.executable,
        "-m",
        "py_compile",
        str(SCRIPT)
    ],
    cwd=str(ROOT),
    text=True,
    capture_output=True,
)

if compile_result.stdout:
    print(compile_result.stdout)

if compile_result.stderr:
    print(compile_result.stderr)

print(
    "PY_COMPILE :",
    "PASS"
    if compile_result.returncode == 0
    else "FAIL"
)

if compile_result.returncode != 0:
    raise SystemExit(
        compile_result.returncode
    )

# =============================================================================
# 5. Run complete V4 immediately
# =============================================================================

print()
print("=" * 120)
print("RUNNING COMPLETE FILM10 V4")
print("=" * 120)
print()

run = subprocess.run(
    [
        sys.executable,
        str(SCRIPT)
    ],
    cwd=str(ROOT),
    text=True,
)

print()
print("=" * 120)

if run.returncode == 0:
    print(
        "FILM10 V4 JSON CONTRACT RECOVERY: PASS"
    )
    print(
        "COMPLETE SEMANTIC CORRECTION V4 FINISHED."
    )
else:
    print(
        "FILM10 V4 JSON CONTRACT RECOVERY: "
        f"DOWNSTREAM FAILURE ({run.returncode})"
    )

print("=" * 120)

raise SystemExit(
    run.returncode
)

