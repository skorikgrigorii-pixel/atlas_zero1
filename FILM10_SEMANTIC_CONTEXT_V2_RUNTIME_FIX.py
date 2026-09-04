from pathlib import Path
import py_compile
import sys

ROOT = Path.cwd().resolve()

TARGET = (
    ROOT
    / "src"
    / "az_enterprise"
    / "core"
    / "project_semantic_context_rc2.py"
)

QUALITY_SCRIPT = (
    ROOT
    / "FILM10_PROJECT_SEMANTIC_CONTEXT_QUALITY_PATCH_V2.py"
)

print("=" * 120)
print("ATLAS ZERO — SEMANTIC CONTEXT V2 RUNTIME FIX")
print("=" * 120)
print("TARGET :", TARGET)
print("LIVE API   : 0")
print("PAID CALLS : 0")

if not TARGET.is_file():
    raise FileNotFoundError(TARGET)

if not QUALITY_SCRIPT.is_file():
    raise FileNotFoundError(QUALITY_SCRIPT)

source = TARGET.read_text(
    encoding="utf-8-sig",
    errors="strict",
)

# ============================================================================
# FIX MISSING Counter IMPORT
# ============================================================================

required_import = "from collections import Counter"

if required_import in source:
    print()
    print("Counter import already present.")

else:
    lines = source.splitlines()

    insert_at = 0

    # Keep imports together. Insert after __future__ import if present,
    # otherwise before the first normal import block.
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import"):
            insert_at = i + 1

    if insert_at == 0:
        for i, line in enumerate(lines):
            if (
                line.startswith("import ")
                or line.startswith("from ")
            ):
                insert_at = i
                break

    lines.insert(
        insert_at,
        required_import,
    )

    source = "\n".join(lines) + "\n"

    TARGET.write_text(
        source,
        encoding="utf-8",
    )

    print()
    print("ADDED:", required_import)

# ============================================================================
# VERIFY SOURCE
# ============================================================================

verify = TARGET.read_text(
    encoding="utf-8-sig",
    errors="strict",
)

if required_import not in verify:
    raise RuntimeError(
        "Counter import was not persisted."
    )

if "Counter()" not in verify:
    raise RuntimeError(
        "V2 extractor using Counter() is not present."
    )

print()
print("=" * 120)
print("PY_COMPILE")
print("=" * 120)

py_compile.compile(
    str(TARGET),
    doraise=True,
)

print("PASS")

print()
print("=" * 120)
print("RUNTIME IMPORT TEST")
print("=" * 120)

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from az_enterprise.core.project_semantic_context_rc2 import (
    ProjectSemanticContextBuilderRC2,
)

context = ProjectSemanticContextBuilderRC2(
    project_id="film_10_nepal_tibet_aftershock",
    root_dir=ROOT,
).build()

print("SOURCE PATH  :", context.source_path)
print("EVENT LABELS :", len(context.event_labels))
print("CONCEPTS     :", len(context.concepts))

if context.source_path != "canonical_db:story_scenes":
    raise RuntimeError(
        "Canonical semantic context was lost."
    )

if len(context.event_labels) < 80:
    raise RuntimeError(
        "Semantic context unexpectedly collapsed."
    )

print("RUNTIME TEST : PASS")

print()
print("=" * 120)
print("FIX RESULT: PASS")
print("=" * 120)

print()
print(
    "Now rerunning existing "
    "FILM10_PROJECT_SEMANTIC_CONTEXT_QUALITY_PATCH_V2.py"
)
