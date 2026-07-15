from az_enterprise.core.openai_adapter_rc2 import (
    OpenAIAdapterRC2,
)


def test_missing_key_blocks_request(
    monkeypatch,
):
    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )

    adapter = OpenAIAdapterRC2(
        api_key=None,
    )

    result = adapter.generate_text(
        instructions="Write text.",
        input_text="Test.",
        allow_paid=True,
    )

    assert (
        result.status
        == "blocked_missing_credential"
    )


def test_live_disabled_blocks_request(
    monkeypatch,
):
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )
    monkeypatch.delenv(
        "AZ_ENABLE_LIVE_CALLS",
        raising=False,
    )

    adapter = OpenAIAdapterRC2()

    result = adapter.generate_text(
        instructions="Write text.",
        input_text="Test.",
        allow_paid=True,
    )

    assert (
        result.status
        == "blocked_live_disabled"
    )


def test_paid_confirmation_is_required(
    monkeypatch,
):
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )
    monkeypatch.setenv(
        "AZ_ENABLE_LIVE_CALLS",
        "1",
    )

    adapter = OpenAIAdapterRC2()

    result = adapter.generate_text(
        instructions="Write text.",
        input_text="Test.",
        allow_paid=False,
    )

    assert (
        result.status
        == "blocked_paid_confirmation_required"
    )


def test_extracts_direct_output_text():
    text = OpenAIAdapterRC2._extract_output_text({
        "output_text": "Готовый текст",
    })

    assert text == "Готовый текст"


def test_extracts_nested_output_text():
    text = OpenAIAdapterRC2._extract_output_text({
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Первая часть",
                    },
                    {
                        "type": "output_text",
                        "text": "Вторая часть",
                    },
                ],
            },
        ],
    })

    assert text == (
        "Первая часть\nВторая часть"
    )
