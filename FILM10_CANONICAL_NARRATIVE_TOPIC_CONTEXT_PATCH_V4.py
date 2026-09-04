from __future__ import annotations

from pathlib import Path
import ast
import importlib
import json
import py_compile
import re
import shutil
import sys

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

TARGET = (
    ROOT
    / "src"
    / "az_enterprise"
    / "core"
    / "project_semantic_context_rc2.py"
)

OUT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "semantic_context_v4"
)

OUT.mkdir(parents=True, exist_ok=True)

print("=" * 120)
print("ATLAS ZERO — CANONICAL NARRATIVE TOPIC CONTEXT PATCH V4")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("TARGET     :", TARGET)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("CLIP RUN   : NO")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")

if not TARGET.is_file():
    raise FileNotFoundError(TARGET)

sys.path.insert(0, str(ROOT / "src"))

# =============================================================================
# CURRENT CONTEXT
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

for label, prompts in before.topic_labels.items():
    print()
    print(label, "PROMPTS:", len(prompts))

    for p in list(prompts)[:8]:
        print("  -", p[:250])

    if len(prompts) > 8:
        print("  ...")

# =============================================================================
# LOCATE CURRENT METHOD
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
        "ProjectSemanticContextBuilderRC2 not found."
    )

for node in class_node.body:
    if (
        isinstance(node, ast.FunctionDef)
        and node.name == "_build_topic_labels"
    ):
        method_node = node
        break

if method_node is None:
    raise RuntimeError(
        "_build_topic_labels not found."
    )

lines = source.splitlines(keepends=True)

start = method_node.lineno - 1
end = method_node.end_lineno

old_method = "".join(lines[start:end])

print()
print("=" * 120)
print("CURRENT METHOD")
print("=" * 120)
print(old_method)

# =============================================================================
# BACKUP
# =============================================================================

BACKUP = TARGET.with_name(
    TARGET.name + ".bak_narrative_topic_v4"
)

if not BACKUP.exists():
    shutil.copy2(
        TARGET,
        BACKUP,
    )
    print("BACKUP CREATED:", BACKUP)
else:
    print("BACKUP EXISTS :", BACKUP)

# =============================================================================
# V4 METHOD
#
# IMPORTANT ARCHITECTURE:
#
#   semantic source = canonical story_scenes.narrative_goal
#
# visual_strategy is deliberately excluded.
# required_assets is deliberately excluded.
# emotional_goal is deliberately excluded.
#
# One huge project prompt is NOT used.
# Each narrative scene produces a short semantic prompt.
#
# No Film10 / Nepal vocabulary exists in this implementation.
# =============================================================================

new_method = r'''    def _build_topic_labels(
        self,
        *,
        concepts: list[str],
        title: str,
    ) -> dict[str, tuple[str, ...]]:
        """
        Build project relevance from canonical narrative semantics.

        The canonical narrative_goal is the semantic source of truth.

        Project-level relevance is represented by multiple short prompts
        instead of one oversized prompt. This is important for CLIP-style
        text encoders with bounded context length.

        Production/editorial directives are not semantic evidence.
        visual_strategy, required_assets and emotional_goal are therefore
        deliberately excluded here.

        No project-specific vocabulary is hardcoded.
        """

        root = Path(self.root_dir).resolve()

        db_candidates = (
            root
            / "workspace"
            / "atlas_zero_enterprise.sqlite3",

            root
            / "atlas_zero_enterprise.sqlite3",
        )

        db_path = next(
            (
                candidate
                for candidate in db_candidates
                if candidate.is_file()
            ),
            None,
        )

        narrative_goals: list[str] = []

        if db_path is not None:
            try:
                conn = sqlite3.connect(
                    str(db_path)
                )

                try:
                    rows = conn.execute(
                        """
                        SELECT narrative_goal
                        FROM story_scenes
                        WHERE project_id=?
                        ORDER BY idx
                        """,
                        (self.project_id,),
                    ).fetchall()

                finally:
                    conn.close()

                narrative_goals = [
                    str(row[0] or "").strip()
                    for row in rows
                    if str(row[0] or "").strip()
                ]

            except Exception:
                narrative_goals = []

        # --------------------------------------------------------------
        # Generic production-marker cleanup.
        #
        # These are structural/editorial markers, not film vocabulary.
        # --------------------------------------------------------------

        def clean_narrative(value: str) -> str:
            text = str(value or "")

            text = re.sub(
                r"\bБЛОК\s+\d+\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bBLOCK\s+\d+\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bOPENING\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bSHOCK\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bHOOK\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bФИНАЛ\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bFINAL\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\s+",
                " ",
                text,
            ).strip()

            return text

        cleaned_goals = [
            clean_narrative(goal)
            for goal in narrative_goals
        ]

        cleaned_goals = [
            goal
            for goal in cleaned_goals
            if goal
        ]

        # --------------------------------------------------------------
        # Generate compact scene-level semantic prompts.
        #
        # _extract_concepts already contains the OS-level language/noise
        # filtering logic. Running it per scene prevents late-film themes
        # from disappearing behind globally frequent early-film terms.
        # --------------------------------------------------------------

        relevant_prompts: list[str] = [
            (
                "visual material directly connected to the "
                f"documentary {title}"
            ),
        ]

        seen: set[str] = {
            relevant_prompts[0].lower()
        }

        for goal in cleaned_goals:

            local_concepts: list[str] = []

            try:
                extracted = self._extract_concepts(
                    goal
                )
            except Exception:
                extracted = ()

            for value in extracted or ():
                item = str(value or "").strip()

                if not item:
                    continue

                low = item.lower()

                if low in {
                    existing.lower()
                    for existing
                    in local_concepts
                }:
                    continue

                local_concepts.append(item)

            # Keep every CLIP prompt deliberately short.
            if local_concepts:
                concept_text = ", ".join(
                    local_concepts[:8]
                )

                prompt = (
                    "documentary visual evidence showing "
                    + concept_text
                )

                key = prompt.lower()

                if key not in seen:
                    seen.add(key)
                    relevant_prompts.append(
                        prompt
                    )

            # ----------------------------------------------------------
            # Add a short direct narrative fragment as complementary
            # evidence. Limit length so later scenes do not become one
            # oversized CLIP prompt.
            # ----------------------------------------------------------

            sentences = [
                part.strip()
                for part in re.split(
                    r"(?<=[.!?])\s+",
                    goal,
                )
                if part.strip()
            ]

            if sentences:
                direct = sentences[0]

                if len(direct) > 220:
                    direct = direct[:220].rsplit(
                        " ",
                        1,
                    )[0]

                if direct:
                    prompt = (
                        "documentary scene depicting "
                        + direct
                    )

                    key = prompt.lower()

                    if key not in seen:
                        seen.add(key)
                        relevant_prompts.append(
                            prompt
                        )

        # --------------------------------------------------------------
        # Safety fallback for projects without canonical scenes.
        # Still project-independent.
        # --------------------------------------------------------------

        if len(relevant_prompts) == 1:

            compact = [
                str(value or "").strip()
                for value in concepts or ()
                if str(value or "").strip()
            ]

            if compact:
                relevant_prompts.append(
                    "documentary visual evidence showing "
                    + ", ".join(
                        compact[:12]
                    )
                )

        off_topic_prompts = (
            (
                "visual material unrelated to the "
                f"documentary {title}"
            ),
            (
                "private everyday family household "
                "personal lifestyle or unrelated "
                "entertainment media"
            ),
            (
                "an unrelated subject with no factual "
                "geographic scientific historical or "
                "event connection to the current documentary"
            ),
        )

        return {
            "relevant":
                tuple(relevant_prompts),

            "off_topic":
                tuple(off_topic_prompts),
        }
'''

# =============================================================================
# REQUIRED IMPORTS
# =============================================================================

required_imports = (
    "from pathlib import Path",
    "import sqlite3",
    "import re",
)

for required in required_imports:

    if required in source:
        continue

    current_lines = source.splitlines()

    insert_at = 0

    for i, line in enumerate(current_lines):
        if line.startswith(
            "from __future__ import"
        ):
            insert_at = i + 1

    if insert_at == 0:
        for i, line in enumerate(
            current_lines
        ):
            if (
                line.startswith("import ")
                or line.startswith("from ")
            ):
                insert_at = i
                break

    current_lines.insert(
        insert_at,
        required,
    )

    source = (
        "\n".join(current_lines)
        + "\n"
    )

# Reparse after potential imports.
tree = ast.parse(source)

class_node = next(
    node
    for node in tree.body
    if (
        isinstance(node, ast.ClassDef)
        and node.name
        == "ProjectSemanticContextBuilderRC2"
    )
)

method_node = next(
    node
    for node in class_node.body
    if (
        isinstance(node, ast.FunctionDef)
        and node.name
        == "_build_topic_labels"
    )
)

lines = source.splitlines(
    keepends=True
)

start = method_node.lineno - 1
end = method_node.end_lineno

replacement = [
    line + "\n"
    for line
    in new_method.rstrip("\n").split("\n")
]

patched = "".join(
    lines[:start]
    + replacement
    + lines[end:]
)

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
print("PATCH WRITTEN")
print("=" * 120)
print(TARGET)

# =============================================================================
# COMPILE
# =============================================================================

py_compile.compile(
    str(TARGET),
    doraise=True,
)

print("PY_COMPILE: PASS")

# =============================================================================
# CLEAN RELOAD
# =============================================================================

module_name = (
    "az_enterprise.core."
    "project_semantic_context_rc2"
)

for key in list(sys.modules):
    if key == module_name:
        del sys.modules[key]

from az_enterprise.core.project_semantic_context_rc2 import (
    ProjectSemanticContextBuilderRC2
    as BuilderV4,
)

after = BuilderV4(
    project_id=PROJECT_ID,
    root_dir=ROOT,
).build()

print()
print("=" * 120)
print("AFTER")
print("=" * 120)

print("SOURCE          :", after.source_path)
print("EVENT LABELS    :", len(after.event_labels))
print("SCENE LABELS    :", len([
    key
    for key in after.event_labels
    if str(key).startswith("scene_")
]))
print("CONCEPTS        :", len(after.concepts))

relevant_prompts = tuple(
    after.topic_labels.get(
        "relevant",
        (),
    )
)

off_topic_prompts = tuple(
    after.topic_labels.get(
        "off_topic",
        (),
    )
)

print(
    "RELEVANT PROMPTS:",
    len(relevant_prompts),
)

print(
    "OFF_TOPIC PROMPTS:",
    len(off_topic_prompts),
)

print()
print("FIRST 15 RELEVANT PROMPTS:")

for i, prompt in enumerate(
    relevant_prompts[:15],
    1,
):
    print(
        f"{i:02d}. {prompt}"
    )

print()
print("LAST 15 RELEVANT PROMPTS:")

for i, prompt in enumerate(
    relevant_prompts[-15:],
    max(
        1,
        len(relevant_prompts) - 14,
    ),
):
    print(
        f"{i:02d}. {prompt}"
    )

# =============================================================================
# STRATEGIC COVERAGE — TEST ONLY
#
# Film10 vocabulary exists here only as a quality-control test.
# It is NOT part of production implementation.
# =============================================================================

topic_text = " ".join(
    relevant_prompts
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
        "наводнен",
        "павод",
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
        "школу",
        "школь",
        "school",
        "трибхуван",
        "tribhuvan",
    ),

    "HYDROPOWER": (
        "гидроэлект",
        "электростан",
        "гэс",
        "hydropower",
        "hydroelectric",
    ),
}

print()
print("=" * 120)
print("STRATEGIC COVERAGE")
print("=" * 120)

coverage = {}

for name, variants in (
    strategic_groups.items()
):

    hits = [
        variant
        for variant in variants
        if variant in topic_text
    ]

    coverage[name] = bool(hits)

    print(
        f"{name:<20}: "
        + (
            "PASS"
            if hits
            else "FAIL"
        )
        + (
            " | "
            + ", ".join(hits)
            if hits
            else ""
        )
    )

coverage_count = sum(
    coverage.values()
)

print()
print(
    "COVERAGE:",
    coverage_count,
    "/",
    len(coverage),
)

# =============================================================================
# CONTAMINATION CHECK
# =============================================================================

production_patterns = {
    "STRICT_SEMANTIC":
        r"\bstrict semantic\b",

    "EVENT_RELEVANCE":
        r"\bevent relevance\b",

    "MISSING_PREFERABLE":
        r"\bmissing preferable\b",

    "WRONG_VISUAL":
        r"\bwrong visual\b",

    "OPENING":
        r"\bopening\b",

    "SHOCK":
        r"\bshock\b",

    "HOOK":
        r"\bhook\b",
}

contamination_hits = {}

for name, pattern in (
    production_patterns.items()
):

    matches = [
        prompt
        for prompt
        in relevant_prompts
        if re.search(
            pattern,
            prompt,
            flags=re.I,
        )
    ]

    if matches:
        contamination_hits[name] = (
            matches
        )

print()
print("=" * 120)
print("PRODUCTION CONTAMINATION")
print("=" * 120)

if not contamination_hits:
    print("NONE")
else:
    for name, matches in (
        contamination_hits.items()
    ):
        print(
            name,
            ":",
            len(matches),
        )

        for prompt in matches[:5]:
            print(
                "  -",
                prompt,
            )

# =============================================================================
# PRODUCTION IMPLEMENTATION HARDCODE CHECK
# =============================================================================

method_lower = new_method.lower()

forbidden_project_terms = (
    "langtang",
    "лангтанг",
    "gyirong",
    "гьиронг",
    "trishuli",
    "тришули",
    "nepal",
    "непал",
    "usgs",
    "tribhuvan",
    "трибхуван",
    "hydropower",
)

hardcode_hits = [
    term
    for term in forbidden_project_terms
    if term in method_lower
]

# =============================================================================
# GATES
# =============================================================================

checks = {
    "SOURCE_CANONICAL_DB":
        after.source_path
        == "canonical_db:story_scenes",

    "EVENT_LABELS_89":
        len(after.event_labels)
        == 89,

    "SCENE_LABELS_86":
        len([
            key
            for key in after.event_labels
            if str(key).startswith(
                "scene_"
            )
        ])
        == 86,

    "MULTI_PROMPT_RELEVANCE":
        len(relevant_prompts)
        >= 40,

    "OFF_TOPIC_PROMPTS_PRESENT":
        len(off_topic_prompts)
        >= 3,

    "STRATEGIC_COVERAGE_11_OF_11":
        coverage_count
        == len(coverage),

    "NO_PRODUCTION_CONTAMINATION":
        not contamination_hits,

    "NO_FILM10_HARDCODE":
        not hardcode_hits,

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
        + (
            "PASS"
            if passed
            else "FAIL"
        )
    )

if hardcode_hits:
    print()
    print(
        "HARDCODE HITS:",
        hardcode_hits,
    )

# =============================================================================
# REPORT
# =============================================================================

REPORT = (
    OUT
    / "FILM10_CANONICAL_NARRATIVE_TOPIC_CONTEXT_V4.json"
)

report = {
    "schema":
        "atlas_zero.semantic_topic_context.v4",

    "project_id":
        PROJECT_ID,

    "source_path":
        after.source_path,

    "event_label_count":
        len(after.event_labels),

    "scene_label_count":
        len([
            key
            for key in after.event_labels
            if str(key).startswith(
                "scene_"
            )
        ]),

    "relevant_prompt_count":
        len(relevant_prompts),

    "off_topic_prompt_count":
        len(off_topic_prompts),

    "relevant_prompts":
        list(relevant_prompts),

    "off_topic_prompts":
        list(off_topic_prompts),

    "strategic_coverage":
        coverage,

    "strategic_coverage_count":
        coverage_count,

    "production_contamination":
        contamination_hits,

    "production_hardcode_hits":
        hardcode_hits,

    "gates":
        checks,

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

if all(checks.values()):

    print(
        "CANONICAL NARRATIVE "
        "TOPIC CONTEXT V4: PASS"
    )

    print()

    print(
        "NEXT STEP:"
    )

    print(
        "Targeted CLIP validation on "
        "7 known-relevant controls "
        "+ unrelated insect control."
    )

else:

    print(
        "CANONICAL NARRATIVE "
        "TOPIC CONTEXT V4: FAIL"
    )

    print()

    print(
        "DO NOT RUN CLIP."
    )

print("=" * 120)

print()
print("No CLIP inference performed.")
print("No DB writes performed.")
print("No assignments written.")
print("No render performed.")
print("No paid API calls.")
