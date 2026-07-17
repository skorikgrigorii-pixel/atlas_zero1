import json

from az_enterprise.core.project_config_rc2 import (
    ProjectConfigRC2,
)
from az_enterprise.core.production_script_regenerator_rc2 import (
    ProductionScriptRegeneratorRC2,
)


def test_regenerator_rebuilds_canonical_script(
    tmp_path,
):
    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    editorial_dir = (
        config.export_dir
        / "rc2"
        / "editorial_package"
    )

    narrative_dir = (
        config.export_dir
        / "rc2"
        / "narrative"
    )

    editorial_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    narrative_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    editorial = {
        "project": {
            "title": "Sample Film",
            "language": "ru",
        },
        "production_constraints": {
            "use_existing_assets_only": True,
        },
        "scenes": [
            {
                "scene_id": "SC01",
                "act_id": "ACT01",
                "order": 1,
                "title_ru": "Начало",
                "duration_sec": 10.0,
                "asset_ids": [
                    "asset_1",
                ],
                "cluster_ids": [
                    "cluster_1",
                ],
                "visual_strategy_ru":
                    "Общий план.",
                "available_assets": 1,
                "narrative_goal_ru":
                    "Открыть фильм.",
                "emotional_goal_ru":
                    "ожидание",
            },
        ],
        "transitions": [],
    }

    narrative = {
        "language": "ru",
        "full_narration_ru":
            "Текст первой сцены.",
        "scenes": [
            {
                "scene_id": "SC01",
                "narration_ru":
                    "Текст первой сцены.",
                "target_words": 3,
            },
        ],
    }

    (
        editorial_dir
        / "editorial_package_sample.json"
    ).write_text(
        json.dumps(
            editorial,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    (
        narrative_dir
        / "narrative_result.json"
    ).write_text(
        json.dumps(
            narrative,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = (
        ProductionScriptRegeneratorRC2(
            config
        ).run()
    )

    assert result["state"] == (
        "PRODUCTION_SCRIPT_REGENERATED"
    )

    assert result["scenes"] == 1

    assert (
        config.project_dir
        / "script"
        / "production_script.json"
    ).exists()

    assert (
        config.project_dir
        / "script"
        / "production_script.txt"
    ).exists()

    assert (
        config.project_dir
        / "script"
        / "production_script.md"
    ).exists()


def test_missing_narrative_is_rejected(
    tmp_path,
):
    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    editorial_dir = (
        config.export_dir
        / "rc2"
        / "editorial_package"
    )

    editorial_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        editorial_dir
        / "editorial_package_sample.json"
    ).write_text(
        json.dumps({
            "project": {
                "title": "Sample",
            },
        }),
        encoding="utf-8",
    )

    try:
        ProductionScriptRegeneratorRC2(
            config
        ).run()

    except FileNotFoundError as exc:
        assert "Narrative Result" in str(
            exc
        )

    else:
        raise AssertionError(
            "FileNotFoundError was not raised"
        )
