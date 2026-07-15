from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class OpenAITextResultRC2:
    status: str
    model: str
    text: str
    response_id: str | None
    usage: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpenAIAdapterRC2:
    """Guarded OpenAI Responses API adapter.

    The adapter performs a live paid request only when:
    - OPENAI_API_KEY is present;
    - AZ_ENABLE_LIVE_CALLS=1;
    - allow_paid=True is supplied explicitly.

    Otherwise it returns a deterministic blocked status.
    """

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_sec: int = 180,
    ) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else os.getenv("OPENAI_API_KEY")
        )

        self.model = (
            model
            or os.getenv("OPENAI_MODEL")
            or "gpt-5.6"
        )

        self.timeout_sec = max(
            5,
            int(timeout_sec),
        )

    @property
    def live_enabled(self) -> bool:
        return (
            os.getenv("AZ_ENABLE_LIVE_CALLS")
            == "1"
        )

    def generate_text(
        self,
        *,
        instructions: str,
        input_text: str,
        allow_paid: bool = False,
        reasoning_effort: str = "low",
    ) -> OpenAITextResultRC2:
        if not self.api_key:
            return OpenAITextResultRC2(
                status="blocked_missing_credential",
                model=self.model,
                text="",
                response_id=None,
                usage={},
                error="OPENAI_API_KEY is missing",
            )

        if not self.live_enabled:
            return OpenAITextResultRC2(
                status="blocked_live_disabled",
                model=self.model,
                text="",
                response_id=None,
                usage={},
                error=(
                    "Set AZ_ENABLE_LIVE_CALLS=1 "
                    "to enable external requests"
                ),
            )

        if not allow_paid:
            return OpenAITextResultRC2(
                status=(
                    "blocked_paid_confirmation_required"
                ),
                model=self.model,
                text="",
                response_id=None,
                usage={},
                error=(
                    "allow_paid=True is required "
                    "for an OpenAI request"
                ),
            )

        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": input_text,
            "reasoning": {
                "effort": reasoning_effort,
            },
        }

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Authorization": (
                    f"Bearer {self.api_key}"
                ),
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_sec,
            ) as response:
                body = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            try:
                details = (
                    exc.read()
                    .decode("utf-8", errors="replace")
                )
            except Exception:
                details = str(exc)

            return OpenAITextResultRC2(
                status="live_failed",
                model=self.model,
                text="",
                response_id=None,
                usage={},
                error=(
                    f"HTTP {exc.code}: {details}"
                ),
            )

        except Exception as exc:
            return OpenAITextResultRC2(
                status="live_failed",
                model=self.model,
                text="",
                response_id=None,
                usage={},
                error=str(exc),
            )

        text = self._extract_output_text(body)

        if not text.strip():
            return OpenAITextResultRC2(
                status="live_failed_empty_output",
                model=self.model,
                text="",
                response_id=body.get("id"),
                usage=body.get("usage") or {},
                error="Response contained no output text",
            )

        return OpenAITextResultRC2(
            status="completed",
            model=str(
                body.get("model")
                or self.model
            ),
            text=text.strip(),
            response_id=body.get("id"),
            usage=body.get("usage") or {},
            error=None,
        )

    @staticmethod
    def _extract_output_text(
        response: dict[str, Any],
    ) -> str:
        direct = response.get("output_text")

        if isinstance(direct, str):
            return direct

        parts: list[str] = []

        for item in response.get(
            "output",
            [],
        ):
            if not isinstance(item, dict):
                continue

            if item.get("type") != "message":
                continue

            for content in item.get(
                "content",
                [],
            ):
                if not isinstance(content, dict):
                    continue

                if content.get("type") in {
                    "output_text",
                    "text",
                }:
                    value = content.get("text")

                    if isinstance(value, str):
                        parts.append(value)

        return "\n".join(parts).strip()
