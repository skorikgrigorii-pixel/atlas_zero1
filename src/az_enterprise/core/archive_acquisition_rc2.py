from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .visual_rights_gate_rc2 import VisualRightsGateRC2


@dataclass
class ArchiveCandidateRC2:
    candidate_id: str
    provider: str
    title: str
    source_url: str
    download_url: str
    license_id: str
    license_url: str
    author: str
    width: int
    height: int
    description: str = ""
    search_query: str = ""
    local_path: str = ""
    rights_allowed: bool = False
    rights_decision: str = ""
    rights_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArchiveAcquisitionRC2:
    """
    ATLAS ZERO RC2 — archival visual acquisition layer.

    Responsibilities:
    - discover archive candidates;
    - preserve source / author / license provenance;
    - evaluate every candidate through VisualRightsGateRC2;
    - download only rights-cleared originals into production media;
    - keep manifests outside the production media scan;
    - deduplicate downloaded files by SHA-256.

    This module does NOT:
    - replace AssetIntelligence;
    - replace Story Engine;
    - replace VisualRightsGateRC2;
    - make copyright decisions independently.
    """

    USER_AGENT = "AtlasZeroDocumentary/1.0"

    def __init__(
        self,
        *,
        project_id: str,
        root: str | Path,
    ) -> None:
        self.project_id = str(project_id)
        self.root = Path(root)

        self.project_dir = (
            self.root
            / "workspace"
            / "projects"
            / self.project_id
        )

        # Research/archive manifests stay outside production media.
        self.archive_root = (
            self.project_dir
            / "02_Visuals"
            / "archive"
            / "acquisition"
        )

        # Rights-cleared files become visible to AssetIntelligence.
        self.production_root = (
            self.project_dir
            / "02_Visuals"
            / "real"
            / "archive"
        )

        self.manifest_dir = self.archive_root / "manifests"
        self.blocked_dir = self.archive_root / "blocked"

        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.blocked_dir.mkdir(parents=True, exist_ok=True)
        self.production_root.mkdir(parents=True, exist_ok=True)

        self.rights_gate = VisualRightsGateRC2()

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _safe_filename(value: str) -> str:
        chars = []

        for char in value:
            if char.isalnum() or char in "-_.":
                chars.append(char)
            elif char.isspace():
                chars.append("_")

        result = "".join(chars).strip("._")

        while "__" in result:
            result = result.replace("__", "_")

        return result[:180] or "archive_asset"

    @staticmethod
    def _metadata_value(
        metadata: dict[str, Any],
        key: str,
    ) -> str:
        value = metadata.get(key) or {}

        if isinstance(value, dict):
            return str(value.get("value") or "").strip()

        return str(value or "").strip()

    def discover_wikimedia(
        self,
        *,
        query: str,
        limit: int = 20,
        required_terms: tuple[str, ...] | None = None,
        excluded_terms: tuple[str, ...] | None = None,
    ) -> list[ArchiveCandidateRC2]:

        api = "https://commons.wikimedia.org/w/api.php"

        params = urllib.parse.urlencode(
            {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 6,
                "gsrlimit": max(1, min(int(limit), 50)),
                "prop": "imageinfo",
                "iiprop": "url|size|extmetadata",
            }
        )

        request = urllib.request.Request(
            api + "?" + params,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=45,
        ) as response:
            payload = json.load(response)

        pages = (
            payload
            .get("query", {})
            .get("pages", {})
        )

        rows: list[ArchiveCandidateRC2] = []

        for page in pages.values():

            imageinfo = page.get("imageinfo") or []

            if not imageinfo:
                continue

            info = imageinfo[0]
            metadata = info.get("extmetadata") or {}

            title = str(page.get("title") or "").strip()

            source_url = (
                "https://commons.wikimedia.org/wiki/"
                + urllib.parse.quote(
                    title.replace(" ", "_"),
                    safe=":_()-,.'",
                )
            )

            download_url = str(
                info.get("url") or ""
            ).strip()

            if not download_url:
                continue

            license_id = self._metadata_value(
                metadata,
                "LicenseShortName",
            )

            license_url = self._metadata_value(
                metadata,
                "LicenseUrl",
            )

            author = self._metadata_value(
                metadata,
                "Artist",
            )

            description = self._metadata_value(
                metadata,
                "ImageDescription",
            )

            candidate_id = hashlib.sha256(
                (
                    "wikimedia:"
                    + title
                    + ":"
                    + download_url
                ).encode("utf-8")
            ).hexdigest()[:24]

            decision = self.rights_gate.evaluate(
                asset_id=candidate_id,
                source_mode="archive",
                license_id=license_id,
                author=author,
                source_url=source_url,
                license_url=license_url,
            )

            rows.append(
                ArchiveCandidateRC2(
                    candidate_id=candidate_id,
                    provider="wikimedia_commons",
                    title=title,
                    source_url=source_url,
                    download_url=download_url,
                    license_id=license_id,
                    license_url=license_url,
                    author=author,
                    width=int(info.get("width") or 0),
                    height=int(info.get("height") or 0),
                    description=description,
                    search_query=query,
                    rights_allowed=bool(
                        decision.allowed
                    ),
                    rights_decision=str(
                        decision.decision
                    ),
                    rights_reason=str(
                        decision.reason
                    ),
                )
            )

        # Keep discovery production-oriented.
        # Reject obvious non-visual documents and weak/social-derived noise.
        filtered: list[ArchiveCandidateRC2] = []

        required_terms_norm = tuple(
            str(term).strip().lower()
            for term in (required_terms or ())
            if str(term).strip()
        )

        excluded_terms_norm = tuple(
            str(term).strip().lower()
            for term in (excluded_terms or ())
            if str(term).strip()
        )

        query_tokens = {
            token.lower()
            for token in query.replace('"', " ").replace("'", " ").split()
            if len(token) >= 3
        }

        blocked_title_tokens = {
            ".pdf",
            "reddit",
            "always-wondered",
            "meme",
            "screenshot",
        }

        for row in rows:
            title_low = row.title.lower()

            if any(token in title_low for token in blocked_title_tokens):
                continue

            # Only production-friendly raster/gif assets.
            parsed_path = urllib.parse.urlparse(
                row.download_url
            ).path.lower()

            if not parsed_path.endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif",
                    ".tif",
                    ".tiff",
                    ".webm",
                    ".mp4",
                    ".mov",
                )
            ):
                continue

            haystack = (
                row.title
                + " "
                + row.description
            ).lower()

            if excluded_terms_norm and any(
                term in haystack
                for term in excluded_terms_norm
            ):
                continue

            if required_terms_norm and not any(
                term in haystack
                for term in required_terms_norm
            ):
                continue

            relevance_hits = sum(
                1
                for token in query_tokens
                if token in haystack
            )

            # Allow strong known Cooper-specific filenames even when metadata is sparse.
            cooper_specific = any(
                token in title_low
                for token in (
                    "cooper",
                    "727",
                    "northwest",
                    "flight 305",
                )
            )

            if relevance_hits == 0 and not cooper_specific:
                continue

            filtered.append(row)

        filtered.sort(
            key=lambda row: (
                not row.rights_allowed,
                -sum(
                    1
                    for token in query_tokens
                    if token in (
                        row.title + " " + row.description
                    ).lower()
                ),
                -(row.width * row.height),
                row.title.lower(),
            )
        )

        return filtered

    def download_candidates(
        self,
        candidates: list[ArchiveCandidateRC2],
        *,
        limit: int = 20,
        minimum_width: int = 800,
        minimum_height: int = 500,
        delay_sec: float = 6.0,
    ) -> dict[str, Any]:

        downloaded: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        existing_hashes: set[str] = set()

        for path in self.production_root.rglob("*"):
            if not path.is_file():
                continue

            try:
                digest = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                existing_hashes.add(digest)
            except OSError:
                pass

        accepted_count = 0

        for candidate in candidates:

            if accepted_count >= int(limit):
                break

            if not candidate.rights_allowed:
                blocked.append(candidate.to_dict())
                continue

            if (
                candidate.width < minimum_width
                or candidate.height < minimum_height
            ):
                row = candidate.to_dict()
                row["skip_reason"] = (
                    "below_minimum_dimensions"
                )
                blocked.append(row)
                continue

            try:
                request = urllib.request.Request(
                    candidate.download_url,
                    headers={
                        "User-Agent": self.USER_AGENT,
                        "Referer": candidate.source_url,
                    },
                )

                with urllib.request.urlopen(
                    request,
                    timeout=120,
                ) as response:
                    content = response.read()

                digest = self._sha256_bytes(
                    content
                )

                if digest in existing_hashes:
                    row = candidate.to_dict()
                    row["skip_reason"] = "duplicate_sha256"
                    blocked.append(row)
                    continue

                suffix = Path(
                    urllib.parse.urlparse(
                        candidate.download_url
                    ).path
                ).suffix.lower()

                if suffix not in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".tif",
                    ".tiff",
                    ".gif",
                    ".webm",
                    ".mp4",
                    ".mov",
                }:
                    suffix = ".bin"

                filename = (
                    candidate.candidate_id[:8]
                    + "_"
                    + self._safe_filename(
                        candidate.title
                        .replace("File:", "")
                    )
                )

                if not filename.lower().endswith(
                    suffix
                ):
                    filename += suffix

                destination = (
                    self.production_root
                    / filename
                )

                destination.write_bytes(content)

                existing_hashes.add(digest)
                accepted_count += 1

                candidate.local_path = str(
                    destination
                )

                row = candidate.to_dict()
                row["sha256"] = digest
                row["byte_size"] = len(content)

                downloaded.append(row)

                if delay_sec > 0:
                    time.sleep(delay_sec)

            except Exception as error:
                row = candidate.to_dict()
                row["error"] = str(error)
                failed.append(row)

        result = {
            "schema": (
                "atlas_zero.archive_acquisition.rc2"
            ),
            "project_id": self.project_id,
            "downloaded": downloaded,
            "blocked": blocked,
            "failed": failed,
            "summary": {
                "candidates": len(candidates),
                "downloaded": len(downloaded),
                "blocked": len(blocked),
                "failed": len(failed),
            },
        }

        return result


    def download_social_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        limit: int = 50,
        max_duration_sec: float = 900.0,
    ) -> dict[str, Any]:
        """
        Download publicly accessible social-video candidates into the
        research corpus.

        IMPORTANT:
        Downloaded social media is NOT production-cleared merely because
        the media can be downloaded. Rights/provenance remain separate.
        """

        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError(
                "yt_dlp Python package is required for social acquisition"
            ) from exc

        social_root = (
            self.project_dir
            / "00_Research"
            / "visual_research"
            / "social_downloads"
        )

        social_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        downloaded = []
        failed = []
        skipped = []

        selected = candidates[:limit]

        for index, item in enumerate(selected, 1):

            candidate_id = str(
                item.get("id")
                or item.get("candidate_id")
                or f"social_{index:04d}"
            )

            platform = str(
                item.get("platform") or "unknown"
            )

            url = str(
                item.get("url")
                or item.get("direct_url")
                or item.get("source_url")
                or ""
            ).strip()

            rights_status = str(
                item.get("rights_status")
                or "RIGHTS_REVIEW"
            )

            if not url:
                failed.append({
                    "candidate_id": candidate_id,
                    "platform": platform,
                    "error": "missing_url",
                })
                continue

            candidate_dir = (
                social_root
                / self._safe_filename(candidate_id)
            )

            candidate_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            output_template = str(
                candidate_dir
                / "%(id)s_%(title).120B.%(ext)s"
            )

            ydl_opts = {
                "outtmpl": output_template,
                "restrictfilenames": True,
                "noplaylist": True,

                # Best practical video+audio combination.
                "format": (
                    "bestvideo*+bestaudio/"
                    "best"
                ),

                "merge_output_format": "mp4",

                # Do not download comments/playlists/etc.
                "getcomments": False,
                "writesubtitles": False,
                "writeautomaticsub": False,
                "writethumbnail": False,

                # Metadata is useful for provenance tracing.
                "writeinfojson": True,

                "quiet": True,
                "no_warnings": True,

                # Do not deliberately bypass authentication,
                # paywalls or private-content restrictions.
                "ignoreerrors": False,
            }

            try:

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:

                    info = ydl.extract_info(
                        url,
                        download=False,
                    )

                    if not info:
                        raise RuntimeError(
                            "metadata_extraction_failed"
                        )

                    duration = info.get("duration")

                    if (
                        duration is not None
                        and float(duration) > max_duration_sec
                    ):
                        skipped.append({
                            "candidate_id": candidate_id,
                            "platform": platform,
                            "url": url,
                            "reason": "duration_limit",
                            "duration_sec": duration,
                        })
                        continue

                    result = ydl.extract_info(
                        url,
                        download=True,
                    )

                    if not result:
                        raise RuntimeError(
                            "download_failed_no_result"
                        )

                    files = [
                        str(p)
                        for p in candidate_dir.iterdir()
                        if p.is_file()
                    ]

                    downloaded.append({
                        "candidate_id": candidate_id,
                        "platform": platform,
                        "source_url": url,
                        "title": result.get("title"),
                        "uploader": result.get("uploader"),
                        "uploader_id": result.get("uploader_id"),
                        "duration_sec": result.get("duration"),
                        "timestamp": result.get("timestamp"),
                        "webpage_url": result.get("webpage_url") or url,
                        "extractor": result.get("extractor"),
                        "rights_status": rights_status,
                        "production_eligible": False,
                        "local_files": files,
                    })

                    print(
                        f"[{index}/{len(selected)}] "
                        f"DOWNLOADED | {candidate_id} | "
                        f"{platform} | "
                        f"{result.get('title')}"
                    )

            except Exception as exc:

                failed.append({
                    "candidate_id": candidate_id,
                    "platform": platform,
                    "source_url": url,
                    "rights_status": rights_status,
                    "error": repr(exc),
                })

                print(
                    f"[{index}/{len(selected)}] "
                    f"FAILED | {candidate_id} | "
                    f"{platform} | {exc}"
                )

        result = {
            "schema": "atlas_zero.social_acquisition.v1",
            "project_id": self.project_id,
            "production_eligible": False,
            "research_only": True,
            "summary": {
                "candidates": len(selected),
                "downloaded": len(downloaded),
                "failed": len(failed),
                "skipped": len(skipped),
            },
            "downloaded": downloaded,
            "failed": failed,
            "skipped": skipped,
        }

        return result


    def write_manifest(
        self,
        result: dict[str, Any],
        *,
        name: str = "archive_acquisition",
    ) -> Path:

        timestamp = time.strftime(
            "%Y%m%d_%H%M%S"
        )

        destination = (
            self.manifest_dir
            / f"{name}_{timestamp}.json"
        )

        destination.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return destination
