from __future__ import annotations

from pathlib import Path
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

REPORT = OUT / "FILM10_TARGETED_CLIP_VALIDATION_V4_2.json"

print("=" * 120)
print("ATLAS ZERO — FILM10 TARGETED CLIP VALIDATION V4.2")
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
    SemanticPredictionRC2,
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
    len([
        k
        for k in event_labels
        if str(k).startswith("scene_")
    ]),
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
    raise RuntimeError(
        "Canonical semantic context is not active."
    )

if len(event_labels) != 89:
    raise RuntimeError(
        f"Expected 89 event labels, got {len(event_labels)}"
    )

if len(topic_labels.get("relevant", ())) < 40:
    raise RuntimeError(
        "V4 multi-prompt relevance context is not active."
    )

# =============================================================================
# ASSETS
# =============================================================================

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

try:
    rows = conn.execute(
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

assets = [
    dict(row)
    for row in rows
]

print("CANONICAL ASSETS  :", len(assets))

if len(assets) != 60:
    raise RuntimeError(
        f"Expected 60 Film10 assets, got {len(assets)}"
    )

# =============================================================================
# CONTROL FIXTURES
# =============================================================================

specs = [
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

for spec in specs:

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
            f"Control not found: {spec['name']}"
        )

    controls.append({
        **spec,
        "asset": matches[0],
    })

if len(controls) != 8:
    raise RuntimeError(
        f"Expected 8 controls, got {len(controls)}"
    )

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

print("BACKEND  :", type(backend).__name__)
print("EXTRACTOR:", "_extract_images(path, media_type)")
print("PREDICTION:", SemanticPredictionRC2.__name__)

# =============================================================================
# HELPERS
# =============================================================================

def resolve_path(asset: dict) -> Path:

    p = Path(
        str(asset["path"])
    )

    if not p.is_absolute():
        p = ROOT / p

    p = p.resolve()

    if not p.exists():
        raise FileNotFoundError(p)

    return p


def validate_prediction(
    result,
    stage: str,
) -> SemanticPredictionRC2:

    if not isinstance(
        result,
        SemanticPredictionRC2,
    ):
        raise RuntimeError(
            f"{stage}: expected SemanticPredictionRC2, "
            f"got {type(result).__name__}"
        )

    if not isinstance(
        result.scores,
        dict,
    ):
        raise RuntimeError(
            f"{stage}: prediction.scores is not dict"
        )

    return result


def top_scores(
    scores: dict[str, float],
    n: int = 5,
):

    return sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:n]


# =============================================================================
# RUN
# =============================================================================

results = []

print()
print("=" * 120)
print("TARGETED CLIP RUN")
print("=" * 120)

for idx, control in enumerate(
    controls,
    1,
):

    asset = control["asset"]
    path = resolve_path(asset)
    media_type = str(asset["media_type"])

    print()
    print("-" * 120)

    print(
        f"{idx}/8 | "
        f"{control['name']} | "
        f"{asset['filename']}"
    )

    print("PATH      :", path)
    print("MEDIA TYPE:", media_type)

    started = time.perf_counter()

    try:

        images = extractor(
            path,
            media_type,
        )

        frames = len(images)

        print("FRAMES    :", frames)

        if frames <= 0:
            raise RuntimeError(
                "No images/frames extracted."
            )

        # -------------------------------------------------------------
        # EVENT CLASSIFICATION
        # -------------------------------------------------------------

        t0 = time.perf_counter()

        event = validate_prediction(
            backend.classify(
                images,
                event_labels,
            ),
            "event",
        )

        event_seconds = (
            time.perf_counter()
            - t0
        )

        # -------------------------------------------------------------
        # TOPIC / RELEVANCE CLASSIFICATION
        # -------------------------------------------------------------

        t0 = time.perf_counter()

        topic = validate_prediction(
            backend.classify(
                images,
                topic_labels,
            ),
            "topic",
        )

        topic_seconds = (
            time.perf_counter()
            - t0
        )

        raw_relevant = float(
            topic.scores.get(
                "relevant",
                0.0,
            )
        )

        raw_off_topic = float(
            topic.scores.get(
                "off_topic",
                0.0,
            )
        )

        # -------------------------------------------------------------
        # EXACT CURRENT ANALYZER LOGIC
        # -------------------------------------------------------------

        final_off_topic = (
            raw_off_topic
        )

        private_override = False

        if (
            event.label
            == "unrelated_private_content"
            and event.score >= 0.32
        ):

            final_off_topic = max(
                final_off_topic,
                float(event.score),
            )

            private_override = True

        relevance_status = (
            analyzer._relevance_status(
                relevant_score=raw_relevant,
                off_topic_score=final_off_topic,
                event_type=event.label,
            )
        )

        margin = (
            raw_relevant
            - final_off_topic
        )

        expected = control["expected"]

        passed = (
            relevance_status
            == expected
        )

        total_seconds = (
            time.perf_counter()
            - started
        )

        print()
        print(
            f"EVENT: "
            f"{event.label} "
            f"({event.score:.6f})"
        )

        print(
            f"TOPIC RAW: "
            f"relevant={raw_relevant:.6f} "
            f"off_topic={raw_off_topic:.6f}"
        )

        if private_override:

            print(
                f"PRIVATE OVERRIDE: "
                f"off_topic -> {final_off_topic:.6f}"
            )

        print(
            f"FINAL: "
            f"relevant={raw_relevant:.6f} "
            f"off_topic={final_off_topic:.6f} "
            f"margin={margin:.6f} "
            f"=> {relevance_status}"
        )

        print(
            "EXPECTED:",
            expected,
            "=>",
            "PASS"
            if passed
            else "FAIL",
        )

        print()
        print("TOP EVENT SCORES:")

        for label, score in top_scores(
            event.scores,
            5,
        ):

            print(
                f"  {label:<28} "
                f"{score:.6f}"
            )

        print()
        print("TOP TOPIC SCORES:")

        for label, score in top_scores(
            topic.scores,
            5,
        ):

            print(
                f"  {label:<28} "
                f"{score:.6f}"
            )

        print()
        print(
            f"TIMING: "
            f"event={event_seconds:.2f}s "
            f"topic={topic_seconds:.2f}s "
            f"total={total_seconds:.2f}s"
        )

        record = {
            "control":
                control["name"],

            "expected":
                expected,

            "decision":
                relevance_status,

            "expected_pass":
                passed,

            "asset_id":
                asset["id"],

            "filename":
                asset["filename"],

            "media_type":
                media_type,

            "path":
                str(path),

            "frames":
                frames,

            "canonical_before": {
                "semantic_class":
                    asset[
                        "semantic_class"
                    ],

                "semantic_confidence":
                    asset[
                        "semantic_confidence"
                    ],
            },

            "event": {
                "label":
                    event.label,

                "score":
                    event.score,

                "scores":
                    event.scores,
            },

            "topic": {
                "label":
                    topic.label,

                "score":
                    topic.score,

                "scores":
                    topic.scores,
            },

            "raw_relevant":
                raw_relevant,

            "raw_off_topic":
                raw_off_topic,

            "final_off_topic":
                final_off_topic,

            "private_override":
                private_override,

            "margin":
                margin,

            "event_seconds":
                round(
                    event_seconds,
                    3,
                ),

            "topic_seconds":
                round(
                    topic_seconds,
                    3,
                ),

            "total_seconds":
                round(
                    total_seconds,
                    3,
                ),

            "status":
                "OK",
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
            "control":
                control["name"],

            "expected":
                control["expected"],

            "asset_id":
                asset["id"],

            "filename":
                asset["filename"],

            "media_type":
                media_type,

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

    # -------------------------------------------------------------
    # Crash-safe diagnostic checkpoint.
    # File only. No canonical DB write.
    # -------------------------------------------------------------

    REPORT.write_text(
        json.dumps(
            {
                "schema":
                    "atlas_zero.film10.targeted_clip_validation.v4.2",

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

ok_rows = [
    row
    for row in results
    if row.get("status") == "OK"
]

error_rows = [
    row
    for row in results
    if row.get("status") != "OK"
]

passes = [
    row
    for row in ok_rows
    if row.get("expected_pass")
]

fails = [
    row
    for row in ok_rows
    if not row.get("expected_pass")
]

positive_rows = [
    row
    for row in ok_rows
    if row["expected"] == "RELEVANT"
]

positive_passes = [
    row
    for row in positive_rows
    if row["decision"] == "RELEVANT"
]

negative_rows = [
    row
    for row in ok_rows
    if row["expected"] == "OFF_TOPIC"
]

negative_passes = [
    row
    for row in negative_rows
    if row["decision"] == "OFF_TOPIC"
]

strict_pass = (
    len(results) == 8
    and len(error_rows) == 0
    and len(passes) == 8
)

print()
print("=" * 120)
print("VALIDATION SUMMARY")
print("=" * 120)

print(
    "CONTROLS        :",
    len(results),
)

print(
    "OK              :",
    len(ok_rows),
)

print(
    "ERRORS          :",
    len(error_rows),
)

print(
    "EXPECTED PASS   :",
    len(passes),
)

print(
    "EXPECTED FAIL   :",
    len(fails),
)

print(
    "RELEVANT PASS   :",
    len(positive_passes),
    "/",
    len(positive_rows),
)

print(
    "NEGATIVE PASS   :",
    len(negative_passes),
    "/",
    len(negative_rows),
)

print()
print("DECISIONS:")

for row in ok_rows:

    print(
        f"  {row['control']:<26} "
        f"expected={row['expected']:<9} "
        f"actual={row['decision']:<9} "
        f"event={row['event']['label']:<20} "
        f"rel={row['raw_relevant']:.4f} "
        f"off={row['final_off_topic']:.4f} "
        + (
            "PASS"
            if row["expected_pass"]
            else "FAIL"
        )
    )

# =============================================================================
# FINAL REPORT
# =============================================================================

final_report = {
    "schema":
        "atlas_zero.film10.targeted_clip_validation.v4.2",

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
        len(ok_rows),

    "errors":
        len(error_rows),

    "expected_pass":
        len(passes),

    "expected_fail":
        len(fails),

    "relevant_pass":
        len(positive_passes),

    "relevant_total":
        len(positive_rows),

    "negative_pass":
        len(negative_passes),

    "negative_total":
        len(negative_rows),

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

    print(
        "TARGETED CLIP VALIDATION V4.2: PASS"
    )

    print()

    print(
        "7/7 known-relevant controls are RELEVANT."
    )

    print(
        "1/1 negative insect control is OFF_TOPIC."
    )

    print()

    print(
        "Full 60-asset semantic reanalysis is now eligible."
    )

else:

    print(
        "TARGETED CLIP VALIDATION V4.2: FAIL"
    )

    print()

    print(
        "Do NOT run full 60-asset semantic analysis."
    )

    print(
        "This run now represents the actual existing "
        "backend + analyzer relevance decision path."
    )

    print()

    print(
        "Next action must be based on the observed "
        "event/topic scores — not vocabulary guessing."
    )

print("=" * 120)

print()
print("No analyzer persistence method called.")
print("No canonical semantic DB writes performed.")
print("No assignments written.")
print("No render performed.")
print("No paid API calls.")
