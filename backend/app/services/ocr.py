"""OCR tier.

RapidOCR (ONNX, bundled models, no system binary) is the default engine so the
prototype runs offline. Tesseract is used when installed. In a cloud deployment
the same `OCREngine` interface is what AWS Textract / Google Cloud Vision would
implement - each returns text plus per-region boxes and confidences, which is
what the physical-constraint analysis needs.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

_engine: Any = None
_engine_name: str = "none"


def _init_engine() -> tuple[Any, str]:
    global _engine, _engine_name
    if _engine is not None:
        return _engine, _engine_name

    try:
        from rapidocr import RapidOCR

        _engine = RapidOCR()
        _engine_name = "rapidocr-onnx"
        log.info("OCR engine: RapidOCR (ONNX, PP-OCRv6)")
        return _engine, _engine_name
    except Exception as exc:  # pragma: no cover - depends on install
        log.warning("RapidOCR unavailable (%s), trying legacy build", exc)

    try:  # pragma: no cover - older Python environments
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
        _engine_name = "rapidocr-onnx-legacy"
        log.info("OCR engine: RapidOCR (legacy ONNX build)")
        return _engine, _engine_name
    except Exception as exc:
        log.warning("Legacy RapidOCR unavailable (%s), trying Tesseract", exc)

    try:
        import pytesseract  # noqa: F401

        _engine = "pytesseract"
        _engine_name = "tesseract"
        log.info("OCR engine: Tesseract")
        return _engine, _engine_name
    except Exception as exc:  # pragma: no cover
        log.warning("Tesseract unavailable (%s)", exc)

    _engine = "none"
    _engine_name = "none"
    return _engine, _engine_name


def _rapidocr_regions(result: Any) -> list[dict[str, Any]]:
    """Normalise RapidOCR output to {text, box, confidence} records.

    v3 returns a RapidOCROutput with parallel `boxes`/`txts`/`scores`; the
    legacy build returns a list of (box, text, score) tuples.
    """
    regions: list[dict[str, Any]] = []
    if result is None:
        return regions

    boxes = getattr(result, "boxes", None)
    if boxes is not None:
        texts = getattr(result, "txts", None) or []
        scores = getattr(result, "scores", None) or []
        for i, box in enumerate(boxes):
            text = str(texts[i]).strip() if i < len(texts) else ""
            score = float(scores[i]) if i < len(scores) else 0.0
            if not text:
                continue
            regions.append({
                "text": text,
                "box": [[float(p[0]), float(p[1])] for p in box],
                "confidence": round(score, 3),
            })
        return regions

    for item in result:
        try:
            box, text, score = item[0], item[1], item[2]
        except (TypeError, IndexError):
            continue
        regions.append({
            "text": str(text).strip(),
            "box": [[float(p[0]), float(p[1])] for p in box],
            "confidence": round(float(score), 3),
        })
    return regions


def _tesseract_regions(image: np.ndarray) -> list[dict[str, Any]]:  # pragma: no cover
    import pytesseract
    from pytesseract import Output

    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    regions: list[dict[str, Any]] = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        x, y = data["left"][i], data["top"][i]
        w, h = data["width"][i], data["height"][i]
        regions.append({
            "text": text,
            "box": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
            "confidence": round(conf / 100.0, 3),
        })
    return regions


def extract(image: np.ndarray) -> dict[str, Any]:
    """Run OCR over a BGR image. Returns text, regions and mean confidence."""
    engine, name = _init_engine()
    regions: list[dict[str, Any]] = []

    if name.startswith("rapidocr"):
        try:
            result = engine(image)
            # The legacy build returns (result, elapsed).
            if isinstance(result, tuple):
                result = result[0]
            regions = _rapidocr_regions(result)
        except Exception as exc:
            log.exception("RapidOCR failed: %s", exc)
    elif name == "tesseract":
        try:
            regions = _tesseract_regions(image)
        except Exception as exc:
            log.exception("Tesseract failed: %s", exc)

    # Order regions top-to-bottom, then left-to-right, so the joined text
    # reads in the same order a human reads the panel.
    regions.sort(key=lambda r: (min(p[1] for p in r["box"]), min(p[0] for p in r["box"])))

    text = "\n".join(r["text"] for r in regions if r["text"])
    confidences = [r["confidence"] for r in regions if r.get("confidence")]

    return {
        "text": text,
        "regions": regions,
        "confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
        "engine": name,
    }


def engine_name() -> str:
    return _init_engine()[1]
