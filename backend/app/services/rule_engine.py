"""Deterministic Legal Metrology rule engine.

This is the authority for every verdict. The LLM never decides compliance on
its own - it explains and cross-references the clauses this engine cites, and
its narrative is scored for agreement (see llm.py). That bounding is the
mitigation for the legal-hallucination risk in the feasibility analysis.

Each check pairs a machine-verifiable condition with the clause retrieved from
the vector store, so the citation shown to the user is the live rule text, not
a hardcoded string.
"""

from __future__ import annotations

from typing import Any

from ..config import settings
from .rag import store

SEVERITY_WEIGHT = {"critical": 30.0, "major": 15.0, "minor": 6.0, "info": 0.0}


def _clause(field: str, query: str, fallback_rule: str, fallback_title: str) -> dict[str, Any]:
    """Live clause for a field, retrieved from the RAG store."""
    hits = store.query_for_field(field, query, top_k=1)
    if hits:
        return hits[0]
    return {
        "clause_id": f"PCR-2011-R{fallback_rule}",
        "rule_number": fallback_rule,
        "title": fallback_title,
        "text": "",
        "field": field,
        "severity": "major",
        "score": 0.0,
    }


def _violation(clause: dict[str, Any], message: str, observed=None, expected=None,
               severity: str | None = None) -> dict[str, Any]:
    return {
        "field": clause["field"],
        "clause_id": clause["clause_id"],
        "rule_number": clause["rule_number"],
        "title": clause["title"],
        "severity": severity or clause.get("severity", "major"),
        "message": message,
        "observed": str(observed) if observed is not None else None,
        "expected": str(expected) if expected is not None else None,
    }


def evaluate(fields: dict[str, Any], physical: dict[str, Any],
             ocr_text: str) -> dict[str, Any]:
    """Run every mandatory-declaration and physical-constraint check."""
    violations: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    text = (ocr_text or "").lower()

    def record(name: str, passed: bool, clause: dict[str, Any], detail: str = "") -> None:
        checks.append({
            "name": name,
            "passed": passed,
            "clause_id": clause["clause_id"],
            "rule_number": clause["rule_number"],
            "detail": detail,
        })

    # --- Rule 6(1)(a) manufacturer / packer / importer -------------------
    clause = _clause("manufacturer", "manufacturer packer importer name complete address",
                     "6(1)(a)", "Name and address of the manufacturer")
    manufacturer = fields.get("manufacturer")
    if not manufacturer:
        violations.append(_violation(
            clause,
            "No manufacturer, packer or importer declaration was found on the label.",
            observed="absent", expected="Manufactured/Packed/Imported by + complete address",
        ))
        record("manufacturer_present", False, clause, "missing")
    elif not fields.get("manufacturer_has_pin"):
        violations.append(_violation(
            clause,
            "The manufacturer declaration has no PIN code, so the address is incomplete.",
            observed=manufacturer, expected="Address including 6-digit PIN code",
            severity="major",
        ))
        record("manufacturer_present", False, clause, "incomplete address")
    else:
        record("manufacturer_present", True, clause, manufacturer)

    # --- Rule 6(1)(b) common or generic name -----------------------------
    clause = _clause("commodity_name", "common generic name of the commodity",
                     "6(1)(b)", "Common or generic name of the commodity")
    if fields.get("commodity_name"):
        record("commodity_name_present", True, clause, fields["commodity_name"])
    else:
        violations.append(_violation(
            clause, "The common or generic name of the commodity could not be identified.",
            observed="absent", expected="Generic name of the product",
        ))
        record("commodity_name_present", False, clause, "missing")

    # --- Rule 6(1)(c) + Rule 5 net quantity ------------------------------
    clause = _clause("net_quantity", "net quantity declaration standard metric unit",
                     "6(1)(c)", "Net quantity declaration")
    quantity = fields.get("net_quantity")
    unit = fields.get("net_quantity_unit")
    value = fields.get("net_quantity_value")
    if not quantity:
        violations.append(_violation(
            clause, "No net quantity declaration was found on the label.",
            observed="absent", expected="Net Quantity / Net Wt. followed by a metric unit",
        ))
        record("net_quantity_present", False, clause, "missing")
    else:
        record("net_quantity_present", True, clause, quantity)
        if not fields.get("net_quantity_labelled", True):
            violations.append(_violation(
                clause,
                "A quantity is printed but is not preceded by the expression "
                "'Net Quantity' or 'Net Wt.' as required.",
                observed=quantity, expected="Net Quantity <value> <unit>",
                severity="minor",
            ))
        # Rule 5 - metric expression thresholds.
        if unit == "g" and value and value >= 1000:
            violations.append(_violation(
                _clause("net_quantity", "unit of weight metric system grams kilograms",
                        "5", "Standard quantities and units of measure"),
                "Quantities of 1000 g or more must be expressed in kilograms.",
                observed=f"{value:g} g", expected=f"{value / 1000:g} kg", severity="minor",
            ))
        if unit == "ml" and value and value >= 1000:
            violations.append(_violation(
                _clause("net_quantity", "unit of measure millilitres litres",
                        "5", "Standard quantities and units of measure"),
                "Quantities of 1000 ml or more must be expressed in litres.",
                observed=f"{value:g} ml", expected=f"{value / 1000:g} l", severity="minor",
            ))

    if fields.get("non_metric_units"):
        violations.append(_violation(
            _clause("net_quantity", "non metric units ounces pounds prohibited",
                    "5", "Standard quantities and units of measure"),
            "Non-metric units appear in the declaration; the metric system is mandatory.",
            observed=", ".join(fields["non_metric_units"]), expected="Metric units (g, kg, ml, l)",
        ))

    # --- Rule 6(1)(d) month and year -------------------------------------
    clause = _clause("manufacture_date", "month and year of manufacture packing import",
                     "6(1)(d)", "Month and year of manufacture")
    if fields.get("manufacture_date"):
        record("manufacture_date_present", True, clause, fields["manufacture_date"])
    else:
        violations.append(_violation(
            clause, "The month and year of manufacture, packing or import is not declared.",
            observed="absent", expected="Manufactured/Packed in MM/YYYY",
        ))
        record("manufacture_date_present", False, clause, "missing")

    # --- Rule 6(1)(e) + Rule 18 retail sale price ------------------------
    clause = _clause("mrp", "maximum retail price inclusive of all taxes",
                     "6(1)(e)", "Retail sale price")
    if not fields.get("mrp"):
        violations.append(_violation(
            clause, "No maximum retail price declaration was found on the label.",
            observed="absent", expected="MRP Rs. <price> inclusive of all taxes",
        ))
        record("mrp_present", False, clause, "missing")
    else:
        record("mrp_present", True, clause, fields["mrp"])
        if not fields.get("mrp_inclusive_of_taxes"):
            violations.append(_violation(
                clause,
                "The retail sale price is declared without the mandatory "
                "'inclusive of all taxes' wording.",
                observed=fields["mrp"], expected="MRP Rs. <price> inclusive of all taxes",
                severity="major",
            ))
        if fields.get("mrp_occurrences", 0) > 1:
            violations.append(_violation(
                _clause("mrp", "two differing maximum retail prices sticker altered",
                        "18(1)", "Prohibition on altering the declared retail sale price"),
                "More than one retail sale price is visible on the package.",
                observed=f"{fields['mrp_occurrences']} MRP declarations",
                expected="A single declared MRP",
            ))

    # --- Rule 6(1)(f) consumer care --------------------------------------
    clause = _clause("consumer_care", "consumer care name address telephone email complaints",
                     "6(1)(f)", "Consumer care details")
    if fields.get("consumer_care") and fields.get("consumer_care_has_contact"):
        record("consumer_care_present", True, clause, fields["consumer_care"])
    elif fields.get("consumer_care"):
        violations.append(_violation(
            clause,
            "Consumer care is mentioned but no telephone number or e-mail address is given.",
            observed=fields["consumer_care"], expected="Contact telephone and/or e-mail",
            severity="major",
        ))
        record("consumer_care_present", False, clause, "no contact channel")
    else:
        violations.append(_violation(
            clause, "No consumer care contact details were found on the label.",
            observed="absent", expected="Consumer care name, address, telephone and e-mail",
        ))
        record("consumer_care_present", False, clause, "missing")

    # --- Rule 6(1)(g) country of origin ----------------------------------
    clause = _clause("country_of_origin", "country of origin imported commodity",
                     "6(1)(g)", "Country of origin")
    imported = "imported by" in text or "import" in text
    if imported and not fields.get("country_of_origin"):
        violations.append(_violation(
            clause, "The package appears to be imported but does not declare a country of origin.",
            observed="absent", expected="Country of origin", severity="major",
        ))
        record("country_of_origin", False, clause, "missing on imported package")
    else:
        record("country_of_origin", True, clause,
               fields.get("country_of_origin") or "not applicable")

    # --- Rule 9(3) minimum character height ------------------------------
    clause = _clause("font_height", "minimum height of numerals letters second schedule",
                     "9(3)", "Minimum height of numerals and letters")
    undersized = physical.get("undersized_declarations") or []
    required = physical.get("min_required_height_mm", 0)
    if undersized:
        worst = min(undersized, key=lambda d: d["height_mm"])
        violations.append(_violation(
            clause,
            f"{len(undersized)} declaration(s) are printed below the minimum character "
            f"height for a {physical.get('estimated_pdp_area_cm2', 0)} sq cm display panel.",
            observed=f"{worst['height_mm']} mm ('{worst['text'][:40]}')",
            expected=f"at least {required} mm",
        ))
        record("font_height", False, clause, f"{len(undersized)} undersized")
    else:
        record("font_height", True, clause, f"minimum {required} mm satisfied")

    # --- Rule 9(1) contrast / conspicuousness ----------------------------
    clause = _clause("contrast", "legible prominent conspicuous colour contrast background",
                     "9(1)", "Declarations to be legible and conspicuous")
    low_contrast = physical.get("low_contrast_declarations") or []
    if low_contrast:
        worst = min(low_contrast, key=lambda d: d["contrast_ratio"])
        violations.append(_violation(
            clause,
            f"{len(low_contrast)} declaration(s) do not contrast conspicuously with the "
            "label background.",
            observed=f"{worst['contrast_ratio']}:1 ('{worst['text'][:40]}')",
            expected=f"at least {settings.min_contrast_ratio}:1",
        ))
        record("contrast", False, clause, f"{len(low_contrast)} low contrast")
    else:
        record("contrast", True, clause, "contrast satisfied")

    return _score(violations, checks, physical)


def _score(violations: list[dict[str, Any]], checks: list[dict[str, Any]],
           physical: dict[str, Any]) -> dict[str, Any]:
    """Bounded compliance score and verdict."""
    penalty = sum(SEVERITY_WEIGHT.get(v["severity"], 10.0) for v in violations)
    score = max(0.0, 100.0 - penalty)

    critical = [v for v in violations if v["severity"] == "critical"]
    major = [v for v in violations if v["severity"] == "major"]

    # A critical or major finding is a contravention of a mandatory rule and is
    # punishable under Rule 32; "partial" is reserved for minor/technical
    # defects (expression of units, wording) that do not defeat the declaration.
    if critical or major:
        verdict = "non_compliant"
    elif violations:
        verdict = "partial"
    else:
        verdict = "compliant"

    # A degraded capture cannot support a confident negative verdict.
    if not physical.get("quality_ok", True) and verdict != "compliant":
        verdict = "needs_review"

    return {
        "verdict": verdict,
        "compliance_score": round(score, 1),
        "violations": violations,
        "checks": checks,
        "counts": {
            "critical": len(critical),
            "major": len(major),
            "minor": len([v for v in violations if v["severity"] == "minor"]),
            "total": len(violations),
            "checks_passed": len([c for c in checks if c["passed"]]),
            "checks_total": len(checks),
        },
    }
