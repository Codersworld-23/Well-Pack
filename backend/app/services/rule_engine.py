"""Deterministic Legal Metrology rule engine.

This is the authority for every verdict. The LLM never decides compliance on
its own - it explains and cross-references the clauses this engine cites, and
its narrative is scored for agreement (see llm.py). That bounding is the
mitigation for the legal-hallucination risk in the feasibility analysis.

Each check is gated on the clause it enforces being active in the corpus, so
switching a clause off in the admin portal switches its check off - the check
is never silently re-attributed to a neighbouring clause.
"""

from __future__ import annotations

from typing import Any

from ..config import settings
from .rag import store

SEVERITY_WEIGHT = {"critical": 30.0, "major": 15.0, "minor": 6.0, "info": 0.0}


def _clause(clause_id: str) -> dict[str, Any] | None:
    """The live clause a check enforces, or None if it is not in the corpus.

    Lookup is by exact clause_id, not by field. Each check enforces exactly one
    clause, and citing the nearest neighbour instead would be wrong: Rule 6(1)(e)
    mandates that an MRP be declared, while Rule 18(1) prohibits altering one -
    an absent MRP is never a contravention of 18(1).

    Returning None means an admin has deactivated or removed that clause, so the
    check it governs no longer applies. That is what makes the corpus genuinely
    authoritative: switching a clause off switches its check off.
    """
    return store.get(clause_id)


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
    skipped: list[dict[str, Any]] = []
    text = (ocr_text or "").lower()

    def record(name: str, passed: bool, clause: dict[str, Any], detail: str = "") -> None:
        checks.append({
            "name": name,
            "passed": passed,
            "clause_id": clause["clause_id"],
            "rule_number": clause["rule_number"],
            "detail": detail,
        })

    def governing(name: str, clause_id: str) -> dict[str, Any] | None:
        """The active clause governing a check, or None if it was switched off."""
        clause = _clause(clause_id)
        if clause is None:
            skipped.append({
                "name": name,
                "clause_id": clause_id,
                "reason": "clause inactive or absent from the corpus",
            })
        return clause

    # --- Rule 6(1)(a) manufacturer / packer / importer -------------------
    clause = governing("manufacturer_present", "PCR-2011-R6.1.a")
    if clause:
        manufacturer = fields.get("manufacturer")
        if not manufacturer:
            violations.append(_violation(
                clause,
                "No manufacturer, packer or importer declaration was found on the label.",
                observed="absent",
                expected="Manufactured/Packed/Imported by + complete address",
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
    clause = governing("commodity_name_present", "PCR-2011-R6.1.b")
    if clause:
        if fields.get("commodity_name"):
            record("commodity_name_present", True, clause, fields["commodity_name"])
        else:
            violations.append(_violation(
                clause,
                "The common or generic name of the commodity could not be identified.",
                observed="absent", expected="Generic name of the product",
            ))
            record("commodity_name_present", False, clause, "missing")

    # --- Rule 6(1)(c) net quantity ---------------------------------------
    quantity = fields.get("net_quantity")
    unit = fields.get("net_quantity_unit")
    value = fields.get("net_quantity_value")

    clause = governing("net_quantity_present", "PCR-2011-R6.1.c")
    if clause:
        if not quantity:
            violations.append(_violation(
                clause, "No net quantity declaration was found on the label.",
                observed="absent",
                expected="Net Quantity / Net Wt. followed by a metric unit",
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

    # --- Rule 5 standard quantities and units of measure -----------------
    clause = governing("units_of_measure", "PCR-2011-R5")
    if clause:
        breached = False
        if quantity and unit == "g" and value and value >= 1000:
            violations.append(_violation(
                clause, "Quantities of 1000 g or more must be expressed in kilograms.",
                observed=f"{value:g} g", expected=f"{value / 1000:g} kg", severity="minor",
            ))
            breached = True
        if quantity and unit == "ml" and value and value >= 1000:
            violations.append(_violation(
                clause, "Quantities of 1000 ml or more must be expressed in litres.",
                observed=f"{value:g} ml", expected=f"{value / 1000:g} l", severity="minor",
            ))
            breached = True
        if fields.get("non_metric_units"):
            violations.append(_violation(
                clause,
                "Non-metric units appear in the declaration; the metric system is mandatory.",
                observed=", ".join(fields["non_metric_units"]),
                expected="Metric units (g, kg, ml, l)",
            ))
            breached = True
        record("units_of_measure", not breached, clause,
               "metric expression correct" if not breached else "metric rules breached")

    # --- Rule 6(1)(d) month and year -------------------------------------
    clause = governing("manufacture_date_present", "PCR-2011-R6.1.d")
    if clause:
        if fields.get("manufacture_date"):
            record("manufacture_date_present", True, clause, fields["manufacture_date"])
        elif fields.get("pointer_declarations"):
            pointers = ", ".join(fields["pointer_declarations"][:2])
            violations.append(_violation(
                clause,
                f"Date of packing is indicated elsewhere on the pack ('{pointers}'). Scan the referenced panel to verify date compliance.",
                observed=pointers, expected="Manufactured/Packed in MM/YYYY on referenced panel",
                severity="minor",
            ))
            record("manufacture_date_present", False, clause, f"referenced on other panel ({pointers})")
        else:
            violations.append(_violation(
                clause,
                "The month and year of manufacture, packing or import is not declared.",
                observed="absent", expected="Manufactured/Packed in MM/YYYY",
            ))
            record("manufacture_date_present", False, clause, "missing")

    # --- Rule 6(1)(e) retail sale price ----------------------------------
    clause = governing("mrp_present", "PCR-2011-R6.1.e")
    if clause:
        if not fields.get("mrp"):
            if fields.get("pointer_declarations"):
                pointers = ", ".join(fields["pointer_declarations"][:2])
                violations.append(_violation(
                    clause,
                    f"Retail sale price is indicated elsewhere on the pack ('{pointers}'). Scan the referenced panel to verify MRP compliance.",
                    observed=pointers, expected="MRP Rs. <price> inclusive of all taxes on referenced panel",
                    severity="minor",
                ))
                record("mrp_present", False, clause, f"referenced on other panel ({pointers})")
            else:
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
                    observed=fields["mrp"],
                    expected="MRP Rs. <price> inclusive of all taxes",
                    severity="major",
                ))

    # --- Rule 18(1) altering the declared retail sale price --------------
    clause = governing("single_mrp", "PCR-2011-R18.1")
    if clause:
        if fields.get("mrp") and fields.get("mrp_occurrences", 0) > 1:
            violations.append(_violation(
                clause, "More than one retail sale price is visible on the package.",
                observed=f"{fields['mrp_occurrences']} MRP declarations",
                expected="A single declared MRP",
            ))
            record("single_mrp", False, clause, "multiple prices")
        else:
            record("single_mrp", True, clause, "single price")

    # --- Rule 6(1)(f) consumer care --------------------------------------
    clause = governing("consumer_care_present", "PCR-2011-R6.1.f")
    if clause:
        if fields.get("consumer_care") and fields.get("consumer_care_has_contact"):
            record("consumer_care_present", True, clause, fields["consumer_care"])
        elif fields.get("consumer_care"):
            violations.append(_violation(
                clause,
                "Consumer care is mentioned but no telephone number or e-mail address "
                "is given.",
                observed=fields["consumer_care"],
                expected="Contact telephone and/or e-mail", severity="major",
            ))
            record("consumer_care_present", False, clause, "no contact channel")
        else:
            violations.append(_violation(
                clause, "No consumer care contact details were found on the label.",
                observed="absent",
                expected="Consumer care name, address, telephone and e-mail",
            ))
            record("consumer_care_present", False, clause, "missing")

    # --- Rule 6(1)(g) country of origin ----------------------------------
    clause = governing("country_of_origin", "PCR-2011-R6.1.g")
    if clause:
        imported = "imported by" in text or "import" in text
        if imported and not fields.get("country_of_origin"):
            violations.append(_violation(
                clause,
                "The package appears to be imported but does not declare a country "
                "of origin.",
                observed="absent", expected="Country of origin", severity="major",
            ))
            record("country_of_origin", False, clause, "missing on imported package")
        else:
            record("country_of_origin", True, clause,
                   fields.get("country_of_origin") or "not applicable")

    # --- Rule 9(3) minimum character height ------------------------------
    clause = governing("font_height", "PCR-2011-R9.3")
    if clause:
        undersized = physical.get("undersized_declarations") or []
        required = physical.get("min_required_height_mm", 0)
        if undersized:
            worst = min(undersized, key=lambda d: d["height_mm"])
            violations.append(_violation(
                clause,
                f"{len(undersized)} declaration(s) are printed below the minimum "
                f"character height for a {physical.get('estimated_pdp_area_cm2', 0)} "
                "sq cm display panel.",
                observed=f"{worst['height_mm']} mm ('{worst['text'][:40]}')",
                expected=f"at least {required} mm",
            ))
            record("font_height", False, clause, f"{len(undersized)} undersized")
        else:
            record("font_height", True, clause, f"minimum {required} mm satisfied")

    # --- Rule 9(1) contrast / conspicuousness ----------------------------
    clause = governing("contrast", "PCR-2011-R9.1")
    if clause:
        low_contrast = physical.get("low_contrast_declarations") or []
        if low_contrast:
            worst = min(low_contrast, key=lambda d: d["contrast_ratio"])
            violations.append(_violation(
                clause,
                f"{len(low_contrast)} declaration(s) do not contrast conspicuously "
                "with the label background.",
                observed=f"{worst['contrast_ratio']}:1 ('{worst['text'][:40]}')",
                expected=f"at least {settings.min_contrast_ratio}:1",
            ))
            record("contrast", False, clause, f"{len(low_contrast)} low contrast")
        else:
            record("contrast", True, clause, "contrast satisfied")

    result = _score(violations, checks, physical)
    result["skipped_checks"] = skipped
    return result


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
