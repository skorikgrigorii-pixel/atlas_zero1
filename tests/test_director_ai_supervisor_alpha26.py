from az_enterprise.core.director_core_rc2 import DirectorCoreRC2


def test_director_ai_targets_are_mapped_to_existing_rc2_stages():
    report = {
        "issues": [
            {"rule_code": "FILM_TOO_LONG"},
            {"rule_code": "ASSET_REUSED_TOO_SOON"},
            {"rule_code": "STATIC_IMAGE_TOO_LONG"},
        ]
    }

    assert DirectorCoreRC2._recommended_targets_from_director_ai(report) == (
        "story",
        "assignment",
        "timeline",
    )


def test_api_not_ready_does_not_trigger_media_rework():
    report = {
        "issues": [{"rule_code": "API_NOT_READY"}],
        "tasks": [{"task_type": "connect_api"}],
    }

    assert DirectorCoreRC2._recommended_targets_from_director_ai(report) == ()


def test_task_types_can_route_rework_without_rule_codes():
    report = {
        "tasks": [
            {"task_type": "strengthen_opening"},
            {"task_type": "replace_repeated_asset"},
            {"task_type": "add_visual_variety"},
        ]
    }

    assert DirectorCoreRC2._recommended_targets_from_director_ai(report) == (
        "story",
        "assignment",
        "timeline",
    )
