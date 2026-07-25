from __future__ import annotations

import json
from pathlib import Path

from az_enterprise.core.production_director import ProductionDirector


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_base_reports(root: Path) -> Path:
    export_dir = root / "workspace" / "exports" / "franklin"
    export_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        export_dir / "production_state.json",
        {
            "project_id": "franklin",
            "shots": 10,
            "missing": 999,
        },
    )
    _write_json(
        export_dir / "missing_story_requirements.json",
        [
            {"scene_id": "S01", "visual_need": "ice"},
            {"scene_id": "S02", "visual_need": "ship"},
        ],
    )
    (export_dir / "director_tasks.csv").write_text(
        "task_uid,task_type,status\nDIR-1,generate_asset,waiting_api\n",
        encoding="utf-8",
    )
    _write_json(
        export_dir / "movie_runtime_rc1" / "asset_inventory.json",
        {
            "counts": {
                "audio": 1,
                "image": 4,
                "video": 2,
            }
        },
    )
    _write_json(
        export_dir / "render_rc1" / "render_manifest.json",
        {
            "clips": [
                {"duration_sec": 4.0},
                {"duration_sec": 6.5},
            ]
        },
    )
    _write_json(
        export_dir / "render_rc1" / "render_report.json",
        {
            "state": "RENDERED",
            "output_mp4_exists": True,
            "clips_total": 10,
            "clips_renderable": 7,
        },
    )
    return export_dir


def test_consumes_existing_reports_not_reimplementation(tmp_path: Path) -> None:
    _seed_base_reports(tmp_path)

    status = ProductionDirector("franklin", deadline_days_remaining=4, root_dir=tmp_path).run()

    assert status["images_missing"] == 2
    assert status["images_found"] == 4
    assert status["videos_found"] == 2


def test_missing_optional_files_do_not_crash(tmp_path: Path) -> None:
    export_dir = tmp_path / "workspace" / "exports" / "franklin"
    export_dir.mkdir(parents=True, exist_ok=True)

    status = ProductionDirector("franklin", deadline_days_remaining=4, root_dir=tmp_path).run()

    assert status["project_id"] == "franklin"
    assert isinstance(status["next_action"], str)
    assert (export_dir / "production_director_status.json").exists()
    assert (export_dir / "production_director_brief.md").exists()


def test_exactly_one_next_action_returned(tmp_path: Path) -> None:
    _seed_base_reports(tmp_path)

    status = ProductionDirector("franklin", deadline_days_remaining=4, root_dir=tmp_path).run()

    assert isinstance(status["next_action"], str)
    assert status["next_action"].strip()
    assert "\n" not in status["next_action"].strip()


def test_incomplete_visual_coverage_selects_visual_production(tmp_path: Path) -> None:
    export_dir = _seed_base_reports(tmp_path)

    _write_json(export_dir / "missing_story_requirements.json", [])

    status = ProductionDirector("franklin", deadline_days_remaining=4, root_dir=tmp_path).run()

    assert status["main_blocker"] == "incomplete visual coverage"
    assert status["next_module"] == "Visual Production"


def test_completed_project_selects_release_packaging(tmp_path: Path) -> None:
    export_dir = _seed_base_reports(tmp_path)

    _write_json(export_dir / "missing_story_requirements.json", [])
    _write_json(
        export_dir / "render_rc1" / "render_report.json",
        {
            "state": "RENDERED",
            "output_mp4_exists": True,
            "clips_total": 10,
            "clips_renderable": 10,
        },
    )

    status = ProductionDirector("franklin", deadline_days_remaining=4, root_dir=tmp_path).run()

    assert status["next_module"] == "Release Packaging"
    assert status["main_blocker"] == "none"


def test_status_json_and_brief_markdown_are_created(tmp_path: Path) -> None:
    export_dir = _seed_base_reports(tmp_path)

    ProductionDirector("franklin", deadline_days_remaining=4, root_dir=tmp_path).run()

    status_path = export_dir / "production_director_status.json"
    brief_path = export_dir / "production_director_brief.md"
    assert status_path.exists()
    assert brief_path.exists()

    saved_status = json.loads(status_path.read_text(encoding="utf-8"))
    brief_text = brief_path.read_text(encoding="utf-8")

    assert saved_status["project_id"] == "franklin"
    assert "module to run:" in brief_text