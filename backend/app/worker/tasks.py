"""Polling worker.

Replaces the previous ARQ/Redis worker with a plain asyncio loop that
claims work directly out of the ``scans`` table. The state machine is
unchanged:

    pending  → claim_one()  → processing → done|failed

Multiple workers can run concurrently. Each one claims a single row at
a time via ``SELECT ... FOR UPDATE SKIP LOCKED``, which is a Postgres
guarantee — two pollers calling the same statement see disjoint result
sets. Without ``SKIP LOCKED`` two workers would both grab the same
``pending`` row, run inference twice, and race on the final UPDATE.

On startup the worker also resets any rows stuck in ``processing``
older than ``worker_stuck_reset_after_s`` back to ``pending`` — that
covers the case where a previous worker crashed mid-job and the row
would otherwise sit in limbo forever.

Run with:

    python -m app.worker.tasks
"""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import SessionLocal
from app.models import Scan, ScanStatus
from app.services.metrics import scan_confidence_histogram, scan_latency_seconds, scan_total
from app.services.storage_service import HEATMAPS_BUCKET, SCANS_BUCKET, download, upload
from app.worker.inference import classify_band
from app.worker.inference import run_inference as run_model

logger = logging.getLogger(__name__)


async def _claim_one() -> str | None:
    """Atomically claim one pending scan, returning its id (None if none pending).

    ``with_for_update(skip_locked=True)`` is the Postgres
    ``FOR UPDATE SKIP LOCKED`` clause. On SQLite (tests) the option is
    silently ignored, which is fine because tests only run one worker.
    """
    async with SessionLocal() as db:
        async with db.begin():
            scan_id = (
                await db.execute(
                    select(Scan.id)
                    .where(Scan.status == ScanStatus.pending)
                    .order_by(Scan.created_at.asc())
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if scan_id is None:
                return None
            await db.execute(
                update(Scan).where(Scan.id == scan_id).values(status=ScanStatus.processing)
            )
            return scan_id


async def _process(scan_id: str) -> None:
    """Run the model on a single claimed scan and update the row to done/failed.

    Errors are caught and persisted as ``status='failed'`` with the
    truncated exception message so a poisoned job never wedges the
    worker.
    """
    async with SessionLocal() as db:
        scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
        if scan is None:
            logger.warning("scan_id=%s vanished between claim and process", scan_id)
            return

        started = time.monotonic()
        try:
            image_bytes = await download(SCANS_BUCKET, scan.image_key)
            inference = run_model(image_bytes)

            heatmap_key = f"users/{scan.user_id}/{uuid4().hex}.png"
            await upload(HEATMAPS_BUCKET, heatmap_key, inference.heatmap_png, content_type="image/png")

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
            logger.info("scan_id=%s done confidence=%.4f", scan_id, inference.confidence)
        except Exception as exc:
            logger.exception("inference failed for scan_id=%s", scan_id)
            scan.status = ScanStatus.failed
            scan.error_message = str(exc)[:1024]
            await db.commit()
            scan_total.labels(status="failed").inc()


async def _reset_stuck() -> int:
    """Release rows stuck in 'processing' back to 'pending'.

    Called once on worker startup. If a previous worker crashed
    mid-job, its row sits at ``processing`` indefinitely; this catches
    those rows after ``worker_stuck_reset_after_s`` and makes them
    eligible to be claimed again.
    """
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.worker_stuck_reset_after_s)
    async with SessionLocal() as db:
        result = await db.execute(
            update(Scan)
            .where(Scan.status == ScanStatus.processing, Scan.updated_at < cutoff)
            .values(status=ScanStatus.pending)
        )
        await db.commit()
        n = result.rowcount or 0
    if n:
        logger.warning(
            "Reset %d scan(s) stuck in 'processing' for >%ds back to 'pending'",
            n,
            settings.worker_stuck_reset_after_s,
        )
    return n


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    logger.info(
        "Polling worker starting — interval=%.1fs stuck_reset=%ds",
        settings.worker_poll_interval_s,
        settings.worker_stuck_reset_after_s,
    )
    await _reset_stuck()

    stop = asyncio.Event()

    def _shutdown(*_: object) -> None:
        logger.info("Shutdown signal received — exiting after current iteration")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except (NotImplementedError, RuntimeError):
            # Windows asyncio does not support add_signal_handler.
            signal.signal(sig, lambda *_: _shutdown())

    while not stop.is_set():
        try:
            scan_id = await _claim_one()
        except SQLAlchemyError:
            logger.exception("Claim query failed — sleeping before retry")
            await asyncio.sleep(settings.worker_poll_interval_s)
            continue
        if scan_id is None:
            await asyncio.sleep(settings.worker_poll_interval_s)
            continue
        await _process(scan_id)


if __name__ == "__main__":
    asyncio.run(main())
