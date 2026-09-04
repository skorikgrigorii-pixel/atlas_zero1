from pathlib import Path
import json
import subprocess
import math
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

QC_DIR = (
    PROJECT
    / "00_Production"
    / "editorial_fragment_qc_v1"
)

QC_JSON = (
    QC_DIR
    / "FILM10_EDITORIAL_FRAGMENT_QC_V1.json"
)

FRAGMENT_JSON = (
    PROJECT
    / "00_Production"
    / "editorial_fragmenter_v2"
    / "FILM10_EDITORIAL_FRAGMENTS_V2.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "editorial_pdf_review_v1"
)

FRAME_DIR = OUT_DIR / "_frames"

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

FRAME_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

PDF = (
    OUT_DIR
    / "FILM10_EDITORIAL_QC_FULL_REVIEW_V1.pdf"
)

MANIFEST = (
    OUT_DIR
    / "FILM10_EDITORIAL_QC_FULL_REVIEW_V1.json"
)

print("=" * 122)
print("ATLAS ZERO - FILM10 FULL EDITORIAL QC PDF BUILDER V1")
print("=" * 122)

print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("FILM RENDER: NO")

# =============================================================================
# FONTS
# =============================================================================

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
]

BOLD_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\segoeuib.ttf"),
]

font_path = next(
    (p for p in FONT_CANDIDATES if p.exists()),
    None,
)

bold_path = next(
    (p for p in BOLD_CANDIDATES if p.exists()),
    font_path,
)

if font_path:
    FONT_SMALL = ImageFont.truetype(
        str(font_path),
        21,
    )

    FONT_MEDIUM = ImageFont.truetype(
        str(font_path),
        25,
    )

    FONT_LARGE = ImageFont.truetype(
        str(bold_path),
        31,
    )

    FONT_HEADER = ImageFont.truetype(
        str(bold_path),
        38,
    )

else:
    FONT_SMALL = ImageFont.load_default()
    FONT_MEDIUM = ImageFont.load_default()
    FONT_LARGE = ImageFont.load_default()
    FONT_HEADER = ImageFont.load_default()

# =============================================================================
# LOAD DATA
# =============================================================================

source_mode = None
rows = []

if QC_JSON.exists():

    print()
    print("Using existing multiframes QC:")
    print(QC_JSON)

    data = json.loads(
        QC_JSON.read_text(
            encoding="utf-8"
        )
    )

    rows = data.get(
        "fragments",
        []
    )

    source_mode = "QC_V1"

else:

    if not FRAGMENT_JSON.exists():
        raise FileNotFoundError(
            "Neither QC nor fragment JSON exists."
        )

    print()
    print("QC JSON not found.")
    print("Building PDF directly from editorial fragments:")
    print(FRAGMENT_JSON)

    data = json.loads(
        FRAGMENT_JSON.read_text(
            encoding="utf-8"
        )
    )

    fragments = data.get(
        "fragments",
        []
    )

    for index, item in enumerate(
        fragments,
        1,
    ):

        rows.append({
            **item,
            "review_number": index,
            "qc_status": "NOT_YET_QC",
            "duplicate_candidates": [],
            "qc_frames": [],
        })

    source_mode = "FRAGMENTS_V2"

if not rows:
    raise RuntimeError(
        "No editorial fragments available."
    )

print()
print("FRAGMENTS:", len(rows))
print("SOURCE MODE:", source_mode)

# =============================================================================
# HELPERS
# =============================================================================

def tc(sec):

    sec = max(
        0.0,
        float(sec),
    )

    m = int(
        sec // 60
    )

    s = (
        sec
        - m * 60
    )

    return (
        f"{m:02d}:"
        f"{s:06.3f}"
    )


def frame_times(
    start,
    end,
):

    duration = (
        end
        - start
    )

    result = []

    for fraction in (
        0.20,
        0.50,
        0.80,
    ):

        value = (
            start
            + duration * fraction
        )

        value = max(
            start + 0.05,
            min(
                end - 0.05,
                value,
            ),
        )

        result.append(
            value
        )

    return result


def extract_frame(
    source,
    timestamp,
    output,
):

    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(source),
            "-frames:v", "1",
            "-vf",
            (
                "scale=720:-2:"
                "force_original_aspect_ratio=decrease"
            ),
            "-q:v", "3",
            str(output),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )

    return (
        result.returncode == 0
        and output.exists()
        and output.stat().st_size > 0
    )


def fit_image(
    image,
    width,
    height,
):

    image = image.convert(
        "RGB"
    )

    fitted = ImageOps.contain(
        image,
        (
            width,
            height,
        ),
        method=Image.Resampling.LANCZOS,
    )

    canvas = Image.new(
        "RGB",
        (
            width,
            height,
        ),
        (0, 0, 0),
    )

    x = (
        width
        - fitted.width
    ) // 2

    y = (
        height
        - fitted.height
    ) // 2

    canvas.paste(
        fitted,
        (
            x,
            y,
        ),
    )

    return canvas


def wrapped(
    value,
    width,
):

    value = str(
        value or ""
    )

    return "\n".join(
        textwrap.wrap(
            value,
            width=width,
            break_long_words=True,
            break_on_hyphens=True,
        )
    )


# =============================================================================
# ENSURE EVERY FRAGMENT HAS 3 QC FRAMES
# =============================================================================

print()
print("=" * 122)
print("PREPARING 20% / 50% / 80% QC FRAMES")
print("=" * 122)

prepared = []

for index, row in enumerate(
    rows,
    1,
):

    start = float(
        row["source_start"]
    )

    end = float(
        row["source_end"]
    )

    source_path = (
        row.get("source_path")
        or row.get("path")
    )

    if not source_path:
        raise RuntimeError(
            f"Fragment #{index} has no source path."
        )

    source = Path(
        source_path
    )

    if not source.exists():
        raise FileNotFoundError(
            source
        )

    fragment_id = str(
        row["fragment_id"]
    )

    existing = (
        row.get("qc_frames")
        or []
    )

    existing_by_sample = {
        int(frame.get("sample_index")):
        frame

        for frame in existing

        if frame.get("sample_index")
    }

    times = frame_times(
        start,
        end,
    )

    qc_frames = []

    for sample_index, timestamp in enumerate(
        times,
        1,
    ):

        existing_frame = (
            existing_by_sample.get(
                sample_index
            )
        )

        existing_path = None

        if existing_frame:
            candidate = (
                existing_frame.get(
                    "path"
                )
            )

            if candidate:
                p = Path(
                    candidate
                )

                if p.exists():
                    existing_path = p

        if existing_path is not None:

            frame_path = (
                existing_path
            )

            ok = True

        else:

            frame_path = (
                FRAME_DIR
                / (
                    f"{index:03d}_"
                    f"{fragment_id}_"
                    f"s{sample_index}.jpg"
                )
            )

            ok = extract_frame(
                source,
                timestamp,
                frame_path,
            )

        qc_frames.append({
            "sample_index":
                sample_index,

            "fraction":
                (
                    0.20
                    if sample_index == 1
                    else 0.50
                    if sample_index == 2
                    else 0.80
                ),

            "timestamp_sec":
                round(
                    timestamp,
                    3,
                ),

            "timestamp_tc":
                tc(
                    timestamp
                ),

            "path":
                str(
                    frame_path
                )
                if ok
                else None,

            "ok":
                ok,
        })

    item = dict(
        row
    )

    item[
        "review_number"
    ] = int(
        row.get(
            "review_number",
            index,
        )
    )

    item[
        "qc_frames"
    ] = qc_frames

    prepared.append(
        item
    )

    good = sum(
        1
        for f in qc_frames
        if f["ok"]
    )

    print(
        f"{index:03d}/"
        f"{len(rows):03d} | "
        f"{good}/3 | "
        f"{start:8.3f}-"
        f"{end:8.3f} | "
        f"{source.name}"
    )

# =============================================================================
# PAGE LAYOUT
# =============================================================================

PAGE_W = 2200
PAGE_H = 1550

MARGIN = 55
HEADER_H = 110

FRAGMENTS_PER_PAGE = 3

CONTENT_H = (
    PAGE_H
    - HEADER_H
    - MARGIN * 2
)

ROW_H = (
    CONTENT_H
    // FRAGMENTS_PER_PAGE
)

FRAME_GAP = 14

TEXT_W = 585

FRAMES_AREA_W = (
    PAGE_W
    - MARGIN * 2
    - TEXT_W
    - 25
)

FRAME_W = (
    FRAMES_AREA_W
    - FRAME_GAP * 2
) // 3

FRAME_H = 315

pages = []

total_pages = math.ceil(
    len(prepared)
    / FRAGMENTS_PER_PAGE
)

print()
print("=" * 122)
print("BUILDING PDF PAGES")
print("=" * 122)

for page_index in range(
    total_pages
):

    page = Image.new(
        "RGB",
        (
            PAGE_W,
            PAGE_H,
        ),
        (246, 246, 246),
    )

    draw = ImageDraw.Draw(
        page
    )

    draw.text(
        (
            MARGIN,
            30,
        ),
        (
            "ATLAS ZERO - FILM10 "
            "EDITORIAL QC FULL REVIEW"
        ),
        font=FONT_HEADER,
        fill=(20, 20, 20),
    )

    page_label = (
        f"Page {page_index + 1}/{total_pages}"
    )

    bbox = draw.textbbox(
        (
            0,
            0,
        ),
        page_label,
        font=FONT_MEDIUM,
    )

    draw.text(
        (
            PAGE_W
            - MARGIN
            - (
                bbox[2]
                - bbox[0]
            ),
            42,
        ),
        page_label,
        font=FONT_MEDIUM,
        fill=(70, 70, 70),
    )

    for local_row in range(
        FRAGMENTS_PER_PAGE
    ):

        global_index = (
            page_index
            * FRAGMENTS_PER_PAGE
            + local_row
        )

        if global_index >= len(
            prepared
        ):
            break

        item = prepared[
            global_index
        ]

        y0 = (
            MARGIN
            + HEADER_H
            + local_row
            * ROW_H
        )

        if local_row > 0:

            draw.line(
                (
                    MARGIN,
                    y0,
                    PAGE_W
                    - MARGIN,
                    y0,
                ),
                fill=(180, 180, 180),
                width=3,
            )

        number = int(
            item.get(
                "review_number",
                global_index + 1,
            )
        )

        status = str(
            item.get(
                "qc_status",
                "UNCLASSIFIED",
            )
        )

        start = float(
            item["source_start"]
        )

        end = float(
            item["source_end"]
        )

        duration = float(
            item.get(
                "duration_sec",
                end - start,
            )
        )

        filename = str(
            item.get(
                "filename",
                Path(
                    item["source_path"]
                ).name,
            )
        )

        fragment_id = str(
            item["fragment_id"]
        )

        duplicate_candidates = (
            item.get(
                "duplicate_candidates"
            )
            or []
        )

        duplicate_refs = []

        for candidate in (
            duplicate_candidates[:8]
        ):

            if isinstance(
                candidate,
                dict,
            ):

                ref = candidate.get(
                    "review_number"
                )

                if ref is not None:
                    duplicate_refs.append(
                        f"#{int(ref):03d}"
                    )

        # -------------------------------------------------------------
        # TEXT COLUMN
        # -------------------------------------------------------------

        text_x = MARGIN

        draw.text(
            (
                text_x,
                y0 + 20,
            ),
            f"#{number:03d}",
            font=FONT_LARGE,
            fill=(10, 10, 10),
        )

        draw.text(
            (
                text_x + 115,
                y0 + 26,
            ),
            status,
            font=FONT_SMALL,
            fill=(100, 30, 30)
            if "REVIEW" in status
            else (55, 55, 55),
        )

        draw.text(
            (
                text_x,
                y0 + 72,
            ),
            (
                f"{tc(start)} -> "
                f"{tc(end)}"
            ),
            font=FONT_MEDIUM,
            fill=(15, 15, 15),
        )

        draw.text(
            (
                text_x,
                y0 + 110,
            ),
            (
                f"Duration: "
                f"{duration:.3f} sec"
            ),
            font=FONT_SMALL,
            fill=(40, 40, 40),
        )

        draw.multiline_text(
            (
                text_x,
                y0 + 150,
            ),
            wrapped(
                filename,
                42,
            ),
            font=FONT_SMALL,
            fill=(25, 25, 25),
            spacing=4,
        )

        draw.multiline_text(
            (
                text_x,
                y0 + 270,
            ),
            wrapped(
                fragment_id,
                44,
            ),
            font=FONT_SMALL,
            fill=(95, 95, 95),
            spacing=4,
        )

        if duplicate_refs:

            draw.multiline_text(
                (
                    text_x,
                    y0 + 325,
                ),
                (
                    "Duplicate candidates: "
                    + ", ".join(
                        duplicate_refs
                    )
                ),
                font=FONT_SMALL,
                fill=(130, 70, 0),
                spacing=4,
            )

        feedback = (
            item.get(
                "manual_editorial_feedback"
            )
        )

        if feedback:

            reason = str(
                feedback.get(
                    "reason",
                    "HUMAN REVIEW",
                )
            )

            draw.multiline_text(
                (
                    text_x,
                    y0 + 380,
                ),
                wrapped(
                    "HUMAN: "
                    + reason,
                    40,
                ),
                font=FONT_SMALL,
                fill=(160, 20, 20),
                spacing=4,
            )

        # -------------------------------------------------------------
        # 3 QC FRAMES
        # -------------------------------------------------------------

        frame_start_x = (
            MARGIN
            + TEXT_W
            + 25
        )

        for fi, frame in enumerate(
            item["qc_frames"]
        ):

            x = (
                frame_start_x
                + fi
                * (
                    FRAME_W
                    + FRAME_GAP
                )
            )

            y = (
                y0
                + 32
            )

            if (
                frame.get(
                    "ok"
                )
                and frame.get(
                    "path"
                )
                and Path(
                    frame["path"]
                ).exists()
            ):

                with Image.open(
                    frame["path"]
                ) as source_image:

                    rendered = fit_image(
                        source_image,
                        FRAME_W,
                        FRAME_H,
                    )

                page.paste(
                    rendered,
                    (
                        x,
                        y,
                    ),
                )

            else:

                draw.rectangle(
                    (
                        x,
                        y,
                        x + FRAME_W,
                        y + FRAME_H,
                    ),
                    fill=(80, 0, 0),
                )

                draw.text(
                    (
                        x + 40,
                        y + 120,
                    ),
                    "FRAME FAILED",
                    font=FONT_MEDIUM,
                    fill=(255, 255, 255),
                )

            label = (
                "20%"
                if fi == 0
                else "50%"
                if fi == 1
                else "80%"
            )

            timestamp_tc = (
                frame.get(
                    "timestamp_tc"
                )
                or ""
            )

            draw.text(
                (
                    x,
                    y + FRAME_H + 8,
                ),
                (
                    f"{label}  "
                    f"{timestamp_tc}"
                ),
                font=FONT_SMALL,
                fill=(20, 20, 20),
            )

    pages.append(
        page
    )

    print(
        f"PAGE "
        f"{page_index + 1:03d}/"
        f"{total_pages:03d}"
    )

# =============================================================================
# SAVE COMPRESSED MULTIPAGE PDF
# =============================================================================

print()
print("=" * 122)
print("WRITING PDF")
print("=" * 122)

if not pages:
    raise RuntimeError(
        "No PDF pages generated."
    )

# Pillow multipage PDF.
# Resolution and quality keep the catalogue readable
# without creating an unnecessarily huge upload.

pages[0].save(
    PDF,
    "PDF",
    resolution=125.0,
    save_all=True,
    append_images=pages[1:],
    quality=82,
    optimize=True,
)

if not PDF.exists():
    raise RuntimeError(
        "PDF was not created."
    )

size_mb = (
    PDF.stat().st_size
    / 1024
    / 1024
)

# =============================================================================
# MANIFEST
# =============================================================================

manifest = {
    "schema":
        "atlas_zero.film10.editorial_qc_pdf_review.v1",

    "project_id":
        PROJECT_ID,

    "source_mode":
        source_mode,

    "fragment_count":
        len(prepared),

    "frames_per_fragment":
        3,

    "sampling":
        [
            "20%",
            "50%",
            "80%",
        ],

    "fragments_per_page":
        FRAGMENTS_PER_PAGE,

    "pages":
        total_pages,

    "pdf":
        str(PDF),

    "pdf_size_mb":
        round(
            size_mb,
            3,
        ),

    "fragments":
        [
            {
                "review_number":
                    row["review_number"],

                "fragment_id":
                    row["fragment_id"],

                "filename":
                    row.get(
                        "filename"
                    ),

                "source_start":
                    row["source_start"],

                "source_end":
                    row["source_end"],

                "duration_sec":
                    row.get(
                        "duration_sec"
                    ),

                "qc_status":
                    row.get(
                        "qc_status"
                    ),

                "duplicate_candidates":
                    row.get(
                        "duplicate_candidates",
                        []
                    ),
            }
            for row in prepared
        ],

    "db_writes":
        False,

    "assignment":
        False,

    "render":
        False,

    "paid_calls":
        False,
}

MANIFEST.write_text(
    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("=" * 122)
print("FILM10 FULL QC PDF: PASS")
print("=" * 122)

print("FRAGMENTS :", len(prepared))
print("PAGES     :", total_pages)
print("PDF SIZE  :", f"{size_mb:.2f} MB")
print("PDF       :", PDF)
print("MANIFEST  :", MANIFEST)

print()
print("No DB writes.")
print("No assignment.")
print("No film render.")
print("No paid API calls.")

# Open folder with final PDF selected.
subprocess.Popen(
    [
        "explorer",
        "/select,",
        str(PDF),
    ]
)

