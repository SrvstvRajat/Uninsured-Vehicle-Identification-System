"""Local scene-text recognition with PaddleOCR."""

import os
import tempfile
import threading
from io import BytesIO

from requests.exceptions import RequestException


MODEL_VERSION = os.environ.get("PADDLE_OCR_VERSION", "PP-OCRv5")
IMAGE_SUFFIXES = {"jpeg": ".jpg", "png": ".png", "heic": ".heic"}


class PaddleOCRError(RuntimeError):
    """PaddleOCR could not produce text readings."""


_ocr = None
_ocr_lock = threading.Lock()
_inference_lock = threading.Lock()


def _get_ocr():
    global _ocr
    if _ocr is not None:
        return _ocr

    try:
        from paddleocr import PaddleOCR
    except ImportError as error:
        raise PaddleOCRError(
            "Install paddlepaddle and paddleocr from requirements.txt."
        ) from error

    with _ocr_lock:
        if _ocr is None:
            try:
                _ocr = PaddleOCR(
                    lang="en",
                    ocr_version=MODEL_VERSION,
                    device="cpu",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except (
                ImportError,
                OSError,
                RequestException,
                RuntimeError,
                TypeError,
                ValueError,
            ) as error:
                raise PaddleOCRError(
                    f"Could not initialize the {MODEL_VERSION} model: {error}"
                ) from error
    return _ocr


def _result_readings(result):
    payload = getattr(result, "json", None)
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict):
        raise PaddleOCRError("PaddleOCR returned an invalid result object.")

    details = payload.get("res", payload)
    if not isinstance(details, dict):
        raise PaddleOCRError("PaddleOCR returned an invalid result payload.")
    texts = details.get("rec_texts")
    scores = details.get("rec_scores")
    if isinstance(texts, str) or isinstance(scores, str):
        raise PaddleOCRError(
            "PaddleOCR result did not contain text and confidence scores."
        )
    try:
        texts = list(texts)
        scores = list(scores)
    except TypeError as error:
        raise PaddleOCRError(
            "PaddleOCR result did not contain text and confidence scores."
        ) from error
    if len(texts) != len(scores):
        raise PaddleOCRError(
            "PaddleOCR returned different numbers of texts and scores."
        )

    readings = []
    for text, score in zip(texts, scores):
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            confidence = float(score)
        except (TypeError, ValueError):
            continue
        if 0.0 <= confidence <= 1.0:
            readings.append({
                "text": text.strip(),
                "confidence": confidence,
            })
    return readings


def read_plate_with_paddle_ocr(image_data, image_format):
    """Detect and recognize text in a temporary uploaded image."""
    suffix = IMAGE_SUFFIXES.get(image_format)
    if suffix is None:
        raise PaddleOCRError("PaddleOCR does not support this image format.")

    with tempfile.NamedTemporaryFile(suffix=suffix) as image_file:
        image_file.write(image_data)
        image_file.flush()
        try:
            image_input = image_file.name
            if image_format == "heic":
                import numpy
                import pillow_heif
                from PIL import Image

                pillow_heif.register_heif_opener()
                with Image.open(BytesIO(image_data)) as image:
                    image_input = numpy.asarray(image.convert("RGB"))
            with _inference_lock:
                results = _get_ocr().predict(image_input)
                readings = []
                for result in results:
                    readings.extend(_result_readings(result))
        except (
            ImportError,
            OSError,
            RequestException,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise PaddleOCRError(
                f"Could not run {MODEL_VERSION} OCR: {error}"
            ) from error
    return readings
