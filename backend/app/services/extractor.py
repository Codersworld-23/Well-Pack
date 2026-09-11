"""Declaration extraction.

Pulls the Rule 6(1) mandatory declarations out of raw OCR text. Patterns are
tolerant of the usual OCR damage on packaging: Rs/RS/INR/= confusion, missing
decimal points, 'Nel Wt' for 'Net Wt', and inconsistent spacing.
"""

from __future__ import annotations

import re
from typing import Any

# --- primitives ---------------------------------------------------------

UNIT_ALIASES = {
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "mls": "ml", "millilitre": "ml", "milliliter": "ml",
    "l": "l", "ltr": "l", "ltrs": "l", "litre": "l", "liter": "l",
    "n": "N", "no": "N", "nos": "N", "pcs": "N", "pieces": "N", "units": "N",
    "mm": "mm", "cm": "cm", "m": "m",
}

NON_METRIC = ("oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds", "fl oz", "gallon")

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# The gap between "MRP" and its value must not swallow words. A permissive
# [^0-9]{0,25} used to leap over intervening label text to reach the first
# number anywhere nearby - on a real pack it read "MRP ( ol PEPPY TOMATO
# 240022", capturing a barcode as the price. Only currency marks and
# punctuation may separate the label from its amount.
#
# The trailing (?!\d) stops a long barcode ("24002200") from being truncated
# into a plausible-looking six-digit price.
MRP_RE = re.compile(
    r"(?:m\.?\s?r\.?\s?p\.?|max(?:imum)?\.?\s*retail\s*price|retail\s*price)"
    r"[\s:.\-=]{0,6}(?:rs\.?|inr|₹|=)?[\s:.\-=]{0,4}"
    r"(\d{1,6}(?:[.,]\d{1,2})?)(?!\d)",
    re.IGNORECASE,
)
PRICE_FALLBACK_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*(\d{1,6}(?:[.,]\d{1,2})?)(?!\d)", re.IGNORECASE
)
INCLUSIVE_RE = re.compile(
    r"incl(?:usive)?\.?\s*of\s*all\s*tax", re.IGNORECASE
)

# "Net" survives OCR as Nel/Ner/Nct/Nel/N e t; "Wt" as Wl/W1/vvt. Accepting the
# damaged spellings is what stops a legible "Nel Wt. 200 g" from being reported
# as an unlabelled quantity - or, when the bare-number fallback also misses, as
# no net quantity at all.
_NET_WORD = r"n[ea]t{1,2}?|ne[tlrc]|nett"
_WT_WORD = r"wt|w[t1l]|weight|welght|qty|quantity|content[s]?|vol(?:ume)?"

QTY_LABEL_RE = re.compile(
    rf"(?:(?:{_NET_WORD})\s*\.?\s*(?:{_WT_WORD})?|(?:{_WT_WORD}))"
    # Allow the value to sit on the next OCR line: the separator may include the
    # newline that region-joining inserted between label and value.
    r"[^0-9a-zA-Z]{0,8}[^0-9]{0,12}(\d{1,6}(?:[.,]\d{1,3})?)\s*([a-zA-Z]{1,10})",
    re.IGNORECASE,
)
QTY_BARE_RE = re.compile(
    r"\b(\d{1,6}(?:[.,]\d{1,3})?)\s*(kg|kgs|g|gm|gms|gram|grams|ml|mls|l|ltr|litre|liter)\b",
    re.IGNORECASE,
)

# Indian packaging routinely prints "06 FEB 2027" (DD MON YYYY). The previous
# pattern required the separator before the year to be a single character and
# could not accept a space after the day, so that entire format parsed as no
# date at all - producing a "date of manufacture not declared" contravention
# against a pack that clearly declares one.
_DATE_CORE = r"(?:\d{1,2}[\s/\-.]+)?(?:\d{1,2}|[A-Za-z]{3,9})[\s/\-.]+\d{2,4}"

MFG_RE = re.compile(
    r"(?:mfg\.?|mfd\.?|manufactured|packed|pkd\.?|imported)\s*"
    r"(?:on|in|date|dt\.?)?[^A-Za-z0-9]{0,6}"
    rf"({_DATE_CORE})",
    re.IGNORECASE,
)
EXPIRY_RE = re.compile(
    r"(?:exp(?:iry|ires)?\.?|best\s*before|use\s*by|bb)\s*"
    r"(?:on|date|dt\.?)?[^A-Za-z0-9]{0,6}"
    rf"({_DATE_CORE}|\d{{1,3}}\s*(?:months?|days?))",
    re.IGNORECASE,
)

PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?:1800[\s-]?\d{3}[\s-]?\d{3,4}|[6-9]\d{9})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PIN_RE = re.compile(r"\b[1-9]\d{5}\b")
FSSAI_RE = re.compile(r"(?:fssai|lic(?:ence|ense)?\s*no\.?)[^0-9]{0,10}(\d{14})", re.IGNORECASE)
BATCH_RE = re.compile(
    r"(?:batch|b\.?\s?no\.?|lot\s*no\.?|batch\s*no\.?)[^A-Za-z0-9]{0,6}([A-Z0-9\-/]{3,15})",
    re.IGNORECASE,
)
ORIGIN_RE = re.compile(
    r"(?:country\s*of\s*origin|made\s*in|product\s*of)[^A-Za-z]{0,6}([A-Za-z ]{3,30})",
    re.IGNORECASE,
)

MANUFACTURER_RE = re.compile(
    r"(?:manufactured\s*(?:&\s*packed\s*)?by|m[fd]{1,2}\.?\s*by|md\.?\s*by|pkd\.?\s*by|packed\s*by|"
    r"marketed\s*by|mkt\.?\s*by|imported\s*by|manufacturer)\s*[:\-]?\s*(.{4,120})",
    re.IGNORECASE,
)

COMPANY_FALLBACK_RE = re.compile(
    r"([A-Za-z0-9\s&.,-]{3,50}(?:Pvt\.?\s*Ltd\.?|Ltd\.?|Limited|Agro|Industries|Beverages))",
    re.IGNORECASE,
)

POINTER_RE = re.compile(
    r"(?:for\s*mfg|formfg|for\s*m\.?r\.?p|formrp|see\s*top|seetop|see\s*neck|seeneck|"
    r"see\s*crown|seecrown|see\s*bottom|seebottom|see\s*cap|seecap|see\s*below|seebelow|"
    r"see\s*panel|seepanel)",
    re.IGNORECASE,
)

DATE_TOKEN_RE = re.compile(rf"\b({_DATE_CORE})\b")

CONSUMER_CARE_RE = re.compile(
    r"(?:consumer\s*care|customer\s*care|consumer\s*complaint|helpline|"
    r"for\s*(?:any\s*)?(?:queries|complaints))\s*[:\-]?\s*(.{0,120})",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :,-.–—")


def _to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _normalise_unit(raw: str) -> str | None:
    return UNIT_ALIASES.get(raw.lower().strip("."))


def _parse_month_year(raw: str) -> str | None:
    """Normalise a date-ish fragment to MM/YYYY where possible."""
    raw = _clean(raw)
    # Search rather than match: in "06 FEB 2027" the month name is not at the
    # start, and taking the leading digits instead would report the day (06) as
    # the month, i.e. June instead of February.
    alpha = re.search(r"([A-Za-z]{3,9})[\s/\-.]+(\d{2,4})", raw)
    if alpha:
        month = MONTHS.get(alpha.group(1)[:3].lower())
        year = alpha.group(2)
        if month:
            year = f"20{year}" if len(year) == 2 else year
            return f"{month:02d}/{year}"
    numeric = re.findall(r"\d+", raw)
    if len(numeric) >= 2:
        month, year = numeric[-2], numeric[-1]
        if len(month) <= 2 and 1 <= int(month) <= 12:
            year = f"20{year}" if len(year) == 2 else year
            return f"{int(month):02d}/{year}"
    return raw or None


def extract_fields(text: str, regions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Extract the mandatory declarations from OCR text."""
    flat = re.sub(r"[ \t]+", " ", text)
    single = flat.replace("\n", " ")
    fields: dict[str, Any] = {}

    # --- MRP (Rule 6(1)(e)) --------------------------------------------
    mrp_match = MRP_RE.search(single) or PRICE_FALLBACK_RE.search(single)
    if mrp_match:
        value = _to_float(mrp_match.group(1))
        fields["mrp_value"] = value
        fields["mrp"] = _clean(mrp_match.group(0))
        fields["mrp_inclusive_of_taxes"] = bool(INCLUSIVE_RE.search(single))

    # --- net quantity (Rule 6(1)(c)) ------------------------------------
    qty_match = QTY_LABEL_RE.search(single)
    unit = _normalise_unit(qty_match.group(2)) if qty_match else None
    if qty_match and unit:
        fields["net_quantity"] = _clean(qty_match.group(0))
        fields["net_quantity_value"] = _to_float(qty_match.group(1))
        fields["net_quantity_unit"] = unit
        fields["net_quantity_labelled"] = True
    else:
        bare = QTY_BARE_RE.search(single)
        if bare:
            fields["net_quantity"] = _clean(bare.group(0))
            fields["net_quantity_value"] = _to_float(bare.group(1))
            fields["net_quantity_unit"] = _normalise_unit(bare.group(2))
            # Present but without the required "Net Quantity" expression.
            fields["net_quantity_labelled"] = False

    fields["non_metric_units"] = [u for u in NON_METRIC if re.search(rf"\b{re.escape(u)}\b", single, re.I)]

    # --- dates (Rule 6(1)(d)) -------------------------------------------
    mfg = MFG_RE.search(single)
    if mfg:
        fields["manufacture_date"] = _parse_month_year(mfg.group(1))
        fields["manufacture_date_raw"] = _clean(mfg.group(0))
    else:
        # Windowed fallback: search near date keywords if columns got interleaved
        for m in re.finditer(r"\b(?:mfg|mfd|packed|pkd|manufactured)\b", single, re.I):
            window = single[m.start(): m.start() + 80]
            date_match = DATE_TOKEN_RE.search(window)
            if date_match:
                fields["manufacture_date"] = _parse_month_year(date_match.group(1))
                fields["manufacture_date_raw"] = _clean(date_match.group(0))
                break

    expiry = EXPIRY_RE.search(single)
    if expiry:
        fields["expiry_date"] = _clean(expiry.group(1))
    else:
        for m in re.finditer(r"\b(?:exp|use\s*by|best\s*before|expiry|bb)\b", single, re.I):
            window = single[m.start(): m.start() + 80]
            date_match = DATE_TOKEN_RE.search(window)
            if date_match:
                fields["expiry_date"] = _clean(date_match.group(0))
                break

    # --- manufacturer / packer (Rule 6(1)(a)) ---------------------------
    manufacturer = MANUFACTURER_RE.search(flat)
    if manufacturer:
        name = _clean(manufacturer.group(1).split("\n")[0])
        fields["manufacturer"] = name[:120]
        block = flat[manufacturer.start(): manufacturer.start() + 300]
        fields["manufacturer_has_pin"] = bool(PIN_RE.search(block))
    else:
        fallback = COMPANY_FALLBACK_RE.search(flat)
        if fallback:
            fields["manufacturer"] = _clean(fallback.group(1))[:120]
            block = flat[fallback.start(): fallback.start() + 300]
            fields["manufacturer_has_pin"] = bool(PIN_RE.search(block))
        else:
            fields["manufacturer_has_pin"] = bool(PIN_RE.search(single))

    # --- consumer care (Rule 6(1)(f)) -----------------------------------
    care = CONSUMER_CARE_RE.search(flat)
    phone = PHONE_RE.search(single)
    email = EMAIL_RE.search(single)
    if care or phone or email:
        parts = []
        if care and _clean(care.group(1)):
            parts.append(_clean(care.group(1))[:100])
        if phone:
            parts.append(phone.group(0))
        if email:
            parts.append(email.group(0))
        fields["consumer_care"] = " | ".join(dict.fromkeys(parts)) or None
        fields["consumer_care_has_contact"] = bool(phone or email)
    else:
        fields["consumer_care_has_contact"] = False

    # --- supporting declarations ----------------------------------------
    origin = ORIGIN_RE.search(single)
    if origin:
        fields["country_of_origin"] = _clean(origin.group(1))[:40]
    fssai = FSSAI_RE.search(single)
    if fssai:
        fields["fssai_licence"] = fssai.group(1)
    batch = BATCH_RE.search(single)
    if batch:
        raw_b = _clean(batch.group(1))
        if not re.search(r"^(?:and|see|top|for|mrp|tax|date|exp)", raw_b, re.I):
            fields["batch_number"] = raw_b

    # --- statutory pointer clauses (Rules 6(1)(d) & 6(1)(e) provisos) ---
    pointers = POINTER_RE.findall(single)
    if pointers:
        fields["pointer_declarations"] = [_clean(p) for p in pointers]

    fields["commodity_name"] = _guess_commodity_name(regions or [], text)
    fields["mrp_occurrences"] = len(MRP_RE.findall(single))

    return {k: v for k, v in fields.items() if v not in (None, "", [])} | {
        "non_metric_units": fields.get("non_metric_units", []),
        "consumer_care_has_contact": fields.get("consumer_care_has_contact", False),
        "manufacturer_has_pin": fields.get("manufacturer_has_pin", False),
        "pointer_declarations": fields.get("pointer_declarations", []),
    }


NOISE_TOKENS = re.compile(
    r"mrp|rs\.?|net|wt|weight|qty|quantity|mfg|exp|batch|fssai|fssat|licno|lic|licence|www|http|"
    r"inclusive|taxes|manufactured|packed|marketed|customer|consumer|care|\d|"
    r"pvt|ltd|limited|agro|foods|industries|beverages|india|co\b|corp|llp|inc|"
    r"street|road|highway|andheri|meerut|varanasi|mumbai|delhi|bangalore|pune|rajasthan|"
    r"licence|license|lic\s*no|read\s*first|see\s*below|for\s*manuf|ingredients|nutrition",
    re.IGNORECASE,
)


def _guess_commodity_name(regions: list[dict[str, Any]], text: str) -> str | None:
    """The generic name is usually the largest non-boilerplate text on the panel."""
    candidates: list[tuple[float, str]] = []
    for region in regions:
        value = (region.get("text") or "").strip()
        if len(value) < 3 or NOISE_TOKENS.search(value):
            continue
        box = region.get("box")
        if not box:
            continue
        heights = [p[1] for p in box]
        candidates.append((max(heights) - min(heights), value))

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1][:80]

    for line in text.split("\n"):
        line = line.strip()
        if len(line) >= 3 and not NOISE_TOKENS.search(line):
            return line[:80]
    return None
