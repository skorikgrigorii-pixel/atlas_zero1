from __future__ import annotations

from pathlib import Path
import ast
import inspect
import json
import py_compile
import re
import shutil
import sqlite3
import sys
from datetime import datetime

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

TARGET = (
    ROOT
    / "src"
    / "az_enterprise"
    / "core"
    / "project_semantic_context_rc2.py"
)

DB_PATH = (
    ROOT
    / "workspace"
    / "atlas_zero_enterprise.sqlite3"
)

OUT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "semantic_context_v3"
)

OUT.mkdir(parents=True, exist_ok=True)

print("=" * 120)
print("ATLAS ZERO — PROJECT SEMANTIC TOPIC COVERAGE PATCH V3")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("TARGET     :", TARGET)
print("DATABASE   :", DB_PATH)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("CLIP RUN   : NO")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

if not TARGET.is_file():
    raise FileNotFoundError(TARGET)

if not DB_PATH.is_file():
    raise FileNotFoundError(DB_PATH)

sys.path.insert(0, str(ROOT / "src"))

# =============================================================================
# PRE-PATCH INTROSPECTION
# =============================================================================

from az_enterprise.core.project_semantic_context_rc2 import (
    ProjectSemanticContextBuilderRC2,
)

before = ProjectSemanticContextBuilderRC2(
    project_id=PROJECT_ID,
    root_dir=ROOT,
).build()

print()
print("=" * 120)
print("BEFORE")
print("=" * 120)

print("SOURCE       :", before.source_path)
print("EVENT LABELS :", len(before.event_labels))
print("CONCEPTS     :", len(before.concepts))

print()
print("TOPIC LABELS:")

for label, prompts in before.topic_labels.items():
    print()
    print(label)
    for p in prompts:
        print("  -", p)

# =============================================================================
# READ CURRENT SOURCE AND LOCATE _build_topic_labels
# =============================================================================

source = TARGET.read_text(
    encoding="utf-8-sig",
    errors="strict",
)

tree = ast.parse(source)

class_node = None
method_node = None

for node in tree.body:
    if (
        isinstance(node, ast.ClassDef)
        and node.name == "ProjectSemanticContextBuilderRC2"
    ):
        class_node = node
        break

if class_node is None:
    raise RuntimeError(
        "ProjectSemanticContextBuilderRC2 class not found."
    )

for node in class_node.body:
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_build_topic_labels"
    ):
        method_node = node
        break

if method_node is None:
    raise RuntimeError(
        "_build_topic_labels method not found."
    )

lines = source.splitlines(keepends=True)

start_line = method_node.lineno - 1
end_line = method_node.end_lineno

old_method = "".join(
    lines[start_line:end_line]
)

print()
print("=" * 120)
print("CURRENT _build_topic_labels")
print("=" * 120)
print(old_method)

# =============================================================================
# BACKUP
# =============================================================================

BACKUP = TARGET.with_name(
    TARGET.name + ".bak_topic_coverage_v3"
)

if not BACKUP.exists():
    shutil.copy2(TARGET, BACKUP)
    print("BACKUP CREATED:", BACKUP)
else:
    print("BACKUP EXISTS :", BACKUP)

# =============================================================================
# DETERMINE CURRENT SIGNATURE
# =============================================================================

signature_match = re.search(
    r"(?m)^    def _build_topic_labels\((.*?)^\s{4}\)",
    old_method,
    flags=re.S,
)

# We don't depend on regex result for patching, but print AST args
arg_names = [
    arg.arg
    for arg in method_node.args.args
]

print()
print("METHOD ARGS:", arg_names)

# Existing call site may pass concepts only, or concepts + title.
# We preserve compatibility by replacing method with a flexible implementation.
#
# IMPORTANT:
# - no Film10 vocabulary is hardcoded here
# - vocabulary comes from canonical context data
# - concepts remain useful
# - full canonical scene narrative is used to prevent first-N truncation
# - topic prompt length is bounded so CLIP is not fed the entire script

new_method = '''    def _build_topic_labels(
        self,
        concepts,
        *args,
        **kwargs,
    ):
        """
        Build project-level relevance labels from the complete semantic context.

        Architecture:
        - project-independent;
        - no film-specific vocabulary;
        - concepts are used as a compact semantic seed;
        - canonical story-scene narrative expands project coverage;
        - generic OFF_TOPIC prompts remain generic negatives.

        This prevents project relevance from being determined only by the
        first N extracted concepts.
        """

        clean_concepts = []

        for value in concepts or ():
            text = str(value or "").strip()

            if not text:
                continue

            if text.lower() in {
                item.lower()
                for item in clean_concepts
            }:
                continue

            clean_concepts.append(text)

        # ------------------------------------------------------------------
        # Recover full canonical story vocabulary when available.
        #
        # This is deliberately generic. The builder already knows project_id
        # and root_dir; no project-specific terms are embedded in core code.
        # ------------------------------------------------------------------

        canonical_text = ""

        try:
            root = Path(self.root_dir).resolve()

            db_candidates = (
                root / "workspace" / "atlas_zero_enterprise.sqlite3",
                root / "atlas_zero_enterprise.sqlite3",
            )

            db_path = next(
                (
                    candidate
                    for candidate in db_candidates
                    if candidate.is_file()
                ),
                None,
            )

            if db_path is not None:
                conn = sqlite3.connect(str(db_path))

                try:
                    rows = conn.execute(
                        """
                        SELECT
                            narrative_goal,
                            visual_strategy
                        FROM story_scenes
                        WHERE project_id=?
                        ORDER BY idx
                        """,
                        (self.project_id,),
                    ).fetchall()
                finally:
                    conn.close()

                parts = []

                for row in rows:
                    for value in row:
                        text = str(value or "").strip()
                        if text:
                            parts.append(text)

                canonical_text = " ".join(parts)

        except Exception:
            canonical_text = ""

        # ------------------------------------------------------------------
        # Extract additional recurring / distinctive terms from complete
        # canonical story text using the builder's existing concept extractor.
        # ------------------------------------------------------------------

        expanded = list(clean_concepts)

        if canonical_text:
            try:
                extra = self._extract_concepts(canonical_text)
            except Exception:
                extra = ()

            for value in extra or ():
                text = str(value or "").strip()

                if not text:
                    continue

                if text.lower() in {
                    item.lower()
                    for item in expanded
                }:
                    continue

                expanded.append(text)

        # ------------------------------------------------------------------
        # Also preserve capitalized/proper-name and domain-bearing phrases
        # from canonical narrative. This complements frequency extraction:
        # important one-off entities must not disappear merely because they
        # occur in only one scene.
        # ------------------------------------------------------------------

        if canonical_text:
            tokens = re.findall(
                r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\\-–—']+",
                canonical_text,
            )

            stop = {
                "блок", "финал", "final", "block",
                "это", "этот", "эта", "эти",
                "его", "ее", "её", "их",
                "для", "как", "что", "когда",
                "где", "здесь", "там",
                "после", "перед", "через",
                "между", "который", "которая",
                "которые", "может", "могут",
                "было", "были", "была",
                "будет", "есть",
                "один", "одна", "одно",
                "несколько", "много",
                "очень", "уже", "ещё", "еще",
            }

            # Unigrams that look like proper/domain entities.
            for token in tokens:
                low = token.lower()

                if low in stop:
                    continue

                if len(token) < 4:
                    continue

                looks_distinctive = (
                    token.isupper()
                    or token[:1].isupper()
                    or any(ch.isdigit() for ch in token)
                )

                if not looks_distinctive:
                    continue

                if low not in {
                    item.lower()
                    for item in expanded
                }:
                    expanded.append(token)

            # Distinctive two-word phrases.
            for a, b in zip(tokens, tokens[1:]):
                phrase = f"{a} {b}".strip()
                low = phrase.lower()

                if (
                    len(a) >= 4
                    and len(b) >= 4
                    and (
                        a[:1].isupper()
                        or b[:1].isupper()
                        or a.isupper()
                        or b.isupper()
                    )
                    and low not in {
                        item.lower()
                        for item in expanded
                    }
                ):
                    expanded.append(phrase)

        # ------------------------------------------------------------------
        # Bound prompt size while retaining much broader project coverage
        # than the previous first-15-concepts implementation.
        # ------------------------------------------------------------------

        semantic_terms = expanded[:64]

        if semantic_terms:
            semantic_summary = ", ".join(semantic_terms)
        else:
            semantic_summary = "the approved documentary subject"

        title = getattr(
            self,
            "project_title",
            None,
        )

        if not title:
            title = getattr(
                self,
                "title",
                None,
            )

        if not title:
            title = str(self.project_id)

        return {
            "relevant": (
                f"visual material directly connected to the documentary project {title}",
                f"documentary evidence depicting {semantic_summary}",
                f"scientific geographic archival satellite news or field material connected to {semantic_summary}",
            ),
            "off_topic": (
                f"visual material unrelated to the documentary project {title}",
                "private everyday family household personal lifestyle or unrelated entertainment media",
                "an unrelated subject with no factual geographic scientific historical or event connection to the current documentary",
            ),
        }
'''

# =============================================================================
# Ensure imports required by generic implementation exist
# =============================================================================

required_imports = [
    "from pathlib import Path",
    "import sqlite3",
    "import re",
]

for required in required_imports:
    if required in source:
        continue

    src_lines = source.splitlines()

    insert_at = 0

    for i, line in enumerate(src_lines):
        if line.startswith("from __future__ import"):
            insert_at = i + 1

    if insert_at == 0:
        for i, line in enumerate(src_lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = i
                break

    src_lines.insert(insert_at, required)

    source = "\n".join(src_lines) + "\n"

    # Reparse because line numbers changed.
    tree = ast.parse(source)

    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "ProjectSemanticContextBuilderRC2"
        ):
            class_node = node
            break

    for node in class_node.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_build_topic_labels"
        ):
            method_node = node
            break

    lines = source.splitlines(keepends=True)
    start_line = method_node.lineno - 1
    end_line = method_node.end_lineno

# =============================================================================
# Replace exactly existing method
# =============================================================================

lines = source.splitlines(keepends=True)

replacement_lines = [
    line + "\n"
    for line in new_method.rstrip("\n").split("\n")
]

patched_lines = (
    lines[:start_line]
    + replacement_lines
    + lines[end_line:]
)

patched = "".join(patched_lines)

if patched == source:
    raise RuntimeError(
        "Patch produced no source change."
    )

TARGET.write_text(
    patched,
    encoding="utf-8",
)

print()
print("=" * 120)
print("PATCH")
print("=" * 120)
print("WRITTEN:", TARGET)

# =============================================================================
# COMPILE
# =============================================================================

print()
print("=" * 120)
print("PY_COMPILE")
print("=" * 120)

py_compile.compile(
    str(TARGET),
    doraise=True,
)

print("PASS")

# =============================================================================
# FORCE CLEAN MODULE RELOAD
# =============================================================================

module_name = (
    "az_enterprise.core.project_semantic_context_rc2"
)

for key in list(sys.modules):
    if key == module_name:
        del sys.modules[key]

from az_enterprise.core.project_semantic_context_rc2 import (
    ProjectSemanticContextBuilderRC2 as BuilderV3,
)

after = BuilderV3(
    project_id=PROJECT_ID,
    root_dir=ROOT,
).build()

# =============================================================================
# AFTER
# =============================================================================

print()
print("=" * 120)
print("AFTER")
print("=" * 120)

print("SOURCE       :", after.source_path)
print("EVENT LABELS :", len(after.event_labels))
print("CONCEPTS     :", len(after.concepts))

print()
print("TOPIC LABELS:")

for label, prompts in after.topic_labels.items():
    print()
    print(label)

    for p in prompts:
        print("  -", p)

# =============================================================================
# PROJECT-INDEPENDENCE CHECK
# =============================================================================

core_source = TARGET.read_text(
    encoding="utf-8",
    errors="replace",
).lower()

film_specific_forbidden = (
    "langtang",
    "лангтанг",
    "gyirong",
    "гьиронг",
    "trishuli",
    "тришули",
    "nepal",
    "непал",
    "hydropower",
    "гидроэлект",
    "rasuwa",
    "расува",
)

# Search only the new method, not historical comments/data elsewhere.
new_method_lower = new_method.lower()

hardcoded_hits = [
    term
    for term in film_specific_forbidden
    if term in new_method_lower
]

# =============================================================================
# FILM10 TEST GATES
# These terms are TESTS only. They are not embedded in production method.
# =============================================================================

topic_text = " ".join(
    str(prompt)
    for prompts in after.topic_labels.values()
    for prompt in prompts
).lower()

strategic_groups = {
    "LANGTANG": (
        "лангтанг",
        "langtang",
    ),
    "GYIRONG": (
        "гьиронг",
        "гиронг",
        "gyirong",
        "kyirong",
    ),
    "TRISHULI": (
        "тришули",
        "trishuli",
    ),
    "NEPAL": (
        "непал",
        "nepal",
    ),
    "USGS": (
        "usgs",
    ),
    "GLACIER": (
        "ледник",
        "ледника",
        "glacier",
    ),
    "SLOPE_COLLAPSE": (
        "разрушение склона",
        "обрушение склона",
        "склон",
        "slope",
    ),
    "FLOOD": (
        "наводнение",
        "паводок",
        "поток",
        "flood",
    ),
    "SATELLITE": (
        "спутник",
        "спутников",
        "satellite",
        "sentinel",
        "landsat",
    ),
    "SCHOOL": (
        "школа",
        "школы",
        "school",
        "tribhuvan",
    ),
    "HYDROPOWER": (
        "гидроэлект",
        "гэс",
        "hydropower",
        "hydroelectric",
    ),
}

coverage = {}

print()
print("=" * 120)
print("STRATEGIC COVERAGE")
print("=" * 120)

for name, variants in strategic_groups.items():
    hits = [
        variant
        for variant in variants
        if variant in topic_text
    ]

    coverage[name] = bool(hits)

    print(
        f"{name:<20}: "
        + ("PASS" if hits else "FAIL")
        + (
            " | " + ", ".join(hits)
            if hits
            else ""
        )
    )

coverage_count = sum(
    1
    for value in coverage.values()
    if value
)

print()
print(
    "COVERAGE:",
    coverage_count,
    "/",
    len(coverage),
)

# =============================================================================
# ARCHITECTURAL GATES
# =============================================================================

checks = {
    "SOURCE_CANONICAL_DB":
        after.source_path == "canonical_db:story_scenes",

    "EVENT_LABELS_89":
        len(after.event_labels) == 89,

    "SCENE_LABELS_86":
        len([
            key
            for key in after.event_labels
            if str(key).startswith("scene_")
        ]) == 86,

    "TOPIC_RELEVANT_PRESENT":
        "relevant" in after.topic_labels,

    "TOPIC_OFF_TOPIC_PRESENT":
        "off_topic" in after.topic_labels,

    "NO_FILM10_HARDCODE_IN_METHOD":
        len(hardcoded_hits) == 0,

    "STRATEGIC_COVERAGE_11_OF_11":
        coverage_count == len(coverage),

    "LIVE_API_OFF":
        True,

    "PAID_CALLS_OFF":
        True,
}

print()
print("=" * 120)
print("QUALITY GATES")
print("=" * 120)

for name, passed in checks.items():
    print(
        f"{name:<42}: "
        + ("PASS" if passed else "FAIL")
    )

if hardcoded_hits:
    print()
    print(
        "FORBIDDEN HARDCODE HITS:",
        hardcoded_hits,
    )

# =============================================================================
# REPORT
# =============================================================================

report = {
    "schema":
        "atlas_zero.project_semantic_topic_coverage.v3",

    "project_id":
        PROJECT_ID,

    "source_path":
        after.source_path,

    "event_labels":
        len(after.event_labels),

    "scene_labels":
        len([
            key
            for key in after.event_labels
            if str(key).startswith("scene_")
        ]),

    "concepts":
        list(after.concepts),

    "topic_labels":
        {
            key: list(value)
            for key, value
            in after.topic_labels.items()
        },

    "strategic_coverage":
        coverage,

    "strategic_coverage_count":
        coverage_count,

    "gates":
        checks,

    "clip_run":
        False,

    "db_writes":
        False,

    "assignments_written":
        False,

    "render_performed":
        False,

    "live_api":
        False,

    "paid_calls":
        False,
}

REPORT = (
    OUT
    / "FILM10_PROJECT_SEMANTIC_TOPIC_COVERAGE_V3.json"
)

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

if all(checks.values()):
    print("SEMANTIC TOPIC COVERAGE V3: PASS")
    print()
    print(
        "NEXT SAFE STEP:"
    )
    print(
        "Targeted CLIP validation only — "
        "known relevant controls + known unrelated insect asset."
    )
else:
    print("SEMANTIC TOPIC COVERAGE V3: FAIL")
    print()
    print(
        "Do NOT run CLIP reanalysis."
    )

print("=" * 120)

print()
print("No asset analysis performed.")
print("No DB writes performed.")
print("No assignments written.")
print("No render performed.")
print("No paid API calls.")
