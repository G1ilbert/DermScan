"""Replaced by Supabase Auth.

This module previously held the custom JWT mint/verify logic, bcrypt
password hashing, and the SHA-256 email-lookup helper. All of that is now
owned by Supabase Auth. See:

* ``app.services.supabase_client`` — Supabase client factories
* ``app.dependencies.auth`` — ``get_current_user`` (Supabase JWT verification)
* ``app.routers.auth`` — register/login/logout endpoints (delegated to Supabase)

This file is kept as a stub so that any stale import surfaces a clear error
instead of silently picking up partially-removed symbols.
"""

raise ImportError(
    "app.services.auth_service was removed during the Supabase Auth migration. "
    "Use app.dependencies.auth.get_current_user and app.services.supabase_client instead."
)
