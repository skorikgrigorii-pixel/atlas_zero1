from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class LeonardoHTTPErrorRC2(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        reason: str,
        response_body: str,
    ) -> None:
        self.status_code = int(status_code)
        self.reason = str(reason)
        self.response_body = str(response_body)

        super().__init__(
            f"Leonardo HTTP {self.status_code}: "
            f"{self.reason}: {self.response_body[:1000]}"
        )


class LeonardoProviderRC2:
    BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"

    DEFAULT_MODEL_ID = (
        "05ce0082-2d80-4a2d-8653-4d1c85e2418e"
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        width: int = 1344,
        height: int = 768,
        number_of_images: int = 1,
        polling_interval_sec: float = 4.0,
        maximum_wait_sec: float = 300.0,
    ) -> None:
        self.api_key = (
            api_key
            or os.getenv("LEONARDO_API_KEY")
            or ""
        ).strip()

        self.model_id = (
            model_id
            or os.getenv("LEONARDO_MODEL_ID")
            or self.DEFAULT_MODEL_ID
        ).strip()

        self.width = int(width)
        self.height = int(height)
        self.number_of_images = int(number_of_images)
        self.polling_interval_sec = float(
            polling_interval_sec
        )
        self.maximum_wait_sec = float(maximum_wait_sec)

    def validate_configuration(self) -> dict[str, Any]:
        issues: list[str] = []

        if not self.api_key:
            issues.append("LEONARDO_API_KEY is missing")

        if not self.model_id:
            issues.append("LEONARDO_MODEL_ID is missing")

        if self.width % 8 != 0:
            issues.append("width must be divisible by 8")

        if self.height % 8 != 0:
            issues.append("height must be divisible by 8")

        return {
            "provider": "leonardo",
            "configured": not issues,
            "model_id": self.model_id,
            "width": self.width,
            "height": self.height,
            "number_of_images": self.number_of_images,
            "issues": issues,
        }

    def create_generation(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
    ) -> dict[str, Any]:
        self._require_key()

        payload: dict[str, Any] = {
            "prompt": str(prompt).strip(),
            "negative_prompt": (
                str(negative_prompt).strip()
                if negative_prompt
                else ""
            ),
            "modelId": self.model_id,
            "width": self.width,
            "height": self.height,
            "num_images": self.number_of_images,
            "contrast": 3.5,
            "alchemy": False,
            "ultra": False,
            "public": False,
        }

        response = self._request_json(
            method="POST",
            path="/generations",
            payload=payload,
        )

        generation_id = (
            response
            .get("sdGenerationJob", {})
            .get("generationId")
            or response.get("generationId")
        )

        if not generation_id:
            raise RuntimeError(
                "Leonardo response has no generationId: "
                + json.dumps(
                    response,
                    ensure_ascii=False,
                )[:2000]
            )

        return {
            "generation_id": str(generation_id),
            "request": payload,
            "response": response,
        }

    def wait_for_generation(
        self,
        generation_id: str,
    ) -> dict[str, Any]:
        started = time.monotonic()

        while True:
            response = self._request_json(
                method="GET",
                path=(
                    "/generations/"
                    + urllib.parse.quote(
                        str(generation_id),
                        safe="",
                    )
                ),
            )

            generation = (
                response.get("generations_by_pk")
                or response.get("generation")
                or response
            )

            images = (
                generation.get("generated_images")
                or generation.get("generatedImages")
                or []
            )

            status = str(
                generation.get("status")
                or response.get("status")
                or ""
            ).upper()

            if images:
                return {
                    "generation_id": generation_id,
                    "status": status or "COMPLETE",
                    "images": images,
                    "response": response,
                }

            if status in {
                "FAILED",
                "ERROR",
                "CANCELLED",
            }:
                raise RuntimeError(
                    f"Leonardo generation {generation_id} "
                    f"finished with status {status}"
                )

            elapsed = time.monotonic() - started

            if elapsed >= self.maximum_wait_sec:
                raise TimeoutError(
                    f"Leonardo generation {generation_id} "
                    f"did not finish in "
                    f"{self.maximum_wait_sec:.1f} sec"
                )

            time.sleep(self.polling_interval_sec)

    def download_images(
        self,
        *,
        result: dict[str, Any],
        destination_dir: Path,
        basename: str,
    ) -> list[dict[str, Any]]:
        destination_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        downloaded: list[dict[str, Any]] = []

        for index, image in enumerate(
            result.get("images", []),
            start=1,
        ):
            url = str(image.get("url") or "").strip()

            if not url:
                continue

            suffix = Path(
                urllib.parse.urlparse(url).path
            ).suffix.lower()

            if suffix not in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            }:
                suffix = ".png"

            destination = (
                destination_dir
                / f"{basename}_{index:02d}{suffix}"
            )
            temporary = destination.with_suffix(
                destination.suffix + ".partial"
            )

            request = urllib.request.Request(
                url=url,
                method="GET",
                headers={
                    "User-Agent":
                        "ATLAS-ZERO-RC2/LeonardoRuntime",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=120,
            ) as response:
                body = response.read()

            if not body:
                raise RuntimeError(
                    f"Empty image returned for {url}"
                )

            temporary.write_bytes(body)
            temporary.replace(destination)

            downloaded.append({
                "image_id": image.get("id"),
                "source_url": url,
                "path": str(destination.resolve()),
                "bytes": len(body),
            })

        if not downloaded:
            raise RuntimeError(
                "Leonardo generation returned no downloadable images"
            )

        return downloaded

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_key()

        body = (
            json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8")
            if payload is not None
            else None
        )

        request = urllib.request.Request(
            url=self.BASE_URL + path,
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization":
                    f"Bearer {self.api_key}",
                "User-Agent":
                    "ATLAS-ZERO-RC2/LeonardoRuntime",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=120,
            ) as response:
                raw = response.read()

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise LeonardoHTTPErrorRC2(
                status_code=int(exc.code),
                reason=str(exc.reason),
                response_body=detail,
            ) from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Leonardo network error: {exc}"
            ) from exc

        if not raw:
            return {}

        try:
            value = json.loads(
                raw.decode("utf-8")
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Leonardo returned invalid JSON: "
                + raw.decode(
                    "utf-8",
                    errors="replace",
                )[:1000]
            ) from exc

        if not isinstance(value, dict):
            raise RuntimeError(
                "Leonardo returned non-object JSON"
            )

        return value

    def _require_key(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "LEONARDO_API_KEY is not configured"
            )
