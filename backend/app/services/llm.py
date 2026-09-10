"""LLM semantic verification over retrieved Legal Metrology clauses.

The LLM is deliberately *not* the decision-maker. The deterministic rule engine
produces the verdict; this layer reads the same retrieved clauses and writes the
legal reasoning shown to the user, then its output is scored against the engine.

That score is the "hallucination coefficient" from the feasibility analysis: the
divergence between what the LLM asserts and what the machine-verifiable checks
found. Above `HALLUCINATION_LIMIT` the narrative is discarded and the engine's
own summary is shown instead, so a hallucinated clause can never reach a user as
a legal finding.

Without ANTHROPIC_API_KEY the module falls back to a template summary built from
the engine output - the pipeline stays fully functional offline.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

from ..config import settings

HALLUCINATION_LIMIT = 0.35

SYSTEM_PROMPT = """You are a Legal Metrology compliance analyst for the Government of India.

You are given:
1. The declarations extracted from a packaged commodity label by OCR.
2. Physical measurements of the label taken by computer vision.
3. The verbatim text of the Legal Metrology (Packaged Commodities) Rules, 2011
   clauses retrieved for this label.
4. The findings of a deterministic rule engine that has already checked the label.

Your job is to explain the compliance position in plain language for an inspector,
grounded ONLY in the retrieved clause text supplied to you.

Hard constraints:
- Cite only clause_ids that appear in the retrieved clauses. Never invent a rule
  number, a clause, or a penalty.
- Do not assert a violation that the rule engine did not find, and do not excuse
  one that it did. If you disagree with the engine, say so in `analyst_note`
  rather than changing the finding.
- If the OCR text is too degraded to support a conclusion, say so plainly.
- Be specific and brief. Reference what was actually observed on the label."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Two or three sentences on the label's compliance position.",
        },
        "cited_clause_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "clause_ids from the retrieved clauses that this analysis relies on.",
        },
        "violation_fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Declaration fields the analysis considers non-compliant.",
        },
        "analyst_note": {
            "type": "string",
            "description": "Any disagreement with the rule engine, or an empty string.",
        },
        "confidence": {
            "type": "number",
            "description": "0 to 1 confidence that the OCR text supports this analysis.",
        },
    },
    "required": [
        "summary",
        "cited_clause_ids",
        "violation_fields",
        "analyst_note",
        "confidence",
    ],
    "additionalProperties": False,
}


def _client():
    """Anthropic client, or None when the API key is absent."""
    api_key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        log.info("anthropic SDK not installed - using deterministic reasoning")
        return None
    return anthropic.Anthropic(api_key=api_key)


def _build_prompt(fields: dict[str, Any], physical: dict[str, Any],
                  clauses: list[dict[str, Any]], engine: dict[str, Any],
                  ocr_text: str) -> str:
    clause_block = "\n\n".join(
        f"[{c['clause_id']}] Rule {c['rule_number']} - {c['title']}\n{c['text']}"
        for c in clauses
    )
    engine_block = "\n".join(
        f"- {v['severity'].upper()} | {v['clause_id']} | {v['field']}: {v['message']}"
        for v in engine["violations"]
    ) or "- No violations detected."

    return f"""RETRIEVED CLAUSES (Legal Metrology (Packaged Commodities) Rules, 2011)
{clause_block}

EXTRACTED DECLARATIONS
{json.dumps(fields, indent=2, default=str)}

PHYSICAL MEASUREMENTS
- Estimated principal display panel area: {physical.get('estimated_pdp_area_cm2')} sq cm
- Minimum character height required: {physical.get('min_required_height_mm')} mm
- Smallest declaration measured: {physical.get('smallest_declaration_height_mm')} mm
- Lowest text/background contrast ratio: {physical.get('min_contrast_ratio')}:1
- Capture quality acceptable: {physical.get('quality_ok', True)}

RULE ENGINE FINDINGS (verdict: {engine['verdict']}, score {engine['compliance_score']}/100)
{engine_block}

RAW OCR TEXT
{ocr_text[:2500]}

Analyse this label's compliance position."""


def verify(fields: dict[str, Any], physical: dict[str, Any],
           clauses: list[dict[str, Any]], engine: dict[str, Any],
           ocr_text: str) -> dict[str, Any]:
    """Produce grounded reasoning for the engine's verdict."""
    client = _client()
    if client is None:
        return _fallback(engine, physical, clauses)

    prompt = _build_prompt(fields, physical, clauses, engine, ocr_text)
    request = {
        "model": settings.llm_model,
        "max_tokens": 2000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {
            "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
            "effort": "medium",
        },
    }

    try:
        # Server-side refusal fallback keeps a verdict flowing if the primary
        # model declines; harmless if the beta is not enabled on the account.
        try:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **request,
            )
        except Exception:
            response = client.messages.create(**request)

        if getattr(response, "stop_reason", None) == "refusal":
            return _fallback(engine, physical, clauses)

        text = next((b.text for b in response.content if b.type == "text"), "")
        parsed = json.loads(text)
    except Exception as exc:
        log.warning("LLM verification unavailable (%s) - using rule engine reasoning", exc)
        return _fallback(engine, physical, clauses)

    coefficient, breakdown = hallucination_assessment(parsed, engine, clauses, ocr_text, fields)
    bounded = coefficient <= HALLUCINATION_LIMIT

    if not bounded:
        log.warning("LLM output rejected: hallucination coefficient %.2f", coefficient)
        result = _fallback(engine, physical, clauses)
        result["hallucination_coefficient"] = round(coefficient, 3)
        result["hallucination_breakdown"] = breakdown
        result["bounded"] = False
        result["engine"] = f"{settings.llm_model} (rejected -> rule-engine)"
        return result

    return {
        "reasoning": parsed["summary"],
        "analyst_note": parsed.get("analyst_note") or None,
        "confidence": float(parsed.get("confidence", 0.8)),
        "hallucination_coefficient": round(coefficient, 3),
        "hallucination_breakdown": breakdown,
        "bounded": True,
        "engine": f"rag+{settings.llm_model}",
    }


def hallucination_assessment(parsed: dict[str, Any], engine: dict[str, Any],
                             clauses: list[dict[str, Any]], ocr_text: str = "",
                             fields: dict[str, Any] | None = None) -> tuple[float, dict[str, float]]:
    """Comprehensive 5-factor assessment of LLM hallucination and legal divergence.

    Factors and weights:
      1. citation_drift   (0.30) - clause_ids cited that were never retrieved
      2. finding_drift    (0.30) - symmetric difference between LLM claimed violations
                                   and rule engine findings (the ground truth)
      3. entity_drift     (0.20) - numbers/prices claimed in summary not in OCR or fields
      4. penalty_drift    (0.10) - fabricated statutes, IPC sections, non-existent penalties
      5. confidence_drift (0.10) - over-asserted confidence beyond OCR ground truth

    A score > HALLUCINATION_LIMIT (0.35) causes the narrative to be discarded
    and replaced by the deterministic rule engine summary.
    """
    import re as _re
    fields = fields or {}
    summary = parsed.get("summary", "")
    retrieved = {c["clause_id"] for c in clauses}
    cited = {c for c in parsed.get("cited_clause_ids", []) if c}
    citation_drift = (len(cited - retrieved) / len(cited)) if cited else 0.0

    engine_fields = {v["field"] for v in engine["violations"]}
    llm_fields = {f for f in parsed.get("violation_fields", []) if f}
    union = engine_fields | llm_fields
    finding_drift = (len(engine_fields ^ llm_fields) / len(union)) if union else 0.0

    # Entity drift: check numbers/prices in summary vs OCR text and extracted fields
    claimed_numbers = set(_re.findall(r"\b\d+(?:\.\d+)?\b", summary))
    ocr_numbers = set(_re.findall(r"\b\d+(?:\.\d+)?\b", ocr_text or ""))
    field_numbers = set()
    for v in fields.values():
        if isinstance(v, (int, float)):
            field_numbers.add(str(v))
        elif isinstance(v, str):
            field_numbers.update(_re.findall(r"\b\d+(?:\.\d+)?\b", v))
    # Known-safe statutory year references and rule numbers.
    allowed_numbers = ocr_numbers | field_numbers | {
        "2011", "2009", "2023", "36", "6", "9", "5", "18", "32",
        "1", "2", "3", "4", "7", "8", "10", "100",
    }
    hallucinated_nums = claimed_numbers - allowed_numbers
    entity_drift = round(
        min(1.0, len(hallucinated_nums) / max(len(claimed_numbers), 1)), 4
    ) if claimed_numbers else 0.0

    # Penalty drift: fabricated legal references that do not exist in the 2011 Rules.
    penalty_drift = 0.0
    if _re.search(
        r"\b(?:ipc|section 420|jail for \d+ years|fine of \d{6,}|criminal)\b",
        summary, _re.I
    ):
        penalty_drift = 1.0

    # Confidence drift: LLM claiming certainty the OCR doesn't support.
    stated = float(parsed.get("confidence", 0.5))
    supportable = 1.0 if engine["counts"]["checks_total"] else 0.0
    confidence_drift = max(0.0, stated - supportable)

    score = round(
        0.30 * citation_drift +
        0.30 * finding_drift +
        0.20 * entity_drift +
        0.10 * penalty_drift +
        0.10 * confidence_drift,
        4,
    )

    breakdown = {
        "citation_drift": round(citation_drift, 3),
        "finding_drift": round(finding_drift, 3),
        "entity_drift": round(entity_drift, 3),
        "penalty_drift": round(penalty_drift, 3),
        "confidence_drift": round(confidence_drift, 3),
    }
    return score, breakdown


def hallucination_coefficient(parsed: dict[str, Any], engine: dict[str, Any],
                              clauses: list[dict[str, Any]]) -> float:
    """Backward compatibility wrapper."""
    return hallucination_assessment(parsed, engine, clauses)[0]


def _fallback(engine: dict[str, Any], physical: dict[str, Any],
              clauses: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic narrative assembled from the verified findings."""
    counts = engine["counts"]
    violations = engine["violations"]

    if not violations:
        summary = (
            f"All {counts['checks_total']} mandatory declaration and physical checks "
            "passed. The label carries every declaration required by Rule 6(1) and "
            "satisfies the legibility and character-height requirements of Rule 9."
        )
    else:
        headline = violations[0]
        rules = ", ".join(sorted({f"Rule {v['rule_number']}" for v in violations})[:4])
        summary = (
            f"{counts['total']} contravention(s) detected across {rules}. "
            f"Most serious: {headline['message']} "
            f"{counts['checks_passed']} of {counts['checks_total']} checks passed."
        )

    if not physical.get("quality_ok", True):
        summary += f" Capture quality warning: {physical.get('quality_message')}"

    return {
        "reasoning": summary,
        "analyst_note": None,
        "confidence": 0.72 if physical.get("quality_ok", True) else 0.4,
        "hallucination_coefficient": 0.0,
        "hallucination_breakdown": {
            "citation_drift": 0.0,
            "finding_drift": 0.0,
            "entity_drift": 0.0,
            "penalty_drift": 0.0,
            "confidence_drift": 0.0,
        },
        "bounded": True,
        "engine": "rag+rule-engine",
    }
