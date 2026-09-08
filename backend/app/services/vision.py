"""OpenCV physical-constraint analysis.

Covers the pixel-level half of the multi-modal pipeline:
  * capture quality - Laplacian blur variance and specular glare ratio
  * character height in millimetres, checked against the Second Schedule
  * WCAG relative-luminance contrast between declaration text and its
    background, checked against the 3:1 conspicuousness floor of Rule 9(1)
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from ..config import settings
from ..data.legal_metrology import min_height_for_area


def load_image(path: str) -> np.ndarray:
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unreadable image: {path}")
    return image


def _glare_ratio(gray: np.ndarray) -> float:
    """Fraction of the frame lost to specular glare.

    Counting bright pixels is not enough - a white label is legitimately bright
    and would be rejected on every capture. Real glare is a *compact blown-out
    blob*: a saturated connected region that fills its own bounding box and does
    not span the whole panel. Large, sprawling saturated areas are the label
    stock itself and are ignored.
    """
    total = float(gray.size)
    saturated = (gray >= 252).astype(np.uint8)
    if not saturated.any():
        return 0.0

    count, labels, stats, _ = cv2.connectedComponentsWithStats(saturated, connectivity=8)
    glare_pixels = 0
    for i in range(1, count):
        area = stats[i, cv2.CC_STAT_AREA]
        share = area / total
        # Too small to matter, or so large it is the label background.
        if share < 0.002 or share > 0.25:
            continue
        bbox = stats[i, cv2.CC_STAT_WIDTH] * stats[i, cv2.CC_STAT_HEIGHT]
        if bbox and (area / bbox) > 0.55:  # compact blob, not scattered highlights
            glare_pixels += int(area)

    return glare_pixels / total


def capture_quality(image: np.ndarray) -> dict[str, Any]:
    """Edge/blur and glare detection - the on-device pre-processing gate.

    Runs server-side too so an API caller cannot bypass it.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Laplacian variance: low variance means few sharp edges, i.e. blur.
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    is_blurry = blur_score < settings.blur_threshold

    glare_ratio = _glare_ratio(gray)
    has_glare = glare_ratio > settings.glare_threshold

    messages = []
    if is_blurry:
        messages.append("Image is out of focus - hold steady and retake.")
    if has_glare:
        messages.append("Glare is washing out part of the label - move away from direct light.")

    return {
        "blur_score": round(blur_score, 2),
        "is_blurry": is_blurry,
        "glare_ratio": round(glare_ratio, 4),
        "has_glare": has_glare,
        "quality_ok": not (is_blurry or has_glare),
        "quality_message": " ".join(messages) or None,
    }


def _relative_luminance(bgr: np.ndarray) -> float:
    """WCAG 2.1 relative luminance from a BGR triple."""
    b, g, r = (float(c) / 255.0 for c in bgr[:3])

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg: np.ndarray, bg: np.ndarray) -> float:
    l1, l2 = _relative_luminance(fg), _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _region_contrast(image: np.ndarray, box: list[list[float]]) -> tuple[float, list[int], list[int]]:
    """Split a text box into ink and paper by Otsu, then compare their means."""
    xs = [int(p[0]) for p in box]
    ys = [int(p[1]) for p in box]
    x0, x1 = max(0, min(xs)), min(image.shape[1], max(xs))
    y0, y1 = max(0, min(ys)), min(image.shape[0], max(ys))
    if x1 - x0 < 3 or y1 - y0 < 3:
        return 21.0, [0, 0, 0], [255, 255, 255]

    crop = image[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    dark = crop[mask == 0]
    light = crop[mask == 255]
    if dark.size == 0 or light.size == 0:
        return 21.0, [0, 0, 0], [255, 255, 255]

    # The minority class is the ink; the majority is the background.
    if dark.shape[0] <= light.shape[0]:
        ink, paper = dark.mean(axis=0), light.mean(axis=0)
    else:
        ink, paper = light.mean(axis=0), dark.mean(axis=0)

    ratio = contrast_ratio(ink, paper)
    return (
        round(float(ratio), 2),
        [int(c) for c in ink[::-1]],   # BGR -> RGB for the client
        [int(c) for c in paper[::-1]],
    )


def _box_height_px(box: list[list[float]]) -> float:
    """Height of a (possibly rotated) quadrilateral text box."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = [(float(p[0]), float(p[1])) for p in box]
    left = math.hypot(x3 - x0, y3 - y0)
    right = math.hypot(x2 - x1, y2 - y1)
    return (left + right) / 2.0


def estimate_pdp_area_cm2(width_px: int, height_px: int) -> tuple[float, float]:
    """Estimate principal display panel area and the px->mm scale.

    Without a reference marker in frame we assume the captured face spans
    `assumed_package_width_mm`. A real deployment would use a fiducial or the
    phone's depth/AR scale; the ratio maths downstream is identical.
    """
    mm_per_px = settings.assumed_package_width_mm / max(width_px, 1)
    width_cm = (width_px * mm_per_px) / 10.0
    height_cm = (height_px * mm_per_px) / 10.0
    return round(width_cm * height_cm, 2), mm_per_px


# Declarations that Rule 9(3) sizes and Rule 9(1) requires to be conspicuous.
DECLARATION_KEYWORDS = (
    "mrp", "m.r.p", "maximum retail", "retail price", "rs", "inclusive of all taxes",
    "net", "net wt", "net weight", "net quantity", "quantity",
    "mfg", "manufactured", "packed", "expiry", "exp", "best before", "use by",
    "consumer care", "customer care", "helpline", "toll free", "marketed by",
    "manufactured by", "packed by", "imported by", "country of origin",
)


def is_declaration(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in DECLARATION_KEYWORDS)


def analyse(image: np.ndarray, ocr_regions: list[dict[str, Any]]) -> dict[str, Any]:
    """Full physical analysis over the OCR regions of one label image."""
    height_px, width_px = image.shape[:2]
    pdp_area_cm2, mm_per_px = estimate_pdp_area_cm2(width_px, height_px)
    min_required_mm = min_height_for_area(pdp_area_cm2)

    undersized: list[dict[str, Any]] = []
    low_contrast: list[dict[str, Any]] = []
    heights_mm: list[float] = []
    contrasts: list[float] = []

    for region in ocr_regions:
        text = (region.get("text") or "").strip()
        box = region.get("box")
        if not text or not box:
            continue

        height_mm = round(_box_height_px(box) * mm_per_px, 2)
        # Cap height reflects the glyph body; boxes include leading/padding.
        glyph_mm = round(height_mm * 0.72, 2)
        region["height_mm"] = glyph_mm

        ratio, ink, paper = _region_contrast(image, box)
        region["contrast_ratio"] = ratio

        if not is_declaration(text):
            continue

        heights_mm.append(glyph_mm)
        contrasts.append(ratio)

        if glyph_mm < min_required_mm:
            undersized.append({
                "text": text[:80],
                "height_mm": glyph_mm,
                "required_mm": min_required_mm,
                "box": box,
            })
        if ratio < settings.min_contrast_ratio:
            low_contrast.append({
                "text": text[:80],
                "contrast_ratio": ratio,
                "required_ratio": settings.min_contrast_ratio,
                "text_color": ink,
                "background_color": paper,
                "box": box,
            })

    return {
        "image_width": width_px,
        "image_height": height_px,
        "estimated_pdp_area_cm2": pdp_area_cm2,
        "mm_per_px": round(mm_per_px, 4),
        "min_required_height_mm": min_required_mm,
        "smallest_declaration_height_mm": round(min(heights_mm), 2) if heights_mm else 0.0,
        "undersized_declarations": undersized,
        "min_contrast_ratio": round(min(contrasts), 2) if contrasts else 0.0,
        "low_contrast_declarations": low_contrast,
        "text_regions": len(ocr_regions),
    }
