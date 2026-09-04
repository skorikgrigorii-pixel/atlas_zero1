from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import sys
import time
import numpy as np

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

REPORT = OUT / "FILM10_CLIP_SCORING_STRATEGY_AUDIT_V4_3.json"

print("=" * 120)
print("ATLAS ZERO — FILM10 CLIP SCORING STRATEGY AUDIT V4.3")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")
print("PURPOSE    : COMPARE SCORING MATH ONLY")

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

positive_prompts = list(
    context.topic_labels.get(
        "relevant",
        (),
    )
)

negative_prompts = list(
    context.topic_labels.get(
        "off_topic",
        (),
    )
)

print()
print("CONTEXT SOURCE    :", context.source_path)
print("POSITIVE PROMPTS  :", len(positive_prompts))
print("NEGATIVE PROMPTS  :", len(negative_prompts))

if context.source_path != "canonical_db:story_scenes":
    raise RuntimeError("Canonical context not active.")

if not positive_prompts:
    raise RuntimeError("No positive prompts.")

if not negative_prompts:
    raise RuntimeError("No negative prompts.")

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
            SELECT id,path,filename,media_type
            FROM assets
            WHERE project_id=?
            ORDER BY filename
            """,
            (PROJECT_ID,),
        ).fetchall()
    ]
finally:
    conn.close()

specs = [
    ("LANGTANG_PHOTO", "Le_Langtang_Lirung", "RELEVANT"),
    ("GYIRONG_MUDSLIDE", "Mudslide_at_Gyirong_Port_2", "RELEVANT"),
    ("DRONE_COLLAPSE", "Chinese_photographer_accidentally_captured", "RELEVANT"),
    ("SENTINEL_BEFORE", "Copernicus_Sentinel2", "RELEVANT"),
    ("GYIRONG_SATELLITE", "Gyirong_Port_before_and_after", "RELEVANT"),
    ("ISS_LANGTANG", "ISS061-E-148219", "RELEVANT"),
    ("LANDSAT_FLOOD", "Landsat_Nepal_flood", "RELEVANT"),
    ("INSECT_NEGATIVE_CONTROL", "ab209686", "OFF_TOPIC"),
]

controls = []

for name, needle, expected in specs:

    matches = [
        asset
        for asset in assets
        if needle.lower()
        in str(asset["filename"]).lower()
    ]

    if not matches:
        raise RuntimeError(
            f"Missing control: {name}"
        )

    controls.append({
        "name": name,
        "expected": expected,
        "asset": matches[0],
    })

# =============================================================================
# ANALYZER — READ ONLY
# =============================================================================

class ReadOnlyDB:
    def __getattr__(self, name):
        raise RuntimeError(
            f"Unexpected DB access: {name}"
        )

analyzer = VisualSemanticAnalyzerRC2(
    ReadOnlyDB(),
    PROJECT_ID,
    backend=None,
    video_frames=4,
)

backend = analyzer.backend
extractor = analyzer._extract_images

torch = backend.torch
processor = backend.processor
model = backend.model
device = backend.device

print("BACKEND           :", type(backend).__name__)
print("DEVICE            :", device)

# =============================================================================
# PROMPT DIAGNOSTIC
# =============================================================================

print()
print("=" * 120)
print("PROMPT SAMPLE")
print("=" * 120)

print()
print("POSITIVE FIRST 12:")

for prompt in positive_prompts[:12]:
    print(" +", prompt)

print()
print("NEGATIVE:")

for prompt in negative_prompts:
    print(" -", prompt)

# =============================================================================
# RAW CLIP SCORING
# =============================================================================

def resolve_path(asset):

    p = Path(str(asset["path"]))

    if not p.is_absolute():
        p = ROOT / p

    p = p.resolve()

    if not p.exists():
        raise FileNotFoundError(p)

    return p


def frame_prompt_logits(image, prompts):

    inputs = processor(
        text=prompts,
        images=image,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=77,
    )

    inputs = {
        key: value.to(
            device,
            non_blocking=False,
        )
        for key, value in inputs.items()
    }

    with torch.inference_mode():
        outputs = model(**inputs)

    # IMPORTANT:
    # use RAW logits here.
    # We are explicitly testing alternatives to the current
    # global prompt softmax.
    logits = (
        outputs.logits_per_image
        .detach()
        .to("cpu")
        .numpy()[0]
        .astype(float)
    )

    del outputs
    del inputs

    backend._cleanup_memory()

    return logits


def stable_sigmoid(x):
    x = float(np.clip(x, -60.0, 60.0))
    return 1.0 / (1.0 + np.exp(-x))


def score_frame(image):

    prompts = (
        positive_prompts
        + negative_prompts
    )

    logits = frame_prompt_logits(
        image,
        prompts,
    )

    p = logits[
        :len(positive_prompts)
    ]

    n = logits[
        len(positive_prompts):
    ]

    # -------------------------------------------------------------
    # Strategy A:
    # strongest positive vs strongest negative
    # -------------------------------------------------------------

    pos_max = float(np.max(p))
    neg_max = float(np.max(n))

    margin_max = (
        pos_max
        - neg_max
    )

    prob_max = stable_sigmoid(
        margin_max
    )

    # -------------------------------------------------------------
    # Strategy B:
    # mean of top 5 positive vs mean of all negatives
    # -------------------------------------------------------------

    top_k = min(
        5,
        len(p),
    )

    pos_top5 = float(
        np.mean(
            np.sort(p)[-top_k:]
        )
    )

    neg_mean = float(
        np.mean(n)
    )

    margin_top5 = (
        pos_top5
        - neg_mean
    )

    prob_top5 = stable_sigmoid(
        margin_top5
    )

    # -------------------------------------------------------------
    # Strategy C:
    # mean of top 10 positive vs strongest negative
    # -------------------------------------------------------------

    top_k10 = min(
        10,
        len(p),
    )

    pos_top10 = float(
        np.mean(
            np.sort(p)[-top_k10:]
        )
    )

    margin_top10_vs_negmax = (
        pos_top10
        - neg_max
    )

    prob_top10_vs_negmax = stable_sigmoid(
        margin_top10_vs_negmax
    )

    # -------------------------------------------------------------
    # Strategy D:
    # median positive vs median negative
    # -------------------------------------------------------------

    pos_median = float(
        np.median(p)
    )

    neg_median = float(
        np.median(n)
    )

    margin_median = (
        pos_median
        - neg_median
    )

    prob_median = stable_sigmoid(
        margin_median
    )

    return {
        "pos_max": pos_max,
        "neg_max": neg_max,

        "pos_top5_mean":
            pos_top5,

        "neg_mean":
            neg_mean,

        "pos_top10_mean":
            pos_top10,

        "pos_median":
            pos_median,

        "neg_median":
            neg_median,

        "A_max_vs_max": {
            "margin":
                margin_max,
            "prob":
                prob_max,
        },

        "B_top5_vs_negmean": {
            "margin":
                margin_top5,
            "prob":
                prob_top5,
        },

        "C_top10_vs_negmax": {
            "margin":
                margin_top10_vs_negmax,
            "prob":
                prob_top10_vs_negmax,
        },

        "D_median_vs_median": {
            "margin":
                margin_median,
            "prob":
                prob_median,
        },
    }


def aggregate_frames(frame_results):

    strategies = [
        "A_max_vs_max",
        "B_top5_vs_negmean",
        "C_top10_vs_negmax",
        "D_median_vs_median",
    ]

    result = {}

    for strategy in strategies:

        margins = [
            row[strategy]["margin"]
            for row in frame_results
        ]

        probs = [
            row[strategy]["prob"]
            for row in frame_results
        ]

        result[strategy] = {
            "margin_mean":
                float(np.mean(margins)),

            "prob_mean":
                float(np.mean(probs)),
        }

    return result

# =============================================================================
# RUN
# =============================================================================

results = []

print()
print("=" * 120)
print("SCORING AUDIT")
print("=" * 120)

for idx, control in enumerate(
    controls,
    1,
):

    asset = control["asset"]
    path = resolve_path(asset)

    print()
    print("-" * 120)
    print(
        f"{idx}/8 | "
        f"{control['name']} | "
        f"expected={control['expected']}"
    )
    print(asset["filename"])

    images = extractor(
        path,
        str(asset["media_type"]),
    )

    print("FRAMES:", len(images))

    started = time.perf_counter()

    frame_results = []

    for frame_idx, image in enumerate(
        images,
        1,
    ):

        row = score_frame(image)

        frame_results.append(row)

        print(
            f"  frame {frame_idx}: "
            f"A={row['A_max_vs_max']['margin']:+.4f} "
            f"B={row['B_top5_vs_negmean']['margin']:+.4f} "
            f"C={row['C_top10_vs_negmax']['margin']:+.4f} "
            f"D={row['D_median_vs_median']['margin']:+.4f}"
        )

    aggregate = aggregate_frames(
        frame_results
    )

    elapsed = (
        time.perf_counter()
        - started
    )

    print()
    print("AGGREGATE:")

    for strategy, values in aggregate.items():

        sign_decision = (
            "RELEVANT"
            if values["margin_mean"] > 0
            else "OFF_TOPIC"
        )

        print(
            f"  {strategy:<24} "
            f"margin={values['margin_mean']:+.6f} "
            f"prob={values['prob_mean']:.6f} "
            f"=> {sign_decision}"
        )

    print(
        f"TIME: {elapsed:.2f}s"
    )

    results.append({
        "control":
            control["name"],

        "expected":
            control["expected"],

        "asset_id":
            asset["id"],

        "filename":
            asset["filename"],

        "frames":
            len(images),

        "aggregate":
            aggregate,

        "frame_results":
            frame_results,

        "seconds":
            round(elapsed, 3),
    })

    REPORT.write_text(
        json.dumps(
            {
                "schema":
                    "atlas_zero.film10.clip_scoring_strategy_audit.v4.3",

                "project_id":
                    PROJECT_ID,

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

                "paid_calls":
                    False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

# =============================================================================
# STRATEGY SUMMARY
# =============================================================================

strategies = [
    "A_max_vs_max",
    "B_top5_vs_negmean",
    "C_top10_vs_negmax",
    "D_median_vs_median",
]

summary = {}

print()
print("=" * 120)
print("STRATEGY SUMMARY — ZERO-MARGIN DECISION")
print("=" * 120)

for strategy in strategies:

    correct = 0
    false_positive = 0
    false_negative = 0

    rows = []

    for result in results:

        margin = (
            result[
                "aggregate"
            ][strategy][
                "margin_mean"
            ]
        )

        predicted = (
            "RELEVANT"
            if margin > 0
            else "OFF_TOPIC"
        )

        expected = result["expected"]

        passed = (
            predicted == expected
        )

        if passed:
            correct += 1

        if (
            expected == "OFF_TOPIC"
            and predicted == "RELEVANT"
        ):
            false_positive += 1

        if (
            expected == "RELEVANT"
            and predicted == "OFF_TOPIC"
        ):
            false_negative += 1

        rows.append({
            "control":
                result["control"],

            "expected":
                expected,

            "predicted":
                predicted,

            "margin":
                margin,

            "pass":
                passed,
        })

    summary[strategy] = {
        "correct":
            correct,

        "total":
            len(results),

        "false_positive":
            false_positive,

        "false_negative":
            false_negative,

        "rows":
            rows,
    }

    print()
    print(strategy)
    print(
        "  CORRECT       :",
        correct,
        "/",
        len(results),
    )
    print(
        "  FALSE POSITIVE:",
        false_positive,
    )
    print(
        "  FALSE NEGATIVE:",
        false_negative,
    )

    for row in rows:

        print(
            f"    {row['control']:<26} "
            f"{row['margin']:+.6f} "
            f"{row['predicted']:<9} "
            + (
                "PASS"
                if row["pass"]
                else "FAIL"
            )
        )

# =============================================================================
# FINAL REPORT
# =============================================================================

best_strategy = max(
    strategies,
    key=lambda s: (
        summary[s]["correct"],
        -summary[s]["false_positive"],
        -summary[s]["false_negative"],
    ),
)

final = {
    "schema":
        "atlas_zero.film10.clip_scoring_strategy_audit.v4.3",

    "project_id":
        PROJECT_ID,

    "context_source":
        context.source_path,

    "positive_prompt_count":
        len(positive_prompts),

    "negative_prompt_count":
        len(negative_prompts),

    "strategies":
        summary,

    "best_zero_margin_strategy":
        best_strategy,

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
        final,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("=" * 120)
print("BEST ZERO-MARGIN STRATEGY")
print("=" * 120)

print(best_strategy)

print()
print("=" * 120)
print("REPORT")
print("=" * 120)

print(REPORT)

print()
print("=" * 120)
print("SCORING STRATEGY AUDIT V4.3: COMPLETE")
print("=" * 120)
print("No production source patched.")
print("No canonical DB writes.")
print("No assignments.")
print("No render.")
print("No paid API calls.")
