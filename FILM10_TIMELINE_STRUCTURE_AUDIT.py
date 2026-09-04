from pathlib import Path
import json

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID

TIMELINE = (
    PROJECT
    / "00_Production"
    / "rough_cut_v2"
    / "FILM10_ROUGH_CUT_TIMELINE_V2.json"
)

GAPS = (
    PROJECT
    / "00_Production"
    / "rough_cut_v2"
    / "FILM10_VISUAL_GAPS_V2.json"
)


def load(path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def extract(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in (
            "shots",
            "timeline",
            "segments",
            "items",
            "records",
            "gaps",
        ):
            value = payload.get(key)

            if isinstance(value, list):
                return value

        for key in ("result", "data"):
            value = payload.get(key)

            if isinstance(value, dict):
                result = extract(value)

                if result:
                    return result

    return []


timeline_payload = load(TIMELINE)
gap_payload = load(GAPS)

timeline = extract(timeline_payload)
gaps = extract(gap_payload)

print("=" * 120)
print("ATLAS ZERO — FILM10 V2 TIMELINE STRUCTURE AUDIT")
print("=" * 120)

print("TIMELINE :", TIMELINE)
print("GAPS     :", GAPS)
print("LIVE API : 0")
print("PAID API : 0")

print()
print("TIMELINE PAYLOAD TYPE :", type(timeline_payload).__name__)

if isinstance(timeline_payload, dict):
    print(
        "TIMELINE TOP KEYS    :",
        sorted(timeline_payload.keys())
    )

print("TIMELINE RECORDS      :", len(timeline))

print()
print("=" * 120)
print("FIRST 3 TIMELINE RECORDS — EXACT")
print("=" * 120)

for i, row in enumerate(timeline[:3], 1):
    print()
    print("RECORD", i)
    print("KEYS:", sorted(row.keys()) if isinstance(row, dict) else "NOT_DICT")
    print(
        json.dumps(
            row,
            ensure_ascii=False,
            indent=2
        )
    )


print()
print("=" * 120)
print("MIDDLE TIMELINE RECORD — EXACT")
print("=" * 120)

if timeline:
    i = len(timeline) // 2

    print("RECORD INDEX:", i + 1)
    print(
        json.dumps(
            timeline[i],
            ensure_ascii=False,
            indent=2
        )
    )


print()
print("=" * 120)
print("LAST 3 TIMELINE RECORDS — EXACT")
print("=" * 120)

for i, row in enumerate(timeline[-3:], len(timeline) - 2):
    print()
    print("RECORD", i)
    print(
        json.dumps(
            row,
            ensure_ascii=False,
            indent=2
        )
    )


print()
print("=" * 120)
print("FIELD INVENTORY")
print("=" * 120)

all_keys = set()

for row in timeline:
    if isinstance(row, dict):
        all_keys.update(row.keys())

for key in sorted(all_keys):
    nonempty = 0
    samples = []

    for row in timeline:
        if not isinstance(row, dict):
            continue

        value = row.get(key)

        if value not in (None, "", [], {}):
            nonempty += 1

            text = repr(value)

            if len(text) > 180:
                text = text[:177] + "..."

            if text not in samples and len(samples) < 3:
                samples.append(text)

    print()
    print("FIELD :", key)
    print("COUNT :", nonempty)
    print("SAMPLE:")

    for sample in samples:
        print("  ", sample)


print()
print("=" * 120)
print("GAP STRUCTURE")
print("=" * 120)

print("GAP PAYLOAD TYPE :", type(gap_payload).__name__)

if isinstance(gap_payload, dict):
    print(
        "GAP TOP KEYS    :",
        sorted(gap_payload.keys())
    )

print("GAP RECORDS      :", len(gaps))

for i, row in enumerate(gaps[:3], 1):
    print()
    print("GAP", i)
    print("KEYS:", sorted(row.keys()) if isinstance(row, dict) else "NOT_DICT")
    print(
        json.dumps(
            row,
            ensure_ascii=False,
            indent=2
        )
    )


print()
print("=" * 120)
print("AUDIT COMPLETE — READ ONLY")
print("=" * 120)
