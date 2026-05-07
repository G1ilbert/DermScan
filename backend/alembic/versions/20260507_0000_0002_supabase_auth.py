"""migrate users table to supabase auth

Drops the email + email_lookup + password_hash columns (and their indexes).
Identity is now Supabase's auth.users.id, mirrored as users.id verbatim.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_users_email_lookup", table_name="users")
    op.drop_column("users", "email_lookup")
    op.drop_column("users", "email")
    op.drop_column("users", "password_hash")


def downgrade() -> None:
    import sqlalchemy as sa

    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("users", sa.Column("email", sa.String(length=512), nullable=False, server_default=""))
    op.add_column("users", sa.Column("email_lookup", sa.String(length=128), nullable=False, server_default=""))
    op.create_index("ix_users_email_lookup", "users", ["email_lookup"], unique=True)
