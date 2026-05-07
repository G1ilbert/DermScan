"""Cloudflare R2 storage helpers (S3-compatible via boto3).

Boto3 is sync-only, so we hand off to a default thread executor so the rest
of the FastAPI request can stay on the event loop.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Optional

import boto3
from botocore.client import Config

from app.config import get_settings


@lru_cache
def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url or None,
        aws_access_key_id=settings.r2_access_key_id or None,
        aws_secret_access_key=settings.r2_secret_access_key or None,
        region_name=settings.r2_region,
        config=Config(signature_version="s3v4"),
    )


async def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    settings = get_settings()
    loop = asyncio.get_running_loop()

    def _put():
        _client().put_object(Bucket=settings.r2_bucket, Key=key, Body=data, ContentType=content_type)
        return key

    return await loop.run_in_executor(None, _put)


async def download_bytes(key: str) -> bytes:
    settings = get_settings()
    loop = asyncio.get_running_loop()

    def _get():
        return _client().get_object(Bucket=settings.r2_bucket, Key=key)["Body"].read()

    return await loop.run_in_executor(None, _get)


async def presign_get(key: str, expires_in: int = 3600) -> Optional[str]:
    if not key:
        return None
    settings = get_settings()
    loop = asyncio.get_running_loop()

    def _sign():
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    return await loop.run_in_executor(None, _sign)
