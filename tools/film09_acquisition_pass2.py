from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd().resolve()
SRC = ROOT / "src"

for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from az_enterprise.core.archive_acquisition_rc2 import ArchiveAcquisitionRC2
from az_enterprise.core.visual_rights_gate_rc2 import VisualRightsGateRC2

PROJECT_ID = "film_09_the_mountain_fell"
PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID
OPS = PROJECT / "00_Production"
REAL = PROJECT / "02_Visuals" / "real"
ARCHIVE = REAL / "archive"
USGS = REAL / "usgs"

os.environ["AZ_ENABLE_LIVE_API"] = "0"
os.environ["AZ_ALLOW_PAID_CALLS"] = "0"

USER_AGENT = "AtlasZeroDocumentary/1.0"

USGS_EVENT_PAGE = (
    "https://www.usgs.gov/programs/landslide-hazards/science/"
    "2026-nepal-debris-avalanche-and-flash-flood"
)

USGS_MAP_PAGE = (
    "https://www.usgs.gov/media/images/"
    "2026-nepal-debris-avalanche-and-flash-flood-map"
)

RETRY_SEARCHES = [
    "Langtang Lirung",
    "Langtang glacier",
    "Langtang valley Nepal",
    "Langtang Himal",
    "Rasuwagadhi border",
    "Rasuwa Nepal",
    "Gyirong Tibet",
    "Kyirong Tibet",
    "Bhote Koshi",
    "Trishuli Nepal river",
    "Nepal Tibet highway",
    "Himalayan glacier Nepal",
    "Nepal debris flow",
]

def now():
    return datetime.now(timezone.utc).isoformat()

def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def request_bytes(url, referer=None, attempts=5):
    last = None

    for attempt in range(attempts):
        try:
            headers = {"User-Agent": USER_AGENT}

            if referer:
                headers["Referer"] = referer

            req = urllib.request.Request(
                url,
                headers=headers,
            )

            with urllib.request.urlopen(
                req,
                timeout=120,
            ) as response:
                return (
                    response.read(),
                    dict(response.headers),
                    response.geturl(),
                )

        except urllib.error.HTTPError as exc:
            last = exc

            if exc.code == 429:
                wait = 12 * (attempt + 1)
                print(
                    f"    HTTP 429 — waiting {wait}s "
                    f"(attempt {attempt + 1}/{attempts})"
                )
                time.sleep(wait)
                continue

            if exc.code in (500, 502, 503, 504):
                wait = 5 * (attempt + 1)
                print(
                    f"    HTTP {exc.code} — retry in {wait}s"
                )
                time.sleep(wait)
                continue

            raise

        except Exception as exc:
            last = exc
            time.sleep(4 * (attempt + 1))

    raise RuntimeError(
        f"download failed after {attempts} attempts: {last}"
    )

def safe_name(value):
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    return value.strip("_.")[:150] or "asset"

def existing_hashes():
    hashes = set()

    for base in (ARCHIVE, USGS):
        if not base.exists():
            continue

        for path in base.rglob("*"):
            if path.is_file():
                try:
                    hashes.add(sha256_file(path))
                except Exception:
                    pass

    return hashes

def discover_usgs_image_urls(page_url):
    content, _, final_url = request_bytes(page_url)
    text = content.decode("utf-8", errors="ignore")

    urls = set()

    patterns = [
        r'https://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?',
        r'//[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?',
    ]

    for pattern in patterns:
        for match in re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            url = html.unescape(match)

            if url.startswith("//"):
                url = "https:" + url

            low = url.lower()

            if any(
                token in low
                for token in (
                    "logo",
                    "icon",
                    "sprite",
                    "favicon",
                    "avatar",
                )
            ):
                continue

            urls.add(url)

    return final_url, sorted(urls)

def download_usgs_assets():
    gate = VisualRightsGateRC2()
    hashes = existing_hashes()

    report = {
        "pages": [],
        "downloaded": [],
        "duplicates": [],
        "failed": [],
        "blocked": [],
    }

    pages = [
        ("event_page", USGS_EVENT_PAGE),
        ("event_map", USGS_MAP_PAGE),
    ]

    for label, page_url in pages:
        print()
        print(f"[USGS] {label}")

        try:
            final_page, urls = discover_usgs_image_urls(
                page_url
            )

            print(f"  candidate image URLs: {len(urls)}")

            report["pages"].append({
                "label": label,
                "page_url": page_url,
                "resolved_url": final_page,
                "candidate_urls": len(urls),
            })

        except Exception as exc:
            report["failed"].append({
                "page": page_url,
                "error": str(exc),
            })
            print(f"  PAGE ERROR: {exc}")
            continue

        for index, url in enumerate(urls, start=1):
            asset_id = hashlib.sha256(
                url.encode("utf-8")
            ).hexdigest()[:24]

            # USGS event/map pages explicitly identify their media
            # Sources/Usage as Public Domain.
            decision = gate.evaluate(
                asset_id=asset_id,
                source_mode="archive",
                license_id="PUBLIC DOMAIN",
                author="U.S. Geological Survey",
                source_url=page_url,
                license_url=page_url,
            )

            if not decision.allowed:
                report["blocked"].append({
                    "url": url,
                    "decision": decision.to_dict(),
                })
                continue

            try:
                data, headers, final_url = request_bytes(
                    url,
                    referer=page_url,
                )

                content_type = (
                    headers.get("Content-Type") or ""
                ).split(";")[0].strip().lower()

                if not content_type.startswith("image/"):
                    continue

                if len(data) < 25_000:
                    continue

                digest = hashlib.sha256(data).hexdigest()

                if digest in hashes:
                    report["duplicates"].append({
                        "url": final_url,
                        "sha256": digest,
                    })
                    continue

                suffix = mimetypes.guess_extension(
                    content_type
                ) or Path(
                    urllib.parse.urlparse(final_url).path
                ).suffix

                if suffix == ".jpe":
                    suffix = ".jpg"

                if suffix.lower() not in (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                ):
                    suffix = ".jpg"

                name = (
                    f"USGS_{label}_{index:03d}_"
                    f"{asset_id}{suffix}"
                )

                dest = USGS / safe_name(name)
                dest.write_bytes(data)
                hashes.add(digest)

                report["downloaded"].append({
                    "asset_id": asset_id,
                    "source_page": page_url,
                    "source_url": final_url,
                    "local_path": str(dest),
                    "sha256": digest,
                    "byte_size": len(data),
                    "rights": decision.to_dict(),
                })

                print(
                    f"  DOWNLOADED {dest.name} "
                    f"{round(len(data)/1024/1024, 2)} MB"
                )

            except Exception as exc:
                report["failed"].append({
                    "source_page": page_url,
                    "url": url,
                    "error": str(exc),
                })

    return report

def retry_wikimedia():
    print()
    print("=" * 72)
    print("WIKIMEDIA RETRY")
    print("=" * 72)

    acq = ArchiveAcquisitionRC2(
        project_id=PROJECT_ID,
        root=ROOT,
    )

    all_rows = []
    discovery = []

    for query in RETRY_SEARCHES:
        print()
        print(f"[SEARCH] {query}")

        try:
            rows = acq.discover_wikimedia(
                query=query,
                limit=35,
            )

            allowed = [
                row for row in rows
                if row.rights_allowed
            ]

            print(
                f"  returned={len(rows)} "
                f"allowed={len(allowed)}"
            )

            discovery.append({
                "query": query,
                "returned": len(rows),
                "allowed": len(allowed),
            })

            all_rows.extend(allowed)

        except Exception as exc:
            print(f"  ERROR: {exc}")
            discovery.append({
                "query": query,
                "error": str(exc),
            })

        # Avoid Wikimedia API burst/429.
        time.sleep(8)

    unique = {}

    for row in all_rows:
        key = row.download_url or row.candidate_id
        unique[key] = row

    candidates = list(unique.values())

    candidates.sort(
        key=lambda row: (
            -(int(row.width or 0) * int(row.height or 0)),
            row.title.lower(),
        )
    )

    print()
    print(
        f"Rights-cleared unique retry candidates: "
        f"{len(candidates)}"
    )

    # Existing acquisition downloader retains the canonical
    # VisualRightsGate behavior.
    result = acq.download_candidates(
        candidates,
        limit=80,
        minimum_width=900,
        minimum_height=500,
        delay_sec=4.0,
    )

    manifest = acq.write_manifest(
        result,
        name="film_09_archive_acquisition_pass2",
    )

    return {
        "discovery": discovery,
        "result": result,
        "manifest": str(manifest),
    }

def inventory():
    rows = []

    for provider, base in (
        ("wikimedia_archive", ARCHIVE),
        ("usgs", USGS),
    ):
        if not base.exists():
            continue

        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue

            try:
                rows.append({
                    "provider": provider,
                    "path": str(path),
                    "filename": path.name,
                    "extension": path.suffix.lower(),
                    "byte_size": path.stat().st_size,
                    "sha256": sha256_file(path),
                })
            except Exception as exc:
                rows.append({
                    "provider": provider,
                    "path": str(path),
                    "error": str(exc),
                })

    return rows

def main():
    OPS.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    USGS.mkdir(parents=True, exist_ok=True)

    # Extract diagnostic failure reasons from PASS 1.
    manifests = sorted(
        (
            PROJECT
            / "02_Visuals"
            / "archive"
            / "acquisition"
            / "manifests"
        ).glob("film_09_archive_acquisition_*.json")
    )

    pass1_failure_summary = {}

    if manifests:
        latest = manifests[-1]

        try:
            payload = json.loads(
                latest.read_text(encoding="utf-8-sig")
            )

            for row in payload.get("failed") or []:
                reason = str(
                    row.get("error") or "unknown"
                )

                key = reason[:300]

                pass1_failure_summary[key] = (
                    pass1_failure_summary.get(key, 0) + 1
                )

        except Exception as exc:
            pass1_failure_summary = {
                "manifest_read_error": str(exc)
            }

    print()
    print("[PASS 1 FAILURE REASONS]")

    for reason, count in sorted(
        pass1_failure_summary.items(),
        key=lambda item: -item[1],
    ):
        print(f"  {count:3d}  {reason}")

    wikimedia = retry_wikimedia()
    usgs = download_usgs_assets()
    media_inventory = inventory()

    total_bytes = sum(
        row.get("byte_size", 0)
        for row in media_inventory
        if not row.get("error")
    )

    report = {
        "project_id": PROJECT_ID,
        "generated_at": now(),
        "pass1_failure_summary": pass1_failure_summary,
        "wikimedia_pass2": wikimedia,
        "usgs_event_acquisition": usgs,
        "inventory": media_inventory,
        "summary": {
            "total_real_assets":
                len(media_inventory),
            "usgs_assets":
                sum(
                    1 for x in media_inventory
                    if x.get("provider") == "usgs"
                ),
            "wikimedia_assets":
                sum(
                    1 for x in media_inventory
                    if x.get("provider")
                    == "wikimedia_archive"
                ),
            "total_bytes": total_bytes,
            "total_mb": round(
                total_bytes / 1024 / 1024,
                2
            ),
        },
        "next_stage":
            "semantic_visual_selection_and_coverage",
    }

    write_json(
        OPS / "FILM_09_ACQUISITION_PASS2_REPORT.json",
        report,
    )

    write_json(
        OPS / "FILM_09_REAL_ASSET_INVENTORY.json",
        {
            "project_id": PROJECT_ID,
            "generated_at": now(),
            "assets": media_inventory,
        },
    )

    print()
    print("=" * 76)
    print("FILM 09 — PASS 2 COMPLETE")
    print("=" * 76)

    print(
        json.dumps(
            report["summary"],
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(
        "NEXT: semantic selection + "
        "real-screen coverage calculation"
    )

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
