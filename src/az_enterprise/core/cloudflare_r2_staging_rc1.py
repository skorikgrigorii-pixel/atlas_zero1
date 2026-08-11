from __future__ import annotations

import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any

import boto3

from .promotion_media_staging_rc1 import (
    PromotionMediaStagingRC1,
    StagedMediaRC1,
)


class CloudflareR2StagingRC1(
    PromotionMediaStagingRC1,
):
    """
    ATLAS ZERO ? Cloudflare R2 staging adapter.

    local media
        ->
    Cloudflare R2
        ->
    temporary public HTTPS URL
        ->
    cleanup after publication
    """

    def __init__(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        endpoint: str,
        bucket: str,
        public_base_url: str,
        prefix: str = "instagram_staging",
        s3_client: Any | None = None,
    ) -> None:

        self.access_key_id = access_key_id.strip()
        self.secret_access_key = secret_access_key.strip()
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket.strip()
        self.public_base_url = public_base_url.rstrip("/")
        self.prefix = prefix.strip("/")

        if not self.access_key_id:
            raise ValueError("R2 access key is required")

        if not self.secret_access_key:
            raise ValueError("R2 secret key is required")

        if not self.endpoint.startswith("https://"):
            raise ValueError("R2 endpoint must use HTTPS")

        if not self.public_base_url.startswith("https://"):
            raise ValueError(
                "R2 public base URL must use HTTPS"
            )

        if not self.bucket:
            raise ValueError("R2 bucket is required")

        self.s3 = (
            s3_client
            if s3_client is not None
            else boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name="auto",
            )
        )

    @classmethod
    def from_env_file(
        cls,
        env_path: Path | str = ".env",
    ) -> "CloudflareR2StagingRC1":

        values: dict[str, str] = {}

        for raw in Path(env_path).read_text(
            encoding="utf-8-sig",
            errors="replace",
        ).splitlines():

            line = raw.strip()

            if (
                not line
                or line.startswith("#")
                or "=" not in line
            ):
                continue

            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        return cls(
            access_key_id=values[
                "CLOUDFLARE_R2_ACCESS_KEY_ID"
            ],
            secret_access_key=values[
                "CLOUDFLARE_R2_SECRET_ACCESS_KEY"
            ],
            endpoint=values[
                "CLOUDFLARE_R2_ENDPOINT"
            ],
            bucket=values[
                "CLOUDFLARE_R2_BUCKET"
            ],
            public_base_url=values[
                "CLOUDFLARE_R2_PUBLIC_BASE_URL"
            ],
        )

    def stage(
        self,
        local_path: Path | str,
    ) -> StagedMediaRC1:

        path = self.validate_local_media(
            local_path
        )

        suffix = path.suffix.lower()

        object_name = (
            f"{uuid.uuid4().hex}"
            f"{suffix}"
        )

        key = (
            f"{self.prefix}/"
            f"{object_name}"
        )

        content_type = (
            mimetypes.guess_type(
                path.name
            )[0]
            or "application/octet-stream"
        )

        with path.open("rb") as handle:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=handle,
                ContentType=content_type,
            )

        head = self.s3.head_object(
            Bucket=self.bucket,
            Key=key,
        )

        remote_size = int(
            head["ContentLength"]
        )

        local_size = int(
            path.stat().st_size
        )

        if remote_size != local_size:
            self.s3.delete_object(
                Bucket=self.bucket,
                Key=key,
            )

            raise RuntimeError(
                "R2 upload size mismatch: "
                f"local={local_size}, "
                f"remote={remote_size}"
            )

        public_url = (
            f"{self.public_base_url}/"
            f"{key}"
        )

        return StagedMediaRC1(
            local_path=path,
            public_url=public_url,
            provider="cloudflare_r2",
            cleanup_token=key,
        )

    def cleanup(
        self,
        staged: StagedMediaRC1,
    ) -> None:

        key = str(
            staged.cleanup_token
            or ""
        ).strip()

        if not key:
            return

        self.s3.delete_object(
            Bucket=self.bucket,
            Key=key,
        )
