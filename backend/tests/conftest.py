"""Pytest fixtures.

We swap the production async engine for an in-memory SQLite DB and stub the
storage, queue, and Supabase clients so unit tests never need real
Postgres / Redis / Supabase Storage / Supabase Auth.

The Postgres-specific column types (UUID, JSONB, ENUM) are remapped to
SQLite-friendly equivalents inside the fixture so the same SQLAlchemy models
work in both environments.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest

# Required env BEFORE importing the app.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("MODEL_PATH", "/tmp/no-such-model.onnx")
# Pin confidence thresholds so tests don't depend on a local .env file.
os.environ.setdefault("CONFIDENCE_THRESHOLD_HIGH", "0.60")
os.environ.setdefault("CONFIDENCE_THRESHOLD_LOW", "0.45")

import pytest_asyncio  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


# Tell SQLAlchemy how to render PG-only types on SQLite. Setting
# ``__visit_name__`` on the class doesn't propagate in SQLAlchemy 2.x because
# the per-class compiler dispatch is baked in at class creation time — so we
# register dialect-specific compilers instead.
@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@compiles(UUID, "sqlite")
def _uuid_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "CHAR(36)"


# --------------------------------------------------------------------------
# In-memory Supabase auth fake
# --------------------------------------------------------------------------


class _SimpleNS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeAdminAPI:
    def __init__(self, store: dict):
        self._store = store

    def sign_out(self, user_id: str):
        return None

    def get_user_by_id(self, user_id: str):
        for email, record in self._store.items():
            if record["id"] == user_id:
                return _SimpleNS(user=_SimpleNS(id=user_id, email=email))
        return _SimpleNS(user=None)


class _FakeAuthAPI:
    def __init__(self):
        # email -> {id, password}
        self._users: dict[str, dict] = {}
        self.admin = _FakeAdminAPI(self._users)

    def _token(self, user_id: str) -> str:
        return f"fake-access::{user_id}"

    def sign_up(self, payload: dict):
        email = payload["email"]
        if email in self._users:
            raise RuntimeError("User already registered")
        user_id = str(uuid.uuid4())
        self._users[email] = {"id": user_id, "password": payload["password"]}
        user = _SimpleNS(id=user_id, email=email)
        session = _SimpleNS(
            access_token=self._token(user_id),
            refresh_token=f"fake-refresh::{user_id}",
            expires_in=3600,
            user=user,
        )
        return _SimpleNS(user=user, session=session)

    def sign_in_with_password(self, payload: dict):
        email = payload["email"]
        record = self._users.get(email)
        if record is None or record["password"] != payload["password"]:
            raise RuntimeError("Invalid login credentials")
        user = _SimpleNS(id=record["id"], email=email)
        session = _SimpleNS(
            access_token=self._token(record["id"]),
            refresh_token=f"fake-refresh::{record['id']}",
            expires_in=3600,
            user=user,
        )
        return _SimpleNS(user=user, session=session)

    def get_user(self, token: str):
        if not token.startswith("fake-access::"):
            raise RuntimeError("Invalid token")
        user_id = token.removeprefix("fake-access::")
        for email, record in self._users.items():
            if record["id"] == user_id:
                return _SimpleNS(user=_SimpleNS(id=user_id, email=email))
        raise RuntimeError("User not found")


class _FakeSupabaseClient:
    def __init__(self):
        self.auth = _FakeAuthAPI()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app import database
    from app.database import Base
    from app.main import app

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
    from app.services import scan_service, storage_service, supabase_client

    async def _upload(bucket, key, data, content_type="application/octet-stream"):
        return key

    async def _download(bucket, key):
        return b""

    async def _presign(bucket, key, expires_in=3600):
        return f"https://signed.example/{bucket}/{key}" if key else None

    monkeypatch.setattr(storage_service, "upload", _upload)
    monkeypatch.setattr(storage_service, "download", _download)
    monkeypatch.setattr(storage_service, "presign_get", _presign)

    class _FakePool:
        async def enqueue_job(self, *args, **kwargs):
            return None

        async def close(self):
            return None

    async def _create_pool(_settings):
        return _FakePool()

    monkeypatch.setattr(scan_service, "create_pool", _create_pool)

    # Single in-memory Supabase fake shared by both the dependency and the
    # auth router for the lifetime of one test.
    fake = _FakeSupabaseClient()
    monkeypatch.setattr(supabase_client, "service_client", lambda: fake)
    # The dependency imports service_client by name.
    from app.dependencies import auth as auth_dep

    monkeypatch.setattr(auth_dep, "service_client", lambda: fake)
    from app.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "service_client", lambda: fake)
