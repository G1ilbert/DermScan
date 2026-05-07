"""Replaced by Supabase Auth.

This module previously provided a Fernet-backed ``EncryptedString``
SQLAlchemy column type used to encrypt ``users.email`` at rest, plus
``encrypt_str`` / ``decrypt_str`` helpers. After the migration to Supabase
Auth, the email column no longer lives in our database — credentials and
contact info are owned by Supabase — so the encryption layer is gone.

This file is kept as a stub so that any stale import surfaces a clear error
instead of silently picking up partially-removed symbols.
"""

raise ImportError(
    "app.middleware.encryption was removed during the Supabase Auth migration. "
    "User email is no longer stored locally; it lives in Supabase auth.users."
)
