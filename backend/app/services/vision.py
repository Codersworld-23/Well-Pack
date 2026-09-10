"""OpenCV physical-constraint analysis.

Covers the pixel-level half of the multi-modal pipeline:
  * capture quality - Laplacian blur variance and specular glare ratio
  * character height in millimetres, checked against the Second Schedule
  * WCAG relative-luminance contrast between declaration text and its
    background, checked against the 3:1 conspicuousness floor of Rule 9(1)
  * pre-processing pipeline for OCR accuracy (CLAHE, denoising, deskew)
  * ORB feature extraction and BFMatcher-based label comparison
  * SSIM structural similarity between two label images
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


# ---------------------------------------------------------------------------
# OCR pre-processing pipeline
# ---------------------------------------------------------------------------

def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """Pre-process a label image for maximum OCR accuracy.

    Pipeline:
      1. Automatic scale to a canonical working height (prevents OCR from
         receiving images that are too small).
      2. CLAHE on the L channel of LAB colour space — normalises uneven
         lighting without blowing out highlights.
      3. Bilateral denoising — edge-preserving; keeps character strokes sharp
         while smoothing paper texture and compression artefacts.
      4. Deskew via Hough line detection — straightens labels photographed
         at a slight angle.

    Returns a BGR image ready for the OCR engine.
    """
    h, w = image.shape[:2]

    # 1. Scale to canonical height (1200 px) if image is too small.
    target_h = 1200
    if h < target_h:
        scale = target_h / h
        image = cv2.resize(image, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_CUBIC)

    # 2. CLAHE on L channel.
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_ch = clahe.apply(l_ch)
    lab = cv2.merge([l_ch, a_ch, b_ch])
    image = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # 3. Bilateral denoising.
    image = cv2.bilateralFilter(image, d=7, sigmaColor=50, sigmaSpace=50)

    # 4. Deskew.
    image = _deskew(image)

    return image


def _deskew(image: np.ndarray, max_angle_deg: float = 12.0) -> np.ndarray:
    """Deskew an image by detecting dominant horizontal text lines.

    Only corrects angles within ±max_angle_deg to avoid mis-rotation on
    non-label imagery.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=120)
    if lines is None:
        return image

    angles: list[float] = []
    for line in lines[:50]:
        rho, theta = line[0]
        angle_deg = math.degrees(theta) - 90.0
        if abs(angle_deg) < max_angle_deg:
            angles.append(angle_deg)

    if not angles:
        return image

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:  # sub-half-degree skew: not worth rotating
        return image

    h, w = image.shape[:2]
    centre = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(centre, median_angle, 1.0)
    return cv2.warpAffine(image, M, (w, h),
                          flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def detect_label_region(image: np.ndarray) -> np.ndarray:
    """Detect and crop the principal label region from a scene photo.

    Uses contour detection to find the largest rectangular/quadrilateral
    region, which is almost always the label panel. Falls back to the full
    image if no clear region is found.
    """
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 100)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image

    # Sort by area descending; the label is the biggest rectangle.
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    image_area = h * w

    for cnt in contours[:5]:
        area = cv2.contourArea(cnt)
        if area < 0.10 * image_area:  # ignore tiny contours
            break
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) in (4, 5):
            x, y, cw, ch = cv2.boundingRect(approx)
            # Require the crop to cover at least 20% of the image.
            if cw * ch >= 0.20 * image_area:
                return image[y:y + ch, x:x + cw]

    # Fallback: largest contour bounding box.
    x, y, cw, ch = cv2.boundingRect(contours[0])
    if cw * ch >= 0.20 * image_area:
        return image[y:y + ch, x:x + cw]

    return image


# ---------------------------------------------------------------------------
# Capture quality gate
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Contrast analysis
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Character height measurement
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Full physical analysis
# ---------------------------------------------------------------------------

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

    orb_count, descriptors = extract_orb_features(image)
    feature_richness = _feature_richness(orb_count)

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
        "orb_keypoints": orb_count,
        "feature_richness": feature_richness,
    }


def _feature_richness(orb_count: int) -> str:
    """Qualitative label of ORB keypoint richness.

    Helps inspectors understand if the label has enough distinctive features
    for reliable tamper/counterfeit detection via ORB matching.
    """
    if orb_count >= 300:
        return "high"
    elif orb_count >= 150:
        return "medium"
    elif orb_count >= 50:
        return "low"
    return "very_low"


# ---------------------------------------------------------------------------
# SSIM — structural similarity
# ---------------------------------------------------------------------------

def compute_ssim(img1: np.ndarray, img2: np.ndarray) -> float:
    """Compute Structural Similarity Index (SSIM) between two packaging images.

    SSIM measures luminance, contrast and structural similarity simultaneously.
    Values close to 1.0 indicate near-identical images; values below 0.7
    suggest significant structural differences (tampered/different product).
    """
    if img1 is None or img2 is None or img1.size == 0 or img2.size == 0:
        return 0.0
    if img1.shape[:2] != img2.shape[:2]:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
    if len(img1.shape) == 3:
        g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    else:
        g1 = img1
    if len(img2.shape) == 3:
        g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    else:
        g2 = img2

    g1 = g1.astype(np.float64)
    g2 = g2.astype(np.float64)
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    kernel = cv2.getGaussianKernel(11, 1.5)
    window = np.outer(kernel, kernel.transpose())

    mu1 = cv2.filter2D(g1, -1, window)[5:-5, 5:-5]
    mu2 = cv2.filter2D(g2, -1, window)[5:-5, 5:-5]
    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = cv2.filter2D(g1 ** 2, -1, window)[5:-5, 5:-5] - mu1_sq
    sigma2_sq = cv2.filter2D(g2 ** 2, -1, window)[5:-5, 5:-5] - mu2_sq
    sigma12 = cv2.filter2D(g1 * g2, -1, window)[5:-5, 5:-5] - mu1_mu2

    denom = (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)
    denom = np.where(denom == 0, 1e-7, denom)
    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / denom
    return round(float(np.clip(ssim_map.mean(), -1.0, 1.0)), 4)


# ---------------------------------------------------------------------------
# ORB feature extraction and matching
# ---------------------------------------------------------------------------

def extract_orb_features(image: np.ndarray, max_features: int = 500) -> tuple[int, np.ndarray | None]:
    """Extract ORB keypoints and binary feature descriptors from packaging."""
    if image is None or image.size == 0:
        return 0, None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    orb = cv2.ORB_create(nfeatures=max_features)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    return len(keypoints), descriptors


def match_orb_features(desc1: np.ndarray | None, desc2: np.ndarray | None) -> dict[str, Any]:
    """Match ORB descriptors using BFMatcher with Hamming norm.

    Returns match count, match ratio, and visual similarity confidence.
    Used for tamper detection and counterfeit label comparison.

    Match quality:
      similarity >= 0.7  → labels are visually very similar (likely same product)
      similarity 0.4–0.7 → similar but potentially different print run / version
      similarity < 0.4   → structurally different (possible counterfeit/tampered)
    """
    if desc1 is None or desc2 is None or len(desc1) == 0 or len(desc2) == 0:
        return {"matches": 0, "match_ratio": 0.0, "similarity": 0.0, "verdict": "insufficient_features"}

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    try:
        matches = bf.match(desc1, desc2)
        matches = sorted(matches, key=lambda m: m.distance)
        # Filter good matches with low Hamming distance (< 50)
        good_matches = [m for m in matches if m.distance < 50]
        min_features = min(len(desc1), len(desc2))
        match_ratio = len(good_matches) / max(min_features, 1)
        similarity = round(min(1.0, match_ratio * 1.6), 3)

        if similarity >= 0.7:
            verdict = "very_similar"
        elif similarity >= 0.4:
            verdict = "similar"
        else:
            verdict = "dissimilar"

        return {
            "matches": len(good_matches),
            "match_ratio": round(match_ratio, 3),
            "similarity": similarity,
            "verdict": verdict,
        }
    except Exception:
        return {"matches": 0, "match_ratio": 0.0, "similarity": 0.0, "verdict": "error"}


def compare_labels(image1: np.ndarray, image2: np.ndarray) -> dict[str, Any]:
    """Full label comparison using both ORB feature matching and SSIM.

    This is the tamper/counterfeit detection entry point. Both algorithms
    are independent — ORB catches structural feature changes (logo removed,
    text moved) while SSIM catches pixel-level differences (colour, texture).

    Combined verdict:
      authentic  → both similarity ≥ 0.65 and ssim ≥ 0.80
      suspicious → mixed signals between ORB and SSIM
      different  → both below threshold
    """
    orb_count1, desc1 = extract_orb_features(image1)
    orb_count2, desc2 = extract_orb_features(image2)

    orb_result = match_orb_features(desc1, desc2)
    ssim_score = compute_ssim(image1, image2)

    orb_sim = orb_result["similarity"]
    orb_ok = orb_sim >= 0.55
    ssim_ok = ssim_score >= 0.75

    if orb_ok and ssim_ok:
        combined = "authentic"
    elif orb_ok or ssim_ok:
        combined = "suspicious"
    else:
        combined = "different"

    return {
        "orb": {
            "keypoints_ref": orb_count1,
            "keypoints_target": orb_count2,
            **orb_result,
        },
        "ssim": {
            "score": ssim_score,
            "verdict": "similar" if ssim_ok else "dissimilar",
        },
        "combined_verdict": combined,
        "combined_confidence": round((orb_sim * 0.5 + ssim_score * 0.5), 3),
    }
