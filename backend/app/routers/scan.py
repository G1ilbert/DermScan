from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas.auth import Envelope
from app.schemas.scan import ScanCreated, ScanHistoryPage, ScanResult
from app.services.auth_service import get_current_user
from app.services.scan_service import (
    create_scan,
    get_history,
    get_scan_for_user,
    to_result,
)
from app.services.storage_service import upload_bytes

router = APIRouter(prefix="/scan", tags=["scan"])

ALLOWED_TYPES = {"image/jpeg", "image/png"}


@router.post("", response_model=Envelope[ScanCreated], status_code=status.HTTP_202_ACCEPTED)
async def submit_scan(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[ScanCreated]:
    settings = get_settings()
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only JPEG or PNG images are accepted")

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large")
    if len(data) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload")

    suffix = "jpg" if file.content_type == "image/jpeg" else "png"
    key = f"users/{user.id}/scans/{uuid4().hex}.{suffix}"
    await upload_bytes(key, data, content_type=file.content_type)

    scan = await create_scan(db, user.id, key)
    return Envelope(
        success=True,
        data=ScanCreated(job_id=scan.job_id, scan_id=scan.id, status=scan.status.value),
        error=None,
    )


@router.get("/result/{job_id}", response_model=Envelope[ScanResult])
async def get_result(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[ScanResult]:
    scan = await get_scan_for_user(db, user.id, job_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return Envelope(success=True, data=await to_result(scan), error=None)


@router.get("/history", response_model=Envelope[ScanHistoryPage])
async def history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[ScanHistoryPage]:
    return Envelope(success=True, data=await get_history(db, user.id, page, page_size), error=None)
