from pathlib import Path
import re
import json
import ast

ROOT = Path.cwd().resolve()
SRC = ROOT / "src"
PROJECT_ID = "film_10_nepal_tibet_aftershock"

OUT_DIR = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "00_Production"
    / "editorial_fragmenter_v1"
)

OUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT = OUT_DIR / "FILM10_EXISTING_FRAGMENT_CAPABILITY_AUDIT_V1.json"

print("=" * 120)
print("ATLAS ZERO — FILM10 EXISTING EDITORIAL FRAGMENT CAPABILITY AUDIT V1")
print("=" * 120)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("RENDER     : NO")
print("CLIP       : NO")

if not SRC.exists():
    raise FileNotFoundError(SRC)

# =============================================================================
# SEARCH TARGETS
# =============================================================================

PATTERNS = {
    "scene_detection": [
        r"scene.?detect",
        r"scene.?change",
        r"shot.?detect",
        r"shot.?boundary",
        r"content.?detector",
        r"scenedetect",
        r"select=.*scene",
        r"lavfi.*scene",
    ],

    "duplicate_detection": [
        r"duplicate",
        r"near.?duplicate",
        r"dedup",
        r"visual.?duplicate",
        r"duplicate.?group",
    ],

    "perceptual_hash": [
        r"perceptual_hash",
        r"phash",
        r"dhash",
        r"ahash",
        r"imagehash",
        r"average_hash",
        r"difference_hash",
    ],

    "frame_sampling": [
        r"extract.*frame",
        r"sample.*frame",
        r"video_frames",
        r"ffmpeg",
        r"ffprobe",
    ],

    "editor_pass": [
        r"EditorPassRC2",
        r"editor_pass",
        r"replacement_blocked",
        r"duplicate_warnings",
    ],
}

files = list(SRC.rglob("*.py"))

print()
print("PYTHON FILES:", len(files))

matches = {
    key: []
    for key in PATTERNS
}

# =============================================================================
# SOURCE SEARCH
# =============================================================================

for path in files:

    try:
        text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        continue

    rel = str(path.relative_to(ROOT))

    lines = text.splitlines()

    for category, patterns in PATTERNS.items():

        hit_lines = []

        for lineno, line in enumerate(lines, 1):

            low = line.lower()

            if any(
                re.search(pattern, low, re.I)
                for pattern in patterns
            ):
                hit_lines.append(
                    {
                        "line": lineno,
                        "text": line.strip()[:300],
                    }
                )

        if hit_lines:

            matches[category].append(
                {
                    "file": rel,
                    "hits": hit_lines[:40],
                    "hit_count": len(hit_lines),
                }
            )

# =============================================================================
# CLASS / FUNCTION MAP FOR RELEVANT FILES
# =============================================================================

relevant_files = {}

for category, rows in matches.items():
    for row in rows:
        relevant_files[row["file"]] = True

symbol_map = {}

for rel in sorted(relevant_files):

    path = ROOT / rel

    try:
        source = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        tree = ast.parse(source)

    except Exception:
        continue

    classes = []
    functions = []

    for node in tree.body:

        if isinstance(node, ast.ClassDef):

            methods = []

            for child in node.body:

                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    methods.append(
                        {
                            "name": child.name,
                            "line": child.lineno,
                        }
                    )

            classes.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "methods": methods,
                }
            )

        elif isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):

            functions.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                }
            )

    symbol_map[rel] = {
        "classes": classes,
        "functions": functions,
    }

# =============================================================================
# PRINT BEST CANDIDATES
# =============================================================================

for category in (
    "scene_detection",
    "duplicate_detection",
    "perceptual_hash",
    "editor_pass",
    "frame_sampling",
):

    print()
    print("=" * 120)
    print(category.upper())
    print("=" * 120)

    rows = matches[category]

    if not rows:
        print("NONE")
        continue

    rows = sorted(
        rows,
        key=lambda x: (
            -x["hit_count"],
            x["file"],
        ),
    )

    for row in rows[:15]:

        print()
        print(
            f"{row['file']} "
            f"| hits={row['hit_count']}"
        )

        for hit in row["hits"][:8]:

            print(
                f"  L{hit['line']:<5} "
                f"{hit['text']}"
            )

# =============================================================================
# HIGH-VALUE SYMBOLS
# =============================================================================

print()
print("=" * 120)
print("RELEVANT CLASS / FUNCTION MAP")
print("=" * 120)

interesting_words = (
    "scene",
    "shot",
    "duplicate",
    "hash",
    "frame",
    "editor",
    "visual",
    "segment",
)

for rel, info in sorted(symbol_map.items()):

    selected_classes = []

    for cls in info["classes"]:

        class_hit = any(
            word in cls["name"].lower()
            for word in interesting_words
        )

        method_hits = [
            m
            for m in cls["methods"]
            if any(
                word in m["name"].lower()
                for word in interesting_words
            )
        ]

        if class_hit or method_hits:

            selected_classes.append(
                (
                    cls,
                    method_hits,
                )
            )

    selected_functions = [
        fn
        for fn in info["functions"]
        if any(
            word in fn["name"].lower()
            for word in interesting_words
        )
    ]

    if not selected_classes and not selected_functions:
        continue

    print()
    print(rel)

    for cls, method_hits in selected_classes:

        print(
            f"  CLASS {cls['name']} "
            f"@ L{cls['line']}"
        )

        for method in method_hits[:20]:
            print(
                f"    {method['name']} "
                f"@ L{method['line']}"
            )

    for fn in selected_functions[:20]:

        print(
            f"  FUNC  {fn['name']} "
            f"@ L{fn['line']}"
        )

# =============================================================================
# SPECIAL INSPECTION: KNOWN LIKELY CORE FILES
# =============================================================================

print()
print("=" * 120)
print("LIKELY EXISTING OWNERS")
print("=" * 120)

likely = []

for path in files:

    name = path.name.lower()

    if any(
        token in name
        for token in (
            "editor",
            "duplicate",
            "semantic",
            "visual",
            "asset",
            "frame",
            "shot",
            "scene",
        )
    ):

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            ).lower()
        except Exception:
            continue

        score = 0

        for token in (
            "perceptual_hash",
            "duplicate",
            "scene",
            "ffmpeg",
            "frame",
            "editor_pass",
            "replacement_blocked",
        ):
            score += text.count(token)

        if score:

            likely.append(
                (
                    score,
                    str(path.relative_to(ROOT)),
                )
            )

for score, rel in sorted(
    likely,
    reverse=True,
)[:25]:

    print(
        f"{score:4d} | {rel}"
    )

# =============================================================================
# REPORT
# =============================================================================

report = {
    "schema":
        "atlas_zero.film10.existing_fragment_capability_audit.v1",

    "project_id":
        PROJECT_ID,

    "python_files":
        len(files),

    "matches":
        matches,

    "symbol_map":
        symbol_map,

    "likely_existing_owners":
        [
            {
                "score": score,
                "file": rel,
            }
            for score, rel in sorted(
                likely,
                reverse=True,
            )[:50]
        ],

    "db_writes":
        False,

    "render":
        False,

    "clip":
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
print("CAPABILITY AUDIT COMPLETE")
print("=" * 120)
print("No DB writes.")
print("No render.")
print("No semantic inference.")
print("No paid API calls.")
