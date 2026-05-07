# Supabase Auth Migration

This document records the migration of DermScan's authentication layer from a
custom JWT + bcrypt + SHA-256 email-lookup scheme to Supabase Auth.

## 1. What changed

Each task was committed independently so the migration can be bisected.

| #   | Commit    | Change                                                                                          |
| --- | --------- | ----------------------------------------------------------------------------------------------- |
| 1   | `6283c08` | Replace `passlib`/`bcrypt`/`python-jose` with the `supabase` Python client in `requirements.txt` |
| 2   | `05ea3a1` | Add `app.services.supabase_client` with cached service-role + per-user client factories          |
| 3   | `707392f` | Add `app.dependencies.auth.get_current_user` — verifies Supabase JWT and lazy-upserts local user |
| 4   | `97e1a73` | Auth router delegates `/register`, `/login`, `/logout`, `/me` to Supabase; drop `/auth/refresh` |
| 5   | `8f6d2ca` | Slim `User` model to `id` + `is_active` + `created_at`; Alembic migration drops PII columns      |
| 6   | `cac4cda` | Scan router + audit middleware switch to the new auth dep; test suite stubs Supabase client     |
| 7   | `45218ff` | Frontend adopts `@supabase/supabase-js` for session storage and auto-refresh                    |
| 8   | `1d37db8` | `.env.example` files + CI workflow use `SUPABASE_*` vars (drop `JWT_SECRET_KEY`/`ENCRYPTION_KEY`) |
| 9   | `a329148` | Gut `auth_service.py` and `middleware/encryption.py` to fail-fast import stubs                  |

## 2. Architecture before vs after

### Before

```
Client ──email/password──▶ FastAPI /auth/login
                              │
                              ├─ SHA-256(email) → ix_users_email_lookup
                              ├─ bcrypt.verify(password, users.password_hash)
                              ├─ Fernet decrypt users.email_encrypted (display)
                              └─ python-jose: mint HS256 JWT (access + refresh)
                                  │
Client ──Bearer access_token──▶ FastAPI route
                                  │
                                  └─ python-jose verify HS256 with JWT_SECRET_KEY
                                      ↓
                                  load User by sub claim
```

State owned by us: `users.email_encrypted`, `users.email_lookup`,
`users.password_hash`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY` (Fernet).

### After

```
Client ──email/password──▶ FastAPI /auth/register|/login
                              │
                              └─ supabase.auth.sign_up / sign_in_with_password
                                  ↓
                              Supabase issues access_token + refresh_token
                                  ↓
Client (Supabase JS)  ◀── persists session, auto-refreshes ──┐
       │                                                      │
       └─Bearer access_token─▶ FastAPI route                   │
                                  │                            │
                                  ├─ HTTPBearer extracts token │
                                  ├─ service_client().auth.get_user(token)  ◀── round-trip to Supabase
                                  ├─ upsert local users row keyed by Supabase user.id (UUID)
                                  └─ request.state.user_id = user.id
```

State owned by us: only `users.id` (FK to `auth.users.id` in Supabase),
`users.is_active`, `users.created_at`, plus app data (scans, audit logs).
All credentials, password hashes, email storage, and refresh-token rotation are
owned by Supabase.

## 3. Behavioral notes

### 3.1 `get_current_user` latency — round-trip per request

`app.dependencies.auth._verify_with_supabase` calls
`service_client().auth.get_user(token)` on **every authenticated request**.
That is a synchronous HTTPS call to Supabase's auth endpoint, wrapped in
`asyncio.to_thread`.

**Implications**

- Adds Supabase RTT (typically 30–150 ms) to every request that hits a protected
  route. Not a problem for the scan submit/poll cadence, but it will dominate
  latency on chatty endpoints.
- Supabase rate limits apply to `auth.getUser` calls — under sustained load
  (many concurrent users polling) this can throttle.
- If Supabase auth has an outage, **every** authenticated request fails 401 even
  though our DB and worker are healthy.

**Mitigation:** see §7 (Next iteration recommendations).

### 3.2 `users.id` lazy upsert pattern

The local `users` row is created the first time an authenticated request lands,
not at registration time:

```python
# app/dependencies/auth.py
user = await _get_or_create_local_user(db, supabase_user_id)
```

We chose this over a Supabase webhook because it requires no extra
infrastructure and self-heals if rows are deleted locally.

**Implications**

- A user can exist in Supabase but have no row in our `users` table until they
  make their first authenticated call. Anything that joins from `users`
  (analytics queries, admin dashboards) will undercount until that first hit.
- The first authenticated request after a fresh DB write is slightly slower
  (one extra `INSERT`).
- `users.id` is not auto-generated locally. If a row is created with a UUID
  that doesn't match a real Supabase user, FK semantics in our schema won't
  catch it — the assumption is enforced only by the auth dependency. Don't
  open paths that write to `users` outside that dependency.

### 3.3 Audit middleware reads `request.state.user_id`

`app.middleware.audit` no longer decodes JWTs itself. It reads
`request.state.user_id`, which is populated by `get_current_user`.

**Implications**

- The middleware records `user_id = None` for any unauthenticated request
  (login, register, /health, /metrics) — that's intentional.
- If a route is added that returns a response **before** `get_current_user`
  runs (e.g. a custom auth dependency that bypasses it), the audit log will
  show `user_id = None` even though the request was authenticated. Always go
  through `get_current_user`.
- This decouples audit logging from the JWT format: if §7 swaps the
  verification mechanism, the middleware does not need to change.

### 3.4 Migration destructiveness — down-migration loses data

Alembic revision `0002_supabase_auth` performs:

```
DROP INDEX ix_users_email_lookup;
ALTER TABLE users DROP COLUMN email_lookup;
ALTER TABLE users DROP COLUMN email;
ALTER TABLE users DROP COLUMN password_hash;
```

> **WARNING — DATA LOSS**
>
> Running `alembic upgrade head` **permanently deletes** every user's
> encrypted email, email-lookup hash, and bcrypt password hash from the
> application database. There is no in-place rollback that recovers them.
>
> Before upgrading in any environment with real users:
> 1. Take a full Postgres backup (`pg_dump`).
> 2. Confirm every active user has been provisioned in Supabase
>    (sign-up flow or admin import).
> 3. Confirm the Supabase `auth.users.id` matches the local `users.id`
>    (UUID equality) for every row you intend to keep.
>
> Down-migration recreates the columns as empty/NULL — it does **not**
> restore deleted values. Recovery requires the pre-upgrade backup.

### 3.5 Frontend `setAccessToken` is a no-op (kept for compat)

`frontend/lib/api.ts` keeps an exported `setAccessToken(token)` function whose
body is empty. The Supabase JS client owns the session via `localStorage` and
its own `onAuthStateChange` listener; manual token plumbing is no longer
necessary.

**Implications**

- Existing callers (login/register pages) that still call `setAccessToken`
  continue to compile — the call is silently dropped.
- Anything that **read** `getAccessToken()` to attach a header manually now
  reads from `supabase.auth.getSession()` instead. Don't reintroduce a
  cached-token global; it desynchronizes from the Supabase session and breaks
  auto-refresh.
- Plan to remove this shim once all callers are confirmed clean.

## 4. Environment variables

| Variable                     | Used by                             | Where to get it                                                                                                          |
| ---------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `SUPABASE_URL`               | Backend (auth dep, supabase_client) | Supabase Dashboard → Project Settings → API → **Project URL**                                                            |
| `SUPABASE_ANON_KEY`          | Backend (per-user client factory)   | Supabase Dashboard → Project Settings → API → **Project API keys → `anon` `public`**                                     |
| `SUPABASE_SERVICE_ROLE_KEY`  | Backend (service-role client, JWT verification) | Supabase Dashboard → Project Settings → API → **Project API keys → `service_role` `secret`** — **NEVER ship to frontend** |
| `NEXT_PUBLIC_SUPABASE_URL`   | Frontend (Supabase JS client)       | Same as `SUPABASE_URL`                                                                                                   |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend (Supabase JS client)    | Same as `SUPABASE_ANON_KEY`                                                                                              |

The service-role key bypasses RLS — treat it like a database password. It
belongs only in backend env (`backend/.env`, Railway service env, CI secrets),
never in any `NEXT_PUBLIC_*` var or frontend bundle.

Removed in this migration: `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ENCRYPTION_KEY`.

## 5. How to run the migration

Pre-flight (production): take a `pg_dump` backup. See §3.4.

```bash
# 1. Set env vars
cd backend
cp .env.example .env
# Fill in SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY from the
# Supabase dashboard (see §4).

# 2. Install updated Python deps
pip install -r requirements.txt

# 3. Apply Alembic migration (DESTRUCTIVE — see §3.4)
alembic upgrade head

# 4. Verify users table schema
psql "$DATABASE_URL" -c '\d users'
# Expected columns: id (uuid, pk), is_active (bool), created_at (timestamptz)
# Expected indexes: users_pkey only (no ix_users_email_lookup)

# 5. Frontend
cd ../frontend
cp .env.example .env.local
# Fill in NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
npm install --legacy-peer-deps

# 6. Smoke test
# - Register a user via the frontend; confirm they appear in Supabase
#   Dashboard → Authentication → Users.
# - Submit a scan; confirm the local users table has a row with that user's
#   Supabase UUID (lazy upsert, §3.2).
```

## 6. Rollback procedure

> **WARNING — DATA LOSS**
>
> The down-migration recreates `email`, `email_lookup`, and `password_hash`
> columns as **empty/NULL**. It does **not** restore the values dropped in
> step 5 of §1. To genuinely roll back, you need the pre-upgrade `pg_dump`
> backup taken in §5.

```bash
# 1. Restore the pre-migration backup (REQUIRED for real rollback)
psql "$DATABASE_URL" < backup-pre-supabase.sql

# 2. Reset Alembic to the prior revision
cd backend
alembic downgrade -1

# 3. Revert the application code
git revert a329148 1d37db8 45218ff cac4cda 8f6d2ca 97e1a73 707392f 05ea3a1 6283c08
# (or check out the parent of 6283c08 directly)

# 4. Restore env vars
# Re-add JWT_SECRET_KEY, JWT_ALGORITHM, ENCRYPTION_KEY to backend/.env;
# remove SUPABASE_*.

# 5. Reinstall deps
pip install -r requirements.txt
```

If the backup is unavailable, the only path forward is to keep Supabase as the
source of truth and re-derive any needed local state from it — the dropped
PII is unrecoverable.

## 7. Next iteration recommendations

### Local JWT verification (remove the per-request round-trip)

The single biggest improvement: replace the `service_client.auth.get_user`
call in `_verify_with_supabase` with local signature verification.

Two options:

**Option A — JWKS (recommended).** Supabase exposes a JWKS endpoint at
`{SUPABASE_URL}/auth/v1/keys`. Cache the keyset in-process, verify the access
token's RS256 signature against it, and trust the `sub` claim as the user id.

```python
# Sketch
import jwt
from jwt import PyJWKClient

_jwks = PyJWKClient(f"{settings.supabase_url}/auth/v1/keys", cache_keys=True)

def verify_local(token: str) -> str:
    signing_key = _jwks.get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience="authenticated",
        issuer=f"{settings.supabase_url}/auth/v1",
    )
    return claims["sub"]
```

**Option B — Shared HS256 secret.** Older Supabase projects sign tokens with
an HS256 `JWT secret` (Project Settings → API → JWT Settings). Adding
`SUPABASE_JWT_SECRET` to env and verifying with `jwt.decode(token, secret,
algorithms=["HS256"])` is simpler than JWKS but the secret leaks the ability
to mint tokens — protect it accordingly.

Either option:

- Removes the Supabase RTT from the hot path (§3.1).
- Decouples app availability from Supabase auth API availability for
  already-authenticated requests.
- Still requires a Supabase round-trip for register/login/logout — that's fine.

### Other follow-ups

- **Drop the `setAccessToken` shim** (§3.5) once all frontend callers have
  been audited.
- **Add a Supabase webhook** that inserts the local `users` row on
  `auth.users` insert, so `users` tracks Supabase 1:1 instead of lazily
  (§3.2). Worth it once any analytics or admin tool joins from `users`.
- **Add an integration test** that hits a real Supabase test project — the
  current `FakeSupabaseClient` in `conftest.py` exercises code paths but
  doesn't catch breaking changes in the upstream `supabase-py` API.
