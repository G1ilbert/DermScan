"""Supabase client factories.

Two clients live here:

* ``service_client`` uses the SERVICE ROLE key and bypasses RLS — use it
  ONLY from trusted server code (e.g. user provisioning, admin token
  verification). Never expose its results raw to the browser.

* ``user_client(jwt)`` mints a request-scoped client authenticated as the
  caller. Use it whenever you need the request to honor RLS policies.

The Supabase Python client is sync-only, so callers that need it inside a
FastAPI request should run blocking calls through ``asyncio.to_thread``.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


def _require_settings() -> tuple[str, str, str]:
    s = get_settings()
    if not s.supabase_url or not s.supabase_anon_key or not s.supabase_service_role_key:
        raise RuntimeError(
            "Supabase env not configured: SUPABASE_URL, SUPABASE_ANON_KEY and "
            "SUPABASE_SERVICE_ROLE_KEY must all be set."
        )
    return s.supabase_url, s.supabase_anon_key, s.supabase_service_role_key


@lru_cache
def service_client() -> Client:
    """Singleton service-role client (bypasses RLS — server-only)."""
    url, _, service_key = _require_settings()
    return create_client(url, service_key)


def user_client(access_token: str) -> Client:
    """Per-request client authenticated as the caller. Honors RLS."""
    url, anon_key, _ = _require_settings()
    client = create_client(url, anon_key)
    client.postgrest.auth(access_token)
    return client
