from __future__ import annotations

import csv
import json
from pathlib import Path

from az_enterprise.core.production_visual_manager import ProductionVisualManager


def _copy_priority5_plan(src_root: Path, dst_root: Path) -> Path:
    src = src_root / "workspace" / "exports" / "franklin" / "priority5_visual_plan.csv"
    dst = dst_root / "workspace" / "exports" / "franklin" / "priority5_visual_plan.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def _prepare_workspace(tmp_path: Path, duplicate_generate_row: bool = False) -> Path:
    source_root = Path(r"c:\Users\3dtool\OneDrive\Документы\GitHub\atlas_zero1")
    plan_path = _copy_priority5_plan(source_root, tmp_path)
    if duplicate_generate_row:
        rows = plan_path.read_text(encoding="utf-8").splitlines()
        body = rows[1:]
        duplicate_row = next(row for row in body if ",GENERATE," in row)
        rows.append(duplicate_row)
        plan_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    image_dir = tmp_path / "workspace" / "projects" / "franklin" / "02_Images"
    image_dir.mkdir(parents=True, exist_ok=True)
    return image_dir


def test_only_generate_rows_enter_queue_and_found_rows_are_ignored(tmp_path: Path) -> None:
    _prepare_workspace(tmp_path, duplicate_generate_row=True)

    manager = ProductionVisualManager("franklin", root_dir=tmp_path)
    result = manager.run_queue()

    queue_items = result["queue_items"]
    assert queue_items
    assert len(queue_items) == 12
    assert all(item["status"] in {"PENDING", "COMPLETED"} for item in queue_items)
    assert all(item["visual_need"] != "drone arctic" for item in queue_items)
    assert all(item["visual_need"] != "ship ice wide" for item in queue_items)


def test_duplicate_visual_needs_are_not_duplicated(tmp_path: Path) -> None:
    _prepare_workspace(tmp_path, duplicate_generate_row=True)

    manager = ProductionVisualManager("franklin", root_dir=tmp_path)
    queue_items = manager.run_queue()["queue_items"]

    needs = [item["visual_need"] for item in queue_items]
    assert len(needs) == len(set(needs))


def test_missing_files_remain_pending_and_existing_non_empty_files_become_completed(tmp_path: Path) -> None:
    image_dir = _prepare_workspace(tmp_path)
    (image_dir / "P5_hull_ice.jpg").write_text("binary placeholder", encoding="utf-8")

    manager = ProductionVisualManager("franklin", root_dir=tmp_path)
    queue_items = manager.run_queue()["queue_items"]

    hull = next(item for item in queue_items if item["visual_need"] == "hull ice")
    ship_ice_video = next(item for item in queue_items if item["visual_need"] == "ship ice video")

    assert hull["status"] == "COMPLETED"
    assert ship_ice_video["status"] == "PENDING"


def test_queue_and_operator_files_are_created(tmp_path: Path) -> None:
    _prepare_workspace(tmp_path)

    manager = ProductionVisualManager("franklin", root_dir=tmp_path)
    manager.run_queue()

    export_dir = tmp_path / "workspace" / "exports" / "franklin"
    assert (export_dir / "visual_generation_queue.json").exists()
    assert (export_dir / "visual_generation_batch.md").exists()
    assert (export_dir / "visual_generation_progress.json").exists()

    batch_text = (export_dir / "visual_generation_batch.md").read_text(encoding="utf-8")
    assert "full prompt:" in batch_text


def test_no_network_or_api_calls_occur(tmp_path: Path, monkeypatch) -> None:
    _prepare_workspace(tmp_path)

    def fail(*args, **kwargs):
        raise AssertionError("network or api call attempted")

    monkeypatch.setattr("urllib.request.urlopen", fail, raising=False)
    monkeypatch.setattr("socket.create_connection", fail, raising=False)

    manager = ProductionVisualManager("franklin", root_dir=tmp_path)
    manager.run_queue()


def test_progress_json_reports_next_item(tmp_path: Path) -> None:
    image_dir = _prepare_workspace(tmp_path)
    (image_dir / "P5_hull_ice.jpg").write_text("ready", encoding="utf-8")

    manager = ProductionVisualManager("franklin", root_dir=tmp_path)
    progress = manager.run_progress()

    assert progress["project_id"] == "franklin"
    assert progress["total_items"] >= 1
    assert progress["completed_items"] >= 1
    assert progress["pending_items"] >= 1
    assert progress["next_item"]["status"] == "PENDING"
    assert progress["image_library_path"].endswith(r"workspace\projects\franklin\02_Images") or progress["image_library_path"].endswith("workspace/projects/franklin/02_Images")