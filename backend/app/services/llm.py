"""RAG-grounded LLM compliance decisions.

The local vector store retrieves clauses from the ingested PDF corpus. An
OpenAI-compatible model evaluates the OCR/vision evidence against those
clauses and returns the compliance label as structured JSON. The deterministic
rule engine remains an offline/error fallback.

Two failure modes this module is built to avoid:

1. *False negatives from the regex extractor.* `extractor.py` is a pattern
   matcher and routinely misses declarations that are plainly readable in the
   OCR text - a misread "Nel Wt" instead of "Net Wt" is enough to make it
   report an absent net quantity. The prompt therefore treats the RAW OCR TEXT
   as primary evidence and the extracted fields as a fallible hint, and the
   model returns `field_corrections` so a missed declaration is recovered.

2. *Silent fallback.* An earlier version discarded the entire LLM decision if
   any single violation cited an unretrieved clause, which - combined with a
   top-5 retrieval covering only half the checks - meant the deterministic
   engine decided every scan. Validation now salvages the usable parts of a
   response and only falls back when nothing survives.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)

# None = not yet probed, True/False = this provider's answer, cached for the
# lifetime of the process.
_supports_json_schema: bool | None = None

ALLOWED_VERDICTS = {"compliant", "partial", "non_compliant", "needs_review"}
ALLOWED_SEVERITIES = {"critical", "major", "minor", "info"}

SYSTEM_PROMPT = """You are a Legal Metrology compliance analyst for the Government of India.
You decide whether a packaged commodity label complies with the Legal Metrology
(Packaged Commodities) Rules, 2011, using ONLY the evidence supplied below.

EVIDENCE PRECEDENCE - this matters more than anything else:
1. RAW OCR TEXT is the primary evidence. It is what the camera actually read
   off the package.
2. EXTRACTED LABEL DECLARATIONS come from a regular-expression extractor that
   is known to MISS declarations that are clearly present in the OCR text. An
   empty or absent field there is NOT evidence of absence.
3. ENGINE HINTS are produced by that same fallible extractor. Treat them as a
   checklist to verify, never as conclusions to repeat.

NEVER report a mandatory declaration as missing until you have searched the RAW
OCR TEXT for it yourself, including OCR-damaged spellings. Real examples of
damage you must see through:
  "Nel Wt", "Ner Wt", "NetWt", "N e t  W t"   -> Net Weight
  "M.RP", "MFP", "MRP.", "Rs", "INR", "₹"     -> retail sale price
  "Mfg", "Mfd", "PKD", "Packed on"            -> date of manufacture/packing
  "1O0g", "5OOml" (letter O for zero)         -> quantity values
  a value and its unit split across lines     -> one declaration
If a declaration is legible in the OCR text in ANY form, it is PRESENT, and you
must record it in field_corrections even when the extracted fields omit it.

PRESENT-BUT-DEFECTIVE IS NOT ABSENT. A declaration that exists but breaks a
requirement - wrong units, missing "inclusive of all taxes", printed too small,
poor contrast, missing the words "Net Quantity" - is still a declaration that is
present. Report the actual defect and quote what the label says. Never write
"no ... was found" or set observed to "absent" for something you can read in the
OCR text. For example, a pack showing "Net Weight 12 oz" has a net quantity
declaration; the contravention is that it is expressed in a non-metric unit, not
that the declaration is missing. Getting this wrong misdescribes the offence and
misdirects the inspector.

The retrieved clauses are the legal source of truth. Do not invent clauses,
rule numbers, penalties or requirements, and cite only clause_ids that appear in
the RETRIEVED CLAUSES block.

Allowed verdicts: compliant, partial, non_compliant, needs_review. Use
needs_review only when the OCR/image quality genuinely leaves a mandatory
conclusion unsupported - not merely because the extractor missed a field.
Return valid JSON matching the requested schema, with no markdown."""

def _object(properties: dict[str, Any]) -> dict[str, Any]:
    """A strict-mode JSON-schema object: every key required, none extra.

    OpenAI strict structured outputs reject any object that omits
    `additionalProperties: false` or leaves a property out of `required`, and
    that applies to nested objects too - a bare {"type": "object"} anywhere in
    the tree fails the whole request.
    """
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# field_corrections is a list of pairs rather than a free-form object because a
# map with arbitrary keys cannot be expressed in strict mode; _clean_corrections
# folds it back into a dict.
_CORRECTION = _object({
    "field": {"type": "string", "enum": sorted({
        "commodity_name", "manufacturer", "net_quantity", "net_quantity_value",
        "net_quantity_unit", "mrp", "mrp_value", "mrp_inclusive_of_taxes",
        "manufacture_date", "expiry_date", "consumer_care", "country_of_origin",
        "batch_number", "fssai_licence",
    })},
    "value": {"type": "string"},
})

_VIOLATION = _object({
    "field": {"type": "string"},
    "clause_id": {"type": "string"},
    "rule_number": {"type": "string"},
    "title": {"type": "string"},
    "severity": {"type": "string", "enum": sorted(ALLOWED_SEVERITIES)},
    "message": {"type": "string"},
    "observed": {"type": "string"},
    "expected": {"type": "string"},
})

_CHECK = _object({
    "name": {"type": "string"},
    "field": {"type": "string"},
    "clause_id": {"type": "string"},
    "rule_number": {"type": "string"},
    "passed": {"type": "boolean"},
    "detail": {"type": "string"},
})

RESPONSE_SCHEMA = _object({
    "verdict": {"type": "string", "enum": sorted(ALLOWED_VERDICTS)},
    "compliance_score": {"type": "number"},
    "summary": {"type": "string"},
    "cited_clause_ids": {"type": "array", "items": {"type": "string"}},
    "field_corrections": {"type": "array", "items": _CORRECTION},
    "violations": {"type": "array", "items": _VIOLATION},
    "checks": {"type": "array", "items": _CHECK},
    "analyst_note": {"type": "string"},
    "confidence": {"type": "number"},
})

# Declarations the model may return under field_corrections. Anything else is
# ignored, so a chatty model cannot inject arbitrary keys into the scan record.
CORRECTABLE_FIELDS = {
    "commodity_name", "manufacturer", "net_quantity", "net_quantity_value",
    "net_quantity_unit", "mrp", "mrp_value", "mrp_inclusive_of_taxes",
    "manufacture_date", "expiry_date", "consumer_care", "country_of_origin",
    "batch_number", "fssai_licence",
}


def _client():
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.warning("No OPENAI_API_KEY configured - using deterministic fallback")
        return None
    try:
        from openai import OpenAI
    except ImportError:
        log.warning("openai SDK is not installed - using deterministic fallback")
        return None
    return OpenAI(
        api_key=api_key,
        base_url=settings.openai_base_url,
        timeout=settings.llm_timeout_seconds,
    )


def available() -> bool:
    """Whether a RAG-grounded LLM decision is configured and importable."""
    return _client() is not None


def _build_prompt(fields: dict[str, Any], physical: dict[str, Any],
                  clauses: list[dict[str, Any]], engine: dict[str, Any],
                  ocr_text: str) -> str:
    clause_block = "\n\n".join(
        f"[{c['clause_id']}] Rule {c['rule_number']} - {c['title']}\n{c['text']}"
        for c in clauses
    ) or "No clauses were retrieved; use needs_review rather than inventing law."
    engine_block = json.dumps({
        "verdict": engine.get("verdict"),
        "compliance_score": engine.get("compliance_score"),
        "violations": engine.get("violations", []),
        "checks": engine.get("checks", []),
    }, indent=2, default=str)

    # Physical measurements are genuine pixel evidence, but the bulky per-region
    # arrays crowd out the OCR text; keep the decision-relevant summary.
    physical_summary = {
        k: v for k, v in physical.items()
        if k not in {"regions", "text_regions_detail", "uncertain_regions"}
    }
    uncertain = physical.get("uncertain_regions") or []
    uncertain_block = (
        "OCR regions read with low confidence - re-read these carefully in the raw "
        f"text before calling anything absent:\n{json.dumps(uncertain[:20], default=str)}"
        if uncertain else "No low-confidence OCR regions."
    )

    return f"""RAW OCR TEXT (PRIMARY EVIDENCE - read this before judging anything absent)
\"\"\"
{ocr_text[:8000]}
\"\"\"

{uncertain_block}

RETRIEVED CLAUSES FROM THE INGESTED PDF CORPUS (the only citable law)
{clause_block}

EXTRACTED LABEL DECLARATIONS (regex output - INCOMPLETE, verify against the OCR text)
{json.dumps(fields, indent=2, default=str)}

PHYSICAL MEASUREMENTS (OpenCV - character heights, contrast, capture quality)
{json.dumps(physical_summary, indent=2, default=str)}

ENGINE HINTS (same fallible extractor - VERIFY EACH, they are not the answer)
{engine_block}

TASK
Work through every mandatory declaration in the retrieved clauses. For each one:
  a. Search the RAW OCR TEXT for it, allowing for OCR damage.
  b. If you find it, emit a passing check and put the value you read into
     field_corrections (this is how a missed declaration gets recovered).
  c. Only if it is genuinely not in the OCR text, emit a violation.

Every violation and check must cite a clause_id from the RETRIEVED CLAUSES block
and quote the evidence you relied on in its message. field_corrections must
contain only values you can actually see in the raw OCR text - never guess a
price, quantity or date.

Return a single JSON object using EXACTLY these top-level keys, spelled this way:
  "verdict"           string: compliant | partial | non_compliant | needs_review
  "compliance_score"  number 0-100
  "summary"           string: your reasoning, for the inspector to read
  "cited_clause_ids"  array of clause_id strings you relied on
  "field_corrections" array of {{field, value}}: declarations you read in the OCR
                      text that the extractor missed, e.g.
                      [{{"field": "net_quantity", "value": "200 g"}}]
  "violations"        array of {{field, clause_id, rule_number, title, severity,
                      message, observed, expected}}; severity is one of
                      critical | major | minor | info
  "checks"            array of {{name, field, clause_id, rule_number, passed, detail}}
  "analyst_note"      string: caveats an inspector should know
  "confidence"        number 0-1
Do not rename these keys and do not nest them inside another object."""


def _complete(client, messages: list[dict[str, str]]) -> str:
    """Request the decision, preferring a strictly-enforced JSON schema.

    RESPONSE_SCHEMA was previously declared but never sent, leaving the provider
    to invent its own key names. Strict `json_schema` mode removes that freedom;
    providers that reject it fall back to plain JSON mode, where _canonical_keys
    reconciles the naming instead.
    """
    global _supports_json_schema

    kwargs = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 4000,
    }
    if _supports_json_schema is not False:
        try:
            response = client.chat.completions.create(
                **kwargs,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "compliance_decision",
                        "strict": True,
                        "schema": RESPONSE_SCHEMA,
                    },
                },
            )
            _supports_json_schema = True
            return response.choices[0].message.content or "{}"
        except Exception as exc:  # noqa: BLE001 - provider capability probe
            # Probe once per process, not once per scan: an unsupported schema
            # would otherwise add a wasted round-trip to every single request.
            _supports_json_schema = False
            log.info("Strict JSON schema unsupported (%s); using json_object mode", exc)

    response = client.chat.completions.create(
        **kwargs, response_format={"type": "json_object"}
    )
    return response.choices[0].message.content or "{}"


def verify(fields: dict[str, Any], physical: dict[str, Any],
           clauses: list[dict[str, Any]], engine: dict[str, Any],
           ocr_text: str) -> dict[str, Any]:
    """Ask the RAG-grounded LLM for the compliance decision."""
    client = _client()
    if client is None:
        return _fallback(engine, physical)
    try:
        content = _complete(
            client,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(fields, physical, clauses, engine, ocr_text)},
            ],
        )
        parsed = _parse_json(content)
        decision, dropped = _normalise_decision(parsed, clauses)
        if decision is None:
            raise ValueError("model returned no usable verdict")
    except Exception as exc:  # noqa: BLE001 - provider compatibility is best effort
        log.warning("OpenAI-compatible verification unavailable (%s) - using fallback", exc)
        return _fallback(engine, physical)

    if dropped:
        log.info("Dropped %d ungrounded LLM item(s) citing unretrieved clauses", dropped)

    coefficient, breakdown = hallucination_assessment(
        parsed, engine, clauses, ocr_text, fields, dropped
    )
    return {
        "decision": decision,
        "reasoning": _summary_for(parsed, decision),
        "analyst_note": parsed.get("analyst_note") or None,
        "field_corrections": _clean_corrections(parsed.get("field_corrections"), ocr_text),
        "confidence": _bounded_float(parsed.get("confidence", 0.7), 0.0, 1.0),
        "hallucination_coefficient": round(coefficient, 3),
        "hallucination_breakdown": breakdown,
        "bounded": coefficient <= 0.35,
        "decision_source": "rag+openai",
        "engine": f"rag+{settings.llm_model}",
    }


# Providers that only honour `json_object` (no strict schema) are free to name
# keys as they please, and this one alternates between "verdict" and
# "compliance_decision" for the same prompt. Losing the verdict meant the whole
# decision was discarded and every scan silently fell back to the regex engine,
# so the aliases are accepted explicitly.
KEY_ALIASES = {
    "verdict": ("verdict", "compliance_decision", "decision", "compliance_verdict",
                "overall_verdict", "status", "result"),
    "compliance_score": ("compliance_score", "score", "compliance_percentage"),
    "summary": ("summary", "reasoning", "explanation", "rationale", "analysis"),
    "cited_clause_ids": ("cited_clause_ids", "citations", "clause_ids", "cited_clauses"),
    "field_corrections": ("field_corrections", "corrected_fields", "corrections",
                          "recovered_fields"),
    "violations": ("violations", "contraventions", "findings", "non_compliances"),
    "checks": ("checks", "check_results", "verifications"),
    "analyst_note": ("analyst_note", "note", "notes", "analyst_notes"),
    "confidence": ("confidence", "confidence_score"),
}


def _parse_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response was not a JSON object")
    return _canonical_keys(parsed)


def _canonical_keys(parsed: dict[str, Any]) -> dict[str, Any]:
    """Map a provider's key naming onto the schema this module expects."""
    lowered = {str(k).lower(): v for k, v in parsed.items()}
    out = dict(parsed)
    for canonical, aliases in KEY_ALIASES.items():
        if canonical in parsed:
            continue
        for alias in aliases:
            if alias in lowered and lowered[alias] is not None:
                out[canonical] = lowered[alias]
                break

    # A verdict returned as a nested object ({"decision": {"verdict": ...}}).
    verdict = out.get("verdict")
    if isinstance(verdict, dict):
        for alias in KEY_ALIASES["verdict"]:
            if isinstance(verdict.get(alias), str):
                out["verdict"] = verdict[alias]
                break
    if isinstance(out.get("verdict"), str):
        out["verdict"] = out["verdict"].strip().lower().replace(" ", "_").replace("-", "_")
    return out


def _summary_for(parsed: dict[str, Any], decision: dict[str, Any]) -> str:
    """The model's narrative summary, or one built from its findings.

    Some providers return an empty `summary` even with a full violation list.
    A blank reasoning panel reads as a broken scan, so compose one instead.
    """
    summary = str(parsed.get("summary", "")).strip()
    if summary:
        return summary

    counts = decision["counts"]
    if not decision["violations"]:
        return (
            f"All {counts['checks_total']} mandatory declaration and physical checks "
            "passed against the retrieved Legal Metrology clauses."
        )
    headline = decision["violations"][0]
    return (
        f"{counts['total']} contravention(s) found across "
        f"{counts['checks_total']} checks. Most serious: {headline['message']}"
    )


def _clean_corrections(raw: Any, ocr_text: str) -> dict[str, Any]:
    """Keep only recognised fields whose value is traceable to the OCR text.

    A correction is the model telling us the extractor missed something. That is
    only trustworthy if the value is actually in the text the camera read, so any
    numeric value the model reports must appear there. This is what stops a
    recovered declaration from becoming an invented one.
    """
    # Strict schema mode returns [{"field": ..., "value": ...}]; json_object
    # mode usually returns a plain {field: value} map. Accept both.
    if isinstance(raw, list):
        raw = {
            item["field"]: item.get("value")
            for item in raw
            if isinstance(item, dict) and item.get("field")
        }
    if not isinstance(raw, dict):
        return {}

    digits_in_ocr = set(re.findall(r"\d+", ocr_text or ""))
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in CORRECTABLE_FIELDS or value in (None, "", []):
            continue
        claimed = re.findall(r"\d+", str(value))
        if claimed and not all(
            any(d == seen or d in seen for seen in digits_in_ocr) for d in claimed
        ):
            log.info("Rejected ungrounded field correction %s=%r", key, value)
            continue
        cleaned[key] = value
    return cleaned


def _score_from(violations: list[dict[str, Any]]) -> float:
    """Compliance score derived from the severity of the findings themselves.

    Uses the same weights as the deterministic engine so a score means the same
    thing whichever tier produced the verdict.
    """
    from .rule_engine import SEVERITY_WEIGHT

    penalty = sum(SEVERITY_WEIGHT.get(v["severity"], 10.0) for v in violations)
    return round(max(0.0, 100.0 - penalty), 1)


def _reconcile_verdict(verdict: str, violations: list[dict[str, Any]]) -> str:
    """Stop a verdict from contradicting the findings it was returned with.

    The model occasionally labels a scan `compliant` while listing a critical
    contravention. The findings are the evidence, so they win; the verdict is
    only tightened, never relaxed.
    """
    severities = {v["severity"] for v in violations}
    if severities & {"critical", "major"}:
        return "non_compliant" if verdict != "needs_review" else verdict
    if severities & {"minor"} and verdict == "compliant":
        return "partial"
    return verdict


def _normalise_decision(parsed: dict[str, Any],
                        clauses: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int]:
    """Validate the model's decision, salvaging what is grounded.

    Returns (decision, dropped_item_count). Items citing a clause that was not
    retrieved are dropped individually - they are ungrounded and cannot be
    verified - rather than invalidating the whole decision, which is what
    previously forced every scan onto the deterministic fallback.
    """
    retrieved = {c["clause_id"]: c for c in clauses}
    if parsed.get("verdict") not in ALLOWED_VERDICTS or not retrieved:
        return None, 0

    dropped = 0

    violations = []
    for item in parsed.get("violations", []):
        if not isinstance(item, dict):
            dropped += 1
            continue
        clause = retrieved.get(item.get("clause_id"))
        if clause is None:
            dropped += 1
            continue
        severity = item.get("severity")
        if severity not in ALLOWED_SEVERITIES:
            # Coerce rather than discard: the finding is grounded in a real
            # clause, only its label is malformed.
            severity = clause.get("severity", "major")
        violations.append({
            "field": str(item.get("field", "general")),
            "clause_id": clause["clause_id"],
            "rule_number": str(item.get("rule_number") or clause["rule_number"]),
            "title": str(item.get("title") or clause["title"]),
            "severity": severity,
            "message": str(item.get("message", "Compliance requirement not met.")),
            "observed": item.get("observed"),
            "expected": item.get("expected"),
        })

    checks = []
    for item in parsed.get("checks", []):
        if not isinstance(item, dict):
            dropped += 1
            continue
        clause = retrieved.get(item.get("clause_id"))
        if clause is None:
            dropped += 1
            continue
        checks.append({
            "name": str(item.get("name") or item.get("field") or "check"),
            "field": str(item.get("field", "general")),
            "clause_id": clause["clause_id"],
            "rule_number": str(item.get("rule_number") or clause["rule_number"]),
            "passed": bool(item.get("passed")),
            "detail": str(item.get("detail") or item.get("message", "")),
            "message": str(item.get("message", "")),
        })

    # Nothing grounded survived: there is no decision to report.
    if not violations and not checks:
        return None, dropped

    verdict = _reconcile_verdict(parsed["verdict"], violations)

    return {
        "verdict": verdict,
        # Scored from the model's own findings rather than from the number it
        # reports. Language models are unreliable arithmetic engines - this one
        # returned 0 alongside eleven passing checks - and a compliance score
        # that contradicts its violation list is indefensible to an inspector.
        "compliance_score": _score_from(violations),
        "violations": violations,
        "checks": checks,
        "counts": {
            "critical": sum(v["severity"] == "critical" for v in violations),
            "major": sum(v["severity"] == "major" for v in violations),
            "minor": sum(v["severity"] == "minor" for v in violations),
            "total": len(violations),
            "checks_passed": sum(c["passed"] for c in checks),
            "checks_total": len(checks),
        },
        "skipped_checks": [],
    }, dropped


def hallucination_assessment(parsed: dict[str, Any], engine: dict[str, Any],
                             clauses: list[dict[str, Any]], ocr_text: str = "",
                             fields: dict[str, Any] | None = None,
                             dropped: int = 0) -> tuple[float, dict[str, float]]:
    """Report grounding drift for transparency; it does not override the LLM label."""
    fields = fields or {}
    retrieved = {c["clause_id"] for c in clauses}
    cited = {c for c in parsed.get("cited_clause_ids", []) if c}
    citation_drift = len(cited - retrieved) / len(cited) if cited else 0.0

    claimed = set(re.findall(r"\b\d+(?:\.\d+)?\b", parsed.get("summary", "")))
    available = set(re.findall(r"\b\d+(?:\.\d+)?\b", ocr_text or ""))
    for value in fields.values():
        available.update(re.findall(r"\b\d+(?:\.\d+)?\b", str(value)))
    entity_drift = len(claimed - available) / len(claimed) if claimed else 0.0

    # The LLM disagreeing with the extractor-driven engine is the system working
    # as intended, so this is reported but weighted lightly.
    decision_drift = float(parsed.get("verdict") not in {None, engine.get("verdict")})

    total_items = len(parsed.get("violations", [])) + len(parsed.get("checks", []))
    grounding_drift = dropped / total_items if total_items else 0.0

    score = round(
        0.40 * citation_drift
        + 0.30 * min(1.0, entity_drift)
        + 0.20 * grounding_drift
        + 0.10 * decision_drift,
        4,
    )
    return score, {
        "citation_drift": round(citation_drift, 3),
        "entity_drift": round(min(1.0, entity_drift), 3),
        "grounding_drift": round(grounding_drift, 3),
        "decision_drift_vs_engine": round(decision_drift, 3),
    }


def _bounded_float(value: Any, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return low


def _fallback(engine: dict[str, Any], physical: dict[str, Any]) -> dict[str, Any]:
    counts = engine["counts"]
    violations = engine["violations"]
    if not violations:
        summary = f"All {counts['checks_total']} mandatory declaration and physical checks passed."
    else:
        headline = violations[0]
        summary = f"{counts['total']} contravention(s) detected. Most serious: {headline['message']}"
    if not physical.get("quality_ok", True):
        summary += f" Capture quality warning: {physical.get('quality_message')}"
    return {
        "decision": {**engine, "skipped_checks": engine.get("skipped_checks", [])},
        "reasoning": summary,
        "analyst_note": (
            "RAG-grounded LLM unavailable; this verdict comes from the deterministic "
            "rule engine, whose regex extractor can miss declarations that are "
            "present on the label. Treat absent-declaration findings as provisional."
        ),
        "field_corrections": {},
        "confidence": 0.72 if physical.get("quality_ok", True) else 0.4,
        "hallucination_coefficient": 0.0,
        "hallucination_breakdown": {},
        "bounded": True,
        "decision_source": "deterministic-fallback",
        "engine": "rag+rule-engine-fallback",
    }
