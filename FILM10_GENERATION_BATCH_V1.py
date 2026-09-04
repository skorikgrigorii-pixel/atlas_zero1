from pathlib import Path
import json

ROOT = Path.cwd()

SRC = (
    ROOT
    / "workspace"
    / "projects"
    / "film_10_nepal_tibet_aftershock"
    / "00_Production"
    / "generation_prompts_v1"
    / "FILM10_GENERATION_PROMPTS_V1.json"
)

OUT = (
    ROOT
    / "workspace"
    / "projects"
    / "film_10_nepal_tibet_aftershock"
    / "02_Visuals"
    / "generated"
    / "film10_generation_batch_v1"
)

OUT.mkdir(
    parents=True,
    exist_ok=True
)

if not SRC.exists():
    raise FileNotFoundError(SRC)

data = json.loads(
    SRC.read_text(
        encoding="utf-8"
    )
)

jobs = data["jobs"]

if len(jobs) != 11:
    raise RuntimeError(
        f"Expected 11 generation jobs, got {len(jobs)}"
    )

print("=" * 120)
print("ATLAS ZERO - FILM10 GENERATION BATCH V1")
print("=" * 120)
print()

manifest = []

for job in jobs:

    job_id = job["job_id"]

    filename = (
        f"{job_id}_"
        f"{job['target']}_"
        f"{job.get('subtype') or 'GENERAL'}"
        f".png"
    )

    record = {
        "job_id": job_id,
        "target": job["target"],
        "subtype": job.get("subtype"),
        "covers_units": job.get("covers_units", []),
        "covers_shots": job.get("covers_shots", []),
        "timeline_coverage_sec": job.get(
            "timeline_coverage_sec",
            0
        ),
        "output_filename": filename,
        "output_path": str(
            OUT / filename
        ),
        "prompt": job["prompt"],
        "negative_prompt": job["negative_prompt"],
        "editorial_disclosure": job[
            "editorial_disclosure"
        ],
    }

    manifest.append(record)

    print("=" * 120)
    print(
        f"{job_id} | "
        f"{job['target']} | "
        f"{job.get('subtype')}"
    )
    print("=" * 120)

    print(
        "OUTPUT:",
        filename
    )

    print(
        "SHOTS :",
        ", ".join(
            str(x)
            for x in job.get(
                "covers_shots",
                []
            )
        )
    )

    print(
        "COVERAGE:",
        f"{float(job.get('timeline_coverage_sec', 0)):.3f} sec"
    )

    print()
    print("PROMPT:")
    print(job["prompt"])

    print()
    print("NEGATIVE PROMPT:")
    print(job["negative_prompt"])

    print()
    print(
        "DISCLOSURE:",
        job["editorial_disclosure"]
    )

    print()


MANIFEST = (
    OUT
    / "FILM10_GENERATION_BATCH_V1.json"
)

MANIFEST.write_text(
    json.dumps(
        {
            "schema":
                "atlas_zero.film10.generation_batch.v1",

            "generation_jobs":
                len(manifest),

            "output_directory":
                str(OUT),

            "jobs":
                manifest,
        },
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


README = (
    OUT
    / "FILM10_GENERATION_BATCH_V1.txt"
)

lines = []

for row in manifest:

    lines.extend([
        "=" * 110,
        (
            f"{row['job_id']} | "
            f"{row['target']} | "
            f"{row['subtype']}"
        ),
        "=" * 110,
        f"OUTPUT: {row['output_filename']}",
        "",
        "PROMPT:",
        row["prompt"],
        "",
        "NEGATIVE PROMPT:",
        row["negative_prompt"],
        "",
    ])

README.write_text(
    "\n".join(lines),
    encoding="utf-8"
)

print("=" * 120)
print("BATCH SUMMARY")
print("=" * 120)
print("GENERATION JOBS :", len(manifest))
print("OUTPUT DIR      :", OUT)
print("MANIFEST        :", MANIFEST)
print("PROMPT TXT      :", README)
print()
print("FILM10 GENERATION BATCH V1: PASS")
print("=" * 120)

