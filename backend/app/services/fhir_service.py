"""FHIR R4 DiagnosticReport export.

Maps a DermScan ``Scan`` to a FHIR R4 DiagnosticReport resource. This is a
simulation — it does not push to a FHIR server. SNOMED CT codes are the
canonical clinical vocabulary; we use 39060008 (Skin lesion) as the report
code so the resource validates against any FHIR R4 server.
"""
from __future__ import annotations

import base64
from datetime import timezone
from typing import Any, Dict, Optional

from app.models import Scan, ScanStatus
from app.services.storage_service import download_bytes


_LABEL_TO_SNOMED: Dict[str, Dict[str, str]] = {
    "melanoma": {"code": "372244006", "display": "Malignant melanoma"},
    "melanocytic_nevus": {"code": "400182000", "display": "Melanocytic nevus"},
    "basal_cell_carcinoma": {"code": "275265005", "display": "Basal cell carcinoma"},
    "actinic_keratosis": {"code": "201101007", "display": "Actinic keratosis"},
    "benign_keratosis": {"code": "201160009", "display": "Benign keratosis"},
    "dermatofibroma": {"code": "254677009", "display": "Dermatofibroma"},
    "vascular_lesion": {"code": "400210000", "display": "Vascular skin lesion"},
}


async def to_fhir_diagnostic_report(scan: Scan, include_image: bool = False) -> Dict[str, Any]:
    prediction = scan.prediction or {}
    label = prediction.get("label")
    band = prediction.get("band")
    confidence = scan.confidence

    fhir_status = "final" if scan.status == ScanStatus.done else "preliminary"
    if scan.status == ScanStatus.failed:
        fhir_status = "entered-in-error"

    conclusion_parts = []
    if label:
        conclusion_parts.append(f"AI prediction: {label.replace('_', ' ')}")
    if confidence is not None:
        conclusion_parts.append(f"confidence {confidence * 100:.1f}%")
    if band:
        conclusion_parts.append(f"band: {band}")
    conclusion = "; ".join(conclusion_parts) or "Pending"

    coded_diagnosis = []
    if label and label in _LABEL_TO_SNOMED:
        snomed = _LABEL_TO_SNOMED[label]
        coded_diagnosis.append(
            {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": snomed["code"],
                        "display": snomed["display"],
                    }
                ]
            }
        )

    issued = scan.updated_at or scan.created_at
    issued_iso = issued.astimezone(timezone.utc).isoformat() if issued else None

    presented_form = []
    if include_image and scan.image_key:
        try:
            image_bytes = await download_bytes(scan.image_key)
            presented_form.append(
                {
                    "contentType": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                    "title": "Original lesion image",
                }
            )
        except Exception:
            pass

    return {
        "resourceType": "DiagnosticReport",
        "id": scan.id,
        "status": fhir_status,
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                        "code": "PAT",
                        "display": "Pathology",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "39060008",
                    "display": "Skin lesion",
                }
            ],
            "text": "AI-assisted skin lesion screening",
        },
        "subject": {"reference": f"Patient/{scan.user_id}"},
        "effectiveDateTime": issued_iso,
        "issued": issued_iso,
        "performer": [
            {"display": "DermScan AI v1"},
        ],
        "conclusion": conclusion,
        "conclusionCode": coded_diagnosis,
        "presentedForm": presented_form,
    }


def confidence_band(confidence: Optional[float], high: float, low: float) -> Optional[str]:
    if confidence is None:
        return None
    if confidence >= high:
        return "result"
    if confidence >= low:
        return "uncertain"
    return "low_quality"
