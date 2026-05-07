from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas.auth import Envelope, LoginRequest, RegisterRequest, TokenPair, UserOut
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    email_lookup_hash,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/auth",
    )


@router.post("/register", response_model=Envelope[UserOut], status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> Envelope[UserOut]:
    existing = await get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=payload.email,
        email_lookup=email_lookup_hash(payload.email),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    await db.refresh(user)
    return Envelope(success=True, data=UserOut(id=user.id, email=payload.email), error=None)


@router.post("/login", response_model=Envelope[TokenPair])
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)) -> Envelope[TokenPair]:
    user = await get_user_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)
    return Envelope(success=True, data=TokenPair(access_token=access, refresh_token=refresh), error=None)


@router.post("/refresh", response_model=Envelope[TokenPair])
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> Envelope[TokenPair]:
    token = request.cookies.get("refresh_token")
    if not token:
        # also accept Authorization header for non-browser clients
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    user_id = decode_token(token, "refresh")
    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, new_refresh)
    return Envelope(success=True, data=TokenPair(access_token=access, refresh_token=new_refresh), error=None)


@router.post("/logout", response_model=Envelope[dict])
async def logout(response: Response) -> Envelope[dict]:
    response.delete_cookie("refresh_token", path="/auth")
    return Envelope(success=True, data={"logged_out": True}, error=None)
