from __future__ import annotations

from pathlib import Path
import inspect
import json
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

REPORT = OUT / "FILM10_TARGETED_CLIP_VALIDATION_V4_FIXED.json"

print("=" * 120)
print("ATLAS ZERO — FILM10 TARGETED CLIP VALIDATION V4 FIXED")
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

from az_enterprise.core.visual_semantic_analyzer_rc2 import (
    VisualSemanticAnalyzerRC2,
)

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
print(
    "SCENE LABELS     :",
    len([k for k in event_labels if str(k).startswith("scene_")]),
)
print(
    "RELEVANT PROMPTS :",
    len(topic_labels.get("relevant", ())),
)
print(
    "OFFTOPIC PROMPTS :",
    len(topic_labels.get("off_topic", ())),
)

if context.source_path != "canonical_db:story_scenes":
    raise RuntimeError("Canonical semantic context not active.")

if len(topic_labels.get("relevant", ())) < 40:
    raise RuntimeError("V4 multi-prompt topic context not active.")

# =============================================================================
# ASSETS
# =============================================================================

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

try:
    assets = [
        dict(row)
        for row in conn.execute(
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
    ]
finally:
    conn.close()

print("CANONICAL ASSETS  :", len(assets))

if len(assets) != 60:
    raise RuntimeError(
        f"Expected 60 Film10 assets, found {len(assets)}"
    )

# =============================================================================
# CONTROLS
# =============================================================================

control_specs = [
    {
        "name": "LANGTANG_PHOTO",
        "contains": ["Le_Langtang_Lirung"],
        "expected": "RELEVANT",
    },
    {
        "name": "GYIRONG_MUDSLIDE",
        "contains": ["Mudslide_at_Gyirong_Port_2"],
        "expected": "RELEVANT",
    },
    {
        "name": "DRONE_COLLAPSE",
        "contains": ["Chinese_photographer_accidentally_captured"],
        "expected": "RELEVANT",
    },
    {
        "name": "SENTINEL_BEFORE",
        "contains": ["Copernicus_Sentinel2"],
        "expected": "RELEVANT",
    },
    {
        "name": "GYIRONG_SATELLITE",
        "contains": ["Gyirong_Port_before_and_after"],
        "expected": "RELEVANT",
    },
    {
        "name": "ISS_LANGTANG",
        "contains": ["ISS061-E-148219"],
        "expected": "RELEVANT",
    },
    {
        "name": "LANDSAT_FLOOD",
        "contains": ["Landsat_Nepal_flood"],
        "expected": "RELEVANT",
    },
    {
        "name": "INSECT_NEGATIVE_CONTROL",
        "contains": ["ab209686", "Figure_1"],
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
        raise RuntimeError(
            f"Control not found: {spec['name']} "
            f"{spec['contains']}"
        )

    controls.append({
        **spec,
        "asset": matches[0],
    })

print()
print("=" * 120)
print("CONTROLS")
print("=" * 120)

for control in controls:
    asset = control["asset"]

    print(
        f"{control['name']:<26} "
        f"| expected={control['expected']:<9} "
        f"| type={asset['media_type']:<6} "
        f"| {asset['filename']}"
    )

if len(controls) != 8:
    raise RuntimeError(
        f"Expected 8 controls, got {len(controls)}"
    )

# =============================================================================
# READ-ONLY ANALYZER
# =============================================================================

class ReadOnlyDB:

    def __getattr__(self, name):
        raise RuntimeError(
            f"READ-ONLY VALIDATION: unexpected DB access: {name}"
        )


analyzer = VisualSemanticAnalyzerRC2(
    ReadOnlyDB(),
    PROJECT_ID,
    backend=None,
    video_frames=4,
)

backend = analyzer.backend
extractor = analyzer._extract_images

print()
print("=" * 120)
print("RUNTIME")
print("=" * 120)

print("ANALYZER :", inspect.signature(VisualSemanticAnalyzerRC2))
print("BACKEND  :", type(backend).__name__)
print("EXTRACTOR:", inspect.signature(extractor))

# Hard contract discovered from actual runtime.
extractor_params = list(
    inspect.signature(extractor).parameters.keys()
)

if extractor_params != ["path", "media_type"]:
    raise RuntimeError(
        "Extractor signature changed. "
        f"Expected ['path','media_type'], got {extractor_params}"
    )

# =============================================================================
# HELPERS
# =============================================================================

def resolve_path(asset):
    p = Path(str(asset["path"]))

    if not p.is_absolute():
        p = ROOT / p

    p = p.resolve()

    if not p.exists():
        raise FileNotFoundError(p)

    return p


def normalize_scores(result):

    if not isinstance(result, dict):
        raise RuntimeError(
            "Unexpected classify result type: "
            f"{type(result).__name__}"
        )

    out = {}

    for key, value in result.items():
        try:
            out[str(key)] = float(value)
        except Exception:
            pass

    if not out:
        raise RuntimeError(
            "Classification result contains no numeric scores."
        )

    return out


def classify(images, labels):
    return normalize_scores(
        backend.classify(
            images,
            labels,
        )
    )


def top_items(scores, n=5):
    return sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:n]


# =============================================================================
# TARGETED RUN
# =============================================================================

results = []

print()
print("=" * 120)
print("TARGETED CLIP RUN")
print("=" * 120)

for idx, control in enumerate(controls, 1):

    asset = control["asset"]
    path = resolve_path(asset)
    media_type = str(asset["media_type"])

    print()
    print("-" * 120)
    print(
        f"{idx}/8 | {control['name']} | "
        f"{asset['filename']}"
    )
    print("PATH      :", path)
    print("MEDIA TYPE:", media_type)

    started = time.perf_counter()

    try:

        # -------------------------------------------------------------
        # FIX:
        # actual existing signature is:
        #
        # _extract_images(path: Path, media_type: str)
        # -------------------------------------------------------------

        images = extractor(
            path,
            media_type,
        )

        try:
            frame_count = len(images)
        except Exception:
            frame_count = None

        print("FRAMES    :", frame_count)

        if not images:
            raise RuntimeError(
                "Existing extractor returned no images."
            )

        event_started = time.perf_counter()

        event_scores = classify(
            images,
            event_labels,
        )

        event_seconds = (
            time.perf_counter()
            - event_started
        )

        topic_started = time.perf_counter()

        topic_scores = classify(
            images,
            topic_labels,
        )

        topic_seconds = (
            time.perf_counter()
            - topic_started
        )

        relevant = float(
            topic_scores.get("relevant", 0.0)
        )

        off_topic = float(
            topic_scores.get("off_topic", 0.0)
        )

        margin = relevant - off_topic

        # Existing analyzer threshold logic.
        if off_topic >= 0.58:
            decision = "OFF_TOPIC"

        elif (
            relevant >= 0.55
            and margin >= 0.12
        ):
            decision = "RELEVANT"

        else:
            decision = "UNCERTAIN"

        expected = control["expected"]

        expected_pass = (
            decision == expected
        )

        top_event = top_items(
            event_scores,
            5,
        )

        total_seconds = (
            time.perf_counter()
            - started
        )

        print()
        print(
            f"TOPIC: relevant={relevant:.6f} "
            f"off_topic={off_topic:.6f} "
            f"margin={margin:.6f} "
            f"=> {decision}"
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
            f"TIMING: event={event_seconds:.2f}s "
            f"topic={topic_seconds:.2f}s "
            f"total={total_seconds:.2f}s"
        )

        record = {
            "control": control["name"],
            "expected": expected,
            "decision": decision,
            "expected_pass": expected_pass,

            "asset_id": asset["id"],
            "filename": asset["filename"],
            "media_type": media_type,
            "path": str(path),

            "canonical_before": {
                "semantic_class":
                    asset["semantic_class"],
                "semantic_confidence":
                    asset["semantic_confidence"],
            },

            "topic_scores": topic_scores,

            "relevant": relevant,
            "off_topic": off_topic,
            "margin": margin,

            "top_event_classes": [
                {
                    "label": label,
                    "score": score,
                }
                for label, score in top_event
            ],

            "event_seconds":
                round(event_seconds, 3),

            "topic_seconds":
                round(topic_seconds, 3),

            "total_seconds":
                round(total_seconds, 3),

            "status": "OK",
        }

    except Exception as exc:

        print()
        print(
            "CONTROL ERROR:",
            type(exc).__name__,
            str(exc),
        )

        traceback.print_exc()

        record = {
            "control": control["name"],
            "expected": control["expected"],
            "asset_id": asset["id"],
            "filename": asset["filename"],
            "media_type": media_type,
            "path": str(path),
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    results.append(record)

    # Crash-safe diagnostic checkpoint only.
    REPORT.write_text(
        json.dumps(
            {
                "schema":
                    "atlas_zero.film10.targeted_clip_validation.v4.fixed",

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

                "canonical_db_writes":
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
    r for r in results
    if r.get("status") == "OK"
]

errors = [
    r for r in results
    if r.get("status") != "OK"
]

passes = [
    r for r in ok_results
    if r.get("expected_pass") is True
]

fails = [
    r for r in ok_results
    if r.get("expected_pass") is False
]

relevant_controls = [
    r for r in ok_results
    if r["expected"] == "RELEVANT"
]

relevant_passes = [
    r for r in relevant_controls
    if r["decision"] == "RELEVANT"
]

negative_controls = [
    r for r in ok_results
    if r["expected"] == "OFF_TOPIC"
]

negative_passes = [
    r for r in negative_controls
    if r["decision"] == "OFF_TOPIC"
]

strict_pass = (
    len(results) == 8
    and len(errors) == 0
    and len(passes) == 8
)

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

final_report = {
    "schema":
        "atlas_zero.film10.targeted_clip_validation.v4.fixed",

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

    "canonical_db_writes":
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

    print("TARGETED CLIP VALIDATION V4 FIXED: PASS")
    print()
    print(
        "All seven positive controls are RELEVANT "
        "and the negative insect control is OFF_TOPIC."
    )
    print(
        "Only now is full semantic reanalysis eligible."
    )

else:

    print("TARGETED CLIP VALIDATION V4 FIXED: FAIL")
    print()
    print(
        "Do NOT run the full 60-asset semantic analysis."
    )
    print(
        "The resulting scores now represent a real "
        "semantic/scoring diagnostic."
    )

print("=" * 120)

print()
print("No analyzer persistence method called.")
print("No canonical semantic DB writes performed.")
print("No assignments written.")
print("No render performed.")
print("No paid API calls.")
