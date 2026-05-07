"""Request audit middleware.

Logs every request to ``audit_logs`` (user_id, method, path, status, ip, ua).
PII is never logged — only IDs and timestamps. The user_id is decoded from a
bearer token if present; if absent the entry is logged anonymously.
"""
from __future__ import annotations

import logging

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings
from app.database import SessionLocal
from app.models import AuditLog

logger = logging.getLogger(__name__)


SKIP_PATHS = {"/metrics", "/health"}


def _user_id_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1]
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload.get("sub")


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        if request.url.path in SKIP_PATHS:
            return response

        user_id = _user_id_from_request(request)
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:512]

        try:
            async with SessionLocal() as db:
                db.add(
                    AuditLog(
                        user_id=user_id,
                        method=request.method,
                        path=request.url.path[:512],
                        status_code=response.status_code,
                        ip=ip,
                        user_agent=ua,
                    )
                )
                await db.commit()
        except Exception:  # never fail the request because of audit
            logger.exception("audit log write failed")

        return response
