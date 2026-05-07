from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, EmailStr, Field

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: EmailStr
