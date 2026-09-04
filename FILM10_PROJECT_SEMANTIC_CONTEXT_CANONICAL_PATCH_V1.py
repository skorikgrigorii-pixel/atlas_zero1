from pathlib import Path
import shutil
import py_compile
import sys
import json
import re
import sqlite3
import inspect
import importlib
import traceback

ROOT = Path.cwd().resolve()
SRC = ROOT / "src"
CORE = SRC / "az_enterprise" / "core"

PROJECT_ID = "film_10_nepal_tibet_aftershock"
DB_PATH = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"

TARGET = CORE / "project_semantic_context_rc2.py"
BACKUP = CORE / "project_semantic_context_rc2.py.bak_canonical_story_context_v1"

sys.path.insert(0, str(SRC))

print("=" * 120)
print("ATLAS ZERO — PROJECT SEMANTIC CONTEXT CANONICAL STORY PATCH V1")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("TARGET     :", TARGET)
print("DB         :", DB_PATH)


# =============================================================================
# PREFLIGHT
# =============================================================================

if not TARGET.is_file():
    raise FileNotFoundError(TARGET)

if not DB_PATH.is_file():
    raise FileNotFoundError(DB_PATH)

original = TARGET.read_text(
    encoding="utf-8-sig",
    errors="strict",
)

print()
print("=" * 120)
print("PREFLIGHT")
print("=" * 120)
print("SOURCE BYTES :", len(original.encode("utf-8")))
print("DB EXISTS    :", DB_PATH.exists())


# =============================================================================
# VERIFY FILM10 CANONICAL STORY
# =============================================================================

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

try:
    scenes = conn.execute(
        """
        SELECT
            id,
            idx,
            block,
            title,
            start_sec,
            end_sec,
            duration_sec,
            narrative_goal,
            emotional_goal,
            visual_strategy,
            required_assets,
            status,
            coverage
        FROM story_scenes
        WHERE project_id=?
        ORDER BY idx
        """,
        (PROJECT_ID,),
    ).fetchall()
finally:
    conn.close()

print("FILM10 SCENES:", len(scenes))

if len(scenes) != 86:
    raise RuntimeError(
        "Expected exactly 86 canonical Film10 scenes; got "
        + str(len(scenes))
    )

nonempty_narrative = sum(
    1
    for row in scenes
    if str(row["narrative_goal"] or "").strip()
)

print("NONEMPTY NARRATIVE GOALS:", nonempty_narrative)

if nonempty_narrative < 80:
    raise RuntimeError(
        "Canonical Film10 story scenes are not sufficiently populated."
    )


# =============================================================================
# BACKUP
# =============================================================================

print()
print("=" * 120)
print("BACKUP")
print("=" * 120)

if BACKUP.exists():
    print("EXISTS :", BACKUP)
else:
    shutil.copy2(TARGET, BACKUP)
    print("CREATED:", BACKUP)


# =============================================================================
# PATCH
# =============================================================================

print()
print("=" * 120)
print("PATCHING EXISTING BUILDER")
print("=" * 120)

old_build = '''    def build(self) -> ProjectSemanticContextRC2:
        source = self._discover_script()

        if source is None:
            return self._fallback_context()

        text = source.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        importer = ExternalScriptImporterRC2(
            project_id=self.project_id,
        )

        parsed_title, scenes = importer._parse(
            text,
            suffix=source.suffix.lower(),
        )

        title = (
            str(parsed_title or "").strip()
            or self._extract_title(text)
        )

        if not scenes:
            return self._fallback_context(
                title=title,
                source=source,
            )

        event_labels: dict[str, tuple[str, ...]] = {}
        concepts: list[str] = []

        for scene in scenes:
            scene_title = str(scene.title or "").strip()

            if not scene_title:
                scene_title = str(scene.scene_id)

            label = (
                "scene_"
                + str(scene.scene_id).lower()
            )

            narration = re.sub(
                r"\\s+",
                " ",
                str(scene.narration_ru or "").strip(),
            )

            # Keep the prompt compact enough for CLIP.
            narration_excerpt = narration[:280]

            event_labels[label] = (
                f"documentary visual for scene: {scene_title}",
                f"historical scientific archaeological or factual "
                f"material illustrating: {scene_title}",
                f"visual evidence matching this documentary passage: "
                f"{narration_excerpt}",
            )

            concepts.append(scene_title)

        event_labels["project_context"] = (
            f"visual material directly related to the documentary {title}",
            f"historical scientific archaeological archival or geographical "
            f"material connected with {title}",
            f"a factual documentary scene belonging to the story {title}",
        )

        event_labels["generic_context"] = (
            "general historical archaeological scientific archival "
            "or geographical documentary context",
            "architecture artifact manuscript landscape museum excavation "
            "or research material useful in a documentary",
        )

        event_labels["unrelated_private_content"] = (
            "a private selfie family photograph or personal everyday scene",
            "an unrelated household object pet food car or private material",
            "visual material with no relationship to the current documentary",
        )

        topic_labels = {
            "relevant": (
                f"material belonging to the documentary {title}",
                f"historical scientific archaeological archival or factual "
                f"evidence related to {title}",
                "visual material matching one of the scenes of the current "
                "documentary script",
            ),
            "off_topic": (
                f"material unrelated to the documentary {title}",
                "private everyday family household or personal media",
                "an unrelated subject with no connection to the current "
                "documentary story",
            ),
        }

        return ProjectSemanticContextRC2(
            project_id=self.project_id,
            title=title,
            source_path=str(source),
            event_labels=event_labels,
            topic_labels=topic_labels,
            location_hint=title,
            concepts=tuple(concepts),
        )
'''

new_build = '''    def build(self) -> ProjectSemanticContextRC2:
        """
        Build semantic context using the strongest available canonical source.

        Source priority:
        1. approved external production script;
        2. canonical story_scenes stored in the ATLAS ZERO database;
        3. conservative generic fallback.

        The canonical DB path is intentionally project-independent. It allows
        projects created inside ATLAS ZERO to receive project-specific semantic
        vocabulary even when they do not have an approved_external_script file.
        """
        source = self._discover_script()

        if source is not None:
            context = self._build_from_approved_script(source)

            if context is not None:
                return context

        context = self._build_from_canonical_story()

        if context is not None:
            return context

        return self._fallback_context()

    def _build_from_approved_script(
        self,
        source: Path,
    ) -> ProjectSemanticContextRC2 | None:
        text = source.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        importer = ExternalScriptImporterRC2(
            project_id=self.project_id,
        )

        parsed_title, scenes = importer._parse(
            text,
            suffix=source.suffix.lower(),
        )

        title = (
            str(parsed_title or "").strip()
            or self._extract_title(text)
        )

        if not scenes:
            return None

        records: list[dict[str, str]] = []

        for scene in scenes:
            scene_id = str(scene.scene_id or "").strip()

            scene_title = str(scene.title or "").strip()

            narration = re.sub(
                r"\\s+",
                " ",
                str(scene.narration_ru or "").strip(),
            )

            records.append(
                {
                    "scene_id": scene_id,
                    "title": scene_title,
                    "narration": narration,
                    "visual_strategy": "",
                }
            )

        return self._context_from_scene_records(
            title=title,
            records=records,
            source_path=str(source),
        )

    def _canonical_db_path(self) -> Path:
        return (
            self.root_dir
            / "workspace"
            / "atlas_zero_enterprise.sqlite3"
        )

    def _canonical_project_title(
        self,
        conn: sqlite3.Connection,
    ) -> str:
        try:
            row = conn.execute(
                """
                SELECT title
                FROM projects
                WHERE id=?
                LIMIT 1
                """,
                (self.project_id,),
            ).fetchone()
        except sqlite3.Error:
            row = None

        if row is not None:
            value = str(row[0] or "").strip()

            if value:
                return value

        return self.project_id.replace("_", " ").strip()

    def _build_from_canonical_story(
        self,
    ) -> ProjectSemanticContextRC2 | None:
        db_path = self._canonical_db_path()

        if not db_path.is_file():
            return None

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            try:
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        idx,
                        block,
                        title,
                        narrative_goal,
                        emotional_goal,
                        visual_strategy
                    FROM story_scenes
                    WHERE project_id=?
                    ORDER BY idx
                    """,
                    (self.project_id,),
                ).fetchall()

                title = self._canonical_project_title(conn)

            finally:
                conn.close()

        except sqlite3.Error:
            return None

        if not rows:
            return None

        records: list[dict[str, str]] = []

        for row in rows:
            narration = re.sub(
                r"\\s+",
                " ",
                str(row["narrative_goal"] or "").strip(),
            )

            if not narration:
                continue

            raw_title = str(row["title"] or "").strip()

            # Generic imported editorial buckets are not semantic scene names.
            if raw_title.upper() in {
                "",
                "GENERAL_CONTEXT",
                "DOCUMENTARY_CONTEXT",
                "PROJECT_CONTEXT",
            }:
                raw_title = ""

            records.append(
                {
                    "scene_id": str(row["id"] or row["idx"]),
                    "title": raw_title,
                    "narration": narration,
                    "visual_strategy": str(
                        row["visual_strategy"] or ""
                    ).strip(),
                }
            )

        if not records:
            return None

        return self._context_from_scene_records(
            title=title,
            records=records,
            source_path="canonical_db:story_scenes",
        )

    def _scene_semantic_phrase(
        self,
        narration: str,
    ) -> str:
        """
        Produce a compact project-independent visual phrase from narration.

        This is deliberately deterministic and local. It does not call an LLM
        and does not contain vocabulary belonging to any specific film.
        """
        clean = re.sub(
            r"\\s+",
            " ",
            str(narration or "").strip(),
        )

        if not clean:
            return "documentary scene"

        concepts = self._extract_concepts(clean)

        if concepts:
            phrase = ", ".join(concepts[:8])
            return phrase[:220]

        return clean[:220]

    def _context_from_scene_records(
        self,
        *,
        title: str,
        records: list[dict[str, str]],
        source_path: str,
    ) -> ProjectSemanticContextRC2:
        corpus_text = " ".join(
            record["narration"]
            for record in records
            if record.get("narration")
        )

        concepts = self._extract_concepts(corpus_text)

        event_labels: dict[str, tuple[str, ...]] = {}

        for index, record in enumerate(records, start=1):
            narration = str(
                record.get("narration") or ""
            ).strip()

            if not narration:
                continue

            semantic_phrase = self._scene_semantic_phrase(
                narration
            )

            scene_title = str(
                record.get("title") or ""
            ).strip()

            label = "scene_{:03d}".format(index)

            prompt_subject = (
                scene_title
                if scene_title
                else semantic_phrase
            )

            narration_excerpt = narration[:260]

            event_labels[label] = (
                f"documentary image or footage specifically showing "
                f"{prompt_subject}",
                f"factual visual evidence directly matching "
                f"{semantic_phrase}",
                f"visual material matching this documentary passage: "
                f"{narration_excerpt}",
            )

        # Project-wide classes remain useful, but they are deliberately
        # secondary to the individual scene classes above.
        concept_text = ", ".join(concepts[:16])

        event_labels["project_context"] = (
            f"visual material directly related to the documentary {title}",
            f"factual visual evidence connected with {concept_text}",
            f"a documentary scene belonging to the subject of {title}",
        )

        event_labels["generic_context"] = (
            "general factual documentary context",
            "scientific geographical archival infrastructure landscape "
            "or human documentary material",
        )

        event_labels["unrelated_private_content"] = (
            "a private selfie family photograph or personal everyday scene",
            "an unrelated household object pet food car or private material",
            "visual material with no relationship to the current documentary",
        )

        topic_labels = self._build_topic_labels(
            concepts=concepts,
            title=title,
        )

        return ProjectSemanticContextRC2(
            project_id=self.project_id,
            title=title,
            source_path=source_path,
            event_labels=event_labels,
            topic_labels=topic_labels,
            location_hint=self._derive_location_hint(
                title,
                concepts,
            ),
            concepts=tuple(concepts),
        )
'''

if old_build not in original:
    raise RuntimeError(
        "Expected build() implementation was not found exactly. "
        "Source was NOT modified."
    )

patched = original.replace(
    old_build,
    new_build,
    1,
)

if patched == original:
    raise RuntimeError("Patch produced no source change.")


# =============================================================================
# ENSURE SQLITE IMPORT
# =============================================================================

if re.search(
    r"(?m)^import sqlite3\\s*$",
    patched,
) is None:
    insertion_anchor = "import re\n"

    if insertion_anchor not in patched:
        raise RuntimeError(
            "Could not safely insert sqlite3 import."
        )

    patched = patched.replace(
        insertion_anchor,
        insertion_anchor + "import sqlite3\n",
        1,
    )


# =============================================================================
# WRITE
# =============================================================================

TARGET.write_text(
    patched,
    encoding="utf-8",
)

print("PATCH WRITTEN:", TARGET)


# =============================================================================
# COMPILE
# =============================================================================

print()
print("=" * 120)
print("PY_COMPILE")
print("=" * 120)

try:
    py_compile.compile(
        str(TARGET),
        doraise=True,
    )
    print("PASS")

except Exception:
    print("FAIL — RESTORING ORIGINAL SOURCE")
    TARGET.write_text(
        original,
        encoding="utf-8",
    )
    raise


# =============================================================================
# RELOAD MODULE
# =============================================================================

module_name = (
    "az_enterprise.core.project_semantic_context_rc2"
)

if module_name in sys.modules:
    module = importlib.reload(
        sys.modules[module_name]
    )
else:
    module = importlib.import_module(
        module_name
    )

Builder = module.ProjectSemanticContextBuilderRC2

builder = Builder(
    project_id=PROJECT_ID,
    root_dir=ROOT,
)

context = builder.build()


# =============================================================================
# VALIDATION
# =============================================================================

print()
print("=" * 120)
print("FILM10 NEW SEMANTIC CONTEXT")
print("=" * 120)

print("TITLE            :", context.title)
print("SOURCE PATH      :", context.source_path)
print("EVENT LABELS     :", len(context.event_labels))
print("TOPIC LABELS     :", len(context.topic_labels))
print("CONCEPTS         :", len(context.concepts))
print("LOCATION HINT    :", context.location_hint)

print()
print("TOP PROJECT CONCEPTS:")

for i, concept in enumerate(
    context.concepts[:36],
    start=1,
):
    print(
        "  {:02d}. {}".format(
            i,
            concept,
        )
    )

print()
print("=" * 120)
print("FIRST 12 SCENE SEMANTIC CLASSES")
print("=" * 120)

scene_labels = [
    (label, prompts)
    for label, prompts
    in context.event_labels.items()
    if label.startswith("scene_")
]

for label, prompts in scene_labels[:12]:
    print()
    print(label)

    for prompt in prompts:
        print("   -", prompt)


# =============================================================================
# STRATEGIC SCENES
# =============================================================================

print()
print("=" * 120)
print("STRATEGIC FILM10 SCENE PROMPTS")
print("=" * 120)

interesting_terms = (
    "лангтанг",
    "дрон",
    "гидро",
    "тришули",
    "гьиронг",
    "спутник",
    "школ",
    "плотин",
    "озер",
    "озёр",
)

hits = 0

for label, prompts in scene_labels:
    joined = " ".join(prompts).lower()

    if any(
        term in joined
        for term in interesting_terms
    ):
        print()
        print(label)

        for prompt in prompts:
            print("   -", prompt)

        hits += 1

print()
print("STRATEGIC PROMPT HITS:", hits)


# =============================================================================
# HARD GATES
# =============================================================================

print()
print("=" * 120)
print("HARD GATES")
print("=" * 120)

checks = {
    "SOURCE_IS_CANONICAL_DB":
        context.source_path
        == "canonical_db:story_scenes",

    "NOT_GENERIC_FALLBACK":
        "documentary_context"
        not in context.event_labels,

    "SCENE_LABELS_GE_80":
        len(scene_labels) >= 80,

    "CONCEPTS_GE_12":
        len(context.concepts) >= 12,

    "TOPIC_LABELS_PRESENT":
        set(context.topic_labels.keys())
        >= {"relevant", "off_topic"},

    "PROJECT_CONTEXT_PRESENT":
        "project_context"
        in context.event_labels,

    "UNRELATED_CLASS_PRESENT":
        "unrelated_private_content"
        in context.event_labels,

    "STRATEGIC_SCENE_HITS_GE_5":
        hits >= 5,
}

all_pass = True

for name, passed in checks.items():
    print(
        "{:<36}: {}".format(
            name,
            "PASS" if passed else "FAIL",
        )
    )

    if not passed:
        all_pass = False


# =============================================================================
# REPORT
# =============================================================================

report_dir = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "semantic_context_v1"
)

report_dir.mkdir(
    parents=True,
    exist_ok=True,
)

report_path = (
    report_dir
    / "FILM10_PROJECT_SEMANTIC_CONTEXT_V1.json"
)

payload = {
    "schema":
        "atlas_zero.project_semantic_context.audit.v1",

    "project_id":
        PROJECT_ID,

    "source_path":
        context.source_path,

    "title":
        context.title,

    "event_label_count":
        len(context.event_labels),

    "scene_label_count":
        len(scene_labels),

    "topic_label_count":
        len(context.topic_labels),

    "concept_count":
        len(context.concepts),

    "concepts":
        list(context.concepts),

    "event_labels": {
        key: list(value)
        for key, value
        in context.event_labels.items()
    },

    "topic_labels": {
        key: list(value)
        for key, value
        in context.topic_labels.items()
    },

    "hard_gates":
        checks,
}

report_path.write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("REPORT:", report_path)


# =============================================================================
# RESULT
# =============================================================================

print()
print("=" * 120)

if all_pass:
    print(
        "FILM10 PROJECT SEMANTIC CONTEXT "
        "CANONICAL STORY PATCH V1: PASS"
    )
else:
    print(
        "FILM10 PROJECT SEMANTIC CONTEXT "
        "CANONICAL STORY PATCH V1: FAIL"
    )

print("=" * 120)

print()
print("No API calls made.")
print("No asset analysis performed.")
print("No assignments written.")
print("No render performed.")

if not all_pass:
    raise RuntimeError(
        "Semantic context hard gates failed. "
        "Do NOT run asset semantic analysis yet."
    )
