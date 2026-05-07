"""Auth endpoints — thin wrappers around Supabase Auth.

We keep the same URL surface so the frontend doesn't need to learn two auth
systems, but every credential, password, and session-refresh decision lives
in Supabase. The local ``users`` table is a foreign-key target only; its
row is created lazily on first authenticated request (see
``app.dependencies.auth.get_current_user``).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas.auth import (
    Envelope,
    LoginRequest,
    RegisterRequest,
    SupabaseSession,
    UserOut,
)
from app.services.supabase_client import service_client

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _supabase_error_message(exc: Exception) -> str:
    msg = getattr(exc, "message", None) or str(exc)
    return msg[:300]


def _session_from_supabase(session_obj) -> SupabaseSession:
    """Map Supabase auth session/user objects to our wire schema."""
    user = getattr(session_obj, "user", None)
    return SupabaseSession(
        access_token=session_obj.access_token,
        refresh_token=session_obj.refresh_token,
        token_type="bearer",
        expires_in=getattr(session_obj, "expires_in", 3600) or 3600,
        user_id=str(user.id) if user else "",
        email=getattr(user, "email", None) if user else None,
    )


@router.post("/register", response_model=Envelope[SupabaseSession], status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> Envelope[SupabaseSession]:
    def _signup():
        return service_client().auth.sign_up({"email": str(payload.email), "password": payload.password})

    try:
        result = await asyncio.to_thread(_signup)
    except Exception as exc:
        logger.warning("supabase signup failed: %s", _supabase_error_message(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_supabase_error_message(exc))

    user = getattr(result, "user", None)
    session = getattr(result, "session", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sign-up did not return a user")

    # Mirror into local users table so FK targets exist immediately. If email
    # confirmation is required, ``session`` will be None — that's fine, the
    # row is provisioned and the user can log in once they confirm.
    existing = await db.get(User, str(user.id))
    if existing is None:
        db.add(User(id=str(user.id)))
        await db.commit()

    if session is None:
        # Email confirmation pending — nothing to hand back as a session.
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail="Account created — check your email to confirm before signing in",
        )

    return Envelope(success=True, data=_session_from_supabase(session), error=None)


@router.post("/login", response_model=Envelope[SupabaseSession])
async def login(payload: LoginRequest) -> Envelope[SupabaseSession]:
    def _signin():
        return service_client().auth.sign_in_with_password(
            {"email": str(payload.email), "password": payload.password}
        )

    try:
        result = await asyncio.to_thread(_signin)
    except Exception as exc:
        logger.info("supabase login failed for %s", payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_supabase_error_message(exc))

    session = getattr(result, "session", None)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return Envelope(success=True, data=_session_from_supabase(session), error=None)


@router.post("/logout", response_model=Envelope[dict])
async def logout(user: User = Depends(get_current_user)) -> Envelope[dict]:
    """Best-effort sign-out — also invalidates the access token at Supabase.

    The client must additionally clear its own session cache; refresh tokens
    are invalidated on the Supabase side.
    """

    def _signout():
        try:
            service_client().auth.admin.sign_out(user.id)
        except Exception:
            # Older clients expose ``sign_out`` differently; best-effort only.
            pass

    await asyncio.to_thread(_signout)
    return Envelope(success=True, data={"logged_out": True}, error=None)


@router.get("/me", response_model=Envelope[UserOut])
async def me(user: User = Depends(get_current_user)) -> Envelope[UserOut]:
    def _fetch():
        try:
            return service_client().auth.admin.get_user_by_id(user.id)
        except Exception:
            return None

    info = await asyncio.to_thread(_fetch)
    email: Optional[str] = None
    if info is not None and getattr(info, "user", None) is not None:
        email = getattr(info.user, "email", None)
    return Envelope(success=True, data=UserOut(id=user.id, email=email), error=None)
