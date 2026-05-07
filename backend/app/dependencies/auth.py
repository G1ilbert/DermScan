"""Auth dependency for Supabase-issued JWTs.

The bearer token from the client is verified by round-tripping to Supabase
(``service_client.auth.get_user``). Supabase returns the canonical user row
(id, email, ...) only when the token is valid and not revoked; on success
we lazily upsert a matching row in our local ``users`` table so foreign
keys (e.g. ``scans.user_id``) resolve.

We also stash ``request.state.user_id`` so the audit middleware can record
the authenticated user without re-decoding the token itself.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.services.supabase_client import service_client

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def _verify_with_supabase(token: str) -> str:
    def _call() -> str:
        try:
            response = service_client().auth.get_user(token)
        except Exception as exc:  # supabase raises on invalid / expired
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            ) from exc
        user = getattr(response, "user", None)
        if user is None or not getattr(user, "id", None):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token did not resolve to a user",
            )
        return str(user.id)

    return await asyncio.to_thread(_call)


async def _get_or_create_local_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(id=user_id)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = await _verify_with_supabase(credentials.credentials)
    user = await _get_or_create_local_user(db, user_id)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    request.state.user_id = user.id
    return user
