from pathlib import Path
import sys
import re
import json
import shutil
import py_compile
import importlib
import sqlite3
from collections import Counter

ROOT = Path.cwd().resolve()
SRC = ROOT / "src"
CORE = SRC / "az_enterprise" / "core"

PROJECT_ID = "film_10_nepal_tibet_aftershock"
TARGET = CORE / "project_semantic_context_rc2.py"
BACKUP = CORE / "project_semantic_context_rc2.py.bak_semantic_extractor_v2"

sys.path.insert(0, str(SRC))

print("=" * 120)
print("ATLAS ZERO — PROJECT SEMANTIC CONTEXT QUALITY PATCH V2")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("TARGET     :", TARGET)

if not TARGET.is_file():
    raise FileNotFoundError(TARGET)

original = TARGET.read_text(
    encoding="utf-8-sig",
    errors="strict",
)

# -------------------------------------------------------------------------
# LOAD CURRENT CONTEXT — BEFORE
# -------------------------------------------------------------------------

module_name = "az_enterprise.core.project_semantic_context_rc2"

module = importlib.import_module(module_name)

Builder = module.ProjectSemanticContextBuilderRC2

before = Builder(
    project_id=PROJECT_ID,
    root_dir=ROOT,
).build()

print()
print("=" * 120)
print("BEFORE")
print("=" * 120)

print("SOURCE :", before.source_path)
print("SCENES :", len([
    x for x in before.event_labels
    if x.startswith("scene_")
]))
print("CONCEPTS:", len(before.concepts))

for i, value in enumerate(before.concepts, 1):
    print(f"{i:02d}. {value}")

if before.source_path != "canonical_db:story_scenes":
    raise RuntimeError(
        "Canonical story context is not active. "
        "V2 patch aborted."
    )

# -------------------------------------------------------------------------
# BACKUP
# -------------------------------------------------------------------------

print()
print("=" * 120)
print("BACKUP")
print("=" * 120)

if BACKUP.exists():
    print("EXISTS :", BACKUP)
else:
    shutil.copy2(TARGET, BACKUP)
    print("CREATED:", BACKUP)

# -------------------------------------------------------------------------
# PATCH _extract_concepts
# -------------------------------------------------------------------------

start_marker = "    def _extract_concepts(\n"
end_marker = "    @staticmethod\n    def _slug("

start = original.find(start_marker)
end = original.find(end_marker, start)

if start < 0 or end < 0:
    raise RuntimeError(
        "Could not locate _extract_concepts() safely. "
        "Source NOT modified."
    )

old_method = original[start:end]

new_method = r'''    def _extract_concepts(
        self,
        text: str,
    ) -> list[str]:
        """
        Extract visually useful documentary concepts without project-specific
        vocabulary.

        The extractor intentionally prefers:
        - named/proper entities;
        - recurring concrete nouns;
        - recurring two- and three-word phrases;
        - geographical/scientific/institutional terms.

        It suppresses:
        - production markers;
        - narration glue;
        - pronouns and discourse words;
        - generic storytelling verbs/adverbs;
        - isolated numbers and timing language.

        This method is deterministic and local.
        """

        cleaned = str(text or "")

        # Production structure must never become visual semantics.
        cleaned = re.sub(
            r"\b(?:БЛОК|BLOCK)\s*\d+\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\b(?:ФИНАЛ|FINAL|HOOK|OPENING|SHOCK)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"[`*_>#\[\](){}|]",
            " ",
            cleaned,
        )

        cleaned = re.sub(r"\s+", " ", cleaned)

        noise = self.STOPWORDS | {
            # Russian discourse / narration glue
            "кто-то", "что-то", "где-то", "когда-то",
            "почему-то", "какой-то", "какая-то", "какие-то",
            "иногда", "наверное", "поэтому", "возможно",
            "невозможно", "особенно", "довольно",
            "действительно", "просто", "снова", "теперь",
            "потом", "пока", "сначала", "именно",
            "кажется", "оказалось", "оказаться",
            "становится", "становиться", "стало",
            "бывает", "быть", "можно", "нужно",
            "увидеть", "видеть", "знать", "сказать",
            "говорить", "делать", "найти", "оставаться",
            "появиться", "происходит", "произошло",
            "происходило", "начинается", "началось",
            "начали", "начинают", "продолжает",
            "продолжали", "оказался", "оказалась",
            "иметь", "имеет", "имело", "значение",
            "вместе", "среди", "через", "внутри",
            "внизу", "вверх", "вниз", "выше", "ниже",
            "рядом", "далеко", "почти", "более",
            "несколько", "много", "многие", "других",
            "другой", "новые", "новый", "новая",
            "первый", "первые", "последний",
            "обычный", "обычно", "сегодня",
            "утром", "вечером", "день", "дней",
            "время", "минут", "минуты", "секунд",
            "годы", "годами", "году",
            "человек", "люди", "людей",
            "который", "которая", "которые",
            "этого", "этой", "этом",
            "такой", "такая", "такие",
            "своей", "своих", "своего",
            "этот", "эта", "эти",
            "того", "тому",
            "здесь", "туда", "отсюда",
            "всего", "самого", "самой",
            "часть", "целую", "целый",
            "случилось", "случае",
            "вопрос", "история", "истории",
            "картина", "названия",
            "записи", "запись",
            "кадры", "кадр",
            "материал", "материала",
            "фильм", "фильма",
            "atlas", "zero",

            # English discourse glue
            "someone", "something", "somewhere",
            "sometimes", "perhaps", "maybe",
            "really", "already", "still",
            "again", "then", "now",
            "today", "yesterday", "tomorrow",
            "people", "person", "time",
            "minute", "minutes", "second", "seconds",
            "story", "film", "documentary",
            "footage", "image", "images",
            "video", "scene", "scenes",
        }

        token_pattern = (
            r"[A-Za-zА-Яа-яЁёÀ-ÿ]"
            r"[A-Za-zА-Яа-яЁёÀ-ÿ0-9\-]{2,}"
        )

        raw_tokens = re.findall(
            token_pattern,
            cleaned,
        )

        def normalize(value: str) -> str:
            return value.lower().strip("-")

        def usable(value: str) -> bool:
            n = normalize(value)

            if len(n) < 4:
                return False

            if n in noise:
                return False

            if n.isdigit():
                return False

            return True

        frequency: Counter[str] = Counter()
        display: dict[str, str] = {}
        proper_bonus: Counter[str] = Counter()

        for token in raw_tokens:
            if not usable(token):
                continue

            key = normalize(token)

            frequency[key] += 1
            display.setdefault(key, token)

            # Repeated capitalisation is useful evidence for names,
            # institutions and geographical entities.
            if token[:1].isupper():
                proper_bonus[key] += 1

        phrase_frequency: Counter[str] = Counter()
        phrase_display: dict[str, str] = {}
        phrase_proper_bonus: Counter[str] = Counter()

        # Two- and three-token windows are substantially more useful
        # for CLIP-like models than isolated generic words.
        for width in (2, 3):
            for index in range(
                0,
                max(0, len(raw_tokens) - width + 1),
            ):
                window = raw_tokens[
                    index:index + width
                ]

                if not all(usable(x) for x in window):
                    continue

                normalized = [
                    normalize(x)
                    for x in window
                ]

                key = " ".join(normalized)
                shown = " ".join(window)

                phrase_frequency[key] += 1
                phrase_display.setdefault(
                    key,
                    shown,
                )

                if any(
                    token[:1].isupper()
                    for token in window
                ):
                    phrase_proper_bonus[key] += 1

        scored: list[
            tuple[float, int, str]
        ] = []

        # Single concepts need recurrence unless they look like
        # a proper-name entity.
        for key, count in frequency.items():
            proper = proper_bonus.get(key, 0)

            if count < 2 and proper < 1:
                continue

            score = float(count)

            score += min(
                proper,
                4,
            ) * 1.35

            scored.append(
                (
                    score,
                    1,
                    display[key],
                )
            )

        # Phrases are strongly preferred.
        for key, count in phrase_frequency.items():
            proper = phrase_proper_bonus.get(
                key,
                0,
            )

            if count < 2 and proper < 1:
                continue

            word_count = len(key.split())

            score = (
                float(count) * 2.2
                + min(proper, 4) * 1.5
                + word_count * 0.8
            )

            scored.append(
                (
                    score,
                    word_count,
                    phrase_display[key],
                )
            )

        scored.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                item[2].lower(),
            )
        )

        concepts: list[str] = []
        seen: set[str] = set()

        for _, _, value in scored:
            normalized = value.lower()

            if normalized in seen:
                continue

            # Avoid adding a weak single word when a selected phrase
            # already expresses the same entity more precisely.
            if " " not in value:
                if any(
                    re.search(
                        r"\b"
                        + re.escape(normalized)
                        + r"\b",
                        existing.lower(),
                    )
                    for existing in concepts
                    if " " in existing
                ):
                    continue

            seen.add(normalized)
            concepts.append(value)

            if len(concepts) >= 36:
                break

        return concepts

'''

patched = (
    original[:start]
    + new_method
    + original[end:]
)

if patched == original:
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

# -------------------------------------------------------------------------
# COMPILE
# -------------------------------------------------------------------------

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
    TARGET.write_text(
        original,
        encoding="utf-8",
    )

    print("FAIL — ORIGINAL RESTORED")
    raise

# -------------------------------------------------------------------------
# RELOAD + AFTER
# -------------------------------------------------------------------------

module = importlib.reload(module)

Builder = module.ProjectSemanticContextBuilderRC2

after = Builder(
    project_id=PROJECT_ID,
    root_dir=ROOT,
).build()

print()
print("=" * 120)
print("AFTER")
print("=" * 120)

print("TITLE       :", after.title)
print("SOURCE      :", after.source_path)
print("EVENT LABELS:", len(after.event_labels))
print("CONCEPTS    :", len(after.concepts))

print()
print("PROJECT CONCEPTS:")

for i, value in enumerate(
    after.concepts,
    1,
):
    print(f"{i:02d}. {value}")

# -------------------------------------------------------------------------
# SCENE PROMPT QUALITY
# -------------------------------------------------------------------------

scene_labels = [
    (label, prompts)
    for label, prompts
    in after.event_labels.items()
    if label.startswith("scene_")
]

print()
print("=" * 120)
print("SELECTED SCENE PROMPTS")
print("=" * 120)

for index in (
    7,   # Langtang Lirung
    14,  # drone
    15,  # collapse
    19,  # river/debris flow
    23,  # Gyirong
    28,  # satellite map
    35,  # USGS / Trishuli
    38,  # drone / new lake
    39,  # satellite / dam / hydropower transition
    41,  # hydropower disaster
    45,  # Bidur school
    46,  # warning
    47,  # buses / bridge
    48,  # school survival
    63,  # seismic + satellite
    67,  # propagation timing
):
    key = f"scene_{index:03d}"

    prompts = after.event_labels.get(key)

    if prompts is None:
        continue

    print()
    print(key)

    for prompt in prompts:
        print("   -", prompt)

# -------------------------------------------------------------------------
# QUALITY GATES
# -------------------------------------------------------------------------

joined_concepts = " ".join(
    after.concepts
).lower()

joined_prompts = " ".join(
    prompt
    for label, prompts
    in scene_labels
    for prompt in prompts
).lower()

forbidden = {
    "блок",
    "финал",
    "кто-то",
    "наверное",
    "поэтому",
}

strategic_groups = {
    "LANGTANG":
        ("лангтанг",),

    "TRISHULI":
        ("тришули",),

    "USGS":
        ("usgs",),

    "GYIRONG":
        ("гьиронг",),

    "SCHOOL":
        ("школ", "трибхуван", "бидур"),

    "DRONE":
        ("дрон",),

    "HYDRO":
        ("гидро", "электростан",),

    "SATELLITE":
        ("спутник", "спутников",),

    "RIVER_FLOW":
        ("река", "реки", "вода", "поток"),

    "MOUNTAIN_COLLAPSE":
        ("склон", "ледник", "гора", "обруш"),
}

strategic_results = {}

for name, terms in strategic_groups.items():
    strategic_results[name] = any(
        term in joined_prompts
        for term in terms
    )

forbidden_hits = [
    word
    for word in forbidden
    if word in {
        x.lower()
        for x in after.concepts
    }
]

checks = {
    "SOURCE_CANONICAL_DB":
        after.source_path
        == "canonical_db:story_scenes",

    "SCENE_LABELS_86":
        len(scene_labels) == 86,

    "CONCEPTS_GE_20":
        len(after.concepts) >= 20,

    "NO_PRODUCTION_MARKERS":
        "блок" not in joined_concepts
        and "финал" not in joined_concepts,

    "NO_FORBIDDEN_SINGLE_CONCEPTS":
        len(forbidden_hits) == 0,

    "LANGTANG_PRESENT":
        strategic_results["LANGTANG"],

    "TRISHULI_PRESENT":
        strategic_results["TRISHULI"],

    "USGS_PRESENT":
        strategic_results["USGS"],

    "GYIRONG_PRESENT":
        strategic_results["GYIRONG"],

    "SCHOOL_PRESENT":
        strategic_results["SCHOOL"],

    "DRONE_PRESENT":
        strategic_results["DRONE"],

    "HYDRO_PRESENT":
        strategic_results["HYDRO"],

    "SATELLITE_PRESENT":
        strategic_results["SATELLITE"],

    "RIVER_FLOW_PRESENT":
        strategic_results["RIVER_FLOW"],

    "MOUNTAIN_COLLAPSE_PRESENT":
        strategic_results["MOUNTAIN_COLLAPSE"],
}

print()
print("=" * 120)
print("QUALITY GATES")
print("=" * 120)

all_pass = True

for name, result in checks.items():
    print(
        f"{name:<38}: "
        + ("PASS" if result else "FAIL")
    )

    if not result:
        all_pass = False

print()
print("STRATEGIC ENTITY COVERAGE:")

for name, result in strategic_results.items():
    print(
        f"  {name:<24}: "
        + ("YES" if result else "NO")
    )

# -------------------------------------------------------------------------
# REPORT
# -------------------------------------------------------------------------

report_dir = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "semantic_context_v2"
)

report_dir.mkdir(
    parents=True,
    exist_ok=True,
)

report_path = (
    report_dir
    / "FILM10_PROJECT_SEMANTIC_CONTEXT_V2.json"
)

payload = {
    "schema":
        "atlas_zero.project_semantic_context.quality.v2",

    "project_id":
        PROJECT_ID,

    "source_path":
        after.source_path,

    "before_concepts":
        list(before.concepts),

    "after_concepts":
        list(after.concepts),

    "scene_label_count":
        len(scene_labels),

    "event_label_count":
        len(after.event_labels),

    "strategic_entity_coverage":
        strategic_results,

    "forbidden_hits":
        forbidden_hits,

    "quality_gates":
        checks,

    "asset_analysis_performed":
        False,

    "assignments_written":
        False,

    "render_performed":
        False,
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

print()
print("=" * 120)

if all_pass:
    print(
        "FILM10 PROJECT SEMANTIC CONTEXT "
        "QUALITY PATCH V2: PASS"
    )
else:
    print(
        "FILM10 PROJECT SEMANTIC CONTEXT "
        "QUALITY PATCH V2: FAIL"
    )

print("=" * 120)

print()
print("No API calls made.")
print("No asset semantic analysis performed.")
print("No assignments written.")
print("No render performed.")

if not all_pass:
    raise RuntimeError(
        "Semantic context quality gates failed. "
        "Do NOT run asset analysis yet."
    )
