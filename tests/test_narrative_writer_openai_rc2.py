from az_enterprise.core.narrative_writer_rc2 import (
    NarrativeWriterRC2,
)
from az_enterprise.core.openai_adapter_rc2 import (
    OpenAITextResultRC2,
)


class FakeCompletedAdapter:
    def generate_text(self, **kwargs):
        return OpenAITextResultRC2(
            status="completed",
            model="fake-model",
            text=(
                "SC01. Отредактированный текст.\n\n"
                "SC02. Продолжение истории."
            ),
            response_id="fake-response",
            usage={},
        )


class FakeBlockedAdapter:
    def generate_text(self, **kwargs):
        return OpenAITextResultRC2(
            status="blocked_missing_credential",
            model="fake-model",
            text="",
            response_id=None,
            usage={},
            error="missing key",
        )


def payload():
    return {
        "strategy": {
            "language": "ru",
            "target_duration_sec": 120.0,
        },
        "scenes": [
            {
                "scene_id": "SC01",
                "title_ru": "Начало",
                "narrative_goal_ru": "Открыть фильм.",
                "emotional_goal_ru": "ожидание",
                "duration_sec": 60.0,
                "cluster_ids": ("cluster-1",),
                "asset_ids": ("asset-1",),
            },
            {
                "scene_id": "SC02",
                "title_ru": "Финал",
                "narrative_goal_ru": "Завершить фильм.",
                "emotional_goal_ru": "кульминация",
                "duration_sec": 60.0,
                "cluster_ids": ("cluster-2",),
                "asset_ids": ("asset-2",),
            },
        ],
        "transitions": [],
    }


def test_local_mode_does_not_require_openai():
    writer = NarrativeWriterRC2(
        project_id="hogueras",
        mode="local_fallback",
    )

    result = writer.run(payload())

    assert result.full_narration_ru
    assert (
        writer.last_editorial_status
        == "local_fallback"
    )


def test_blocked_openai_uses_local_fallback():
    writer = NarrativeWriterRC2(
        project_id="hogueras",
        mode="openai_editorial",
        openai_adapter=FakeBlockedAdapter(),
        allow_paid=True,
    )

    result = writer.run(payload())

    assert result.full_narration_ru
    assert (
        writer.last_editorial_status
        == "blocked_missing_credential"
    )


def test_completed_openai_replaces_full_text():
    writer = NarrativeWriterRC2(
        project_id="hogueras",
        mode="openai_editorial",
        openai_adapter=FakeCompletedAdapter(),
        allow_paid=True,
    )

    result = writer.run(payload())

    assert result.full_narration_ru.startswith(
        "SC01. Отредактированный текст."
    )
    assert (
        writer.last_editorial_status
        == "completed"
    )


def test_unknown_mode_is_rejected():
    try:
        NarrativeWriterRC2(
            project_id="hogueras",
            mode="unknown",
        )
    except ValueError as exc:
        assert "Unsupported narrative mode" in str(exc)
    else:
        raise AssertionError(
            "ValueError was not raised"
        )
