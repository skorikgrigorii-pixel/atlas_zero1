from __future__ import annotations

import csv
import json
import os
import sys
import traceback
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd().resolve()

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from az_enterprise.core.archive_acquisition_rc2 import ArchiveAcquisitionRC2


PROJECT_ID = "film_09_the_mountain_fell"
PROJECT_DIR = ROOT / "workspace" / "projects" / PROJECT_ID
OPS_DIR = PROJECT_DIR / "00_Production"

os.environ["AZ_ENABLE_LIVE_API"] = "0"
os.environ["AZ_ALLOW_PAID_CALLS"] = "0"


SEARCHES = [
    {
        "query": "Langtang Lirung Nepal",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ("map of nepal districts",)
    },
    {
        "query": "Langtang Himal Nepal glacier",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Langtang National Park Himalaya",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Rasuwa Nepal Himalaya",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Rasuwagadhi Nepal China border",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Gyirong Tibet Nepal border",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Kyirong Tibet Nepal",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Bhote Koshi river Nepal",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Trishuli River Nepal",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Himalayan glacier Nepal",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Himalaya debris flow Nepal",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Nepal Tibet highway Rasuwa",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Langtang valley village Nepal",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    },
    {
        "query": "Langtang glacier Nepal aerial",
        "limit": 50,
        "required_terms": (),
        "excluded_terms": ()
    }
]


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temp.replace(path)


def main():
    print("=" * 76)
    print("ATLAS ZERO — FILM 09 RIGHTS-CLEARED ARCHIVE ACQUISITION")
    print("=" * 76)

    acq = ArchiveAcquisitionRC2(
        project_id=PROJECT_ID,
        root=ROOT,
    )

    all_candidates = []
    discovery_report = []

    for item in SEARCHES:
        query = item["query"]

        print()
        print(f"[DISCOVER] {query}")

        try:
            rows = acq.discover_wikimedia(
                query=query,
                limit=item.get("limit", 50),
                required_terms=tuple(item.get("required_terms") or ()),
                excluded_terms=tuple(item.get("excluded_terms") or ()),
            )

            allowed = [x for x in rows if x.rights_allowed]
            blocked = [x for x in rows if not x.rights_allowed]

            discovery_report.append({
                "query": query,
                "returned": len(rows),
                "allowed": len(allowed),
                "blocked": len(blocked),
            })

            print(
                f"  returned={len(rows)} "
                f"allowed={len(allowed)} "
                f"blocked={len(blocked)}"
            )

            all_candidates.extend(rows)

        except Exception as exc:
            discovery_report.append({
                "query": query,
                "error": str(exc),
            })

            print(f"  ERROR: {exc}")

    # Deduplicate candidate IDs / URLs before download.
    unique = {}
    for row in all_candidates:
        key = row.download_url or row.candidate_id
        if key not in unique:
            unique[key] = row
        else:
            # Prefer a candidate that passed rights.
            if row.rights_allowed and not unique[key].rights_allowed:
                unique[key] = row

    candidates = list(unique.values())

    candidates.sort(
        key=lambda x: (
            not x.rights_allowed,
            -(int(x.width or 0) * int(x.height or 0)),
            x.title.lower(),
        )
    )

    rights_allowed = [
        row for row in candidates
        if row.rights_allowed
    ]

    rights_blocked = [
        row for row in candidates
        if not row.rights_allowed
    ]

    print()
    print("[SUMMARY BEFORE DOWNLOAD]")
    print(f"Unique candidates : {len(candidates)}")
    print(f"Rights allowed    : {len(rights_allowed)}")
    print(f"Rights blocked    : {len(rights_blocked)}")

    candidates_manifest = {
        "project_id": PROJECT_ID,
        "generated_at": now(),
        "discovery": discovery_report,
        "summary": {
            "unique_candidates": len(candidates),
            "rights_allowed": len(rights_allowed),
            "rights_blocked": len(rights_blocked),
        },
        "candidates": [x.to_dict() for x in candidates],
    }

    write_json(
        OPS_DIR / "FILM_09_DISCOVERY_MANIFEST.json",
        candidates_manifest
    )

    print()
    print("[DOWNLOAD]")
    print("Downloading rights-cleared archive candidates...")

    result = acq.download_candidates(
        candidates,
        limit=120,
        minimum_width=1000,
        minimum_height=600,
        delay_sec=1.5,
    )

    manifest_path = acq.write_manifest(
        result,
        name="film_09_archive_acquisition"
    )

    print()
    print("[DOWNLOAD RESULT]")
    print(json.dumps(result.get("summary", {}), indent=2))
    print(f"Archive manifest: {manifest_path}")

    rights_ledger = []

    for row in candidates:
        rights_ledger.append({
            "candidate_id": row.candidate_id,
            "provider": row.provider,
            "title": row.title,
            "source_url": row.source_url,
            "download_url": row.download_url,
            "license_id": row.license_id,
            "license_url": row.license_url,
            "author": row.author,
            "width": row.width,
            "height": row.height,
            "rights_allowed": row.rights_allowed,
            "rights_decision": row.rights_decision,
            "rights_reason": row.rights_reason,
            "local_path": row.local_path,
        })

    write_json(
        OPS_DIR / "FILM_09_RIGHTS_LEDGER.json",
        {
            "project_id": PROJECT_ID,
            "generated_at": now(),
            "assets": rights_ledger,
        }
    )

    # Human-friendly CSV.
    csv_path = OPS_DIR / "FILM_09_RIGHTS_LEDGER.csv"

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:

        fields = [
            "candidate_id",
            "provider",
            "title",
            "source_url",
            "download_url",
            "license_id",
            "license_url",
            "author",
            "width",
            "height",
            "rights_allowed",
            "rights_decision",
            "rights_reason",
            "local_path",
        ]

        writer = csv.DictWriter(
            handle,
            fieldnames=fields
        )

        writer.writeheader()

        for row in rights_ledger:
            writer.writerow(row)

    downloaded = result.get("downloaded") or []

    production_report = {
        "project_id": PROJECT_ID,
        "generated_at": now(),
        "status": (
            "ACQUISITION_COMPLETE"
            if downloaded
            else "ACQUISITION_REQUIRES_REVIEW"
        ),
        "safety": {
            "AZ_ENABLE_LIVE_API":
                os.environ.get("AZ_ENABLE_LIVE_API"),
            "AZ_ALLOW_PAID_CALLS":
                os.environ.get("AZ_ALLOW_PAID_CALLS"),
        },
        "archive": {
            "queries": len(SEARCHES),
            "candidate_count": len(candidates),
            "rights_allowed_count": len(rights_allowed),
            "rights_blocked_count": len(rights_blocked),
            "downloaded_count":
                len(result.get("downloaded") or []),
            "failed_count":
                len(result.get("failed") or []),
        },
        "next_stage": [
            "AssetIntelligence/CV scan",
            "semantic assignment against Film 09 beats",
            "event-specific USGS/Copernicus/NASA acquisition",
            "calculate real-screen coverage",
            "generate missing-shot manual Leonardo queue"
        ]
    }

    write_json(
        OPS_DIR / "FILM_09_ACQUISITION_REPORT.json",
        production_report
    )

    print()
    print("=" * 76)
    print("FILM 09 ARCHIVE ACQUISITION COMPLETE")
    print("=" * 76)

    print(
        f"Downloaded rights-cleared files: "
        f"{len(downloaded)}"
    )

    print(
        "Production media directory: "
        + str(
            PROJECT_DIR
            / "02_Visuals"
            / "real"
            / "archive"
        )
    )

    print(
        "Rights ledger: "
        + str(
            OPS_DIR
            / "FILM_09_RIGHTS_LEDGER.csv"
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
