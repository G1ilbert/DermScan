from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class ScanCreated(BaseModel):
    job_id: str
    scan_id: str
    status: str


class ScanResult(BaseModel):
    job_id: str
    scan_id: str
    status: str
    confidence: Optional[float] = None
    prediction: Optional[dict[str, Any]] = None
    image_url: Optional[str] = None
    heatmap_url: Optional[str] = None
    confidence_band: Optional[str] = None  # "result" | "uncertain" | "low_quality"
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class ScanHistoryItem(BaseModel):
    scan_id: str
    job_id: str
    status: str
    confidence: Optional[float] = None
    confidence_band: Optional[str] = None
    created_at: datetime


class ScanHistoryPage(BaseModel):
    items: List[ScanHistoryItem]
    page: int
    page_size: int
    total: int
