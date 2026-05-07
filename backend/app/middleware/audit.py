"""Request audit middleware.

Logs every request to ``audit_logs`` (user_id, method, path, status, ip, ua).
PII is never logged — only IDs and timestamps. The user_id is read from
``request.state.user_id``, which the auth dependency populates after it has
verified the Supabase JWT. Requests that never hit an authenticated route
are logged with a NULL user_id.
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database import SessionLocal
from app.models import AuditLog

logger = logging.getLogger(__name__)


SKIP_PATHS = {"/metrics", "/health"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        if request.url.path in SKIP_PATHS:
            return response

        user_id = getattr(request.state, "user_id", None)
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
