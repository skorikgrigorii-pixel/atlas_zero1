from __future__ import annotations

import csv
import html
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from .paths import ROOT
from .production_visual_manager import ProductionVisualManager


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class ImageFeatures:
    width: int
    height: int
    format: str
    mtime: float
    byte_size: int
    hash_hex: str
    brightness: float
    contrast: float
    saturation: float
    edge_density: float
    blue_ratio: float


@dataclass
class CandidateImage:
    path: Path
    features: ImageFeatures
    mtime_rank: int
    is_batch_candidate: bool = False
    batch_rank: int | None = None


class VisualAssetRegistrar:
    """Safely registers unassigned generated visuals against pending queue items."""

    def __init__(self, project_id: str, root_dir: Path | None = None) -> None:
        self.project_id = project_id
        self.root_dir = Path(root_dir) if root_dir is not None else ROOT
        self.export_dir = self.root_dir / "workspace" / "exports" / project_id
        self.queue_path = self.export_dir / "visual_generation_queue.json"
        self.report_json_path = self.export_dir / "visual_registration_report.json"
        self.report_html_path = self.export_dir / "visual_registration_report.html"
        self.review_csv_path = self.export_dir / "visual_registration_review.csv"

    def run(self) -> dict[str, Any]:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        queue_items = self._load_queue_items()
        recommended_names = {
            str(item.get("recommended_filename") or "").strip().lower()
            for item in queue_items
            if str(item.get("recommended_filename") or "").strip()
        }
        pending_items = [item for item in queue_items if str(item.get("status") or "").upper() == "PENDING"]
        image_library = self._detect_image_library(queue_items)

        scan_result = self._collect_candidates(image_library, recommended_names)
        candidates = scan_result["candidates"]
        ignored_unsupported = scan_result["ignored_unsupported"]
        skipped_registered = scan_result["skipped_registered"]

        duplicate_files = self._detect_duplicates(candidates, queue_items)
        matches = self._match_candidates(candidates, pending_items, duplicate_files)

        auto_accepted = 0
        review = 0
        rejected = 0
        touched_queue_ids: set[str] = set()

        for row in matches:
            decision = row["decision"]
            if decision == "AUTO_ACCEPT":
                queue_item = row["queue_item"]
                target_path = Path(str(queue_item.get("target_path") or "").strip())
                if target_path.exists():
                    row["decision"] = "REVIEW"
                    row["reasons"].append("target already exists; no overwrite")
                    review += 1
                    continue
                if self._safe_create_target_copy(Path(row["source_file"]), target_path):
                    queue_item["status"] = "COMPLETED"
                    auto_accepted += 1
                    touched_queue_ids.add(str(queue_item.get("queue_id") or ""))
                else:
                    row["decision"] = "REVIEW"
                    row["reasons"].append("target copy failed validation")
                    review += 1
            elif decision == "REVIEW":
                review += 1
            else:
                rejected += 1

        self.queue_path.write_text(json.dumps(queue_items, ensure_ascii=False, indent=2), encoding="utf-8")
        progress = ProductionVisualManager(project_id=self.project_id, root_dir=self.root_dir).run_progress()

        report_rows = [
            {
                "source_file": row["source_file"],
                "queue_id": row.get("queue_id"),
                "recommended_filename": row.get("recommended_filename"),
                "confidence": row["confidence"],
                "reasons": row["reasons"],
                "decision": row["decision"],
            }
            for row in matches
        ]
        report = {
            "project_id": self.project_id,
            "image_library_path": str(image_library),
            "queue_path": str(self.queue_path),
            "scanned": len(candidates),
            "ignored_unsupported": ignored_unsupported,
            "skipped_registered": skipped_registered,
            "auto_accepted": auto_accepted,
            "review": review,
            "rejected": rejected,
            "touched_queue_ids": sorted(qid for qid in touched_queue_ids if qid),
            "matches": report_rows,
            "progress": progress,
        }

        self.report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.report_html_path.write_text(self._build_html_report(report), encoding="utf-8")
        self._write_review_csv(report_rows)

        return {
            "project_id": self.project_id,
            "scanned": len(candidates),
            "auto_accepted": auto_accepted,
            "review": review,
            "rejected": rejected,
            "completed": progress.get("completed_items"),
            "pending": progress.get("pending_items"),
            "next_item": progress.get("next_item"),
            "report_json": str(self.report_json_path),
            "report_html": str(self.report_html_path),
            "review_csv": str(self.review_csv_path),
        }

    def _load_queue_items(self) -> list[dict[str, Any]]:
        if not self.queue_path.exists():
            return []
        data = json.loads(self.queue_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def _detect_image_library(self, queue_items: list[dict[str, Any]]) -> Path:
        for item in queue_items:
            target_path = str(item.get("target_path") or "").strip()
            if target_path:
                parent = Path(target_path).parent
                if parent.exists() or "02_Images" in parent.as_posix():
                    return parent
        return self.root_dir / "workspace" / "projects" / self.project_id / "02_Images"

    def _collect_candidates(self, image_library: Path, recommended_names: set[str]) -> dict[str, Any]:
        candidates: list[CandidateImage] = []
        ignored_unsupported = 0
        skipped_registered = 0

        image_library.mkdir(parents=True, exist_ok=True)
        files = sorted([p for p in image_library.iterdir() if p.is_file()], key=lambda p: (p.stat().st_mtime, p.name.lower()))
        for file_path in files:
            ext = file_path.suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                ignored_unsupported += 1
                continue
            if file_path.name.lower() in recommended_names or file_path.name.upper().startswith("P5_"):
                skipped_registered += 1
                continue
            features = self._extract_features(file_path)
            if features is None:
                ignored_unsupported += 1
                continue
            candidates.append(CandidateImage(path=file_path, features=features, mtime_rank=len(candidates)))

        batch_candidates = [c for c in candidates if "chatgpt image" in c.path.name.lower()]
        for idx, candidate in enumerate(batch_candidates):
            candidate.is_batch_candidate = True
            candidate.batch_rank = idx

        return {
            "candidates": candidates,
            "ignored_unsupported": ignored_unsupported,
            "skipped_registered": skipped_registered,
        }

    def _extract_features(self, file_path: Path) -> ImageFeatures | None:
        try:
            with Image.open(file_path) as check_img:
                check_img.verify()
            with Image.open(file_path) as img:
                rgb = img.convert("RGB")
                gray = rgb.convert("L")
                stat_rgb = ImageStat.Stat(rgb)
                stat_gray = ImageStat.Stat(gray)
                r, g, b = stat_rgb.mean
                brightness = float(0.2126 * r + 0.7152 * g + 0.0722 * b)
                contrast = float(stat_gray.stddev[0]) if stat_gray.stddev else 0.0
                resize_small = rgb.resize((96, 96))
                pixels = list(resize_small.getdata())
                saturation = 0.0
                if pixels:
                    saturation = float(sum((max(px) - min(px)) / 255.0 for px in pixels) / len(pixels))
                edge_stat = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES))
                edge_density = float(edge_stat.mean[0] / 255.0)
                total = r + g + b
                blue_ratio = float(b / total) if total > 0 else 0.0
                return ImageFeatures(
                    width=int(rgb.width),
                    height=int(rgb.height),
                    format=str((img.format or file_path.suffix[1:]).upper()),
                    mtime=float(file_path.stat().st_mtime),
                    byte_size=int(file_path.stat().st_size),
                    hash_hex=self._dhash_hex(gray),
                    brightness=brightness,
                    contrast=contrast,
                    saturation=saturation,
                    edge_density=edge_density,
                    blue_ratio=blue_ratio,
                )
        except Exception:
            return None

    def _detect_duplicates(
        self,
        candidates: list[CandidateImage],
        queue_items: list[dict[str, Any]],
    ) -> dict[str, str]:
        duplicates: dict[str, str] = {}

        existing_hashes: dict[str, str] = {}
        for item in queue_items:
            recommended = str(item.get("recommended_filename") or "").strip()
            target_path = Path(str(item.get("target_path") or "").strip())
            if not recommended or not target_path.exists() or not target_path.is_file():
                continue
            features = self._extract_features(target_path)
            if features is not None:
                existing_hashes[recommended] = features.hash_hex

        for idx, cand in enumerate(candidates):
            for other in candidates[idx + 1 :]:
                if self._hamming_hex(cand.features.hash_hex, other.features.hash_hex) <= 4:
                    duplicates[str(other.path)] = f"duplicate of {cand.path.name}"

        for cand in candidates:
            if str(cand.path) in duplicates:
                continue
            for name, existing_hash in existing_hashes.items():
                if self._hamming_hex(cand.features.hash_hex, existing_hash) <= 4:
                    duplicates[str(cand.path)] = f"duplicate of existing {name}"
                    break

        return duplicates

    def _match_candidates(
        self,
        candidates: list[CandidateImage],
        pending_items: list[dict[str, Any]],
        duplicate_files: dict[str, str],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not candidates:
            return rows
        pending_count = len(pending_items)
        candidate_count = len(candidates)
        batch_count = sum(1 for c in candidates if c.is_batch_candidate)

        scored_pairs: list[tuple[float, int, int, list[str]]] = []
        for cand_idx, candidate in enumerate(candidates):
            if str(candidate.path) in duplicate_files:
                continue
            for item_idx, item in enumerate(pending_items):
                confidence, reasons = self._score_candidate_item(
                    candidate=candidate,
                    item=item,
                    candidate_rank=cand_idx,
                    pending_rank=item_idx,
                    total_candidates=candidate_count,
                    total_pending=pending_count,
                    total_batch=batch_count,
                )
                scored_pairs.append((confidence, cand_idx, item_idx, reasons))

        scored_pairs.sort(key=lambda x: x[0], reverse=True)
        assigned_candidates: set[int] = set()
        assigned_items: set[int] = set()
        assignments: dict[int, tuple[int, float, list[str]]] = {}

        for confidence, cand_idx, item_idx, reasons in scored_pairs:
            if cand_idx in assigned_candidates or item_idx in assigned_items:
                continue
            if confidence < 0.25:
                continue
            assigned_candidates.add(cand_idx)
            assigned_items.add(item_idx)
            assignments[cand_idx] = (item_idx, confidence, reasons)

        for cand_idx, candidate in enumerate(candidates):
            path_key = str(candidate.path)
            if path_key in duplicate_files:
                rows.append(
                    {
                        "source_file": path_key,
                        "queue_id": None,
                        "recommended_filename": None,
                        "confidence": 0.0,
                        "reasons": [duplicate_files[path_key]],
                        "decision": "REJECT",
                        "queue_item": None,
                    }
                )
                continue

            assignment = assignments.get(cand_idx)
            if assignment is None:
                rows.append(
                    {
                        "source_file": path_key,
                        "queue_id": None,
                        "recommended_filename": None,
                        "confidence": 0.0,
                        "reasons": ["no reliable pending match"],
                        "decision": "REJECT",
                        "queue_item": None,
                    }
                )
                continue

            item_idx, confidence, reasons = assignment
            queue_item = pending_items[item_idx]
            decision = "AUTO_ACCEPT" if confidence >= 0.80 else "REVIEW"
            rows.append(
                {
                    "source_file": path_key,
                    "queue_id": str(queue_item.get("queue_id") or ""),
                    "recommended_filename": str(queue_item.get("recommended_filename") or ""),
                    "confidence": round(confidence, 4),
                    "reasons": reasons,
                    "decision": decision,
                    "queue_item": queue_item,
                }
            )
        return rows

    def _score_candidate_item(
        self,
        candidate: CandidateImage,
        item: dict[str, Any],
        candidate_rank: int,
        pending_rank: int,
        total_candidates: int,
        total_pending: int,
        total_batch: int,
    ) -> tuple[float, list[str]]:
        visual_need = str(item.get("visual_need") or "").strip().lower()
        rec_name = str(item.get("recommended_filename") or "").strip().lower()
        prompt = str(item.get("prompt") or "").strip().lower()

        expected_document = any(k in visual_need or k in rec_name for k in ("document", "letter", "note", "text", "archive"))
        expected_underwater = any(k in visual_need or k in rec_name for k in ("underwater", "ship"))
        expected_sonar = "sonar" in visual_need or "screen" in visual_need
        expected_lab = any(k in visual_need or k in rec_name for k in ("bones", "lab", "medical"))

        f = candidate.features
        reasons: list[str] = []

        filename_hint = self._filename_hint_score(candidate.path.name.lower(), visual_need, rec_name)
        if filename_hint > 0:
            reasons.append("filename hint")

        profile_score = 0.15
        if expected_document:
            doc_score = 0.0
            if f.saturation <= 0.16:
                doc_score += 0.45
            if f.brightness >= 45:
                doc_score += 0.35
            if f.blue_ratio <= 0.36:
                doc_score += 0.20
            profile_score = max(profile_score, min(doc_score, 1.0))
            reasons.append("document profile")

        if expected_underwater:
            under_score = 0.0
            if f.blue_ratio >= 0.33:
                under_score += 0.50
            if f.brightness <= 95:
                under_score += 0.20
            if f.saturation >= 0.07:
                under_score += 0.20
            if f.edge_density >= 0.015:
                under_score += 0.10
            profile_score = max(profile_score, min(under_score, 1.0))
            reasons.append("underwater profile")

        if expected_sonar:
            sonar_score = 0.0
            if f.brightness <= 70:
                sonar_score += 0.35
            if f.contrast >= 15:
                sonar_score += 0.35
            if f.saturation <= 0.12:
                sonar_score += 0.15
            if f.edge_density >= 0.02:
                sonar_score += 0.15
            profile_score = max(profile_score, min(sonar_score, 1.0))
            reasons.append("sonar/screen profile")

        if expected_lab:
            lab_score = 0.0
            if 35 <= f.brightness <= 140:
                lab_score += 0.35
            if 0.02 <= f.saturation <= 0.25:
                lab_score += 0.30
            if f.edge_density >= 0.02:
                lab_score += 0.20
            if f.contrast >= 8:
                lab_score += 0.15
            profile_score = max(profile_score, min(lab_score, 1.0))
            reasons.append("archive/lab profile")

        if "prompt" in prompt and not reasons:
            reasons.append("prompt available")

        shape_score = 1.0 if 1.25 <= (f.width / max(f.height, 1)) <= 1.7 else 0.6
        if shape_score >= 1.0:
            reasons.append("cinematic aspect")

        if total_candidates <= 1 or total_pending <= 1:
            time_score = 0.5
        else:
            c_norm = candidate_rank / max(total_candidates - 1, 1)
            q_norm = pending_rank / max(total_pending - 1, 1)
            time_score = max(0.0, 1.0 - abs(c_norm - q_norm))
        if time_score >= 0.75:
            reasons.append("mtime sequence weak alignment")

        batch_sequence_score = 0.0
        if candidate.is_batch_candidate and candidate.batch_rank is not None and total_batch > 1 and total_pending > 1:
            b_norm = candidate.batch_rank / max(total_batch - 1, 1)
            q_norm = pending_rank / max(total_pending - 1, 1)
            batch_sequence_score = max(0.0, 1.0 - abs(b_norm - q_norm))
            if batch_sequence_score >= 0.70:
                reasons.append("batch sequence weak alignment")

        source_pattern_score = 1.0 if candidate.is_batch_candidate else 0.0
        if source_pattern_score > 0:
            reasons.append("generated filename pattern")

        confidence = (
            0.52 * profile_score
            + 0.18 * filename_hint
            + 0.10 * time_score
            + 0.08 * shape_score
            + 0.06 * source_pattern_score
            + 0.06 * batch_sequence_score
        )

        bonus = 0.0
        if source_pattern_score > 0 and batch_sequence_score >= 0.70 and profile_score >= 0.70:
            bonus += 0.08
        if (expected_document or expected_lab) and profile_score >= 0.90 and candidate.features.format == "PNG":
            bonus += 0.04
        if (expected_underwater or expected_sonar) and profile_score >= 0.90:
            bonus += 0.04

        if not (expected_document or expected_underwater or expected_sonar or expected_lab):
            confidence -= 0.10
        confidence = max(0.0, min(confidence + bonus, 1.0))

        unique_reasons: list[str] = []
        for reason in reasons:
            if reason not in unique_reasons:
                unique_reasons.append(reason)
        return confidence, unique_reasons or ["weak local signals"]

    @staticmethod
    def _filename_hint_score(candidate_name: str, visual_need: str, rec_name: str) -> float:
        hint_tokens = [
            token
            for token in (visual_need.replace("_", " ") + " " + rec_name.replace("_", " ")).split()
            if len(token) >= 4
        ]
        if not hint_tokens:
            return 0.0
        matches = sum(1 for token in hint_tokens if token in candidate_name)
        if matches <= 0:
            return 0.0
        return min(1.0, matches / max(1, len(set(hint_tokens))))

    def _safe_create_target_copy(self, source_path: Path, target_path: Path) -> bool:
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                return False
            if source_path.suffix.lower() in {".jpg", ".jpeg"}:
                shutil.copy2(source_path, target_path)
            else:
                with Image.open(source_path) as src:
                    src.convert("RGB").save(target_path, format="JPEG", quality=95)
            with Image.open(target_path) as dst:
                dst.verify()
            return True
        except Exception:
            if target_path.exists():
                try:
                    target_path.unlink()
                except OSError:
                    pass
            return False

    def _write_review_csv(self, rows: list[dict[str, Any]]) -> None:
        review_rows = [row for row in rows if row["decision"] in {"REVIEW", "REJECT"}]
        with self.review_csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "source_file",
                    "queue_id",
                    "recommended_filename",
                    "confidence",
                    "decision",
                    "reasons",
                ],
            )
            writer.writeheader()
            for row in review_rows:
                writer.writerow(
                    {
                        "source_file": row.get("source_file"),
                        "queue_id": row.get("queue_id") or "",
                        "recommended_filename": row.get("recommended_filename") or "",
                        "confidence": row.get("confidence"),
                        "decision": row.get("decision"),
                        "reasons": " | ".join(row.get("reasons") or []),
                    }
                )

    def _build_html_report(self, report: dict[str, Any]) -> str:
        rows = report.get("matches") or []
        body_rows = []
        for row in rows:
            reasons = "<br>".join(html.escape(str(r)) for r in row.get("reasons") or [])
            body_rows.append(
                "<tr>"
                f"<td>{html.escape(str(row.get('source_file') or ''))}</td>"
                f"<td>{html.escape(str(row.get('queue_id') or ''))}</td>"
                f"<td>{html.escape(str(row.get('recommended_filename') or ''))}</td>"
                f"<td>{html.escape(str(row.get('confidence') or 0))}</td>"
                f"<td>{html.escape(str(row.get('decision') or ''))}</td>"
                f"<td>{reasons}</td>"
                "</tr>"
            )

        return "\n".join(
            [
                "<!doctype html>",
                "<html lang='en'>",
                "<head>",
                "<meta charset='utf-8'>",
                f"<title>Visual Registration Report: {html.escape(self.project_id)}</title>",
                "<style>",
                "body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #111; }",
                "h1, h2 { margin: 0 0 10px 0; }",
                "table { border-collapse: collapse; width: 100%; margin-top: 12px; }",
                "th, td { border: 1px solid #ccc; padding: 6px 8px; font-size: 13px; vertical-align: top; }",
                "th { background: #f1f1f1; text-align: left; }",
                "</style>",
                "</head>",
                "<body>",
                f"<h1>Visual Registration Report: {html.escape(self.project_id)}</h1>",
                f"<p>Scanned: {report.get('scanned', 0)} | Auto accepted: {report.get('auto_accepted', 0)} | Review: {report.get('review', 0)} | Rejected: {report.get('rejected', 0)}</p>",
                "<h2>Matches</h2>",
                "<table>",
                "<thead><tr><th>Source File</th><th>Queue ID</th><th>Recommended Filename</th><th>Confidence</th><th>Decision</th><th>Reasons</th></tr></thead>",
                "<tbody>",
                *body_rows,
                "</tbody>",
                "</table>",
                "</body>",
                "</html>",
            ]
        )

    @staticmethod
    def _dhash_hex(gray_image: Image.Image) -> str:
        resized = gray_image.resize((9, 8))
        pixels = list(resized.getdata())
        bits: list[int] = []
        for row in range(8):
            row_start = row * 9
            for col in range(8):
                left = pixels[row_start + col]
                right = pixels[row_start + col + 1]
                bits.append(1 if left > right else 0)

        value = 0
        for bit in bits:
            value = (value << 1) | bit
        return f"{value:016x}"

    @staticmethod
    def _hamming_hex(left: str, right: str) -> int:
        if not left or not right:
            return 64
        try:
            a = int(left, 16)
            b = int(right, 16)
        except ValueError:
            return 64
        return (a ^ b).bit_count()