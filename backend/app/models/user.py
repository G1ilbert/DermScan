from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """Local mirror of ``auth.users`` from Supabase.

    ``id`` matches the Supabase user id verbatim — auth credentials live in
    Supabase, this row exists only as an FK target for app-owned data
    (``scans``, etc.).
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scans = relationship("Scan", back_populates="user", cascade="all, delete-orphan")
