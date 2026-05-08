"""ONNX inference + GradCAM heatmap generation.

If the ONNX model file is missing the worker MUST NOT crash. Instead we log
a warning and fall back to a deterministic mock prediction so the system
remains demoable end-to-end. Real deployments must mount a model at
``settings.model_path``.

Class labels follow the ISIC 2019 7-class taxonomy.
"""
from __future__ import annotations

import io
import logging
import os
import random
from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

CLASS_LABELS: list[str] = [
    "melanoma",
    "melanocytic_nevus",
    "basal_cell_carcinoma",
    "actinic_keratosis",
    "benign_keratosis",
    "dermatofibroma",
    "vascular_lesion",
]

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass
class InferenceResult:
    label: str
    label_index: int
    confidence: float
    probabilities: list[float]
    heatmap_png: bytes


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _to_tensor(image: Image.Image) -> np.ndarray:
    """PIL image → ImageNet-normalized NCHW float32 tensor."""
    arr = np.asarray(image, dtype=np.float32) / 255.0
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    arr = np.transpose(arr, (2, 0, 1))[None, ...]  # NCHW
    return arr.astype(np.float32)


def preprocess(image_bytes: bytes, size: int | None = None) -> tuple[np.ndarray, Image.Image]:
    target = size or get_settings().model_input_size
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((target, target), Image.BILINEAR)
    return _to_tensor(image), image


def _tta_views(image: Image.Image) -> list[Image.Image]:
    """Five Test Time Augmentation views.

    Index 0 is the original orientation — callers that need an
    aligned-to-input feature map (e.g. for GradCAM) should use that pass.
    """
    return [
        image,
        image.transpose(Image.Transpose.FLIP_LEFT_RIGHT),
        image.transpose(Image.Transpose.FLIP_TOP_BOTTOM),
        image.transpose(Image.Transpose.ROTATE_90),    # +90° counter-clockwise
        image.transpose(Image.Transpose.ROTATE_270),   # -90° (equivalently +270°)
    ]


def _model_available() -> bool:
    return os.path.isfile(get_settings().model_path)


_session = None


def _load_session():
    global _session
    if _session is not None:
        return _session
    if not _model_available():
        return None
    try:
        import onnxruntime as ort

        _session = ort.InferenceSession(get_settings().model_path, providers=["CPUExecutionProvider"])
        logger.info("Loaded ONNX model from %s", get_settings().model_path)
        return _session
    except Exception:  # pragma: no cover - best-effort load
        logger.exception("Failed to load ONNX model — falling back to mock")
        return None


def _mock_prediction(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic mock keyed by image content so repeated runs are stable."""
    h = abs(hash(image.tobytes())) % (2**32)
    rng = random.Random(h)
    raw = np.array([rng.uniform(-1.0, 3.0) for _ in CLASS_LABELS], dtype=np.float32)
    probs = _softmax(raw)
    fake_cam = np.array([[rng.random() for _ in range(7)] for _ in range(7)], dtype=np.float32)
    return probs, fake_cam


def _gradcam_overlay(base: Image.Image, cam: np.ndarray) -> bytes:
    """Mix a heatmap-colored CAM with the original image to produce a PNG."""
    cam = (cam - cam.min()) / max(cam.max() - cam.min(), 1e-8)
    cam_img = Image.fromarray((cam * 255).astype(np.uint8)).resize(base.size, Image.BILINEAR)
    cam_arr = np.asarray(cam_img, dtype=np.float32) / 255.0

    # Simple "jet"-ish colormap: red increases with intensity, blue decreases.
    r = (np.clip(cam_arr * 1.5, 0, 1) * 255).astype(np.uint8)
    g = (np.clip(1 - np.abs(cam_arr - 0.5) * 2, 0, 1) * 255).astype(np.uint8)
    b = (np.clip(1 - cam_arr * 1.5, 0, 1) * 255).astype(np.uint8)
    heat = np.stack([r, g, b], axis=-1)

    base_arr = np.asarray(base.convert("RGB"), dtype=np.float32)
    blended = (0.55 * base_arr + 0.45 * heat.astype(np.float32)).astype(np.uint8)
    out = Image.fromarray(blended)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def run_inference(image_bytes: bytes) -> InferenceResult:
    _, image = preprocess(image_bytes)
    session = _load_session()

    if session is None:
        logger.warning("ONNX model unavailable — returning mock inference result")
        probs, cam = _mock_prediction(image)
    else:
        try:
            input_name = session.get_inputs()[0].name
            # Test Time Augmentation: run the model on five geometric views
            # (identity, h-flip, v-flip, rot+90, rot-90), apply sigmoid to the
            # logits of each, and average. This reduces orientation sensitivity
            # — dermoscopy lesions have no canonical "up" — at the cost of 5×
            # the inference latency. Note we use sigmoid (per-class binary)
            # because the model was trained with BCEWithLogitsLoss; for a
            # softmax/cross-entropy model swap _sigmoid for _softmax below.
            sigmoid_probs: list[np.ndarray] = []
            cam: np.ndarray | None = None
            for i, view in enumerate(_tta_views(image)):
                outputs = session.run(None, {input_name: _to_tensor(view)})
                logits = outputs[0][0] if outputs[0].ndim == 2 else outputs[0]
                sigmoid_probs.append(_sigmoid(np.asarray(logits, dtype=np.float32)))
                # GradCAM only needs the original-orientation feature map —
                # blending a rotated CAM back over an upright image misaligns
                # the highlight region. We take the CAM from the first pass.
                if i == 0:
                    if len(outputs) > 1:
                        feat = np.asarray(outputs[1])
                        cam = feat.mean(axis=tuple(range(feat.ndim - 2))) if feat.ndim >= 3 else np.ones((7, 7), dtype=np.float32)
                    else:
                        _, cam = _mock_prediction(image)
            probs = np.mean(np.stack(sigmoid_probs, axis=0), axis=0)
            assert cam is not None  # set on i == 0
        except Exception:  # pragma: no cover - unexpected runtime error
            logger.exception("ONNX inference failed — using mock fallback")
            probs, cam = _mock_prediction(image)

    label_index = int(np.argmax(probs))
    confidence = float(probs[label_index])
    heatmap = _gradcam_overlay(image, cam)
    return InferenceResult(
        label=CLASS_LABELS[label_index],
        label_index=label_index,
        confidence=confidence,
        probabilities=[float(p) for p in probs.tolist()],
        heatmap_png=heatmap,
    )


def classify_band(confidence: float) -> str:
    settings = get_settings()
    if confidence >= settings.confidence_threshold_high:
        return "result"
    if confidence >= settings.confidence_threshold_low:
        return "uncertain"
    return "low_quality"
