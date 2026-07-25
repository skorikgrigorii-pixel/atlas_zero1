from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from collections import OrderedDict

from .paths import ROOT


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ProductionVisualManager:
    """Offline queue manager for Franklin priority-5 visual production."""

    def __init__(self, project_id: str, root_dir: Path | None = None) -> None:
        self.project_id = project_id
        self.root_dir = Path(root_dir) if root_dir is not None else ROOT
        self.export_dir = self.root_dir / "workspace" / "exports" / project_id
        self.plan_path = self.export_dir / "priority5_visual_plan.csv"
        self.queue_path = self.export_dir / "visual_generation_queue.json"
        self.batch_path = self.export_dir / "visual_generation_batch.md"
        self.progress_path = self.export_dir / "visual_generation_progress.json"
        self.image_library_path = self._detect_image_library_path()

    def run_queue(self) -> dict[str, Any]:
        items = self._build_queue_items()
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        self.batch_path.write_text(self._build_batch_markdown(items), encoding="utf-8")
        progress = self._build_progress(items)
        self.progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"queue_items": items, "progress": progress}

    def run_progress(self) -> dict[str, Any]:
        items = self._build_queue_items()
        progress = self._build_progress(items)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        self.batch_path.write_text(self._build_batch_markdown(items), encoding="utf-8")
        self.progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        return progress

    def _build_queue_items(self) -> list[dict[str, Any]]:
        rows = self._read_plan_rows()
        deduped: OrderedDict[str, dict[str, str]] = OrderedDict()
        for row in rows:
            if str(row.get("status", "")).strip().upper() != "GENERATE":
                continue
            visual_need = str(row.get("visual_need") or "").strip()
            if visual_need and visual_need not in deduped:
                deduped[visual_need] = row

        queue_items: list[dict[str, Any]] = []
        for row in deduped.values():
            recommended_filename = str(row.get("recommended_filename") or "").strip()
            target_path = self.image_library_path / recommended_filename
            completed = (
                target_path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
                and target_path.exists()
                and target_path.is_file()
                and target_path.stat().st_size > 0
            )
            queue_items.append(
                {
                    "queue_id": f"{self.project_id}-P5-{len(queue_items) + 1:03d}",
                    "priority": int(row.get("priority") or 5),
                    "visual_need": str(row.get("visual_need") or "").strip(),
                    "recommended_filename": recommended_filename,
                    "prompt": str(row.get("prompt") or "").strip(),
                    "scenes_covered": str(row.get("scenes_covered") or "").strip(),
                    "shots_covered": str(row.get("shots_covered") or "").strip(),
                    "target_path": str(target_path),
                    "status": "COMPLETED" if completed else "PENDING",
                }
            )
        return queue_items

    def _build_batch_markdown(self, queue_items: list[dict[str, Any]]) -> str:
        lines = ["# Franklin Visual Generation Batch", ""]
        pending_items = [item for item in queue_items if item["status"] == "PENDING"]
        if not pending_items:
            lines.append("No pending visual items.")
            lines.append("")
            return "\n".join(lines)

        for order, item in enumerate(pending_items, start=1):
            lines.extend(
                [
                    f"## {order}. {item['visual_need']}",
                    f"- exact filename: {item['recommended_filename']}",
                    f"- exact destination folder: {self.image_library_path.as_posix()}",
                    f"- scenes and shots covered: {self._scenes_and_shots_line(item)}",
                    "- full prompt:",
                    f"  {item['prompt']}",
                    "",
                ]
            )
        return "\n".join(lines)

    def _build_progress(self, queue_items: list[dict[str, Any]]) -> dict[str, Any]:
        completed_items = sum(1 for item in queue_items if item["status"] == "COMPLETED")
        total_items = len(queue_items)
        pending_items = total_items - completed_items
        next_item = next((item for item in queue_items if item["status"] == "PENDING"), None)
        return {
            "project_id": self.project_id,
            "total_items": total_items,
            "completed_items": completed_items,
            "pending_items": pending_items,
            "completion_percent": round((completed_items / total_items * 100.0) if total_items else 100.0, 1),
            "next_item": next_item,
            "image_library_path": str(self.image_library_path),
        }

    def _read_plan_rows(self) -> list[dict[str, str]]:
        if not self.plan_path.exists():
            return []
        try:
            with self.plan_path.open("r", encoding="utf-8", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        except UnicodeDecodeError:
            with self.plan_path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]

    def _detect_image_library_path(self) -> Path:
        project_library = self.root_dir / "workspace" / "projects" / self.project_id / "02_Images"
        if project_library.exists():
            return project_library
        fallback = self.root_dir / "Franklin_Film" / "02_Images"
        if fallback.exists():
            return fallback
        return project_library

    @staticmethod
    def _scenes_and_shots_line(item: dict[str, Any]) -> str:
        scenes = str(item.get("scenes_covered") or "").strip()
        shots = str(item.get("shots_covered") or "").strip()
        if scenes and shots:
            return f"{scenes} / {shots}"
        return scenes or shots or ""