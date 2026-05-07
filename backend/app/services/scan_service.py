"""Scan-domain logic: enqueue jobs to ARQ, fetch results, paginate history."""
from __future__ import annotations

from uuid import uuid4

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Scan, ScanStatus
from app.schemas.scan import ScanHistoryItem, ScanHistoryPage, ScanResult
from app.services.storage_service import presign_get


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


def _classify_band(confidence: float | None) -> str | None:
    if confidence is None:
        return None
    settings = get_settings()
    if confidence >= settings.confidence_threshold_high:
        return "result"
    if confidence >= settings.confidence_threshold_low:
        return "uncertain"
    return "low_quality"


async def create_scan(db: AsyncSession, user_id: str, image_key: str) -> Scan:
    job_id = uuid4().hex
    scan = Scan(user_id=user_id, job_id=job_id, image_key=image_key, status=ScanStatus.pending)
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    pool = await create_pool(_redis_settings())
    try:
        await pool.enqueue_job("run_inference", scan.id, _job_id=job_id)
    finally:
        await pool.close()
    return scan


async def get_scan_for_user(db: AsyncSession, user_id: str, job_id: str) -> Scan | None:
    result = await db.execute(select(Scan).where(Scan.job_id == job_id, Scan.user_id == user_id))
    return result.scalar_one_or_none()


async def get_scan_by_id_for_user(db: AsyncSession, user_id: str, scan_id: str) -> Scan | None:
    result = await db.execute(select(Scan).where(Scan.id == scan_id, Scan.user_id == user_id))
    return result.scalar_one_or_none()


async def to_result(scan: Scan) -> ScanResult:
    image_url = await presign_get(scan.image_key) if scan.image_key else None
    heatmap_url = await presign_get(scan.heatmap_key) if scan.heatmap_key else None
    return ScanResult(
        job_id=scan.job_id,
        scan_id=scan.id,
        status=scan.status.value if hasattr(scan.status, "value") else str(scan.status),
        confidence=scan.confidence,
        prediction=scan.prediction,
        image_url=image_url,
        heatmap_url=heatmap_url,
        confidence_band=_classify_band(scan.confidence) if scan.status == ScanStatus.done else None,
        error_message=scan.error_message,
        created_at=scan.created_at,
    )


async def get_history(db: AsyncSession, user_id: str, page: int, page_size: int) -> ScanHistoryPage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size

    total_result = await db.execute(select(func.count(Scan.id)).where(Scan.user_id == user_id))
    total = total_result.scalar_one()

    items_result = await db.execute(
        select(Scan)
        .where(Scan.user_id == user_id)
        .order_by(Scan.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    scans = items_result.scalars().all()

    items = [
        ScanHistoryItem(
            scan_id=s.id,
            job_id=s.job_id,
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            confidence=s.confidence,
            confidence_band=_classify_band(s.confidence) if s.status == ScanStatus.done else None,
            created_at=s.created_at,
        )
        for s in scans
    ]
    return ScanHistoryPage(items=items, page=page, page_size=page_size, total=total)
