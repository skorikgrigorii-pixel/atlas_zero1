import json

from az_enterprise.core.production_script_assembler_rc2 import (
    ProductionScriptAssemblerRC2,
)


def editorial_package():
    return {
        "project": {
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
                "duration_sec": 60.0,
                "asset_ids": [
                    "asset-1",
                ],
                "cluster_ids": [
                    "cluster-1",
                ],
                "visual_strategy_ru":
                    "Общие планы.",
                "available_assets": 1,
                "narrative_goal_ru":
                    "Открыть фильм.",
                "emotional_goal_ru":
                    "ожидание",
            },
            {
                "scene_id": "SC02",
                "act_id": "ACT02",
                "order": 2,
                "title_ru": "Финал",
                "duration_sec": 60.0,
                "asset_ids": [
                    "asset-2",
                ],
                "cluster_ids": [
                    "cluster-2",
                ],
                "visual_strategy_ru":
                    "Кульминационные планы.",
                "available_assets": 1,
                "narrative_goal_ru":
                    "Завершить фильм.",
                "emotional_goal_ru":
                    "кульминация",
            },
        ],
        "transitions": [
            {
                "from_scene_id": "SC01",
                "to_scene_id": "SC02",
                "transition_type":
                    "visual_dissolve",
                "rationale_ru":
                    "Перейти к финалу.",
                "narrator_bridge_required":
                    False,
            },
        ],
    }


def narrative_result():
    return {
        "language": "ru",
        "full_narration_ru":
            "Полный текст фильма.",
        "scenes": [
            {
                "scene_id": "SC01",
                "narration_ru":
                    "Текст первой сцены.",
                "target_words": 120,
            },
            {
                "scene_id": "SC02",
                "narration_ru":
                    "Текст второй сцены.",
                "target_words": 120,
            },
        ],
    }


def test_assembler_builds_script():
    assembler = (
        ProductionScriptAssemblerRC2(
            project_id="sample",
            title="Sample Film",
        )
    )

    result = assembler.build(
        editorial_package=
            editorial_package(),
        narrative_result=
            narrative_result(),
    )

    assert result[
        "project_id"
    ] == "sample"

    assert result[
        "scene_count"
    ] == 2

    assert result[
        "duration_sec"
    ] == 120.0

    assert result[
        "scenes"
    ][0]["start_sec"] == 0.0

    assert result[
        "scenes"
    ][1]["start_sec"] == 60.0


def test_assembler_exports_files(
    tmp_path,
):
    assembler = (
        ProductionScriptAssemblerRC2(
            project_id="sample",
            title="Sample Film",
        )
    )

    result = assembler.build(
        editorial_package=
            editorial_package(),
        narrative_result=
            narrative_result(),
    )

    paths = assembler.export(
        result,
        tmp_path,
    )

    assert (
        tmp_path
        / "production_script.json"
    ).exists()

    assert (
        tmp_path
        / "production_script.txt"
    ).exists()

    assert (
        tmp_path
        / "production_script.md"
    ).exists()

    payload = json.loads(
        (
            tmp_path
            / "production_script.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert payload[
        "scene_count"
    ] == 2


def test_missing_narration_is_rejected():
    assembler = (
        ProductionScriptAssemblerRC2(
            project_id="sample",
            title="Sample Film",
        )
    )

    broken = narrative_result()
    broken["scenes"] = []

    try:
        assembler.build(
            editorial_package=
                editorial_package(),
            narrative_result=broken,
        )
    except ValueError as exc:
        assert (
            "no scenes"
            in str(exc)
        )
    else:
        raise AssertionError(
            "ValueError was not raised"
        )
