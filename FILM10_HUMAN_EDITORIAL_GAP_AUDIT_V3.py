from pathlib import Path
import json
import html
import sys
from collections import Counter, defaultdict

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

TIMELINE = (
    PROJECT
    / "00_Production"
    / "human_editorial_assignment_v2"
    / "FILM10_HUMAN_EDITORIAL_TIMELINE_V2.json"
)

GAPS = (
    PROJECT
    / "00_Production"
    / "human_editorial_assignment_v2"
    / "FILM10_HUMAN_EDITORIAL_GAPS_V2.json"
)

OUT_DIR = (
    PROJECT
    / "00_Production"
    / "human_editorial_gap_audit_v3"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

JSON_OUT = (
    OUT_DIR
    / "FILM10_GAP_EDITORIAL_AUDIT_V3.json"
)

HTML_OUT = (
    OUT_DIR
    / "FILM10_GAP_EDITORIAL_AUDIT_V3.html"
)

TXT_OUT = (
    OUT_DIR
    / "FILM10_GAP_EDITORIAL_AUDIT_V3.txt"
)

PDF_OUT = (
    OUT_DIR
    / "FILM10_GAP_EDITORIAL_AUDIT_V3.pdf"
)

print("=" * 126)
print("ATLAS ZERO - FILM10 HUMAN EDITORIAL GAP AUDIT V3 + PDF")
print("=" * 126)

print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("ASSIGNMENT : NO")
print("RENDER     : NO")
print("PDF        : YES")

for path in (
    TIMELINE,
    GAPS,
):
    if not path.exists():
        raise FileNotFoundError(path)

# =============================================================================
# LOAD
# =============================================================================

timeline_payload = json.loads(
    TIMELINE.read_text(
        encoding="utf-8"
    )
)

gaps_payload = json.loads(
    GAPS.read_text(
        encoding="utf-8"
    )
)

timeline = timeline_payload.get(
    "timeline",
    []
)

gaps = gaps_payload.get(
    "gaps",
    []
)

if len(timeline) != 260:
    raise RuntimeError(
        f"Expected 260 timeline rows, got {len(timeline)}"
    )

if not gaps:
    raise RuntimeError(
        "Gap list is empty."
    )

print()
print("TIMELINE ROWS :", len(timeline))
print("GAPS          :", len(gaps))

# =============================================================================
# INDEX
# =============================================================================

by_index = {
    int(row["shot_index"]): row
    for row in timeline
}


def compact_visual(row):

    if not row:
        return None

    if not row.get("asset_path"):

        return {
            "shot_index":
                row.get("shot_index"),

            "status":
                "VISUAL_GAP",

            "target_category":
                row.get("target_category"),
        }

    return {
        "shot_index":
            row.get("shot_index"),

        "status":
            row.get("status"),

        "target_category":
            row.get("target_category"),

        "asset_type":
            row.get("asset_type"),

        "asset_path":
            row.get("asset_path"),

        "fragment_review_number":
            row.get("fragment_review_number"),

        "semantic_category":
            row.get("semantic_category"),

        "source_start":
            row.get("source_start"),

        "source_end":
            row.get("source_end"),
    }


def find_prev_assigned(shot_index):

    for idx in range(
        shot_index - 1,
        0,
        -1,
    ):

        row = by_index.get(idx)

        if (
            row
            and row.get("asset_path")
        ):
            return row

    return None


def find_next_assigned(shot_index):

    for idx in range(
        shot_index + 1,
        261,
    ):

        row = by_index.get(idx)

        if (
            row
            and row.get("asset_path")
        ):
            return row

    return None


# =============================================================================
# EDITORIAL GAP POLICY
# =============================================================================

def decision_for(
    target,
    narration,
    visual_need,
):

    if target == "SCHOOL":

        return {
            "decision":
                "EXACT_REAL_VISUAL_REQUIRED",

            "priority":
                "CRITICAL",

            "action":
                "SEARCH_THEN_GENERATE_IF_NEEDED",

            "reason":
                "School narration is specific. Random Nepal footage would be misleading.",
        }

    if target == "HYDROPOWER":

        return {
            "decision":
                "EXACT_REAL_VISUAL_REQUIRED",

            "priority":
                "CRITICAL",

            "action":
                "SEARCH_THEN_GENERATE_IF_NEEDED",

            "reason":
                "Hydropower, tunnel and worker narration requires specific infrastructure or rescue imagery.",
        }

    if target == "GLACIER_COLLAPSE":

        return {
            "decision":
                "REUSE_SAFE",

            "priority":
                "HIGH",

            "action":
                "REUSE_UNUSED_COLLAPSE_RANGE_OR_GENERATE",

            "reason":
                "Strong real collapse footage already exists. Prefer unused source range.",
        }

    if target == "GYIRONG_MUDSLIDE":

        return {
            "decision":
                "REUSE_SAFE",

            "priority":
                "HIGH",

            "action":
                "REUSE_UNUSED_GYIRONG_RANGE",

            "reason":
                "Several human-approved Gyirong sequences exist. Prefer unused source ranges.",
        }

    if target == "GLACIER_CONTEXT":

        return {
            "decision":
                "STATIC_OK",

            "priority":
                "MEDIUM",

            "action":
                "USE_STATIC_OR_UNUSED_GLACIER_RANGE",

            "reason":
                "Context narration can use Langtang, ISS, glacier stills or unused mountain footage.",
        }

    if target == "AFTERMATH":

        return {
            "decision":
                "REUSE_SAFE",

            "priority":
                "LOW",

            "action":
                "REUSE_UNUSED_AFTERMATH_RANGE",

            "reason":
                "Generic aftermath can use existing human-approved aftermath footage.",
        }

    return {
        "decision":
            "SEARCH",

        "priority":
            "MEDIUM",

        "action":
            "SEARCH_OR_GENERATE",

        "reason":
            "No safe existing editorial category was established.",
    }


# =============================================================================
# BUILD AUDIT
# =============================================================================

audit = []

decision_counts = Counter()
target_counts = Counter()
priority_counts = Counter()

duration_by_target = defaultdict(float)
duration_by_decision = defaultdict(float)

for gap in gaps:

    shot_index = int(
        gap["shot_index"]
    )

    row = by_index.get(
        shot_index
    )

    if row is None:
        raise RuntimeError(
            f"Gap shot {shot_index} missing from timeline."
        )

    target = str(
        gap.get("target_category")
        or row.get("target_category")
        or "UNRESOLVED"
    )

    narration = str(
        gap.get("narration")
        or row.get("narration")
        or ""
    )

    visual_need = str(
        gap.get("visual_need")
        or row.get("visual_need")
        or ""
    )

    duration = float(
        gap.get("duration_sec")
        or (
            float(gap["timeline_end"])
            - float(gap["timeline_start"])
        )
    )

    decision = decision_for(
        target,
        narration,
        visual_need,
    )

    previous_row = find_prev_assigned(
        shot_index
    )

    next_row = find_next_assigned(
        shot_index
    )

    item = {
        "shot_index":
            shot_index,

        "shot_id":
            gap.get("shot_id"),

        "timeline_start":
            gap.get("timeline_start"),

        "timeline_end":
            gap.get("timeline_end"),

        "duration_sec":
            round(duration, 3),

        "target_category":
            target,

        "visual_need":
            visual_need,

        "story_goal":
            gap.get("story_goal")
            or row.get("story_goal"),

        "narration":
            narration,

        "current_reason":
            gap.get("reason")
            or row.get("selection_reason"),

        "decision":
            decision["decision"],

        "priority":
            decision["priority"],

        "recommended_action":
            decision["action"],

        "decision_reason":
            decision["reason"],

        "previous_assigned":
            compact_visual(
                previous_row
            ),

        "next_assigned":
            compact_visual(
                next_row
            ),
    }

    audit.append(item)

    decision_counts[
        item["decision"]
    ] += 1

    target_counts[
        target
    ] += 1

    priority_counts[
        item["priority"]
    ] += 1

    duration_by_target[
        target
    ] += duration

    duration_by_decision[
        item["decision"]
    ] += duration


TOTAL_GAP_SEC = sum(
    item["duration_sec"]
    for item in audit
)

# =============================================================================
# CONSOLE SUMMARY
# =============================================================================

print()
print("=" * 126)
print("GAP SUMMARY BY TARGET")
print("=" * 126)

for target, count in (
    target_counts.most_common()
):

    print(
        f"{target:<28} "
        f"shots={count:3d} "
        f"time={duration_by_target[target]:8.3f}s"
    )

print()
print("=" * 126)
print("GAP SUMMARY BY DECISION")
print("=" * 126)

for decision, count in (
    decision_counts.most_common()
):

    print(
        f"{decision:<30} "
        f"shots={count:3d} "
        f"time={duration_by_decision[decision]:8.3f}s"
    )

print()
print("=" * 126)
print("PRIORITY SUMMARY")
print("=" * 126)

for priority in (
    "CRITICAL",
    "HIGH",
    "MEDIUM",
    "LOW",
):

    print(
        f"{priority:<12} "
        f"shots={priority_counts.get(priority, 0):3d}"
    )


# =============================================================================
# JSON
# =============================================================================

output_payload = {
    "schema":
        "atlas_zero.film10.human_editorial_gap_audit.v3",

    "project_id":
        PROJECT_ID,

    "gap_count":
        len(audit),

    "gap_duration_sec":
        round(
            TOTAL_GAP_SEC,
            3,
        ),

    "target_counts":
        dict(target_counts),

    "decision_counts":
        dict(decision_counts),

    "priority_counts":
        dict(priority_counts),

    "duration_by_target_sec":
        {
            key: round(value, 3)
            for key, value
            in duration_by_target.items()
        },

    "duration_by_decision_sec":
        {
            key: round(value, 3)
            for key, value
            in duration_by_decision.items()
        },

    "gaps":
        audit,

    "outputs": {
        "json":
            str(JSON_OUT),

        "txt":
            str(TXT_OUT),

        "html":
            str(HTML_OUT),

        "pdf":
            str(PDF_OUT),
    },

    "db_writes":
        False,

    "assignment":
        False,

    "render":
        False,

    "paid_calls":
        False,
}

JSON_OUT.write_text(
    json.dumps(
        output_payload,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


# =============================================================================
# TXT
# =============================================================================

txt_lines = []

txt_lines.extend([
    "ATLAS ZERO - FILM10 GAP EDITORIAL AUDIT V3",
    "=" * 100,
    f"GAPS: {len(audit)}",
    f"GAP TIME: {TOTAL_GAP_SEC:.3f}s",
    "",
])

for item in audit:

    txt_lines.extend([
        "",
        "=" * 100,
        f"SHOT {item['shot_index']:03d}",
        f"TARGET   : {item['target_category']}",
        f"DURATION : {item['duration_sec']:.3f}s",
        f"PRIORITY : {item['priority']}",
        f"DECISION : {item['decision']}",
        f"ACTION   : {item['recommended_action']}",
        "",
        f"VISUAL NEED:",
        item["visual_need"],
        "",
        f"NARRATION:",
        item["narration"],
        "",
        f"REASON:",
        item["decision_reason"],
    ])

TXT_OUT.write_text(
    "\n".join(txt_lines),
    encoding="utf-8",
)


# =============================================================================
# HTML
# =============================================================================

def visual_text(visual):

    if not visual:
        return "NONE"

    if visual.get(
        "asset_path"
    ):

        path = Path(
            visual["asset_path"]
        )

        result = (
            f"shot #{int(visual['shot_index']):03d}"
            f" | {visual.get('asset_type')}"
            f" | {path.name}"
        )

        if (
            visual.get("source_start")
            is not None
            and visual.get("source_end")
            is not None
        ):

            result += (
                f" | {float(visual['source_start']):.3f}"
                f"-{float(visual['source_end']):.3f}"
            )

        return result

    return (
        f"shot #{int(visual['shot_index']):03d}"
        " | GAP"
    )


cards = []

for item in audit:

    priority_class = (
        "critical"
        if item["priority"] == "CRITICAL"
        else "high"
        if item["priority"] == "HIGH"
        else "medium"
        if item["priority"] == "MEDIUM"
        else "low"
    )

    cards.append(
        f"""
        <div class="card {priority_class}">

            <div class="head">
                <span>
                    SHOT #{item["shot_index"]:03d}
                </span>

                <span>
                    {html.escape(item["target_category"])}
                </span>
            </div>

            <div class="meta">
                {item["duration_sec"]:.3f}s |
                {html.escape(item["priority"])} |
                {html.escape(item["decision"])}
            </div>

            <div class="section">
                <b>Narration</b><br>
                {html.escape(item["narration"])}
            </div>

            <div class="section">
                <b>Visual need</b><br>
                {html.escape(item["visual_need"])}
            </div>

            <div class="section action">
                <b>Action</b><br>
                {html.escape(item["recommended_action"])}
            </div>

            <div class="section">
                <b>Why</b><br>
                {html.escape(item["decision_reason"])}
            </div>

            <div class="neighbors">

                <div>
                    <b>Previous assigned</b><br>
                    {html.escape(
                        visual_text(
                            item["previous_assigned"]
                        )
                    )}
                </div>

                <div>
                    <b>Next assigned</b><br>
                    {html.escape(
                        visual_text(
                            item["next_assigned"]
                        )
                    )}
                </div>

            </div>

        </div>
        """
    )

html_doc = f"""
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<title>FILM10 Gap Editorial Audit V3</title>

<style>

body {{
    margin: 0;
    padding: 24px;
    background: #111;
    color: #eee;
    font-family: Arial, sans-serif;
}}

h1 {{
    margin-top: 0;
}}

.summary {{
    background: #1c1c1c;
    padding: 18px;
    margin-bottom: 20px;
    border-radius: 8px;
    line-height: 1.6;
}}

.grid {{
    display: grid;
    grid-template-columns:
        repeat(2, minmax(0, 1fr));
    gap: 16px;
}}

.card {{
    background: #1b1b1b;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 14px;
}}

.card.critical {{
    border-left: 8px solid #a22;
}}

.card.high {{
    border-left: 8px solid #b76;
}}

.card.medium {{
    border-left: 8px solid #777;
}}

.card.low {{
    border-left: 8px solid #444;
}}

.head {{
    display: flex;
    justify-content: space-between;
    font-size: 20px;
    font-weight: bold;
    gap: 12px;
}}

.meta {{
    margin-top: 7px;
    color: #bbb;
}}

.section {{
    margin-top: 14px;
    line-height: 1.4;
}}

.action {{
    background: #252525;
    padding: 10px;
}}

.neighbors {{
    margin-top: 14px;
    display: grid;
    grid-template-columns:
        1fr 1fr;
    gap: 10px;
    color: #aaa;
}}

</style>

</head>

<body>

<h1>
ATLAS ZERO - FILM10 GAP EDITORIAL AUDIT V3
</h1>

<div class="summary">

<b>Gaps:</b>
{len(audit)}
<br>

<b>Total gap time:</b>
{TOTAL_GAP_SEC:.3f}s
<br>

<b>Critical:</b>
{priority_counts.get("CRITICAL", 0)}
<br>

<b>High:</b>
{priority_counts.get("HIGH", 0)}
<br>

<b>Medium:</b>
{priority_counts.get("MEDIUM", 0)}
<br>

<b>Low:</b>
{priority_counts.get("LOW", 0)}

</div>

<div class="grid">

{''.join(cards)}

</div>

</body>

</html>
"""

HTML_OUT.write_text(
    html_doc,
    encoding="utf-8",
)


# =============================================================================
# PDF BUILDER
# =============================================================================

print()
print("=" * 126)
print("BUILDING PDF")
print("=" * 126)

try:

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import (
        getSampleStyleSheet,
        ParagraphStyle,
    )
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
        KeepTogether,
    )

except Exception as exc:

    raise RuntimeError(
        "ReportLab is required for PDF generation. "
        "Install with: pip install reportlab"
    ) from exc


# -----------------------------------------------------------------------------
# Unicode font discovery
# -----------------------------------------------------------------------------

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
    Path(r"C:\Windows\Fonts\tahoma.ttf"),
]

FONT_BOLD_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\segoeuib.ttf"),
    Path(r"C:\Windows\Fonts\calibrib.ttf"),
    Path(r"C:\Windows\Fonts\tahomabd.ttf"),
]

font_regular = next(
    (
        path
        for path in FONT_CANDIDATES
        if path.exists()
    ),
    None,
)

font_bold = next(
    (
        path
        for path in FONT_BOLD_CANDIDATES
        if path.exists()
    ),
    None,
)

if not font_regular:
    raise RuntimeError(
        "Could not find a Windows Unicode font."
    )

if not font_bold:
    font_bold = font_regular

pdfmetrics.registerFont(
    TTFont(
        "AZRegular",
        str(font_regular),
    )
)

pdfmetrics.registerFont(
    TTFont(
        "AZBold",
        str(font_bold),
    )
)

print(
    "PDF FONT REGULAR:",
    font_regular
)

print(
    "PDF FONT BOLD   :",
    font_bold
)


# -----------------------------------------------------------------------------
# Document
# -----------------------------------------------------------------------------

doc = SimpleDocTemplate(
    str(PDF_OUT),
    pagesize=A4,
    rightMargin=14 * mm,
    leftMargin=14 * mm,
    topMargin=13 * mm,
    bottomMargin=14 * mm,
    title="ATLAS ZERO FILM10 Gap Editorial Audit V3",
    author="ATLAS ZERO",
)

PAGE_W, PAGE_H = A4

usable_width = (
    PAGE_W
    - doc.leftMargin
    - doc.rightMargin
)


# -----------------------------------------------------------------------------
# Styles
# -----------------------------------------------------------------------------

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "AZTitle",
    parent=styles["Title"],
    fontName="AZBold",
    fontSize=18,
    leading=22,
    alignment=TA_CENTER,
    spaceAfter=10,
)

subtitle_style = ParagraphStyle(
    "AZSubtitle",
    parent=styles["Normal"],
    fontName="AZRegular",
    fontSize=9,
    leading=12,
    textColor=colors.HexColor("#444444"),
    alignment=TA_CENTER,
    spaceAfter=14,
)

section_style = ParagraphStyle(
    "AZSection",
    parent=styles["Heading2"],
    fontName="AZBold",
    fontSize=13,
    leading=16,
    spaceBefore=8,
    spaceAfter=7,
)

card_title_style = ParagraphStyle(
    "AZCardTitle",
    parent=styles["Heading3"],
    fontName="AZBold",
    fontSize=11,
    leading=14,
    spaceAfter=3,
)

normal_style = ParagraphStyle(
    "AZNormal",
    parent=styles["Normal"],
    fontName="AZRegular",
    fontSize=8.4,
    leading=11,
    spaceAfter=4,
)

small_style = ParagraphStyle(
    "AZSmall",
    parent=styles["Normal"],
    fontName="AZRegular",
    fontSize=7.3,
    leading=9.2,
    textColor=colors.HexColor("#555555"),
)

label_style = ParagraphStyle(
    "AZLabel",
    parent=styles["Normal"],
    fontName="AZBold",
    fontSize=8.3,
    leading=10.5,
)

action_style = ParagraphStyle(
    "AZAction",
    parent=styles["Normal"],
    fontName="AZBold",
    fontSize=8.5,
    leading=11,
)


def esc(value):

    return html.escape(
        str(
            value
            if value is not None
            else ""
        )
    )


def pdf_visual_text(
    visual
):

    if not visual:
        return "NONE"

    if visual.get(
        "asset_path"
    ):

        name = Path(
            visual["asset_path"]
        ).name

        text = (
            f"Shot #{int(visual['shot_index']):03d} | "
            f"{visual.get('asset_type') or ''} | "
            f"{name}"
        )

        if (
            visual.get("source_start")
            is not None
            and visual.get("source_end")
            is not None
        ):

            text += (
                f" | {float(visual['source_start']):.3f}"
                f"-{float(visual['source_end']):.3f}"
            )

        return text

    return (
        f"Shot #{int(visual['shot_index']):03d} | GAP"
    )


story = []

# -----------------------------------------------------------------------------
# Cover / summary
# -----------------------------------------------------------------------------

story.append(
    Paragraph(
        "ATLAS ZERO",
        title_style,
    )
)

story.append(
    Paragraph(
        "FILM10 - HUMAN EDITORIAL GAP AUDIT V3",
        title_style,
    )
)

story.append(
    Paragraph(
        "film_10_nepal_tibet_aftershock",
        subtitle_style,
    )
)

summary_data = [
    [
        Paragraph(
            "<b>Metric</b>",
            normal_style,
        ),
        Paragraph(
            "<b>Value</b>",
            normal_style,
        ),
    ],
    [
        Paragraph(
            "Remaining visual gaps",
            normal_style,
        ),
        Paragraph(
            str(len(audit)),
            normal_style,
        ),
    ],
    [
        Paragraph(
            "Total gap duration",
            normal_style,
        ),
        Paragraph(
            f"{TOTAL_GAP_SEC:.3f} sec",
            normal_style,
        ),
    ],
    [
        Paragraph(
            "Critical",
            normal_style,
        ),
        Paragraph(
            str(
                priority_counts.get(
                    "CRITICAL",
                    0,
                )
            ),
            normal_style,
        ),
    ],
    [
        Paragraph(
            "High",
            normal_style,
        ),
        Paragraph(
            str(
                priority_counts.get(
                    "HIGH",
                    0,
                )
            ),
            normal_style,
        ),
    ],
    [
        Paragraph(
            "Medium",
            normal_style,
        ),
        Paragraph(
            str(
                priority_counts.get(
                    "MEDIUM",
                    0,
                )
            ),
            normal_style,
        ),
    ],
    [
        Paragraph(
            "Low",
            normal_style,
        ),
        Paragraph(
            str(
                priority_counts.get(
                    "LOW",
                    0,
                )
            ),
            normal_style,
        ),
    ],
]

summary_table = Table(
    summary_data,
    colWidths=[
        usable_width * 0.65,
        usable_width * 0.35,
    ],
)

summary_table.setStyle(
    TableStyle([
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#E8E8E8"),
        ),
        (
            "GRID",
            (0, 0),
            (-1, -1),
            0.4,
            colors.HexColor("#AAAAAA"),
        ),
        (
            "VALIGN",
            (0, 0),
            (-1, -1),
            "TOP",
        ),
        (
            "LEFTPADDING",
            (0, 0),
            (-1, -1),
            6,
        ),
        (
            "RIGHTPADDING",
            (0, 0),
            (-1, -1),
            6,
        ),
        (
            "TOPPADDING",
            (0, 0),
            (-1, -1),
            5,
        ),
        (
            "BOTTOMPADDING",
            (0, 0),
            (-1, -1),
            5,
        ),
    ])
)

story.append(summary_table)
story.append(Spacer(1, 8 * mm))

story.append(
    Paragraph(
        "Gap distribution",
        section_style,
    )
)

target_table_data = [
    [
        Paragraph(
            "<b>Target</b>",
            normal_style,
        ),
        Paragraph(
            "<b>Shots</b>",
            normal_style,
        ),
        Paragraph(
            "<b>Duration</b>",
            normal_style,
        ),
    ]
]

for target, count in (
    target_counts.most_common()
):

    target_table_data.append([
        Paragraph(
            esc(target),
            normal_style,
        ),
        Paragraph(
            str(count),
            normal_style,
        ),
        Paragraph(
            f"{duration_by_target[target]:.3f}s",
            normal_style,
        ),
    ])

target_table = Table(
    target_table_data,
    colWidths=[
        usable_width * 0.56,
        usable_width * 0.16,
        usable_width * 0.28,
    ],
    repeatRows=1,
)

target_table.setStyle(
    TableStyle([
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#E8E8E8"),
        ),
        (
            "GRID",
            (0, 0),
            (-1, -1),
            0.35,
            colors.HexColor("#BBBBBB"),
        ),
        (
            "VALIGN",
            (0, 0),
            (-1, -1),
            "TOP",
        ),
        (
            "LEFTPADDING",
            (0, 0),
            (-1, -1),
            5,
        ),
        (
            "RIGHTPADDING",
            (0, 0),
            (-1, -1),
            5,
        ),
        (
            "TOPPADDING",
            (0, 0),
            (-1, -1),
            4,
        ),
        (
            "BOTTOMPADDING",
            (0, 0),
            (-1, -1),
            4,
        ),
    ])
)

story.append(target_table)

story.append(PageBreak())

# -----------------------------------------------------------------------------
# Gap cards
# -----------------------------------------------------------------------------

story.append(
    Paragraph(
        "EDITORIAL GAP REVIEW",
        title_style,
    )
)

story.append(
    Paragraph(
        "Each card shows the missing visual, narration context, "
        "recommended solution and neighboring assigned visuals.",
        subtitle_style,
    )
)


PRIORITY_BG = {
    "CRITICAL":
        colors.HexColor("#F5D7D7"),

    "HIGH":
        colors.HexColor("#F4E3D1"),

    "MEDIUM":
        colors.HexColor("#EEEEEE"),

    "LOW":
        colors.HexColor("#F5F5F5"),
}


for idx, item in enumerate(
    audit,
    1,
):

    header = Table(
        [[
            Paragraph(
                f"SHOT #{item['shot_index']:03d}",
                card_title_style,
            ),
            Paragraph(
                esc(
                    item[
                        "target_category"
                    ]
                ),
                card_title_style,
            ),
        ]],
        colWidths=[
            usable_width * 0.34,
            usable_width * 0.66,
        ],
    )

    header.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                PRIORITY_BG.get(
                    item["priority"],
                    colors.HexColor("#EEEEEE"),
                ),
            ),
            (
                "BOX",
                (0, 0),
                (-1, -1),
                0.8,
                colors.HexColor("#777777"),
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                7,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                7,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                6,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                6,
            ),
        ])
    )

    metadata = Paragraph(
        (
            f"<b>Duration:</b> {item['duration_sec']:.3f}s"
            f" &nbsp;&nbsp; "
            f"<b>Priority:</b> {esc(item['priority'])}"
            f" &nbsp;&nbsp; "
            f"<b>Decision:</b> {esc(item['decision'])}"
        ),
        small_style,
    )

    narration = Paragraph(
        (
            "<b>NARRATION</b><br/>"
            + esc(item["narration"])
        ),
        normal_style,
    )

    visual_need = Paragraph(
        (
            "<b>VISUAL NEED</b><br/>"
            + esc(item["visual_need"])
        ),
        normal_style,
    )

    action = Paragraph(
        (
            "<b>ACTION:</b> "
            + esc(
                item[
                    "recommended_action"
                ]
            )
        ),
        action_style,
    )

    reason = Paragraph(
        (
            "<b>WHY</b><br/>"
            + esc(
                item[
                    "decision_reason"
                ]
            )
        ),
        normal_style,
    )

    neighbors_data = [
        [
            Paragraph(
                "<b>Previous assigned</b>",
                label_style,
            ),
            Paragraph(
                "<b>Next assigned</b>",
                label_style,
            ),
        ],
        [
            Paragraph(
                esc(
                    pdf_visual_text(
                        item[
                            "previous_assigned"
                        ]
                    )
                ),
                small_style,
            ),
            Paragraph(
                esc(
                    pdf_visual_text(
                        item[
                            "next_assigned"
                        ]
                    )
                ),
                small_style,
            ),
        ],
    ]

    neighbors = Table(
        neighbors_data,
        colWidths=[
            usable_width * 0.5,
            usable_width * 0.5,
        ],
    )

    neighbors.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#F0F0F0"),
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                colors.HexColor("#CCCCCC"),
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),
        ])
    )

    card = [
        header,
        Spacer(1, 2 * mm),
        metadata,
        Spacer(1, 2 * mm),
        narration,
        Spacer(1, 1.5 * mm),
        visual_need,
        Spacer(1, 1.5 * mm),
        action,
        Spacer(1, 1.5 * mm),
        reason,
        Spacer(1, 2 * mm),
        neighbors,
        Spacer(1, 5 * mm),
    ]

    story.append(
        KeepTogether(card)
    )


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------

def add_page_number(
    canvas,
    doc_obj,
):

    canvas.saveState()

    canvas.setFont(
        "AZRegular",
        7,
    )

    canvas.setFillColor(
        colors.HexColor("#777777")
    )

    canvas.drawString(
        14 * mm,
        7 * mm,
        "ATLAS ZERO | Film10 Gap Editorial Audit V3",
    )

    canvas.drawRightString(
        PAGE_W - 14 * mm,
        7 * mm,
        f"Page {doc_obj.page}",
    )

    canvas.restoreState()


doc.build(
    story,
    onFirstPage=add_page_number,
    onLaterPages=add_page_number,
)

if not PDF_OUT.exists():
    raise RuntimeError(
        "PDF was not created."
    )

if PDF_OUT.stat().st_size < 10000:
    raise RuntimeError(
        f"PDF appears too small: {PDF_OUT.stat().st_size} bytes"
    )

print(
    "PDF SIZE:",
    PDF_OUT.stat().st_size,
    "bytes"
)


# =============================================================================
# FINAL
# =============================================================================

print()
print("=" * 126)
print("OUTPUT")
print("=" * 126)

print(
    "JSON :",
    JSON_OUT
)

print(
    "TXT  :",
    TXT_OUT
)

print(
    "HTML :",
    HTML_OUT
)

print(
    "PDF  :",
    PDF_OUT
)

print()
print("=" * 126)
print("FILM10 HUMAN EDITORIAL GAP AUDIT V3 + PDF: PASS")
print("=" * 126)

print(
    f"{len(audit)} gaps documented."
)

print(
    f"{TOTAL_GAP_SEC:.3f}s gap duration."
)

print("JSON generated.")
print("TXT generated.")
print("HTML generated.")
print("PDF generated.")
print("No DB writes.")
print("No assignment.")
print("No render.")
print("No paid API calls.")

# Open PDF, not HTML.
import subprocess

subprocess.Popen(
    [
        "cmd",
        "/c",
        "start",
        "",
        str(PDF_OUT),
    ],
    shell=False,
)

