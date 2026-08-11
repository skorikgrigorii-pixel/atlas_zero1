from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StagedMediaRC1:
    local_path: Path
    public_url: str
    provider: str
    cleanup_token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_path":
                str(self.local_path),
            "public_url":
                self.public_url,
            "provider":
                self.provider,
            "cleanup_token":
                self.cleanup_token,
        }


class PromotionMediaStagingRC1(
    ABC,
):
    """
    ATLAS ZERO ? public media staging contract.

    Responsibility:
        local media file
            ->
        temporary public HTTPS URL

    This class intentionally knows nothing about
    Instagram, TikTok, Cloudflare, S3 or any other
    publication target/provider.
    """

    def validate_local_media(
        self,
        local_path: Path | str,
    ) -> Path:

        path = Path(
            local_path
        )

        if not path.is_file():
            raise FileNotFoundError(
                f"Media file not found: {path}"
            )

        if path.stat().st_size <= 0:
            raise RuntimeError(
                f"Media file is empty: {path}"
            )

        return path

    @abstractmethod
    def stage(
        self,
        local_path: Path | str,
    ) -> StagedMediaRC1:
        raise NotImplementedError

    @abstractmethod
    def cleanup(
        self,
        staged: StagedMediaRC1,
    ) -> None:
        raise NotImplementedError
