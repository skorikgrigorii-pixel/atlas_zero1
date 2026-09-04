from __future__ import annotations

from pathlib import Path
import sys
import json
import subprocess
import hashlib
import html
from collections import defaultdict

from PIL import Image

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from az_enterprise.core.visual_asset_registrar import VisualAssetRegistrar

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

SOURCE_JSON = (
    PROJECT
    / "00_Production"
    / "editorial_fragmenter_v2"
    / "FILM10_EDITORIAL_FRAGMENTS_V2.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "editorial_fragment_qc_v1"
)

FRAME_DIR = OUT_DIR / "frames"

REPORT = (
    OUT_DIR
    / "FILM10_EDITORIAL_FRAGMENT_QC_V1.json"
)

HTML = (
    OUT_DIR
    / "FILM10_EDITORIAL_FRAGMENT_QC_V1.html"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

FRAME_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

print("=" * 122)
print("ATLAS ZERO — FILM10 EDITORIAL FRAGMENT MULTIFRAME QC V1")
print("=" * 122)

print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("SOURCE CUT : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")
print("OCR        : NO")
print("CLIP       : NO")

if not SOURCE_JSON.exists():
    raise FileNotFoundError(SOURCE_JSON)

payload = json.loads(
    SOURCE_JSON.read_text(
        encoding="utf-8"
    )
)

fragments = payload.get(
    "fragments",
    []
)

if not fragments:
    raise RuntimeError(
        "No editorial fragments found."
    )

print()
print("EDITORIAL FRAGMENTS:", len(fragments))

# =============================================================================
# EXISTING HASH OWNER CHECK
# =============================================================================

print()
print("=" * 122)
print("EXISTING DUPLICATE-DETECTION OWNER")
print("=" * 122)

hash_owner = getattr(
    VisualAssetRegistrar,
    "_dhash_hex",
    None,
)

if hash_owner is None:
    raise RuntimeError(
        "VisualAssetRegistrar._dhash_hex not available. "
        "Refusing to create a parallel hash implementation."
    )

print(
    "HASH OWNER :",
    "VisualAssetRegistrar._dhash_hex"
)

# =============================================================================
# HELPERS
# =============================================================================

def tc(sec: float) -> str:
    sec = max(0.0, float(sec))
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:06.3f}"


def sample_times(
    start: float,
    end: float,
) -> list[float]:

    duration = end - start

    positions = (
        0.20,
        0.50,
        0.80,
    )

    result = []

    for fraction in positions:

        t = (
            start
            + duration * fraction
        )

        # Stay away from exact source boundary.
        t = max(
            start + 0.05,
            min(
                end - 0.05,
                t,
            ),
        )

        result.append(t)

    return result


def extract_frame(
    source: Path,
    timestamp: float,
    output: Path,
) -> tuple[bool, str]:

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{timestamp:.3f}",
        "-i", str(source),
        "-frames:v", "1",
        "-vf",
        "scale=640:-2:"
        "force_original_aspect_ratio=decrease",
        "-q:v", "3",
        str(output),
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )

    ok = (
        proc.returncode == 0
        and output.exists()
        and output.stat().st_size > 0
    )

    return (
        ok,
        proc.stderr[-1200:]
        if not ok
        else "",
    )


def dhash(path: Path) -> str:

    with Image.open(path) as image:

        gray = image.convert("L")

        value = (
            VisualAssetRegistrar
            ._dhash_hex(gray)
        )

    return str(value)


def hamming(
    a: str,
    b: str,
) -> int:

    if not a or not b:
        return 999

    try:

        ai = int(a, 16)
        bi = int(b, 16)

        return (
            ai ^ bi
        ).bit_count()

    except Exception:

        # Existing hash representation may be bit string.
        if len(a) == len(b):

            return sum(
                ca != cb
                for ca, cb
                in zip(a, b)
            )

        return 999


# =============================================================================
# 3-FRAME EXTRACTION
# =============================================================================

qc_rows = []

print()
print("=" * 122)
print("MULTIFRAME EXTRACTION")
print("=" * 122)

for index, fragment in enumerate(
    fragments,
    1,
):

    source = Path(
        fragment["source_path"]
    )

    if not source.exists():
        raise FileNotFoundError(source)

    start = float(
        fragment["source_start"]
    )

    end = float(
        fragment["source_end"]
    )

    fragment_id = str(
        fragment["fragment_id"]
    )

    times = sample_times(
        start,
        end,
    )

    frame_rows = []

    success = 0

    for sample_index, timestamp in enumerate(
        times,
        1,
    ):

        frame_path = (
            FRAME_DIR
            / (
                f"{index:03d}_"
                f"{fragment_id}_"
                f"s{sample_index}.jpg"
            )
        )

        ok, error = extract_frame(
            source,
            timestamp,
            frame_path,
        )

        hash_value = None

        if ok:

            hash_value = dhash(
                frame_path
            )

            success += 1

        frame_rows.append({
            "sample_index":
                sample_index,

            "timestamp_sec":
                round(timestamp, 3),

            "timestamp_tc":
                tc(timestamp),

            "path":
                str(frame_path)
                if ok
                else None,

            "dhash":
                hash_value,

            "ok":
                ok,

            "error":
                error or None,
        })

    row = {
        **fragment,

        "review_number":
            index,

        "qc_frames":
            frame_rows,

        "frames_ok":
            success,

        "qc_status":
            (
                "READY_FOR_DUPLICATE_CHECK"
                if success == 3
                else "REVIEW"
            ),

        "duplicate_candidates":
            [],
    }

    qc_rows.append(row)

    print(
        f"{index:03d}/{len(fragments):03d} | "
        f"{success}/3 | "
        f"{start:8.3f}-{end:8.3f} | "
        f"{source.name}"
    )

# =============================================================================
# MULTIFRAME DUPLICATE DETECTION
#
# Important:
# candidate only — never automatic reject.
#
# Two fragments are considered strongly similar only when at least
# TWO of their representative frames have close dHash matches.
# =============================================================================

print()
print("=" * 122)
print("VISUAL DUPLICATE CANDIDATE DETECTION")
print("=" * 122)

DUP_HASH_DISTANCE = 7

duplicate_pairs = []

for i in range(
    len(qc_rows)
):

    a = qc_rows[i]

    a_hashes = [
        x["dhash"]
        for x in a["qc_frames"]
        if x["dhash"]
    ]

    if not a_hashes:
        continue

    for j in range(
        i + 1,
        len(qc_rows),
    ):

        b = qc_rows[j]

        # Neighbouring fragments from the SAME source are not
        # considered duplicates merely because visual continuity exists.
        same_source = (
            Path(
                a["source_path"]
            ).resolve()
            ==
            Path(
                b["source_path"]
            ).resolve()
        )

        if same_source:
            continue

        b_hashes = [
            x["dhash"]
            for x in b["qc_frames"]
            if x["dhash"]
        ]

        if not b_hashes:
            continue

        distances = []

        for ha in a_hashes:

            best = min(
                hamming(
                    ha,
                    hb,
                )
                for hb in b_hashes
            )

            distances.append(
                best
            )

        strong_matches = sum(
            1
            for value in distances
            if value <= DUP_HASH_DISTANCE
        )

        minimum = min(
            distances
        )

        average = (
            sum(distances)
            / len(distances)
        )

        if strong_matches >= 2:

            pair = {
                "a_review_number":
                    a["review_number"],

                "a_fragment_id":
                    a["fragment_id"],

                "a_filename":
                    a["filename"],

                "b_review_number":
                    b["review_number"],

                "b_fragment_id":
                    b["fragment_id"],

                "b_filename":
                    b["filename"],

                "strong_frame_matches":
                    strong_matches,

                "minimum_hamming":
                    minimum,

                "average_hamming":
                    round(
                        average,
                        3,
                    ),
            }

            duplicate_pairs.append(
                pair
            )

            a[
                "duplicate_candidates"
            ].append({
                "review_number":
                    b["review_number"],

                "fragment_id":
                    b["fragment_id"],

                "filename":
                    b["filename"],

                "strong_frame_matches":
                    strong_matches,

                "minimum_hamming":
                    minimum,
            })

            b[
                "duplicate_candidates"
            ].append({
                "review_number":
                    a["review_number"],

                "fragment_id":
                    a["fragment_id"],

                "filename":
                    a["filename"],

                "strong_frame_matches":
                    strong_matches,

                "minimum_hamming":
                    minimum,
            })

# Update state.

for row in qc_rows:

    if row["frames_ok"] < 3:

        row["qc_status"] = (
            "REVIEW_FRAME_EXTRACTION"
        )

    elif row["duplicate_candidates"]:

        row["qc_status"] = (
            "DUPLICATE_CANDIDATE"
        )

    else:

        row["qc_status"] = (
            "QC_VISUALLY_UNIQUE_CANDIDATE"
        )

print(
    "DUPLICATE PAIRS:",
    len(duplicate_pairs)
)

for pair in duplicate_pairs[:50]:

    print(
        f"#{pair['a_review_number']:03d} "
        f"<-> "
        f"#{pair['b_review_number']:03d} "
        f"| matches="
        f"{pair['strong_frame_matches']} "
        f"| min_hamming="
        f"{pair['minimum_hamming']} "
        f"| "
        f"{pair['a_filename']} "
        f"<-> "
        f"{pair['b_filename']}"
    )

# =============================================================================
# KNOWN MANUAL-QC EXAMPLES FROM CURRENT REVIEW
#
# These are NOT deleted.
# They are deliberately written as REVIEW_REQUIRED examples so they
# can become supervised editorial feedback instead of disappearing.
# =============================================================================

manual_review_numbers = {
    45:
        "TECHNICAL_OR_ARTICLE_INSERT",

    56:
        "INTERFACE_OR_CALL_SCREEN",

    115:
        "CHANNEL_IDENT_OR_BRAND_STING",
}

for row in qc_rows:

    number = row[
        "review_number"
    ]

    if number in manual_review_numbers:

        row[
            "manual_editorial_feedback"
        ] = {
            "state":
                "REVIEW_REQUIRED",

            "reason":
                manual_review_numbers[
                    number
                ],

            "source":
                "HUMAN_VISUAL_REVIEW",
        }

        row[
            "qc_status"
        ] = (
            "HUMAN_REVIEW_REQUIRED"
        )

# =============================================================================
# SUMMARY
# =============================================================================

status_counts = defaultdict(
    int
)

for row in qc_rows:

    status_counts[
        row["qc_status"]
    ] += 1

frames_total = (
    len(qc_rows)
    * 3
)

frames_ok = sum(
    row["frames_ok"]
    for row in qc_rows
)

print()
print("=" * 122)
print("QC SUMMARY")
print("=" * 122)

print(
    "FRAGMENTS       :",
    len(qc_rows),
)

print(
    "QC FRAMES       :",
    frames_total,
)

print(
    "FRAMES OK       :",
    frames_ok,
)

print(
    "FRAME FAILURES  :",
    frames_total - frames_ok,
)

print(
    "DUPLICATE PAIRS :",
    len(duplicate_pairs),
)

for key in sorted(
    status_counts
):

    print(
        f"{key:<34}: "
        f"{status_counts[key]}"
    )

# =============================================================================
# JSON REPORT
# =============================================================================

report_payload = {
    "schema":
        "atlas_zero.film10.editorial_fragment_qc.v1",

    "project_id":
        PROJECT_ID,

    "source_fragment_report":
        str(SOURCE_JSON),

    "hash_owner":
        "VisualAssetRegistrar._dhash_hex",

    "sampling_positions": [
        0.20,
        0.50,
        0.80,
    ],

    "duplicate_hash_distance":
        DUP_HASH_DISTANCE,

    "summary": {
        "fragments":
            len(qc_rows),

        "qc_frames":
            frames_total,

        "frames_ok":
            frames_ok,

        "frame_failures":
            frames_total
            - frames_ok,

        "duplicate_pairs":
            len(
                duplicate_pairs
            ),

        "status_counts":
            dict(status_counts),
    },

    "manual_review_examples":
        manual_review_numbers,

    "duplicate_pairs":
        duplicate_pairs,

    "fragments":
        qc_rows,

    "db_writes":
        False,

    "source_files_modified":
        False,

    "assignment":
        False,

    "render":
        False,

    "clip":
        False,

    "ocr":
        False,

    "paid_calls":
        False,
}

REPORT.write_text(
    json.dumps(
        report_payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

# =============================================================================
# HTML — THREE FRAMES PER FRAGMENT
# =============================================================================

cards = []

for row in qc_rows:

    images = []

    for frame in row[
        "qc_frames"
    ]:

        if (
            frame["ok"]
            and frame["path"]
        ):

            p = Path(
                frame["path"]
            )

            try:

                rel = p.relative_to(
                    OUT_DIR
                ).as_posix()

            except Exception:

                rel = p.as_uri()

            images.append(
                f"""
                <div class="sample">
                    <img src="{html.escape(rel)}">
                    <div class="sampletime">
                        {html.escape(frame["timestamp_tc"])}
                    </div>
                </div>
                """
            )

        else:

            images.append(
                """
                <div class="sample failed">
                    FRAME FAILED
                </div>
                """
            )

    duplicate_text = ""

    if row[
        "duplicate_candidates"
    ]:

        refs = ", ".join(
            "#"
            + str(x[
                "review_number"
            ]).zfill(3)
            for x in row[
                "duplicate_candidates"
            ][:12]
        )

        duplicate_text = (
            "<div class='duplicates'>"
            "Possible duplicate: "
            + html.escape(refs)
            + "</div>"
        )

    feedback = row.get(
        "manual_editorial_feedback"
    )

    feedback_html = ""

    if feedback:

        feedback_html = (
            "<div class='human'>"
            "HUMAN REVIEW: "
            + html.escape(
                feedback["reason"]
            )
            + "</div>"
        )

    cards.append(
        f"""
        <div class="card">

            <div class="head">
                <span>
                    #{row["review_number"]:03d}
                </span>

                <span class="status">
                    {html.escape(row["qc_status"])}
                </span>
            </div>

            <div class="frames">
                {''.join(images)}
            </div>

            <div class="body">

                <div class="time">
                    {html.escape(row["source_start_tc"])}
                    →
                    {html.escape(row["source_end_tc"])}
                </div>

                <div class="duration">
                    {row["duration_sec"]:.3f} sec
                </div>

                <div class="file">
                    {html.escape(row["filename"])}
                </div>

                <div class="id">
                    {html.escape(row["fragment_id"])}
                </div>

                {duplicate_text}
                {feedback_html}

            </div>

        </div>
        """
    )

html_doc = f"""
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<title>
FILM10 Editorial Fragment QC V1
</title>

<style>

body {{
    margin: 0;
    padding: 20px;
    background: #101010;
    color: #eee;
    font-family: Arial, sans-serif;
}}

h1 {{
    margin-top: 0;
}}

.summary {{
    padding: 15px;
    margin-bottom: 20px;
    background: #1b1b1b;
    border-radius: 8px;
    line-height: 1.6;
}}

.grid {{
    display: grid;
    grid-template-columns:
        repeat(2, minmax(0, 1fr));
    gap: 18px;
}}

.card {{
    background: #1b1b1b;
    border: 1px solid #444;
    border-radius: 8px;
    overflow: hidden;
}}

.head {{
    display: flex;
    justify-content: space-between;
    gap: 10px;
    padding: 12px;
    font-size: 23px;
    font-weight: bold;
}}

.status {{
    font-size: 12px;
    color: #bbb;
    align-self: center;
}}

.frames {{
    display: grid;
    grid-template-columns:
        repeat(3, minmax(0, 1fr));
    background: #000;
}}

.sample {{
    position: relative;
    min-height: 190px;
    border-right: 1px solid #333;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #000;
}}

.sample:last-child {{
    border-right: 0;
}}

.sample img {{
    width: 100%;
    height: 230px;
    object-fit: contain;
}}

.sampletime {{
    position: absolute;
    bottom: 4px;
    left: 4px;
    padding: 3px 5px;
    background: rgba(0,0,0,.72);
    font-size: 11px;
}}

.failed {{
    background: #310000;
}}

.body {{
    padding: 13px;
}}

.time {{
    font-size: 18px;
    font-weight: bold;
}}

.duration {{
    margin-top: 4px;
}}

.file {{
    margin-top: 8px;
    word-break: break-word;
}}

.id {{
    margin-top: 7px;
    color: #888;
    font-size: 11px;
}}

.duplicates {{
    margin-top: 10px;
    padding: 8px;
    background: #3b2e00;
}}

.human {{
    margin-top: 10px;
    padding: 8px;
    background: #4b1515;
    font-weight: bold;
}}

</style>

</head>

<body>

<h1>
ATLAS ZERO — FILM10 MULTIFRAME EDITORIAL QC
</h1>

<div class="summary">

<b>Fragments:</b>
{len(qc_rows)}
<br>

<b>Representative frames:</b>
{frames_ok}/{frames_total}
<br>

<b>Duplicate candidate pairs:</b>
{len(duplicate_pairs)}
<br>

<b>Sampling:</b>
20% / 50% / 80%
<br>

<b>Hash owner:</b>
VisualAssetRegistrar._dhash_hex

</div>

<div class="grid">

{''.join(cards)}

</div>

</body>

</html>
"""

HTML.write_text(
    html_doc,
    encoding="utf-8",
)

print()
print("=" * 122)
print("OUTPUT")
print("=" * 122)

print(
    "JSON :",
    REPORT,
)

print(
    "HTML :",
    HTML,
)

print()
print("=" * 122)
print("FILM10 MULTIFRAME QC V1: COMPLETE")
print("=" * 122)

print(
    "No fragment was automatically deleted."
)

print(
    "No source video was modified."
)

print(
    "No DB writes."
)

print(
    "No assignment."
)

print(
    "No render."
)

print(
    "No paid API calls."
)

# Open QC catalogue.

subprocess.Popen(
    [
        "cmd",
        "/c",
        "start",
        "",
        str(HTML),
    ],
    shell=False,
)

