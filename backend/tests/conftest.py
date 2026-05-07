"""Pytest fixtures.

We swap the production async engine for an in-memory SQLite DB and stub the
storage + queue calls so unit tests never need a real Postgres / Redis / R2.

The Postgres-specific column types (UUID, JSONB, ENUM) are remapped to
SQLite-friendly equivalents inside the fixture so the same SQLAlchemy models
work in both environments.
"""
from __future__ import annotations

import asyncio
import base64
import os
from typing import AsyncIterator

import pytest

# Required env BEFORE importing the app.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault(
    "ENCRYPTION_KEY",
    base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
)
os.environ.setdefault("R2_BUCKET", "dermscan-test")
os.environ.setdefault("MODEL_PATH", "/tmp/no-such-model.onnx")

import pytest_asyncio  # noqa: E402

from sqlalchemy import JSON  # noqa: E402
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID  # noqa: E402

# Tell SQLAlchemy how to render PG-only types on SQLite.
UUID.impl = lambda self, dialect=None: None  # type: ignore[assignment]


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator:
    # Late imports so the env vars above are picked up.
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app import database
    from app.database import Base
    from app.main import app

    # Patch JSONB / ENUM compilation for SQLite. Both decay gracefully for tests.
    JSONB.__visit_name__ = "JSON"  # type: ignore[attr-defined]

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    database.engine = engine
    database.SessionLocal = SessionLocal

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _stub_external_services(monkeypatch):
    from app.services import scan_service, storage_service

    async def _upload(key, data, content_type="application/octet-stream"):
        return key

    async def _download(key):
        return b""

    async def _presign(key, expires_in=3600):
        return f"https://signed.example/{key}" if key else None

    monkeypatch.setattr(storage_service, "upload_bytes", _upload)
    monkeypatch.setattr(storage_service, "download_bytes", _download)
    monkeypatch.setattr(storage_service, "presign_get", _presign)

    # Avoid hitting Redis when scan is created.
    class _FakePool:
        async def enqueue_job(self, *args, **kwargs):
            return None

        async def close(self):
            return None

    async def _create_pool(_settings):
        return _FakePool()

    monkeypatch.setattr(scan_service, "create_pool", _create_pool)
