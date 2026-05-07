"""PDF report generation with fpdf2.

Generates a one-page screening report containing the original image, the
GradCAM heatmap, the prediction, and a "this is not a diagnosis" disclaimer.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

from fpdf import FPDF
from PIL import Image

from app.models import Scan
from app.services.storage_service import download_bytes


DISCLAIMER = (
    "DermScan provides AI-assisted screening only and is NOT a medical diagnosis. "
    "Always consult a licensed dermatologist for any concerning skin lesion."
)


def _band_color(band: Optional[str]) -> tuple[int, int, int]:
    return {
        "result": (220, 53, 69),
        "uncertain": (255, 193, 7),
        "low_quality": (108, 117, 125),
    }.get(band or "", (33, 37, 41))


async def _fetch_image_jpeg(key: str) -> Optional[bytes]:
    if not key:
        return None
    try:
        raw = await download_bytes(key)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None


async def build_pdf(scan: Scan) -> bytes:
    image_bytes = await _fetch_image_jpeg(scan.image_key)
    heatmap_bytes = await _fetch_image_jpeg(scan.heatmap_key) if scan.heatmap_key else None

    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "DermScan Screening Report", ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, f"Scan ID: {scan.id}", ln=True)
    pdf.cell(0, 6, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ln=True)
    pdf.cell(0, 6, f"Captured:  {scan.created_at.strftime('%Y-%m-%d %H:%M UTC') if scan.created_at else '—'}", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Result", ln=True)
    pdf.set_font("Helvetica", "", 11)

    prediction = scan.prediction or {}
    label = prediction.get("label", "—")
    band = prediction.get("band")
    confidence = scan.confidence or 0.0

    r, g, b = _band_color(band)
    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(60, 8, f"  {(band or 'pending').upper()}  ", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, f"  Predicted class: {label}", ln=True)

    pdf.cell(0, 7, f"Confidence: {confidence * 100:.1f}%", ln=True)
    pdf.ln(2)

    if image_bytes:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Original image", ln=True)
        pdf.image(io.BytesIO(image_bytes), w=80)
        pdf.ln(2)

    if heatmap_bytes:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Attention heatmap (GradCAM)", ln=True)
        pdf.image(io.BytesIO(heatmap_bytes), w=80)
        pdf.ln(2)

    pdf.set_y(-30)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 4.5, DISCLAIMER)

    return bytes(pdf.output(dest="S"))
