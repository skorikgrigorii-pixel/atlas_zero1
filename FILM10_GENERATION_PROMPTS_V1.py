from __future__ import annotations

from pathlib import Path
from collections import Counter
from datetime import datetime
import html
import json

ROOT = Path.cwd()

PROJECT_ID = "film_10_nepal_tibet_aftershock"

PROJECT = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

DECISION_FILE = (
    PROJECT
    / "00_Production"
    / "production_decision_v1"
    / "FILM10_PRODUCTION_DECISION_V1.json"
)

OUT = (
    PROJECT
    / "00_Production"
    / "generation_prompts_v1"
)

OUT.mkdir(
    parents=True,
    exist_ok=True
)

JSON_OUT = OUT / "FILM10_GENERATION_PROMPTS_V1.json"
TXT_OUT  = OUT / "FILM10_GENERATION_PROMPTS_V1.txt"
HTML_OUT = OUT / "FILM10_GENERATION_PROMPTS_V1.html"
PDF_OUT  = OUT / "FILM10_GENERATION_PROMPTS_V1.pdf"


print("=" * 120)
print("ATLAS ZERO - FILM10 GENERATION PROMPTS V1")
print("=" * 120)
print("LIVE API   : 0")
print("PAID CALLS : 0")
print("DB WRITES  : NO")
print("RENDER     : NO")
print("GENERATION : PROMPTS ONLY")
print()


if not DECISION_FILE.exists():
    raise FileNotFoundError(
        DECISION_FILE
    )


raw = json.loads(
    DECISION_FILE.read_text(
        encoding="utf-8"
    )
)

requirements = raw[
    "new_file_requirements"
]


# =============================================================================
# SELECT ONLY MATERIAL WE ACTUALLY WANT TO GENERATE NOW
# =============================================================================

GENERATE_TARGETS = {
    "SCHOOL_BIDUR",
    "WARNING_COMMUNICATION",
    "USGS_SEISMIC_SCIENCE",
    "EDITORIAL_REVIEW_REQUIRED",
}


selected = [
    x
    for x in requirements
    if x.get("target")
    in GENERATE_TARGETS
]


print(
    "ALL NEW REQUIREMENTS :",
    len(requirements)
)

print(
    "GENERATE NOW         :",
    len(selected)
)


# =============================================================================
# TARGET-SPECIFIC EDITORIAL POLICY
# =============================================================================

def target_policy(req):

    target = req["target"]
    subtype = req.get(
        "subtype",
        "GENERAL"
    )

    if target == "SCHOOL_BIDUR":

        if subtype == "SCHOOL_BUS":

            return {
                "asset_role":
                    "EDITORIAL_RECONSTRUCTION",

                "scene":
                    (
                        "A school bus carrying evacuated students "
                        "leaves the danger area in Bidur, Nepal. "
                        "The environment must feel authentically Nepalese, "
                        "with Himalayan foothill architecture, wet roads, "
                        "overcast monsoon weather and restrained urgency."
                    ),

                "camera":
                    (
                        "documentary medium-wide roadside shot, "
                        "natural eye-level camera, subtle handheld realism"
                    ),
            }

        if subtype == "OLD_BRIDGE":

            return {
                "asset_role":
                    "EDITORIAL_RECONSTRUCTION",

                "scene":
                    (
                        "An old bridge in the Bidur/Trishuli river environment "
                        "during an emergency evacuation. A school bus or "
                        "evacuating people have just crossed or are crossing. "
                        "The river below is dangerous and rising, but the image "
                        "must not invent a spectacular bridge collapse unless "
                        "the narration specifically requires it."
                    ),

                "camera":
                    (
                        "documentary wide establishing shot, "
                        "bridge and river geography clearly readable"
                    ),
            }

        if subtype == "EVACUATION":

            return {
                "asset_role":
                    "EDITORIAL_RECONSTRUCTION",

                "scene":
                    (
                        "Students and teachers evacuating a secondary school "
                        "in Bidur, Nepal after receiving an urgent upstream "
                        "flood warning. Students leave classrooms and school "
                        "grounds quickly but in an organized way. Teachers "
                        "direct them toward higher and safer ground."
                    ),

                "camera":
                    (
                        "observational documentary photography, "
                        "medium-wide human-scale shot, natural movement"
                    ),
            }

        return {
            "asset_role":
                "EDITORIAL_RECONSTRUCTION",

            "scene":
                (
                    "Exterior establishing view of a secondary school "
                    "in Bidur, Nepal shortly before emergency evacuation. "
                    "Authentic Nepalese school environment, students and "
                    "teachers present, Himalayan foothill town geography."
                ),

            "camera":
                (
                    "documentary establishing shot, natural perspective"
                ),
        }


    if target == "WARNING_COMMUNICATION":

        if subtype == "PHONE_WARNING":

            return {
                "asset_role":
                    "EDITORIAL_RECONSTRUCTION",

                "scene":
                    (
                        "A crucial emergency warning being transmitted by "
                        "mobile phone in Nepal. Focus on the human reaction "
                        "to receiving alarming upstream information: phone "
                        "in hand, concerned face, immediate decision to warn "
                        "others. No readable phone message."
                    ),

                "camera":
                    (
                        "documentary close and medium shots, "
                        "natural available light, restrained urgency"
                    ),
            }

        return {
            "asset_role":
                "EDITORIAL_RECONSTRUCTION",

            "scene":
                (
                    "A rapid human warning chain inside a Nepalese school: "
                    "one staff member receives urgent information and tells "
                    "school administrators and teachers, who immediately "
                    "begin organizing evacuation."
                ),

            "camera":
                (
                    "observational documentary medium shot, "
                    "natural expressions and realistic body language"
                ),
        }


    if target == "USGS_SEISMIC_SCIENCE":

        if subtype == "USGS_SIGNAL_1":

            return {
                "asset_role":
                    "SCIENTIFIC_GRAPHIC_BASE",

                "scene":
                    (
                        "Scientific documentary visualization of the first "
                        "unusual seismic signal associated with the Langtang "
                        "Lirung mass movement. Show a clean seismic waveform "
                        "combined with subtle Himalayan terrain/map context. "
                        "The graphic must visually explain why a large slope "
                        "failure can produce a signal resembling an earthquake."
                    ),

                "camera":
                    (
                        "flat 16:9 scientific visualization, no cinematic camera"
                    ),
            }

        if subtype == "USGS_SIGNAL_2":

            return {
                "asset_role":
                    "SCIENTIFIC_GRAPHIC_BASE",

                "scene":
                    (
                        "Scientific documentary visualization comparing a "
                        "later seismic signal with the earlier mass-movement "
                        "signal. Use waveform structure and restrained Himalayan "
                        "map context. Exact numbers and labels will be added "
                        "later during compositing."
                    ),

                "camera":
                    (
                        "flat 16:9 scientific visualization"
                    ),
            }

        return {
            "asset_role":
                "SCIENTIFIC_GRAPHIC_BASE",

            "scene":
                (
                    "Scientific explanatory graphic connecting Himalayan "
                    "slope collapse, moving rock and ice mass, and recorded "
                    "seismic energy. Clear documentary science visualization."
                ),

            "camera":
                "flat 16:9 scientific visualization",
        }


    # -------------------------------------------------------------------------
    # EDITORIAL REVIEW:
    # narration is deliberately part of the prompt because these four
    # requirements are shot-specific.
    # -------------------------------------------------------------------------

    narration = str(
        req.get(
            "generation_prompt",
            ""
        )
    ).strip()

    if not narration:

        narration = (
            "Create a neutral documentary visual matching "
            "the supplied Film10 shot context."
        )

    return {
        "asset_role":
            "SHOT_SPECIFIC_EDITORIAL",

        "scene":
            narration,

        "camera":
            (
                "photorealistic documentary composition, "
                "natural perspective appropriate to the scene"
            ),
    }


# =============================================================================
# BUILD FINAL GENERATION JOBS
# =============================================================================

jobs = []


GLOBAL_REALISM = (
    "Photorealistic high-end documentary image. "
    "Natural light, realistic weather, physically plausible environment, "
    "authentic Nepal/Himalayan geography and architecture where applicable. "
    "Human proportions and clothing must be realistic and regionally plausible. "
    "Restrained documentary tone, not disaster-movie spectacle. "
    "The frame should look suitable for a serious investigative documentary."
)


GLOBAL_COMPOSITION = (
    "16:9 landscape composition, full-frame image, 1920x1080-safe framing, "
    "important subjects away from extreme edges, enough visual depth for "
    "subtle pan/zoom animation during editing."
)


GLOBAL_NO_FAKE_ARCHIVE = (
    "This is an editorial reconstruction or explanatory visual. "
    "Do not imitate CCTV timestamps, television news graphics, agency branding, "
    "Reuters/AP/AFP footage, archival watermarks or authentic historical "
    "recording artifacts. Do not imply that generated imagery is real footage."
)


GLOBAL_NEGATIVE = (
    "text, subtitles, captions, watermark, logo, news lower third, "
    "fake CCTV timestamp, fake agency branding, fake newspaper layout, "
    "Hollywood explosion, fireball, fantasy landscape, surreal flood, "
    "apocalyptic sky, exaggerated panic, crowds screaming at camera, "
    "posing people, fashion photography, tourism advertising, "
    "perfect studio lighting, oversaturated colors, HDR look, "
    "duplicated people, cloned faces, malformed hands, extra fingers, "
    "deformed limbs, floating objects, impossible architecture, "
    "European or American school architecture, generic alpine resort, "
    "Chinese megacity skyline, invented readable signs"
)


for n, req in enumerate(
    selected,
    1
):

    policy = target_policy(
        req
    )

    role = policy[
        "asset_role"
    ]

    if role == "SCIENTIFIC_GRAPHIC_BASE":

        prompt = (
            policy["scene"]
            + " "
            + "Professional scientific documentary graphic. "
            + "Accurate visual hierarchy, restrained colors, "
              "clean waveform and terrain structure. "
              "Do not invent scientific measurements. "
              "Do not render agency logos. "
              "Leave exact numerical labels and typography for "
              "post-production compositing. "
            + GLOBAL_COMPOSITION
        )

        negative = (
            "fake USGS logo, invented scientific values, fake measurements, "
            "decorative infographic, corporate presentation template, "
            "3D fantasy globe, paragraph text, watermark, logo, "
            "cartoon earthquake, glowing tectonic plates"
        )

    else:

        prompt = (
            policy["scene"]
            + " "
            + GLOBAL_REALISM
            + " Camera: "
            + policy["camera"]
            + ". "
            + GLOBAL_COMPOSITION
            + " "
            + GLOBAL_NO_FAKE_ARCHIVE
        )

        negative = GLOBAL_NEGATIVE


    job = {
        "job_id":
            f"F10_GEN_{n:02d}",

        "requirement_id":
            req[
                "requirement_id"
            ],

        "target":
            req[
                "target"
            ],

        "subtype":
            req.get(
                "subtype"
            ),

        "asset_role":
            role,

        "covers_units":
            req.get(
                "covers_units",
                []
            ),

        "covers_shots":
            req.get(
                "covers_shots",
                []
            ),

        "timeline_coverage_sec":
            req.get(
                "total_timeline_sec",
                0
            ),

        "output_spec": {
            "aspect_ratio":
                "16:9",

            "preferred_resolution":
                "1920x1080 or higher",

            "master_type":
                "STILL_IMAGE",

            "animation_strategy":
                (
                    "ATLAS ZERO pan/zoom/crop in edit; "
                    "do not require long AI video generation"
                ),
        },

        "prompt":
            prompt,

        "negative_prompt":
            negative,

        "editorial_disclosure":
            (
                "GENERATED_EDITORIAL_RECONSTRUCTION"
                if role != "SCIENTIFIC_GRAPHIC_BASE"
                else "GENERATED_SCIENTIFIC_GRAPHIC_BASE"
            ),

        "must_not_be_presented_as_real_archive":
            True,

        "rights_status_after_generation":
            "GENERATED_ASSET_PENDING_PLATFORM_TERMS_CHECK",
    }

    jobs.append(
        job
    )


# =============================================================================
# VALIDATION
# =============================================================================

expected = Counter({
    "SCHOOL_BIDUR":
        3,

    "WARNING_COMMUNICATION":
        2,

    "USGS_SEISMIC_SCIENCE":
        2,

    "EDITORIAL_REVIEW_REQUIRED":
        4,
})


actual = Counter(
    x[
        "target"
    ]
    for x in jobs
)


if actual != expected:

    raise RuntimeError(
        "Generation target mismatch. "
        f"Expected {dict(expected)}, "
        f"got {dict(actual)}"
    )


if len(jobs) != 11:

    raise RuntimeError(
        f"Expected exactly 11 generation jobs, got {len(jobs)}"
    )


for job in jobs:

    if not job[
        "prompt"
    ].strip():

        raise RuntimeError(
            f"Empty prompt: {job['job_id']}"
        )

    if not job[
        "negative_prompt"
    ].strip():

        raise RuntimeError(
            f"Empty negative prompt: {job['job_id']}"
        )


# =============================================================================
# JSON
# =============================================================================

report = {
    "schema":
        "atlas_zero.film10.generation_prompts.v1",

    "generated_at":
        datetime.now().isoformat(),

    "project_id":
        PROJECT_ID,

    "source":
        str(
            DECISION_FILE
        ),

    "policy": {
        "generation_jobs":
            len(
                jobs
            ),

        "fake_archive_allowed":
            False,

        "generic_himalaya_fallback_allowed":
            False,

        "exact_narration_alignment_required":
            True,

        "real_event_assets_not_replaced":
            [
                "LANGTANG_2015_ARCHIVE_CONTEXT",
                "HYDROPOWER_INFRASTRUCTURE",
                "TUNNEL_WORKER_RESCUE",
                "GLACIER_COLLAPSE_REAL",
            ],

        "live_api":
            False,

        "paid_calls":
            False,
    },

    "by_target":
        dict(
            actual
        ),

    "jobs":
        jobs,
}


JSON_OUT.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


# =============================================================================
# TXT
# =============================================================================

lines = []

lines.append(
    "ATLAS ZERO - FILM10 GENERATION PROMPTS V1"
)

lines.append(
    "=" * 110
)

lines.append("")

lines.append(
    f"GENERATION JOBS : {len(jobs)}"
)

lines.append("")

for target, count in actual.items():

    lines.append(
        f"{target:32s}: {count}"
    )


for job in jobs:

    lines.append("")
    lines.append(
        "=" * 110
    )

    lines.append(
        f"{job['job_id']} | "
        f"{job['requirement_id']} | "
        f"{job['target']} / "
        f"{job['subtype']}"
    )

    lines.append(
        "=" * 110
    )

    lines.append(
        "ROLE     : "
        + job[
            "asset_role"
        ]
    )

    lines.append(
        "UNITS    : "
        + ", ".join(
            job[
                "covers_units"
            ]
        )
    )

    lines.append(
        "SHOTS    : "
        + ", ".join(
            str(x)
            for x in job[
                "covers_shots"
            ]
        )
    )

    lines.append(
        "COVERAGE : "
        + f"{float(job['timeline_coverage_sec']):.3f} sec"
    )

    lines.append("")
    lines.append(
        "PROMPT:"
    )
    lines.append(
        job[
            "prompt"
        ]
    )

    lines.append("")
    lines.append(
        "NEGATIVE PROMPT:"
    )
    lines.append(
        job[
            "negative_prompt"
        ]
    )

    lines.append("")
    lines.append(
        "DISCLOSURE:"
    )
    lines.append(
        job[
            "editorial_disclosure"
        ]
    )


TXT_OUT.write_text(
    "\n".join(
        lines
    ),
    encoding="utf-8"
)


# =============================================================================
# HTML
# =============================================================================

def esc(value):
    return html.escape(
        str(
            value or ""
        )
    )


parts = [
    """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Film10 Generation Prompts V1</title>
<style>
body {
    font-family: Arial, sans-serif;
    margin: 30px;
    line-height: 1.45;
}
.job {
    border: 1px solid #aaa;
    padding: 15px;
    margin: 20px 0;
    page-break-inside: avoid;
}
.prompt {
    background: #f4f4f4;
    padding: 10px;
    white-space: pre-wrap;
}
.negative {
    background: #fafafa;
    padding: 10px;
    white-space: pre-wrap;
}
</style>
</head>
<body>
"""
]

parts.append(
    "<h1>ATLAS ZERO — Film10 Generation Prompts V1</h1>"
)

parts.append(
    f"<p><b>{len(jobs)} generation jobs.</b> "
    "Generated imagery is editorial reconstruction/scientific visualization, "
    "not archival evidence.</p>"
)


for job in jobs:

    parts.append(
        "<div class='job'>"
    )

    parts.append(
        f"<h2>{esc(job['job_id'])} — "
        f"{esc(job['target'])} / "
        f"{esc(job['subtype'])}</h2>"
    )

    parts.append(
        f"<p><b>Requirement:</b> "
        f"{esc(job['requirement_id'])}<br>"
        f"<b>Role:</b> "
        f"{esc(job['asset_role'])}<br>"
        f"<b>Coverage:</b> "
        f"{float(job['timeline_coverage_sec']):.3f} sec<br>"
        f"<b>Shots:</b> "
        f"{esc(', '.join(str(x) for x in job['covers_shots']))}</p>"
    )

    parts.append(
        "<h3>Prompt</h3>"
    )

    parts.append(
        f"<div class='prompt'>{esc(job['prompt'])}</div>"
    )

    parts.append(
        "<h3>Negative prompt</h3>"
    )

    parts.append(
        f"<div class='negative'>{esc(job['negative_prompt'])}</div>"
    )

    parts.append(
        "</div>"
    )


parts.append(
    "</body></html>"
)


HTML_OUT.write_text(
    "\n".join(
        parts
    ),
    encoding="utf-8"
)


# =============================================================================
# PDF
# =============================================================================

try:

    from reportlab.lib import colors
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
    )

except Exception as exc:

    raise RuntimeError(
        f"ReportLab import failed: {exc}"
    )


font_candidates = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
]


font_path = next(
    (
        p
        for p in font_candidates
        if p.exists()
    ),
    None
)


if font_path is None:
    raise RuntimeError(
        "Unicode Windows font not found."
    )


pdfmetrics.registerFont(
    TTFont(
        "AZUnicode",
        str(font_path)
    )
)


styles = getSampleStyleSheet()


title_style = ParagraphStyle(
    "AZTitle",
    parent=styles["Title"],
    fontName="AZUnicode",
    fontSize=16,
    leading=20,
)


heading_style = ParagraphStyle(
    "AZHeading",
    parent=styles["Heading2"],
    fontName="AZUnicode",
    fontSize=11,
    leading=14,
)


body_style = ParagraphStyle(
    "AZBody",
    parent=styles["BodyText"],
    fontName="AZUnicode",
    fontSize=8.3,
    leading=10.5,
)


small_style = ParagraphStyle(
    "AZSmall",
    parent=body_style,
    fontSize=7.4,
    leading=9,
)


doc = SimpleDocTemplate(
    str(PDF_OUT),
    pagesize=A4,
    leftMargin=14 * mm,
    rightMargin=14 * mm,
    topMargin=14 * mm,
    bottomMargin=14 * mm,
)


story = []


story.append(
    Paragraph(
        "ATLAS ZERO — Film10 Generation Prompts V1",
        title_style
    )
)

story.append(
    Paragraph(
        (
            f"{len(jobs)} generation jobs. "
            "All generated disaster imagery is editorial reconstruction "
            "or scientific visualization and must not be represented as "
            "authentic archival footage."
        ),
        body_style
    )
)

story.append(
    Spacer(
        1,
        8
    )
)


summary = [[
    "Target",
    "Jobs",
]]


for target, count in actual.items():

    summary.append([
        target,
        str(count),
    ])


table = Table(
    summary,
    colWidths=[
        130 * mm,
        30 * mm,
    ]
)


table.setStyle(
    TableStyle([
        (
            "GRID",
            (0, 0),
            (-1, -1),
            0.25,
            colors.grey
        ),
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.lightgrey
        ),
        (
            "FONTNAME",
            (0, 0),
            (-1, -1),
            "AZUnicode"
        ),
    ])
)


story.append(
    table
)

story.append(
    PageBreak()
)


for i, job in enumerate(jobs):

    story.append(
        Paragraph(
            (
                f"{job['job_id']} — "
                f"{job['target']} / "
                f"{job['subtype']}"
            ),
            heading_style
        )
    )

    story.append(
        Paragraph(
            (
                f"<b>Requirement:</b> {job['requirement_id']}<br/>"
                f"<b>Role:</b> {job['asset_role']}<br/>"
                f"<b>Coverage:</b> "
                f"{float(job['timeline_coverage_sec']):.3f} sec<br/>"
                f"<b>Shots:</b> "
                + ", ".join(
                    str(x)
                    for x in job[
                        "covers_shots"
                    ]
                )
            ),
            small_style
        )
    )

    story.append(
        Spacer(
            1,
            5
        )
    )

    story.append(
        Paragraph(
            "<b>PROMPT</b>",
            body_style
        )
    )

    story.append(
        Paragraph(
            html.escape(
                job[
                    "prompt"
                ]
            ),
            body_style
        )
    )

    story.append(
        Spacer(
            1,
            5
        )
    )

    story.append(
        Paragraph(
            "<b>NEGATIVE PROMPT</b>",
            body_style
        )
    )

    story.append(
        Paragraph(
            html.escape(
                job[
                    "negative_prompt"
                ]
            ),
            body_style
        )
    )

    if i != len(jobs) - 1:
        story.append(
            PageBreak()
        )


doc.build(
    story
)


# =============================================================================
# OUTPUT VALIDATION
# =============================================================================

for p in (
    JSON_OUT,
    TXT_OUT,
    HTML_OUT,
    PDF_OUT,
):

    if not p.exists():
        raise RuntimeError(
            f"Missing output: {p}"
        )

    if p.stat().st_size <= 0:
        raise RuntimeError(
            f"Empty output: {p}"
        )


print()
print("=" * 120)
print("GENERATION PROMPT SUMMARY")
print("=" * 120)

print(
    "GENERATION JOBS :",
    len(jobs)
)

print()

for target, count in actual.items():

    sec = sum(
        float(x["timeline_coverage_sec"])
        for x in jobs
        if x["target"] == target
    )

    print(
        f"  {target:32s} "
        f"{count:2d} jobs | "
        f"{sec:8.3f} sec timeline coverage"
    )


print()
print("JOBS:")

for job in jobs:

    print(
        f"  {job['job_id']} | "
        f"{job['target']:28s} | "
        f"{str(job['subtype']):22s} | "
        f"{float(job['timeline_coverage_sec']):7.3f} sec | "
        f"{len(job['covers_shots'])} shots"
    )


print()
print("=" * 120)
print("OUTPUTS")
print("=" * 120)

for p in (
    JSON_OUT,
    TXT_OUT,
    HTML_OUT,
    PDF_OUT,
):

    print(
        p.relative_to(ROOT),
        "|",
        p.stat().st_size,
        "bytes"
    )


print()
print("=" * 120)
print("FILM10 GENERATION PROMPTS V1: PASS")
print("=" * 120)
print("NEXT: generate F10_GEN_01 ... F10_GEN_11.")
print("=" * 120)

