import io
import os

import pytest
from PIL import Image


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (380, 380), (180, 90, 70)).save(buf, format="PNG")
    return buf.getvalue()


def test_preprocess_shape_and_range():
    from app.worker.inference import preprocess

    arr, image = preprocess(_png_bytes())
    assert arr.shape == (1, 3, 380, 380)
    assert arr.dtype.name == "float32"
    # ImageNet normalization keeps values in roughly [-2.2, 2.7]
    assert arr.min() > -3.0 and arr.max() < 3.0
    assert image.size == (380, 380)


def test_classify_band_thresholds():
    from app.worker.inference import classify_band

    assert classify_band(0.95) == "result"
    assert classify_band(0.90) == "result"
    assert classify_band(0.80) == "uncertain"
    assert classify_band(0.70) == "uncertain"
    assert classify_band(0.69) == "low_quality"
    assert classify_band(0.0) == "low_quality"


def test_inference_falls_back_to_mock_when_model_missing(monkeypatch):
    """The contract: missing ONNX file must NOT crash — returns a mock result."""
    monkeypatch.setattr("app.worker.inference._model_available", lambda: False)
    # Reset cached session so the missing-model branch is taken.
    import app.worker.inference as inf

    inf._session = None

    result = inf.run_inference(_png_bytes())
    assert result.label in inf.CLASS_LABELS
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.heatmap_png, bytes) and result.heatmap_png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(result.probabilities) == len(inf.CLASS_LABELS)


def test_mock_prediction_is_deterministic_for_same_image():
    import app.worker.inference as inf

    inf._session = None
    img_bytes = _png_bytes()
    a = inf.run_inference(img_bytes)
    b = inf.run_inference(img_bytes)
    assert a.label == b.label
    assert a.confidence == pytest.approx(b.confidence)


def test_environment_uses_test_model_path():
    """Sanity check that conftest set MODEL_PATH to a non-existent file."""
    assert not os.path.isfile(os.environ["MODEL_PATH"])
