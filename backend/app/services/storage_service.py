"""Supabase Storage helpers.

Replaces the previous Cloudflare R2 (S3-compatible via boto3) backend. The
Supabase Python client is sync-only, so we hand off to a default thread
executor and keep the FastAPI request on the event loop.

Interface:
    await upload(bucket, key, data, content_type=...)
    await download(bucket, key)
    await presign_get(bucket, key, expires_in=3600)

Buckets are passed in by the caller — see ``SCANS_BUCKET`` and
``HEATMAPS_BUCKET`` below for the canonical names. Both buckets must
exist in Supabase Storage and should be configured as **private**; access
is brokered through short-lived signed URLs minted by ``presign_get``.
"""
from __future__ import annotations

import asyncio

from app.services.supabase_client import service_client

SCANS_BUCKET = "scans"
HEATMAPS_BUCKET = "heatmaps"


def _bucket(name: str):
    return service_client().storage.from_(name)


async def upload(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    def _put() -> str:
        _bucket(bucket).upload(
            path=key,
            file=data,
            file_options={"content-type": content_type, "upsert": "false"},
        )
        return key

    return await asyncio.to_thread(_put)


async def download(bucket: str, key: str) -> bytes:
    def _get() -> bytes:
        return _bucket(bucket).download(key)

    return await asyncio.to_thread(_get)


async def presign_get(bucket: str, key: str, expires_in: int = 3600) -> str | None:
    if not key:
        return None

    def _sign() -> str | None:
        result = _bucket(bucket).create_signed_url(key, expires_in)
        # storage3 has switched between camelCase and snake_case across
        # versions; accept either.
        if isinstance(result, dict):
            return result.get("signedURL") or result.get("signed_url")
        return getattr(result, "signedURL", None) or getattr(result, "signed_url", None)

    return await asyncio.to_thread(_sign)
