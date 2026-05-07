from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ScanCreated(BaseModel):
    job_id: str
    scan_id: str
    status: str


class ScanResult(BaseModel):
    job_id: str
    scan_id: str
    status: str
    confidence: float | None = None
    prediction: dict[str, Any] | None = None
    image_url: str | None = None
    heatmap_url: str | None = None
    confidence_band: str | None = None  # "result" | "uncertain" | "low_quality"
    error_message: str | None = None
    created_at: datetime | None = None


class ScanHistoryItem(BaseModel):
    scan_id: str
    job_id: str
    status: str
    confidence: float | None = None
    confidence_band: str | None = None
    created_at: datetime


class ScanHistoryPage(BaseModel):
    items: list[ScanHistoryItem]
    page: int
    page_size: int
    total: int
