from pathlib import Path
import json
import sys
import inspect
import re

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

OUT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "semantic_analysis_v2"
)

CHECKPOINT = OUT / "visual_semantic_checkpoint_v2.json"

print("=" * 120)
print("ATLAS ZERO — FILM10 RELEVANCE ROOT-CAUSE AUDIT V3")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("MODE       : READ ONLY")
print("CLIP RUN   : NO")
print("DB WRITES  : NO")
print("RENDER     : NO")

if not CHECKPOINT.is_file():
    raise FileNotFoundError(CHECKPOINT)

checkpoint = json.loads(
    CHECKPOINT.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )
)

results = checkpoint.get("results", [])

print()
print("CHECKPOINT RESULTS:", len(results))
print("FAILURES          :", len(checkpoint.get("failures", [])))

if len(results) != 23:
    print(
        "WARNING: expected current checkpoint around 23 records, "
        f"found {len(results)}"
    )

# =============================================================================
# CURRENT PROJECT CONTEXT
# =============================================================================

from az_enterprise.core.project_semantic_context_rc2 import (
    ProjectSemanticContextBuilderRC2,
)

context = ProjectSemanticContextBuilderRC2(
    project_id=PROJECT_ID,
    root_dir=ROOT,
).build()

print()
print("=" * 120)
print("CURRENT TOPIC LABELS")
print("=" * 120)

print("SOURCE:", context.source_path)

for label, prompts in context.topic_labels.items():
    print()
    print(label)

    for prompt in prompts:
        print("   -", prompt)

# =============================================================================
# ANALYZER SOURCE — EXACT RELEVANCE LOGIC
# =============================================================================

import az_enterprise.core.visual_semantic_analyzer_rc2 as vsa_module

Analyzer = vsa_module.VisualSemanticAnalyzerRC2

source = inspect.getsource(Analyzer)

print()
print("=" * 120)
print("RELEVANCE LOGIC FOUND IN VisualSemanticAnalyzerRC2")
print("=" * 120)

lines = source.splitlines()

interesting_terms = (
    "relevant",
    "off_topic",
    "OFF_TOPIC",
    "RELEVANT",
    "UNCERTAIN",
    "topic_scores",
    "unrelated_private_content",
)

printed = set()

for i, line in enumerate(lines):
    if any(term in line for term in interesting_terms):
        lo = max(0, i - 4)
        hi = min(len(lines), i + 8)

        key = (lo, hi)

        if key in printed:
            continue

        printed.add(key)

        print()
        print(f"--- SOURCE LINES {lo + 1}-{hi} ---")

        for j in range(lo, hi):
            print(f"{j + 1:04d}: {lines[j]}")

# =============================================================================
# RAW CHECKPOINT RECORD SCHEMA
# =============================================================================

print()
print("=" * 120)
print("RAW RESULT KEYS")
print("=" * 120)

if results:
    print(sorted(results[0].keys()))

# =============================================================================
# SELECTED RESULTS
# =============================================================================

targets = (
    "04449591_Le_Langtang_Lirung",
    "10cc48e5_Mudslide_at_Gyirong",
    "1bo7n5vi00mh1_A_Chinese_photographer",
    "46c3b098_Nepal_flood_before_2026-08-24",
    "4984b8c0_Gyirong_Port_before_and_after",
    "70800697_ISS061",
    "7275ac0d_Mudslide_at_Gyirong",
    "8336a096_Landsat",
    "DclmekDjUjK_Video_by_cgtn",
)

selected = []

for item in results:
    filename = str(item.get("filename") or "")

    if any(fragment.lower() in filename.lower() for fragment in targets):
        selected.append(item)

print()
print("=" * 120)
print("SELECTED ASSET RELEVANCE RECORDS")
print("=" * 120)

for item in selected:
    print()
    print("-" * 120)
    print("FILE       :", item.get("filename"))
    print("EVENT      :", item.get("event_type"))
    print("EVENT CONF :", item.get("event_confidence"))
    print("RELEVANCE  :", item.get("relevance_status"))
    print("REL SCORE  :", item.get("relevance_score"))
    print("OFF TOPIC  :", item.get("off_topic_score"))

    for key in (
        "topic_scores",
        "topic",
        "topic_class",
        "topic_confidence",
        "relevance",
        "semantic_evidence",
        "evidence",
        "description",
        "detected_objects",
        "detected_actions",
    ):
        if key in item:
            value = item.get(key)

            print()
            print(f"{key}:")

            if isinstance(value, (dict, list)):
                print(
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(value)

# =============================================================================
# DISTRIBUTION OF AVAILABLE NUMERIC RELEVANCE FIELDS
# =============================================================================

print()
print("=" * 120)
print("ALL 23 — RELEVANCE SCORE TABLE")
print("=" * 120)

for i, item in enumerate(results, 1):
    filename = str(item.get("filename") or "")

    rel = item.get("relevance_score")
    off = item.get("off_topic_score")

    try:
        rel_txt = f"{float(rel):.4f}"
    except Exception:
        rel_txt = str(rel)

    try:
        off_txt = f"{float(off):.4f}"
    except Exception:
        off_txt = str(off)

    print(
        f"{i:02d}. "
        f"{filename[:62]:<62} "
        f"| {str(item.get('event_type')):<16} "
        f"| {str(item.get('relevance_status')):<9} "
        f"| rel={rel_txt:<8} "
        f"| off={off_txt}"
    )

# =============================================================================
# CHECK WHETHER CURRENT TOPIC PROMPTS ARE PROJECT-SPECIFIC ENOUGH
# =============================================================================

topic_text = " ".join(
    prompt
    for prompts in context.topic_labels.values()
    for prompt in prompts
).lower()

strategic_terms = {
    "langtang": "лангтанг",
    "gyirong": "гьиронг",
    "trishuli": "тришули",
    "nepal": "непал",
    "usgs": "usgs",
    "glacier": "ледник",
    "slope": "склон",
    "flood": "навод",
    "satellite": "спут",
    "school": "школ",
    "hydropower": "гидро",
}

print()
print("=" * 120)
print("TOPIC PROMPT STRATEGIC COVERAGE")
print("=" * 120)

coverage = {}

for name, term in strategic_terms.items():
    hit = term in topic_text
    coverage[name] = hit

    print(
        f"{name:<16}: "
        + ("YES" if hit else "NO")
    )

# =============================================================================
# ROOT-CAUSE FLAGS
# =============================================================================

known_relevant_fragments = (
    "Langtang_Lirung",
    "Mudslide_at_Gyirong",
    "Sentinel2",
    "ISS061",
    "Landsat",
    "Gyirong_Port_before_and_after",
)

known_relevant = [
    item
    for item in results
    if any(
        frag.lower()
        in str(item.get("filename") or "").lower()
        for frag in known_relevant_fragments
    )
]

false_off_topic = [
    item
    for item in known_relevant
    if str(item.get("relevance_status")) == "OFF_TOPIC"
]

print()
print("=" * 120)
print("ROOT-CAUSE SUMMARY")
print("=" * 120)

print("KNOWN RELEVANT CONTROL ASSETS :", len(known_relevant))
print("FALSE OFF_TOPIC               :", len(false_off_topic))

for item in false_off_topic:
    print(
        "  -",
        item.get("filename"),
        "| event=",
        item.get("event_type"),
        "| rel=",
        item.get("relevance_score"),
        "| off=",
        item.get("off_topic_score"),
    )

print()
print("STRATEGIC TOPIC COVERAGE:")
print(
    sum(1 for value in coverage.values() if value),
    "/",
    len(coverage),
)

print()
print("=" * 120)
print("AUDIT COMPLETE")
print("=" * 120)

print("No CLIP inference performed.")
print("No asset analysis performed.")
print("No DB writes performed.")
print("No assignments written.")
print("No render performed.")
print("No API calls made.")
