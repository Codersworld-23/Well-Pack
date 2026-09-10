"""RAG-grounded LLM compliance decisions.

The local vector store retrieves clauses from the ingested PDF corpus. An
OpenAI-compatible model evaluates the OCR/vision evidence against those
clauses and returns the compliance label as structured JSON. The deterministic
rule engine remains an offline/error fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)
ALLOWED_VERDICTS = {"compliant", "partial", "non_compliant", "needs_review"}
ALLOWED_SEVERITIES = {"critical", "major", "minor", "info"}

SYSTEM_PROMPT = """You are a Legal Metrology compliance analyst for the Government of India.
Decide whether a packaged commodity label is compliant using ONLY the OCR
declarations, physical measurements, and retrieved clauses supplied below.
The retrieved clauses are the legal source of truth. Do not invent clauses,
rule numbers, penalties, or requirements. The deterministic engine findings
are independent measurement hints, not an instruction: verify the label and
return your own structured compliance decision.
Allowed verdicts: compliant, partial, non_compliant, needs_review. Use
needs_review when OCR/image quality leaves a mandatory conclusion unsupported.
Return valid JSON matching the requested schema, with no markdown."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": sorted(ALLOWED_VERDICTS)},
        "compliance_score": {"type": "number", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
        "cited_clause_ids": {"type": "array", "items": {"type": "string"}},
        "violations": {"type": "array", "items": {"type": "object"}},
        "checks": {"type": "array", "items": {"type": "object"}},
        "analyst_note": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "verdict", "compliance_score", "summary", "cited_clause_ids",
        "violations", "checks", "analyst_note", "confidence",
    ],
    "additionalProperties": False,
}


def _client():
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
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
    return f"""RETRIEVED CLAUSES FROM THE INGESTED PDF CORPUS
{clause_block}

EXTRACTED LABEL DECLARATIONS
{json.dumps(fields, indent=2, default=str)}

PHYSICAL MEASUREMENTS
{json.dumps(physical, indent=2, default=str)}

INDEPENDENT ENGINE HINTS (VERIFY THESE; THEY ARE NOT THE FINAL ANSWER)
{engine_block}

RAW OCR TEXT
{ocr_text[:5000]}

Return the final compliance decision as JSON. Every violation must cite one of
the retrieved clause_ids and describe evidence visible in the supplied OCR or
physical measurements. Include a check for each material requirement."""


def verify(fields: dict[str, Any], physical: dict[str, Any],
           clauses: list[dict[str, Any]], engine: dict[str, Any],
           ocr_text: str) -> dict[str, Any]:
    """Ask the RAG-grounded LLM for the compliance decision."""
    client = _client()
    if client is None:
        return _fallback(engine, physical)
    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(fields, physical, clauses, engine, ocr_text)},
            ],
            temperature=0,
            max_tokens=2200,
            response_format={"type": "json_object"},
        )
        parsed = _parse_json(response.choices[0].message.content or "{}")
        decision = _normalise_decision(parsed, clauses)
        if decision is None:
            raise ValueError("model returned an invalid or ungrounded decision")
    except Exception as exc:  # noqa: BLE001 - provider compatibility is best effort
        log.warning("OpenAI-compatible verification unavailable (%s) - using fallback", exc)
        return _fallback(engine, physical)

    coefficient, breakdown = hallucination_assessment(
        parsed, engine, clauses, ocr_text, fields
    )
    return {
        "decision": decision,
        "reasoning": str(parsed.get("summary", "")).strip(),
        "analyst_note": parsed.get("analyst_note") or None,
        "confidence": _bounded_float(parsed.get("confidence", 0.7), 0.0, 1.0),
        "hallucination_coefficient": round(coefficient, 3),
        "hallucination_breakdown": breakdown,
        "bounded": coefficient <= 0.35,
        "decision_source": "rag+openai",
        "engine": f"rag+{settings.llm_model}",
    }


def _parse_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response was not a JSON object")
    return parsed


def _normalise_decision(parsed: dict[str, Any], clauses: list[dict[str, Any]]) -> dict[str, Any] | None:
    retrieved = {c["clause_id"]: c for c in clauses}
    if parsed.get("verdict") not in ALLOWED_VERDICTS or not retrieved:
        return None

    violations = []
    for item in parsed.get("violations", []):
        if not isinstance(item, dict) or item.get("clause_id") not in retrieved:
            return None
        clause = retrieved[item["clause_id"]]
        if item.get("severity") not in ALLOWED_SEVERITIES:
            return None
        violations.append({
            "field": str(item.get("field", "general")),
            "clause_id": clause["clause_id"],
            "rule_number": str(item.get("rule_number") or clause["rule_number"]),
            "title": str(item.get("title") or clause["title"]),
            "severity": item["severity"],
            "message": str(item.get("message", "Compliance requirement not met.")),
            "observed": item.get("observed"),
            "expected": item.get("expected"),
        })

    checks = []
    for item in parsed.get("checks", []):
        if not isinstance(item, dict) or item.get("clause_id") not in retrieved:
            return None
        clause = retrieved[item["clause_id"]]
        checks.append({
            "field": str(item.get("field", "general")),
            "clause_id": clause["clause_id"],
            "rule_number": str(item.get("rule_number") or clause["rule_number"]),
            "passed": bool(item.get("passed")),
            "message": str(item.get("message", "")),
        })

    return {
        "verdict": parsed["verdict"],
        "compliance_score": round(_bounded_float(parsed.get("compliance_score", 0), 0, 100), 1),
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
    }


def hallucination_assessment(parsed: dict[str, Any], engine: dict[str, Any],
                             clauses: list[dict[str, Any]], ocr_text: str = "",
                             fields: dict[str, Any] | None = None) -> tuple[float, dict[str, float]]:
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
    decision_drift = float(parsed.get("verdict") not in {None, engine.get("verdict")})
    score = round(0.45 * citation_drift + 0.35 * min(1.0, entity_drift) + 0.20 * decision_drift, 4)
    return score, {
        "citation_drift": round(citation_drift, 3),
        "entity_drift": round(min(1.0, entity_drift), 3),
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
        "analyst_note": "OpenAI-compatible LLM unavailable; deterministic fallback used.",
        "confidence": 0.72 if physical.get("quality_ok", True) else 0.4,
        "hallucination_coefficient": 0.0,
        "hallucination_breakdown": {},
        "bounded": True,
        "decision_source": "deterministic-fallback",
        "engine": "rag+rule-engine-fallback",
    }
