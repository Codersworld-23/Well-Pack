"""Generate synthetic packaged-commodity labels for testing and demos.

Produces one compliant label and several deliberately non-compliant ones, each
exercising a different Legal Metrology failure mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "samples"

W, H = 800, 1000


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("arial.ttf", "DejaVuSans.ttf", "calibri.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _bold(size: int) -> ImageFont.FreeTypeFont:
    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "calibrib.ttf", "seguibl.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return _font(size)


def draw_label(lines: list[tuple[str, int, tuple[int, int, int], bool]],
               path: Path, bg=(255, 255, 255)) -> None:
    """lines: (text, font_size, colour, bold)"""
    image = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle([12, 12, W - 12, H - 12], outline=(30, 30, 30), width=3)

    y = 55
    for text, size, colour, bold in lines:
        font = _bold(size) if bold else _font(size)
        draw.text((45, y), text, font=font, fill=colour)
        y += size + 20

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=95)
    print(f"wrote {path}")


BLACK = (10, 10, 10)
GREY = (176, 176, 176)


def compliant() -> None:
    draw_label([
        ("SURYA GOLD", 62, BLACK, True),
        ("Refined Sunflower Oil", 40, BLACK, True),
        ("", 10, BLACK, False),
        ("Net Quantity: 500 ml", 34, BLACK, True),
        ("MRP Rs. 149.00", 34, BLACK, True),
        ("(inclusive of all taxes)", 26, BLACK, False),
        ("Manufactured in 03/2026", 28, BLACK, False),
        ("Best Before 12 months from packing", 26, BLACK, False),
        ("Batch No. SG2026A", 26, BLACK, False),
        ("", 8, BLACK, False),
        ("Manufactured by: Surya Foods Pvt Ltd,", 26, BLACK, False),
        ("Plot 24, MIDC Industrial Area,", 26, BLACK, False),
        ("Pune, Maharashtra 411019", 26, BLACK, False),
        ("", 8, BLACK, False),
        ("Consumer Care: care@suryafoods.in", 26, BLACK, False),
        ("Toll Free 1800 123 4567", 26, BLACK, False),
        ("FSSAI Lic No. 10019011000123", 24, BLACK, False),
        ("Country of Origin: India", 24, BLACK, False),
    ], OUT_DIR / "compliant_label.png")


def missing_declarations() -> None:
    """No MRP, no manufacture date, no consumer care - three critical failures."""
    draw_label([
        ("CRUNCHY BITES", 62, BLACK, True),
        ("Potato Wafers", 40, BLACK, True),
        ("", 12, BLACK, False),
        ("Net Wt 200 g", 34, BLACK, True),
        ("", 12, BLACK, False),
        ("Marketed by: Snack Corner", 28, BLACK, False),
        ("Delhi", 28, BLACK, False),
        ("", 12, BLACK, False),
        ("Store in a cool dry place", 26, BLACK, False),
        ("No artificial colours", 26, BLACK, False),
    ], OUT_DIR / "missing_declarations.png")


def low_contrast() -> None:
    """Declarations printed in light grey on white - Rule 9(1) failure."""
    draw_label([
        ("PURE HARVEST", 62, BLACK, True),
        ("Basmati Rice", 40, BLACK, True),
        ("", 12, BLACK, False),
        ("Net Quantity: 1000 g", 30, GREY, False),
        ("MRP Rs. 220.00 inclusive of all taxes", 28, GREY, False),
        ("Packed in 01/2026", 28, GREY, False),
        ("", 10, BLACK, False),
        ("Manufactured by: Harvest Mills Ltd,", 26, GREY, False),
        ("Sector 8, Karnal, Haryana 132001", 26, GREY, False),
        ("Consumer Care: 1800 200 3000", 26, GREY, False),
        ("care@harvestmills.in", 26, GREY, False),
    ], OUT_DIR / "low_contrast.png")


def undersized_text() -> None:
    """Mandatory declarations printed far too small - Rule 9(3) failure."""
    draw_label([
        ("MOUNTAIN SPRING", 66, BLACK, True),
        ("Packaged Drinking Water", 44, BLACK, True),
        ("", 40, BLACK, False),
        ("Net Quantity: 1 l", 11, BLACK, False),
        ("MRP Rs. 20.00 inclusive of all taxes", 11, BLACK, False),
        ("Packed in 02/2026", 11, BLACK, False),
        ("Manufactured by: Spring Beverages Ltd, Nashik 422001", 11, BLACK, False),
        ("Consumer Care: 1800 111 2222 care@springbev.in", 11, BLACK, False),
    ], OUT_DIR / "undersized_text.png")


def non_metric() -> None:
    """Imported package: non-metric primary unit, no country of origin."""
    draw_label([
        ("MAPLE CRISP", 62, BLACK, True),
        ("Breakfast Cereal", 40, BLACK, True),
        ("", 12, BLACK, False),
        ("Net Weight 12 oz", 34, BLACK, True),
        ("MRP Rs. 450.00", 32, BLACK, True),
        ("Manufactured in 11/2025", 28, BLACK, False),
        ("", 10, BLACK, False),
        ("Imported by: Global Foods India,", 26, BLACK, False),
        ("Andheri East, Mumbai 400069", 26, BLACK, False),
        ("Consumer Care: help@globalfoods.co.in", 26, BLACK, False),
    ], OUT_DIR / "non_metric.png")


if __name__ == "__main__":
    compliant()
    missing_declarations()
    low_contrast()
    undersized_text()
    non_metric()
    print(f"\nSamples in {OUT_DIR}", file=sys.stderr)
