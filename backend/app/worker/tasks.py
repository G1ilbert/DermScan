"""ARQ worker tasks.

Pipeline for each scan job:
  1. Mark scan as ``processing``
  2. Download original image from R2
  3. Preprocess + ONNX inference + GradCAM
  4. Upload heatmap PNG to R2
  5. Persist prediction + confidence + status=done
"""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Scan, ScanStatus
from app.services.metrics import scan_confidence_histogram, scan_latency_seconds, scan_total
from app.services.storage_service import download_bytes, upload_bytes
from app.worker.inference import classify_band
from app.worker.inference import run_inference as run_model

logger = logging.getLogger(__name__)


async def run_inference(ctx: dict, scan_id: str) -> dict[str, Any]:
    """Process a single scan job. Errors are caught and persisted so a poisoned
    job never wedges the worker."""
    async with SessionLocal() as db:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        if scan is None:
            logger.warning("scan_id=%s not found — skipping", scan_id)
            return {"ok": False, "error": "not_found"}

        scan.status = ScanStatus.processing
        await db.commit()
        started = time.monotonic()

        try:
            image_bytes = await download_bytes(scan.image_key)
            inference = run_model(image_bytes)

            heatmap_key = f"users/{scan.user_id}/heatmaps/{uuid4().hex}.png"
            await upload_bytes(heatmap_key, inference.heatmap_png, content_type="image/png")

            scan.heatmap_key = heatmap_key
            scan.confidence = inference.confidence
            scan.prediction = {
                "label": inference.label,
                "label_index": inference.label_index,
                "probabilities": inference.probabilities,
                "band": classify_band(inference.confidence),
            }
            scan.status = ScanStatus.done
            await db.commit()

            scan_total.labels(status="done").inc()
            scan_confidence_histogram.observe(inference.confidence)
            scan_latency_seconds.observe(time.monotonic() - started)

            return {
                "ok": True,
                "scan_id": scan.id,
                "confidence": inference.confidence,
                "band": classify_band(inference.confidence),
            }
        except Exception as exc:
            logger.exception("inference failed for scan_id=%s", scan_id)
            scan.status = ScanStatus.failed
            scan.error_message = str(exc)[:1024]
            await db.commit()
            scan_total.labels(status="failed").inc()
            return {"ok": False, "error": str(exc)}


class WorkerSettings:
    functions = [run_inference]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 120
