from __future__ import annotations

from pathlib import Path
import dataclasses
import inspect
import json
import sys

ROOT = Path.cwd().resolve()

sys.path.insert(
    0,
    str(ROOT / "src"),
)

print("=" * 120)
print("ATLAS ZERO — SEMANTIC PREDICTION RUNTIME CONTRACT AUDIT V4.1")
print("=" * 120)
print("ROOT       :", ROOT)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("CLIP RUN   : NO")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

import az_enterprise.core.visual_semantic_analyzer_rc2 as mod

Analyzer = mod.VisualSemanticAnalyzerRC2

print()
print("=" * 120)
print("MODULE")
print("=" * 120)
print("FILE:", inspect.getsourcefile(mod))

# =============================================================================
# FIND SemanticPredictionRC2
# =============================================================================

Prediction = getattr(
    mod,
    "SemanticPredictionRC2",
    None,
)

if Prediction is None:

    # Search imported/global classes in the module.
    for name, value in vars(mod).items():

        if (
            inspect.isclass(value)
            and name == "SemanticPredictionRC2"
        ):
            Prediction = value
            break

if Prediction is None:
    raise RuntimeError(
        "SemanticPredictionRC2 was not found in "
        "visual_semantic_analyzer_rc2 module globals."
    )

print()
print("=" * 120)
print("SemanticPredictionRC2")
print("=" * 120)

print("CLASS      :", Prediction)
print("MODULE     :", Prediction.__module__)
print(
    "SOURCE FILE:",
    inspect.getsourcefile(Prediction),
)

print(
    "SIGNATURE  :",
    inspect.signature(Prediction),
)

print(
    "DATACLASS  :",
    dataclasses.is_dataclass(Prediction),
)

annotations = getattr(
    Prediction,
    "__annotations__",
    {},
)

print()
print("ANNOTATIONS:")

if annotations:
    for key, value in annotations.items():
        print(
            f"  {key:<24}: {value}"
        )
else:
    print("  NONE")

if dataclasses.is_dataclass(Prediction):

    print()
    print("DATACLASS FIELDS:")

    for field in dataclasses.fields(
        Prediction
    ):
        print(
            f"  {field.name:<24} "
            f"type={field.type} "
            f"default={field.default!r}"
        )

print()
print("CLASS SOURCE:")

try:
    print(
        inspect.getsource(
            Prediction
        )
    )
except Exception as exc:
    print(
        "SOURCE UNAVAILABLE:",
        type(exc).__name__,
        str(exc),
    )

# =============================================================================
# BACKEND CLASS
# =============================================================================

Backend = getattr(
    mod,
    "HuggingFaceClipBackendRC2",
    None,
)

if Backend is None:

    for name, value in vars(mod).items():

        if (
            inspect.isclass(value)
            and "HuggingFaceClipBackendRC2"
            in name
        ):
            Backend = value
            break

if Backend is None:
    raise RuntimeError(
        "HuggingFaceClipBackendRC2 not found."
    )

print()
print("=" * 120)
print("HuggingFaceClipBackendRC2")
print("=" * 120)

print(
    "CLASS     :",
    Backend,
)

print(
    "SIGNATURE :",
    inspect.signature(Backend),
)

print()
print("CLASSIFY SIGNATURE:")

print(
    inspect.signature(
        Backend.classify
    )
)

print()
print("CLASSIFY SOURCE:")

try:
    print(
        inspect.getsource(
            Backend.classify
        )
    )
except Exception as exc:
    print(
        "SOURCE UNAVAILABLE:",
        type(exc).__name__,
        str(exc),
    )

# =============================================================================
# ANALYZER RELEVANCE PATH
# =============================================================================

print()
print("=" * 120)
print("VisualSemanticAnalyzerRC2 RELEVANCE PATH")
print("=" * 120)

methods = (
    "_analyze_asset",
    "_relevance_status",
    "_story_value",
)

method_sources = {}

for name in methods:

    print()
    print("-" * 120)
    print(name)
    print("-" * 120)

    method = getattr(
        Analyzer,
        name,
        None,
    )

    if method is None:
        print("NOT FOUND")
        continue

    print(
        "SIGNATURE:",
        inspect.signature(method),
    )

    try:
        src = inspect.getsource(
            method
        )

        method_sources[name] = src

        print(src)

    except Exception as exc:

        print(
            "SOURCE UNAVAILABLE:",
            type(exc).__name__,
            str(exc),
        )

# =============================================================================
# LOOK FOR SemanticPredictionRC2 CONSUMERS
# =============================================================================

print()
print("=" * 120)
print("PREDICTION ATTRIBUTE ACCESS IN MODULE")
print("=" * 120)

module_source = inspect.getsource(
    mod
)

interesting = []

for i, line in enumerate(
    module_source.splitlines(),
    1,
):

    low = line.lower()

    if (
        "event_pred" in low
        or "topic_pred" in low
        or "time_pred" in low
        or ".scores" in low
        or ".label" in low
        or ".confidence" in low
        or "semanticpredictionrc2" in low
    ):
        interesting.append(
            {
                "line": i,
                "text": line,
            }
        )

for item in interesting:

    print(
        f"{item['line']:>5}: "
        f"{item['text']}"
    )

# =============================================================================
# REPORT
# =============================================================================

OUT = (
    ROOT
    / "workspace"
    / "projects"
    / "film_10_nepal_tibet_aftershock"
    / "00_Production"
    / "semantic_validation_v4"
)

OUT.mkdir(
    parents=True,
    exist_ok=True,
)

REPORT = (
    OUT
    / "FILM10_SEMANTIC_PREDICTION_RUNTIME_CONTRACT_V4_1.json"
)

report = {
    "schema":
        "atlas_zero.semantic_prediction_runtime_contract.v4.1",

    "prediction_class":
        str(Prediction),

    "prediction_module":
        Prediction.__module__,

    "prediction_signature":
        str(inspect.signature(Prediction)),

    "prediction_annotations": {
        str(k): str(v)
        for k, v in annotations.items()
    },

    "is_dataclass":
        dataclasses.is_dataclass(Prediction),

    "backend_class":
        str(Backend),

    "backend_signature":
        str(inspect.signature(Backend)),

    "classify_signature":
        str(
            inspect.signature(
                Backend.classify
            )
        ),

    "analyzer_methods": {
        name: (
            str(
                inspect.signature(
                    getattr(
                        Analyzer,
                        name,
                    )
                )
            )
            if hasattr(
                Analyzer,
                name,
            )
            else None
        )
        for name in methods
    },

    "prediction_attribute_access":
        interesting,

    "clip_run":
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
}

REPORT.write_text(
    json.dumps(
        report,
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
print("RUNTIME CONTRACT AUDIT: COMPLETE")
print("=" * 120)
print("No CLIP inference performed.")
print("No DB writes performed.")
print("No assignments written.")
print("No render performed.")
print("No paid API calls.")
