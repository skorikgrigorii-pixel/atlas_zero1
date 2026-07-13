from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

ROOT = Path.cwd()
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from az_enterprise.core.database import Database
from az_enterprise.core.movie_runtime_rc1 import MovieRuntimeRC1


PROJECT_ID = "franklin"

PROJECT_DIR = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
)

IMAGE_DIR = PROJECT_DIR / "02_Images"

EXPORT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "visual_intelligence_v1"
)

CATALOG_PATH = EXPORT_DIR / "asset_semantic_catalog.json"
REPORT_PATH = EXPORT_DIR / "visual_intelligence_report.json"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}

SEMANTIC_CLASSES = {
    "arctic_aerial": [
        "aerial view of arctic sea ice",
        "ship viewed from above in pack ice",
        "wide frozen arctic landscape",
    ],
    "ship_in_ice": [
        "nineteenth century expedition ship trapped in ice",
        "wooden sailing ship surrounded by arctic ice",
        "Franklin expedition ship in frozen sea",
    ],
    "ship_detail": [
        "close view of frozen ship hull",
        "ship rigging covered in ice",
        "bow of wooden ship among ice",
    ],
    "crew_command": [
        "Victorian naval commander on ship deck",
        "Franklin expedition officers",
        "nineteenth century ship captain and crew",
    ],
    "crew_working": [
        "Victorian sailors working on deck",
        "expedition crew handling ropes",
        "sailors preparing an arctic ship",
    ],
    "crew_survival": [
        "arctic explorers dragging supplies over ice",
        "men struggling through frozen landscape",
        "Franklin expedition crew abandoning ship",
    ],
    "archive_letter": [
        "historical handwritten letter with wax seal",
        "Victorian Admiralty correspondence",
        "old handwritten expedition document",
    ],
    "archive_map": [
        "historical arctic map and compass",
        "old navigation map",
        "Victorian expedition chart",
    ],
    "archive_records": [
        "archive room with historical documents",
        "researcher examining Admiralty records",
        "boxes of old expedition documents",
    ],
    "medical_records": [
        "Victorian medical notes",
        "historical anatomical notebook",
        "nineteenth century medical journal",
    ],
    "final_note": [
        "Franklin expedition final written note",
        "historic message saying all well",
        "last expedition record found on map",
    ],
    "underwater_wreck": [
        "sunken wooden shipwreck underwater",
        "wreck of nineteenth century expedition ship",
        "dark underwater archaeological shipwreck",
    ],
    "underwater_robot": [
        "underwater remotely operated vehicle exploring wreck",
        "submersible robot with lights",
        "modern underwater archaeology robot",
    ],
    "sonar_scan": [
        "sonar scan of shipwreck",
        "multibeam sonar computer display",
        "modern archaeological scanning system",
    ],
    "ice_detail": [
        "close view of thick arctic ice",
        "ice pressure against wooden hull",
        "frozen ropes and rigging",
    ],
}

CLASS_TO_TAGS = {
    "arctic_aerial": [
        "arctic", "ice", "aerial", "wide", "isolation",
    ],
    "ship_in_ice": [
        "ship", "ice", "expedition", "arctic", "wide",
    ],
    "ship_detail": [
        "ship", "hull", "rigging", "ice", "detail",
    ],
    "crew_command": [
        "crew", "captain", "commander", "deck", "victorian",
    ],
    "crew_working": [
        "crew", "sailors", "deck", "ropes", "working",
    ],
    "crew_survival": [
        "crew", "survival", "ice", "sledge", "struggle",
    ],
    "archive_letter": [
        "archive", "letter", "document", "handwriting", "seal",
    ],
    "archive_map": [
        "archive", "map", "navigation", "document", "compass",
    ],
    "archive_records": [
        "archive", "records", "documents", "research",
    ],
    "medical_records": [
        "medical", "records", "document", "bones", "health",
    ],
    "final_note": [
        "final_note", "document", "message", "map", "discovery",
    ],
    "underwater_wreck": [
        "underwater", "wreck", "ship", "discovery", "dark",
    ],
    "underwater_robot": [
        "underwater", "robot", "rov", "technology", "discovery",
    ],
    "sonar_scan": [
        "sonar", "scan", "technology", "wreck", "research",
    ],
    "ice_detail": [
        "ice", "detail", "frozen", "pressure", "rigging",
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def difference_hash(path: Path, size: int = 16) -> str:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("L")
        image = image.resize(
            (size + 1, size),
            Image.Resampling.LANCZOS,
        )

        pixels = list(image.getdata())

    bits = []

    for row in range(size):
        offset = row * (size + 1)

        for column in range(size):
            left = pixels[offset + column]
            right = pixels[offset + column + 1]
            bits.append("1" if left > right else "0")

    value = int("".join(bits), 2)
    width = math.ceil(len(bits) / 4)

    return f"{value:0{width}x}"


def hamming_distance(left: str, right: str) -> int:
    return (
        int(left, 16) ^ int(right, 16)
    ).bit_count()


def filename_tokens(path: Path) -> set[str]:
    text = path.stem.lower()

    substitutions = {
        "crew": " crew ",
        "commander": " captain commander ",
        "working": " sailors working ",
        "deck": " deck ",
        "drone": " aerial wide ",
        "aerial": " aerial wide ",
        "hull": " hull ship ",
        "bow": " bow ship ",
        "rigging": " rigging ropes ",
        "icepressure": " ice pressure ",
        "closeic": " ice detail ",
        "document": " archive document ",
        "notes": " archive medical document ",
        "map": " archive map ",
        "robot": " underwater robot rov ",
        "sonar": " sonar scan ",
        "bones": " bones medical ",
        "ship_ice": " ship ice arctic ",
    }

    for source, replacement in substitutions.items():
        text = text.replace(source, replacement)

    return set(
        re.findall(
            r"[a-zа-яё0-9]+",
            text,
            flags=re.IGNORECASE,
        )
    )


def heuristic_class(path: Path) -> tuple[str, float]:
    words = filename_tokens(path)

    class_words = {
        "arctic_aerial": {
            "aerial", "drone", "wide",
        },
        "ship_in_ice": {
            "ship", "ice", "erebus", "terror",
        },
        "ship_detail": {
            "hull", "bow", "rigging", "deck",
        },
        "crew_command": {
            "crew", "commander", "captain",
        },
        "crew_working": {
            "crew", "working", "sailors",
        },
        "crew_survival": {
            "sledge", "survival", "men",
        },
        "archive_letter": {
            "letter", "document", "admiralty",
        },
        "archive_map": {
            "map", "navigation", "compass",
        },
        "archive_records": {
            "archive", "records", "library",
        },
        "medical_records": {
            "medical", "bones", "anatomy",
        },
        "final_note": {
            "note", "message", "all", "well",
        },
        "underwater_wreck": {
            "underwater", "wreck", "sunken",
        },
        "underwater_robot": {
            "robot", "rov", "submersible",
        },
        "sonar_scan": {
            "sonar", "scan", "screen",
        },
        "ice_detail": {
            "ice", "frozen", "pressure",
        },
    }

    ranking: list[tuple[float, str]] = []

    for semantic_class, expected in class_words.items():
        overlap = len(words & expected)

        score = overlap / max(
            1,
            min(len(words), len(expected)),
        )

        ranking.append((score, semantic_class))

    ranking.sort(reverse=True)

    best_score, best_class = ranking[0]

    if best_score <= 0:
        return "unclassified", 0.0

    return best_class, round(best_score, 4)


class ClipAnalyzer:
    def __init__(self) -> None:
        self.available = False
        self.error: str | None = None
        self.model = None
        self.processor = None
        self.torch = None

        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            self.torch = torch

            model_name = "openai/clip-vit-base-patch32"

            self.processor = CLIPProcessor.from_pretrained(
                model_name
            )

            self.model = CLIPModel.from_pretrained(
                model_name
            )

            self.model.eval()
            self.available = True

        except Exception as exc:
            self.error = str(exc)

    def classify(
        self,
        path: Path,
    ) -> tuple[str, float, dict[str, float]]:
        if not self.available:
            semantic_class, confidence = heuristic_class(path)

            return semantic_class, confidence, {
                semantic_class: confidence
            }

        labels = list(SEMANTIC_CLASSES)
        prompts = [
            SEMANTIC_CLASSES[label][0]
            for label in labels
        ]

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")

            inputs = self.processor(
                text=prompts,
                images=image,
                return_tensors="pt",
                padding=True,
            )

        with self.torch.no_grad():
            outputs = self.model(**inputs)
            probabilities = (
                outputs.logits_per_image
                .softmax(dim=1)[0]
                .cpu()
                .tolist()
            )

        ranking = sorted(
            zip(labels, probabilities),
            key=lambda item: item[1],
            reverse=True,
        )

        scores = {
            label: round(float(score), 5)
            for label, score in ranking[:5]
        }

        best_class, best_score = ranking[0]

        return (
            best_class,
            round(float(best_score), 5),
            scores,
        )


def image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)

        width, height = image.size

    aspect_ratio = round(
        width / max(height, 1),
        4,
    )

    orientation = (
        "landscape"
        if width > height
        else "portrait"
        if height > width
        else "square"
    )

    return {
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "orientation": orientation,
    }


def ensure_columns(db: Database) -> None:
    columns = {
        row["name"]
        for row in db.rows(
            "PRAGMA table_info(assets)"
        )
    }

    migrations = {
        "semantic_class": "TEXT",
        "semantic_description": "TEXT",
        "visual_group": "TEXT",
        "perceptual_hash": "TEXT",
        "semantic_confidence": "REAL DEFAULT 0",
        "max_use": "INTEGER DEFAULT 3",
    }

    for name, definition in migrations.items():
        if name not in columns:
            db.execute(
                f"ALTER TABLE assets "
                f"ADD COLUMN {name} {definition}"
            )


def main() -> None:
    EXPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not IMAGE_DIR.exists():
        raise FileNotFoundError(
            f"Image directory not found: {IMAGE_DIR}"
        )

    db = Database()
    db.init()

    runtime = MovieRuntimeRC1(
        db,
        PROJECT_ID,
    )

    scanned = runtime._scan_project_assets()
    runtime._sync_project_assets(scanned)

    ensure_columns(db)

    image_paths = sorted(
        [
            path
            for path in IMAGE_DIR.rglob("*")
            if path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
        ],
        key=lambda item: item.name.lower(),
    )

    analyzer = ClipAnalyzer()

    print("=" * 72)
    print("ATLAS ZERO — VISUAL INTELLIGENCE ENGINE V1")
    print("=" * 72)
    print("Images:", len(image_paths))
    print("CLIP available:", analyzer.available)

    if analyzer.error:
        print("CLIP fallback reason:", analyzer.error)

    catalog: list[dict[str, Any]] = []
    canonical_by_hash: dict[str, dict[str, Any]] = {}

    for index, path in enumerate(
        image_paths,
        start=1,
    ):
        digest = sha256(path)
        perceptual_hash = difference_hash(path)
        metadata = image_metadata(path)

        exact_duplicate_of: str | None = None
        near_duplicate_of: str | None = None

        if digest in canonical_by_hash:
            exact_duplicate_of = (
                canonical_by_hash[digest]["asset_id"]
            )
        else:
            for previous in catalog:
                distance = hamming_distance(
                    perceptual_hash,
                    previous["perceptual_hash"],
                )

                if distance <= 7:
                    near_duplicate_of = previous["asset_id"]
                    break

        semantic_class, confidence, scores = (
            analyzer.classify(path)
        )

        tags = CLASS_TO_TAGS.get(
            semantic_class,
            ["unclassified"],
        )

        max_use = 3

        if semantic_class in {
            "archive_letter",
            "archive_map",
            "medical_records",
            "final_note",
            "sonar_scan",
            "underwater_robot",
        }:
            max_use = 2

        if exact_duplicate_of or near_duplicate_of:
            max_use = 0

        asset_row = db.one(
            """
            SELECT id
            FROM assets
            WHERE project_id=?
              AND path=?
            """,
            (
                PROJECT_ID,
                str(path.resolve()),
            ),
        )

        if not asset_row:
            asset_row = db.one(
                """
                SELECT id
                FROM assets
                WHERE project_id=?
                  AND filename=?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    PROJECT_ID,
                    path.name,
                ),
            )

        asset_id = (
            str(asset_row["id"])
            if asset_row
            else digest[:16]
        )

        duplicate_of = (
            exact_duplicate_of
            or near_duplicate_of
        )

        description = (
            f"{semantic_class.replace('_', ' ')}; "
            + ", ".join(tags)
        )

        db.execute(
            """
            UPDATE assets
            SET
                sha256=?,
                tags=?,
                category=?,
                semantic_class=?,
                semantic_description=?,
                visual_group=?,
                perceptual_hash=?,
                semantic_confidence=?,
                max_use=?,
                duplicate_of=?,
                width=?,
                height=?
            WHERE id=?
            """,
            (
                digest,
                json.dumps(
                    tags,
                    ensure_ascii=False,
                ),
                semantic_class,
                semantic_class,
                description,
                semantic_class,
                perceptual_hash,
                confidence,
                max_use,
                duplicate_of,
                metadata["width"],
                metadata["height"],
                asset_id,
            ),
        )

        item = {
            "index": index,
            "asset_id": asset_id,
            "filename": path.name,
            "path": str(path.resolve()),
            "semantic_class": semantic_class,
            "semantic_confidence": confidence,
            "semantic_scores": scores,
            "tags": tags,
            "visual_group": semantic_class,
            "max_use": max_use,
            "duplicate_of": duplicate_of,
            "exact_duplicate": bool(
                exact_duplicate_of
            ),
            "near_duplicate": bool(
                near_duplicate_of
            ),
            "perceptual_hash": perceptual_hash,
            **metadata,
        }

        catalog.append(item)

        if digest not in canonical_by_hash:
            canonical_by_hash[digest] = item

        print(
            f"[{index:03d}/{len(image_paths):03d}] "
            f"{semantic_class:<20} "
            f"{confidence:>7.3f} "
            f"{path.name}"
        )

    class_counts = Counter(
        item["semantic_class"]
        for item in catalog
    )

    duplicate_count = sum(
        1
        for item in catalog
        if item["duplicate_of"]
    )

    usable_count = sum(
        1
        for item in catalog
        if item["max_use"] > 0
    )

    catalog_payload = {
        "version": "1.0",
        "project_id": PROJECT_ID,
        "analyzer": (
            "clip-vit-base-patch32"
            if analyzer.available
            else "filename-heuristic-fallback"
        ),
        "assets_total": len(catalog),
        "assets_usable": usable_count,
        "duplicates": duplicate_count,
        "class_counts": dict(class_counts),
        "assets": catalog,
    }

    CATALOG_PATH.write_text(
        json.dumps(
            catalog_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = {
        "project_id": PROJECT_ID,
        "state": "ANALYZED",
        "clip_available": analyzer.available,
        "clip_error": analyzer.error,
        "assets_total": len(catalog),
        "assets_usable": usable_count,
        "duplicates": duplicate_count,
        "semantic_groups": len(class_counts),
        "class_counts": dict(class_counts),
        "catalog": str(CATALOG_PATH),
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("VISUAL INTELLIGENCE RESULT")
    print("=" * 72)
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
