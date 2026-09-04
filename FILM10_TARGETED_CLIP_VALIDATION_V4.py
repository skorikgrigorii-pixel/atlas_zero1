from __future__ import annotations

from pathlib import Path
import inspect
import json
import os
import sqlite3
import sys
import time
import traceback

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

DB_PATH = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"

OUT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "semantic_validation_v4"
)

OUT.mkdir(parents=True, exist_ok=True)

REPORT = OUT / "FILM10_TARGETED_CLIP_VALIDATION_V4.json"

print("=" * 120)
print("ATLAS ZERO — FILM10 TARGETED CLIP VALIDATION V4")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("MODE       : TARGETED / READ-ONLY")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

if not DB_PATH.is_file():
    raise FileNotFoundError(DB_PATH)

sys.path.insert(0, str(ROOT / "src"))

from az_enterprise.core.project_semantic_context_rc2 import (
    ProjectSemanticContextBuilderRC2,
)

import az_enterprise.core.visual_semantic_analyzer_rc2 as vsa_mod

VisualSemanticAnalyzerRC2 = vsa_mod.VisualSemanticAnalyzerRC2

# =============================================================================
# CONTEXT
# =============================================================================

context = ProjectSemanticContextBuilderRC2(
    project_id=PROJECT_ID,
    root_dir=ROOT,
).build()

event_labels = context.event_labels
topic_labels = context.topic_labels

print()
print("=" * 120)
print("SEMANTIC CONTEXT")
print("=" * 120)
print("SOURCE           :", context.source_path)
print("EVENT LABELS     :", len(event_labels))
print("SCENE LABELS     :", len([
    k for k in event_labels
    if str(k).startswith("scene_")
]))
print("RELEVANT PROMPTS :", len(topic_labels.get("relevant", ())))
print("OFFTOPIC PROMPTS :", len(topic_labels.get("off_topic", ())))

if context.source_path != "canonical_db:story_scenes":
    raise RuntimeError("Canonical semantic context not active.")

if len(topic_labels.get("relevant", ())) < 40:
    raise RuntimeError("V4 multi-prompt topic context not active.")

# =============================================================================
# CANONICAL ASSETS
# =============================================================================

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

try:
    assets = conn.execute(
        """
        SELECT
            id,
            path,
            filename,
            media_type,
            semantic_class,
            semantic_confidence
        FROM assets
        WHERE project_id=?
        ORDER BY filename
        """,
        (PROJECT_ID,),
    ).fetchall()
finally:
    conn.close()

assets = [dict(row) for row in assets]

print("CANONICAL ASSETS  :", len(assets))

if len(assets) != 60:
    raise RuntimeError(
        f"Expected 60 Film10 assets, found {len(assets)}"
    )

# =============================================================================
# CONTROL SELECTION
#
# Explicit filenames are TEST FIXTURES only.
# No Film10 vocabulary enters production code.
# =============================================================================

control_specs = [
    {
        "name": "LANGTANG_PHOTO",
        "contains": [
            "Le_Langtang_Lirung",
        ],
        "expected": "RELEVANT",
    },
    {
        "name": "GYIRONG_MUDSLIDE",
        "contains": [
            "Mudslide_at_Gyirong_Port_2",
        ],
        "expected": "RELEVANT",
    },
    {
        "name": "DRONE_COLLAPSE",
        "contains": [
            "Chinese_photographer_accidentally_captured",
        ],
        "expected": "RELEVANT",
    },
    {
        "name": "SENTINEL_BEFORE",
        "contains": [
            "Copernicus_Sentinel2",
        ],
        "expected": "RELEVANT",
    },
    {
        "name": "GYIRONG_SATELLITE",
        "contains": [
            "Gyirong_Port_before_and_after",
        ],
        "expected": "RELEVANT",
    },
    {
        "name": "ISS_LANGTANG",
        "contains": [
            "ISS061-E-148219",
        ],
        "expected": "RELEVANT",
    },
    {
        "name": "LANDSAT_FLOOD",
        "contains": [
            "Landsat_Nepal_flood",
        ],
        "expected": "RELEVANT",
    },
    {
        "name": "INSECT_NEGATIVE_CONTROL",
        "contains": [
            "ab209686",
            "Figure_1",
        ],
        "expected": "OFF_TOPIC",
    },
]

controls = []

for spec in control_specs:

    matches = []

    for asset in assets:
        filename = str(asset["filename"])

        if any(
            needle.lower() in filename.lower()
            for needle in spec["contains"]
        ):
            matches.append(asset)

    if not matches:
        print()
        print(
            "CONTROL NOT FOUND:",
            spec["name"],
            "| patterns:",
            spec["contains"],
        )
        continue

    # Prefer exact unique match.
    asset = matches[0]

    controls.append({
        **spec,
        "asset": asset,
    })

print()
print("=" * 120)
print("CONTROLS")
print("=" * 120)

for item in controls:
    asset = item["asset"]

    print(
        f"{item['name']:<26} "
        f"| expected={item['expected']:<9} "
        f"| {asset['filename']}"
    )

if len(controls) != 8:
    raise RuntimeError(
        f"Expected 8 controls, resolved {len(controls)}."
    )

# =============================================================================
# INSTANTIATE EXISTING ANALYZER ONLY TO REUSE ITS EXISTING BACKEND /
# FRAME EXTRACTION LOGIC.
#
# We do NOT call analyze() and do NOT call _analyze_asset(), because those
# participate in normal persistence/checkpoint flow.
# =============================================================================

class ReadOnlyDB:
    """
    Minimal guard object.

    If an unexpected code path attempts DB mutation through this object,
    fail immediately.
    """
    def __getattr__(self, name):
        raise RuntimeError(
            f"READ-ONLY VALIDATION: unexpected DB access: {name}"
        )

# First inspect constructor so script remains explicit about current OS.
print()
print("=" * 120)
print("ANALYZER SIGNATURE")
print("=" * 120)
print(inspect.signature(VisualSemanticAnalyzerRC2))

# Existing analyzer constructor expects a DB object but initialization should
# only configure context/backend. If it unexpectedly touches DB, we abort.
try:
    analyzer = VisualSemanticAnalyzerRC2(
        ReadOnlyDB(),
        PROJECT_ID,
        backend=None,
        video_frames=4,
    )
except Exception as exc:
    print()
    print("READ-ONLY CONSTRUCTION FAILED:")
    print(type(exc).__name__, str(exc))
    print()
    print("No fallback to writable DB will be attempted.")
    raise

backend = analyzer.backend

print()
print("BACKEND TYPE:", type(backend).__name__)

if hasattr(backend, "model_name"):
    print("MODEL       :", backend.model_name)

# =============================================================================
# DISCOVER EXISTING IMAGE EXTRACTION METHOD
# =============================================================================

candidate_extractors = [
    "_extract_images",
    "_extract_asset_images",
    "_extract_frames",
    "_load_asset_images",
]

extractor_name = None
extractor = None

for name in candidate_extractors:
    if hasattr(analyzer, name):
        extractor_name = name
        extractor = getattr(analyzer, name)
        break

if extractor is None:
    print()
    print("AVAILABLE PRIVATE METHODS:")
    for name in dir(analyzer):
        if name.startswith("_"):
            print(" ", name)
    raise RuntimeError(
        "Could not locate analyzer image/frame extraction method."
    )

print("EXTRACTOR   :", extractor_name)
print("SIGNATURE   :", inspect.signature(extractor))

# =============================================================================
# HELPERS
# =============================================================================

def resolve_asset_path(asset: dict) -> Path:
    raw = str(asset.get("path") or "").strip()

    if not raw:
        raise RuntimeError(
            f"Empty path for {asset['filename']}"
        )

    p = Path(raw)

    if not p.is_absolute():
        p = ROOT / p

    p = p.resolve()

    if not p.exists():
        raise FileNotFoundError(p)

    return p


def extract_images(asset: dict, path: Path):
    """
    Call the existing extractor according to its current signature.
    No semantic persistence.
    """

    sig = inspect.signature(extractor)
    params = list(sig.parameters.values())

    attempts = []

    # Bound method signature excludes self.
    if len(params) == 1:
        attempts = [
            (path,),
            (str(path),),
            (asset,),
        ]
    elif len(params) == 2:
        attempts = [
            (asset, path),
            (asset, str(path)),
            (path, asset),
        ]
    else:
        attempts = [
            (asset,),
            (path,),
            (str(path),),
        ]

    errors = []

    for args in attempts:
        try:
            result = extractor(*args)

            if result is not None:
                return result

        except Exception as exc:
            errors.append(
                f"{args!r} => {type(exc).__name__}: {exc}"
            )

    raise RuntimeError(
        "Existing extractor could not be invoked:\n"
        + "\n".join(errors)
    )


def normalize_classification(result):
    """
    Existing backend classify() is expected to return mapping label -> score.
    Keep this defensive so we don't silently reinterpret unknown schemas.
    """

    if isinstance(result, dict):
        normalized = {}

        for key, value in result.items():
            try:
                normalized[str(key)] = float(value)
            except Exception:
                pass

        if normalized:
            return normalized

    raise RuntimeError(
        "Unexpected backend classification result: "
        + repr(result)[:500]
    )


def classify(images, labels):
    result = backend.classify(
        images,
        labels,
    )
    return normalize_classification(result)


def top_items(scores, n=5):
    return sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:n]


# =============================================================================
# TARGETED VALIDATION
# =============================================================================

results = []

print()
print("=" * 120)
print("TARGETED CLIP RUN")
print("=" * 120)

for index, control in enumerate(controls, 1):

    asset = control["asset"]
    path = resolve_asset_path(asset)

    print()
    print("-" * 120)
    print(
        f"{index}/8 | {control['name']} | {asset['filename']}"
    )
    print("PATH:", path)

    started = time.perf_counter()

    try:
        images = extract_images(
            asset,
            path,
        )

        try:
            image_count = len(images)
        except Exception:
            image_count = None

        print("IMAGES/FRAMES:", image_count)

        event_started = time.perf_counter()

        event_scores = classify(
            images,
            event_labels,
        )

        event_elapsed = (
            time.perf_counter()
            - event_started
        )

        topic_started = time.perf_counter()

        topic_scores = classify(
            images,
            topic_labels,
        )

        topic_elapsed = (
            time.perf_counter()
            - topic_started
        )

        relevant = float(
            topic_scores.get(
                "relevant",
                0.0,
            )
        )

        off_topic = float(
            topic_scores.get(
                "off_topic",
                0.0,
            )
        )

        margin = relevant - off_topic

        # Reproduce CURRENT analyzer decision thresholds for diagnosis.
        #
        # We are NOT changing them here.
        if off_topic >= 0.58:
            decision = "OFF_TOPIC"
        elif (
            relevant >= 0.55
            and margin >= 0.12
        ):
            decision = "RELEVANT"
        else:
            decision = "UNCERTAIN"

        top_event = top_items(
            event_scores,
            5,
        )

        elapsed = (
            time.perf_counter()
            - started
        )

        expected = control["expected"]

        expected_pass = (
            decision == expected
        )

        print()
        print(
            "TOPIC:"
            f" relevant={relevant:.6f}"
            f" off_topic={off_topic:.6f}"
            f" margin={margin:.6f}"
            f" => {decision}"
        )

        print(
            "EXPECTED:",
            expected,
            "=>",
            "PASS" if expected_pass else "FAIL",
        )

        print()
        print("TOP EVENT CLASSES:")

        for label, score in top_event:
            print(
                f"  {label:<24} {score:.6f}"
            )

        print()
        print(
            f"TIMING: event={event_elapsed:.2f}s "
            f"topic={topic_elapsed:.2f}s "
            f"total={elapsed:.2f}s"
        )

        record = {
            "control":
                control["name"],

            "expected":
                expected,

            "decision":
                decision,

            "expected_pass":
                expected_pass,

            "asset_id":
                asset["id"],

            "filename":
                asset["filename"],

            "path":
                str(path),

            "canonical_before": {
                "semantic_class":
                    asset["semantic_class"],

                "semantic_confidence":
                    asset["semantic_confidence"],
            },

            "topic_scores":
                topic_scores,

            "relevant":
                relevant,

            "off_topic":
                off_topic,

            "margin":
                margin,

            "top_event_classes": [
                {
                    "label": label,
                    "score": score,
                }
                for label, score
                in top_event
            ],

            "event_seconds":
                round(event_elapsed, 3),

            "topic_seconds":
                round(topic_elapsed, 3),

            "total_seconds":
                round(elapsed, 3),

            "status":
                "OK",
        }

    except Exception as exc:

        print()
        print(
            "CONTROL FAILED:",
            type(exc).__name__,
            str(exc),
        )

        traceback.print_exc()

        record = {
            "control":
                control["name"],

            "expected":
                control["expected"],

            "asset_id":
                asset["id"],

            "filename":
                asset["filename"],

            "path":
                str(path),

            "status":
                "ERROR",

            "error_type":
                type(exc).__name__,

            "error":
                str(exc),
        }

    results.append(record)

    # Save after every control.
    REPORT.write_text(
        json.dumps(
            {
                "schema":
                    "atlas_zero.film10.targeted_clip_validation.v4",

                "project_id":
                    PROJECT_ID,

                "context_source":
                    context.source_path,

                "event_label_count":
                    len(event_labels),

                "relevant_prompt_count":
                    len(
                        topic_labels.get(
                            "relevant",
                            (),
                        )
                    ),

                "results":
                    results,

                "complete":
                    False,

                "db_writes":
                    False,

                "assignments":
                    False,

                "render":
                    False,

                "live_api":
                    False,

                "paid_calls":
                    False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

# =============================================================================
# SUMMARY
# =============================================================================

ok_results = [
    row
    for row in results
    if row.get("status") == "OK"
]

errors = [
    row
    for row in results
    if row.get("status") != "OK"
]

passes = [
    row
    for row in ok_results
    if row.get("expected_pass")
]

fails = [
    row
    for row in ok_results
    if not row.get("expected_pass")
]

relevant_controls = [
    row
    for row in ok_results
    if row["expected"] == "RELEVANT"
]

relevant_passes = [
    row
    for row in relevant_controls
    if row["decision"] == "RELEVANT"
]

negative_controls = [
    row
    for row in ok_results
    if row["expected"] == "OFF_TOPIC"
]

negative_passes = [
    row
    for row in negative_controls
    if row["decision"] == "OFF_TOPIC"
]

print()
print("=" * 120)
print("VALIDATION SUMMARY")
print("=" * 120)

print("CONTROLS        :", len(results))
print("OK              :", len(ok_results))
print("ERRORS          :", len(errors))
print("EXPECTED PASS   :", len(passes))
print("EXPECTED FAIL   :", len(fails))
print(
    "RELEVANT PASS   :",
    len(relevant_passes),
    "/",
    len(relevant_controls),
)
print(
    "NEGATIVE PASS   :",
    len(negative_passes),
    "/",
    len(negative_controls),
)

print()
print("DECISIONS:")

for row in ok_results:
    print(
        f"  {row['control']:<26} "
        f"expected={row['expected']:<9} "
        f"actual={row['decision']:<9} "
        f"rel={row['relevant']:.4f} "
        f"off={row['off_topic']:.4f} "
        + (
            "PASS"
            if row["expected_pass"]
            else "FAIL"
        )
    )

# Strict diagnostic gate:
# all seven known relevant must be RELEVANT,
# insect must be OFF_TOPIC.
strict_pass = (
    len(errors) == 0
    and len(results) == 8
    and len(passes) == 8
)

final_report = {
    "schema":
        "atlas_zero.film10.targeted_clip_validation.v4",

    "project_id":
        PROJECT_ID,

    "context_source":
        context.source_path,

    "event_label_count":
        len(event_labels),

    "relevant_prompt_count":
        len(
            topic_labels.get(
                "relevant",
                (),
            )
        ),

    "controls":
        len(results),

    "ok":
        len(ok_results),

    "errors":
        len(errors),

    "expected_pass":
        len(passes),

    "expected_fail":
        len(fails),

    "relevant_pass":
        len(relevant_passes),

    "relevant_total":
        len(relevant_controls),

    "negative_pass":
        len(negative_passes),

    "negative_total":
        len(negative_controls),

    "strict_pass":
        strict_pass,

    "results":
        results,

    "complete":
        True,

    "db_writes":
        False,

    "assignments":
        False,

    "render":
        False,

    "live_api":
        False,

    "paid_calls":
        False,
}

REPORT.write_text(
    json.dumps(
        final_report,
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

if strict_pass:
    print("TARGETED CLIP VALIDATION V4: PASS")
    print()
    print(
        "Semantic context is now good enough "
        "to consider full 60-asset reanalysis."
    )
else:
    print("TARGETED CLIP VALIDATION V4: FAIL")
    print()
    print(
        "Do NOT run the full 60-asset analysis."
    )
    print(
        "Next step is to diagnose event/topic scoring "
        "from these eight controls."
    )

print("=" * 120)

print()
print("No analyzer persistence method called.")
print("No canonical semantic DB writes performed.")
print("No assignments written.")
print("No render performed.")
print("No paid API calls.")
