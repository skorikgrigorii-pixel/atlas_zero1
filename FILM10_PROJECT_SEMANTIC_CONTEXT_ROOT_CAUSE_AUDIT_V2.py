from pathlib import Path
import sys
import inspect
import json
import sqlite3
import traceback

ROOT = Path.cwd().resolve()
SRC = ROOT / "src"
PROJECT_ID = "film_10_nepal_tibet_aftershock"
DB_PATH = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"

sys.path.insert(0, str(SRC))

from az_enterprise.core.project_semantic_context_rc2 import (
    ProjectSemanticContextBuilderRC2,
)

print("=" * 120)
print("ATLAS ZERO — PROJECT SEMANTIC CONTEXT ROOT-CAUSE AUDIT V2")
print("=" * 120)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("MODE       : READ ONLY")


# =============================================================================
# SOURCE + CONTRACT
# =============================================================================

source_file = Path(
    inspect.getsourcefile(ProjectSemanticContextBuilderRC2)
).resolve()

print()
print("=" * 120)
print("BUILDER SOURCE")
print("=" * 120)
print(source_file)

print()
print("SIGNATURE:")
print(inspect.signature(ProjectSemanticContextBuilderRC2))

print()
print("METHODS:")

for name, member in inspect.getmembers(
    ProjectSemanticContextBuilderRC2
):
    if name.startswith("__"):
        continue

    if inspect.isfunction(member):
        try:
            sig = inspect.signature(member)
        except Exception:
            sig = "?"

        print("  {:<40} {}".format(name, sig))


# =============================================================================
# COMPLETE BUILDER SOURCE
# =============================================================================

print()
print("=" * 120)
print("COMPLETE BUILDER SOURCE")
print("=" * 120)

try:
    text = inspect.getsource(
        ProjectSemanticContextBuilderRC2
    )
    print(text)
except Exception:
    traceback.print_exc()


# =============================================================================
# MODULE CONSTANTS
# =============================================================================

print()
print("=" * 120)
print("MODULE CONSTANTS / TAXONOMIES")
print("=" * 120)

module = sys.modules[
    ProjectSemanticContextBuilderRC2.__module__
]

for name, value in vars(module).items():

    if name.startswith("__"):
        continue

    if callable(value):
        continue

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
            list,
            tuple,
            set,
            dict,
            type(None),
        ),
    ):
        rendered = repr(value)

        if len(rendered) > 8000:
            rendered = rendered[:8000] + "...<TRUNCATED>"

        print(
            "{} = {}".format(
                name,
                rendered,
            )
        )


# =============================================================================
# BUILD ACTUAL FILM10 CONTEXT
# =============================================================================

print()
print("=" * 120)
print("BUILD ACTUAL FILM10 SEMANTIC CONTEXT")
print("=" * 120)

builder = ProjectSemanticContextBuilderRC2(
    project_id=PROJECT_ID,
    root_dir=".",
)

try:
    context = builder.build()
except Exception:
    print("BUILD FAILED")
    traceback.print_exc()
    raise


print()
print("CONTEXT TYPE:")
print(type(context))

print()
print("CONTEXT ATTRIBUTES:")

if hasattr(context, "__dict__"):
    for key, value in vars(context).items():

        if key in (
            "event_labels",
            "topic_labels",
        ):
            print(
                "{} = <{} entries>".format(
                    key,
                    len(value or {}),
                )
            )
        else:
            rendered = repr(value)

            if len(rendered) > 3000:
                rendered = (
                    rendered[:3000]
                    + "...<TRUNCATED>"
                )

            print(
                "{} = {}".format(
                    key,
                    rendered,
                )
            )


# =============================================================================
# EXACT EVENT LABELS
# =============================================================================

event_labels = getattr(
    context,
    "event_labels",
    {},
) or {}

print()
print("=" * 120)
print("FILM10 EVENT LABELS")
print("=" * 120)
print("COUNT:", len(event_labels))

for index, (label, prompts) in enumerate(
    event_labels.items(),
    start=1,
):
    print()
    print(
        "[{:03d}] {}".format(
            index,
            label,
        )
    )

    if isinstance(
        prompts,
        (list, tuple),
    ):
        for prompt in prompts:
            print(
                "      - {}".format(
                    prompt
                )
            )
    else:
        print(
            "      - {}".format(
                prompts
            )
        )


# =============================================================================
# EXACT TOPIC LABELS
# =============================================================================

topic_labels = getattr(
    context,
    "topic_labels",
    {},
) or {}

print()
print("=" * 120)
print("FILM10 TOPIC LABELS")
print("=" * 120)
print("COUNT:", len(topic_labels))

for label, prompts in topic_labels.items():

    print()
    print(label)

    if isinstance(
        prompts,
        (list, tuple),
    ):
        for prompt in prompts:
            print(
                "      - {}".format(
                    prompt
                )
            )
    else:
        print(
            "      - {}".format(
                prompts
            )
        )


# =============================================================================
# SOURCE PATH
# =============================================================================

source_path = getattr(
    context,
    "source_path",
    None,
)

print()
print("=" * 120)
print("SEMANTIC SOURCE")
print("=" * 120)

print("SOURCE PATH:", source_path)

if source_path:

    path = Path(source_path)

    if not path.is_absolute():
        path = ROOT / path

    print("RESOLVED:", path.resolve())
    print("EXISTS  :", path.exists())

    if path.exists():

        print("SIZE    :", path.stat().st_size)

        try:
            raw = path.read_text(
                encoding="utf-8-sig",
                errors="replace",
            )

            print()
            print("SOURCE PREVIEW:")
            print("-" * 120)
            print(raw[:12000])
            print("-" * 120)

        except Exception as exc:
            print(
                "SOURCE READ ERROR:",
                repr(exc),
            )


# =============================================================================
# CANONICAL STORY SCENES
# =============================================================================

print()
print("=" * 120)
print("CANONICAL FILM10 STORY SCENES")
print("=" * 120)

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

    print("SCENES:", len(scenes))

    for row in scenes:
        d = dict(row)

        print()
        print(
            "SCENE {:03d}".format(
                int(d.get("idx") or 0)
            )
        )

        for key in (
            "id",
            "block",
            "title",
            "start_sec",
            "end_sec",
            "duration_sec",
            "narrative_goal",
            "emotional_goal",
            "visual_strategy",
            "required_assets",
            "status",
            "coverage",
        ):
            value = d.get(key)

            if value not in (
                None,
                "",
            ):
                print(
                    "  {:<18}: {}".format(
                        key,
                        value,
                    )
                )

finally:
    conn.close()


# =============================================================================
# CANONICAL SHOT SEMANTICS SAMPLE
# =============================================================================

print()
print("=" * 120)
print("CANONICAL SHOT SEMANTICS")
print("=" * 120)

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

try:

    shots = conn.execute(
        """
        SELECT
            idx,
            start_sec,
            end_sec,
            block,
            story_goal,
            visual_need,
            emotion,
            status,
            assigned_asset_id
        FROM shots
        WHERE project_id=?
        ORDER BY idx
        """,
        (PROJECT_ID,),
    ).fetchall()

    print("SHOTS:", len(shots))

    # Print all unique semantic requests rather than 260
    # near-identical rows.
    unique = []
    seen = set()

    for row in shots:

        d = dict(row)

        signature = (
            str(d.get("story_goal") or "").strip(),
            str(d.get("visual_need") or "").strip(),
        )

        if signature in seen:
            continue

        seen.add(signature)
        unique.append(d)

    print(
        "UNIQUE STORY/VISUAL REQUESTS:",
        len(unique),
    )

    for i, d in enumerate(
        unique,
        start=1,
    ):
        print()
        print(
            "[{:03d}] shot_idx={}".format(
                i,
                d["idx"],
            )
        )

        print(
            "  STORY :",
            d.get("story_goal"),
        )

        print(
            "  VISUAL:",
            d.get("visual_need"),
        )

finally:
    conn.close()


# =============================================================================
# DIAGNOSTIC
# =============================================================================

print()
print("=" * 120)
print("SEMANTIC CONTEXT DIAGNOSTIC")
print("=" * 120)

generic_labels = {
    "documentary_context",
    "generic_context",
    "project_context",
    "relevant",
    "off_topic",
}

specific_event_labels = [
    label
    for label in event_labels
    if label not in generic_labels
]

print(
    "EVENT LABEL COUNT           :",
    len(event_labels),
)

print(
    "SPECIFIC EVENT LABEL COUNT  :",
    len(specific_event_labels),
)

print(
    "SPECIFIC EVENT LABELS       :",
    specific_event_labels,
)

print(
    "TOPIC LABEL COUNT           :",
    len(topic_labels),
)

print(
    "SOURCE PATH PRESENT         :",
    bool(source_path),
)

print(
    "CONTEXT COLLAPSED           :",
    (
        len(specific_event_labels) == 0
        or (
            len(event_labels) <= 3
            and "documentary_context"
            in event_labels
        )
    ),
)


# =============================================================================
# CHECK BACKUPS / HISTORICAL IMPLEMENTATIONS
# =============================================================================

print()
print("=" * 120)
print("SEMANTIC CONTEXT RELATED FILES")
print("=" * 120)

core_dir = (
    ROOT
    / "src"
    / "az_enterprise"
    / "core"
)

for path in sorted(
    core_dir.glob("*semantic*context*.py")
):
    print(path.name)


print()
print("=" * 120)
print("AUDIT COMPLETE — READ ONLY")
print("=" * 120)

print("No source files modified.")
print("No database rows modified.")
print("No API calls made.")
print("No render performed.")
