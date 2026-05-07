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


class SupabaseSession(BaseModel):
    """Subset of the Supabase auth session returned to the client.

    The frontend hands ``access_token`` back as a ``Bearer`` token on every
    API call, and uses ``refresh_token`` against Supabase directly to rotate
    sessions — the backend does not own refresh anymore.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: Optional[EmailStr] = None


class UserOut(BaseModel):
    id: str
    email: Optional[EmailStr] = None
