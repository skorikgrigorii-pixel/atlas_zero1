from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw

from az_enterprise.core.visual_asset_registrar import VisualAssetRegistrar


def _write_img(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (640, 420)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _write_pattern_img(path: Path, base: tuple[int, int, int], accent: tuple[int, int, int], size: tuple[int, int] = (1200, 800)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, base)
    draw = ImageDraw.Draw(img)
    for x in range(0, size[0], 40):
        draw.line([(x, 0), (x, size[1])], fill=accent, width=2)
    for y in range(0, size[1], 36):
        draw.line([(0, y), (size[0], y)], fill=accent, width=1)
    img.save(path)


def _queue_item(project: str, idx: int, visual_need: str, rec_name: str, image_dir: Path, status: str = "PENDING") -> dict[str, str | int]:
    return {
        "queue_id": f"{project}-P5-{idx:03d}",
        "priority": 5,
        "visual_need": visual_need,
        "recommended_filename": rec_name,
        "prompt": f"Required visual: {visual_need}",
        "scenes_covered": "S01",
        "shots_covered": "1",
        "target_path": str(image_dir / rec_name),
        "status": status,
    }


def _setup_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = "franklin"
    export_dir = tmp_path / "workspace" / "exports" / project
    export_dir.mkdir(parents=True, exist_ok=True)
    image_dir = tmp_path / "workspace" / "projects" / project / "02_Images"
    image_dir.mkdir(parents=True, exist_ok=True)
    queue_path = export_dir / "visual_generation_queue.json"
    return export_dir, image_dir, queue_path


def _write_plan_from_queue(export_dir: Path, queue_items: list[dict[str, object]]) -> None:
    plan_path = export_dir / "priority5_visual_plan.csv"
    with plan_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "priority",
                "visual_need",
                "recommended_filename",
                "prompt",
                "scenes_covered",
                "shots_covered",
                "status",
            ],
        )
        writer.writeheader()
        for item in queue_items:
            writer.writerow(
                {
                    "priority": item.get("priority", 5),
                    "visual_need": item.get("visual_need", ""),
                    "recommended_filename": item.get("recommended_filename", ""),
                    "prompt": item.get("prompt", ""),
                    "scenes_covered": item.get("scenes_covered", ""),
                    "shots_covered": item.get("shots_covered", ""),
                    "status": "GENERATE",
                }
            )


def _run_with_queue(tmp_path: Path, queue_items: list[dict[str, object]]) -> dict[str, object]:
    export_dir, _, queue_path = _setup_workspace(tmp_path)
    _write_plan_from_queue(export_dir, queue_items)
    queue_path.write_text(json.dumps(queue_items, ensure_ascii=False, indent=2), encoding="utf-8")
    result = VisualAssetRegistrar("franklin", root_dir=tmp_path).run()
    assert (export_dir / "visual_registration_report.json").exists()
    assert (export_dir / "visual_registration_report.html").exists()
    assert (export_dir / "visual_registration_review.csv").exists()
    return result


def test_existing_p5_file_is_not_overwritten_and_original_is_preserved(tmp_path: Path) -> None:
    _, image_dir, _ = _setup_workspace(tmp_path)
    existing_target = image_dir / "P5_document_text.jpg"
    existing_target.write_bytes(b"do-not-overwrite")

    chatgpt_source = image_dir / "ChatGPT Image 11 Jul 2026 20_40_00.png"
    _write_img(chatgpt_source, (220, 215, 205), size=(1200, 800))

    queue = [
        _queue_item("franklin", 1, "document text", "P5_document_text.jpg", image_dir, status="PENDING"),
    ]
    before = existing_target.read_bytes()
    result = _run_with_queue(tmp_path, queue)

    assert existing_target.read_bytes() == before
    assert chatgpt_source.exists()
    assert result["auto_accepted"] == 0


def test_unsupported_file_is_ignored(tmp_path: Path) -> None:
    _, image_dir, _ = _setup_workspace(tmp_path)
    (image_dir / "notes.txt").write_text("ignore", encoding="utf-8")
    _write_img(image_dir / "candidate_document.png", (230, 225, 215), size=(1200, 800))

    queue = [_queue_item("franklin", 1, "archive document", "P5_archive_document.jpg", image_dir)]
    _run_with_queue(tmp_path, queue)

    report_path = tmp_path / "workspace" / "exports" / "franklin" / "visual_registration_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ignored_unsupported"] >= 1


def test_duplicate_is_detected(tmp_path: Path) -> None:
    _, image_dir, _ = _setup_workspace(tmp_path)
    src_a = image_dir / "ChatGPT Image A.png"
    src_b = image_dir / "ChatGPT Image B.png"
    _write_img(src_a, (20, 80, 180), size=(1200, 800))
    src_b.write_bytes(src_a.read_bytes())

    queue = [_queue_item("franklin", 1, "underwater ship", "P5_underwater_ship.jpg", image_dir)]
    _run_with_queue(tmp_path, queue)

    report_path = tmp_path / "workspace" / "exports" / "franklin" / "visual_registration_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rejected = [row for row in report["matches"] if row["decision"] == "REJECT"]
    assert rejected
    assert any("duplicate" in " ".join(row["reasons"]).lower() for row in rejected)


def test_low_confidence_goes_to_review(tmp_path: Path) -> None:
    _, image_dir, _ = _setup_workspace(tmp_path)
    # Ambiguous visual profile + weak hint: should map, but below auto-accept threshold.
    _write_img(image_dir / "candidate_misc.png", (128, 126, 122), size=(1200, 800))
    queue = [_queue_item("franklin", 1, "medical notes", "P5_medical_notes.jpg", image_dir)]

    result = _run_with_queue(tmp_path, queue)
    assert result["review"] >= 1
    assert result["auto_accepted"] == 0


def test_auto_accept_creates_exact_recommended_filename(tmp_path: Path) -> None:
    _, image_dir, _ = _setup_workspace(tmp_path)
    source = image_dir / "candidate_underwater_ship_hint.png"
    _write_pattern_img(source, (10, 55, 150), (5, 25, 95), size=(1200, 800))

    queue = [_queue_item("franklin", 1, "underwater ship", "P5_underwater_ship.jpg", image_dir)]
    result = _run_with_queue(tmp_path, queue)

    target = image_dir / "P5_underwater_ship.jpg"
    assert result["auto_accepted"] == 1
    assert target.exists()
    assert source.exists()


def test_repeated_run_is_idempotent(tmp_path: Path) -> None:
    _, image_dir, queue_path = _setup_workspace(tmp_path)
    source = image_dir / "candidate_archive_document_hint.png"
    _write_img(source, (222, 218, 198), size=(1200, 800))
    queue = [_queue_item("franklin", 1, "archive document", "P5_archive_document.jpg", image_dir)]
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    registrar = VisualAssetRegistrar("franklin", root_dir=tmp_path)
    first = registrar.run()
    second = registrar.run()

    assert first["auto_accepted"] == 1
    assert second["auto_accepted"] == 0
    assert second["completed"] == first["completed"]


def test_progress_is_updated_after_registration(tmp_path: Path) -> None:
    export_dir, image_dir, queue_path = _setup_workspace(tmp_path)
    _write_pattern_img(image_dir / "candidate_sonar_screen_hint.png", (20, 20, 20), (245, 245, 245), size=(1200, 800))
    queue = [_queue_item("franklin", 1, "sonar screen", "P5_sonar_screen.jpg", image_dir)]
    _write_plan_from_queue(export_dir, queue)
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    result = VisualAssetRegistrar("franklin", root_dir=tmp_path).run()
    progress_path = export_dir / "visual_generation_progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))

    assert progress_path.exists()
    assert result["completed"] == 1
    assert progress["completed_items"] == 1
    assert progress["pending_items"] == 0