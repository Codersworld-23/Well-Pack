"""Scan-to-verdict orchestration.

    ingest -> quality gate -> OCR -> extraction -> physical analysis
           -> semantic cache -> RAG retrieval -> rule engine -> LLM narrative
           -> verdict, cached and logged
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import settings
from . import extractor, llm, ocr, rule_engine, vision
from .cache import cache
from .rag import store

log = logging.getLogger(__name__)


def run(image_path: str, *, db, use_cache: bool = True) -> dict[str, Any]:
    """Run the full pipeline over one label image."""
    started = time.perf_counter()

    # 1. Ingest and pre-process --------------------------------------------
    image = vision.load_image(image_path)
    quality = vision.capture_quality(image)

    # 2. OCR ----------------------------------------------------------------
    ocr_result = ocr.extract(image)
    text = ocr_result["text"]

    if not text.strip():
        return _empty_result(quality, ocr_result, started)

    # 3. Semantic cache ------------------------------------------------------
    if use_cache:
        cached = cache.lookup(text)
        if cached:
            return {
                **cached,
                "cache_hit": True,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "ocr_text": text,
            }

    # 4. Extraction + physical analysis --------------------------------------
    fields = extractor.extract_fields(text, ocr_result["regions"])
    physical = vision.analyse(image, ocr_result["regions"])
    physical.update(quality)

    # 5. RAG retrieval -------------------------------------------------------
    retrieval_query = _retrieval_query(fields, text)
    clauses = store.query(retrieval_query, top_k=settings.retrieval_top_k)

    # 6. Deterministic rule engine (the authority on the verdict) ------------
    engine = rule_engine.evaluate(fields, physical, text)

    # 7. LLM narrative, bounded against the engine ---------------------------
    analysis = llm.verify(fields, physical, clauses, engine, text)

    # 8. Assemble ------------------------------------------------------------
    confidence = round(
        min(1.0, ocr_result["confidence"] * 0.6 + analysis["confidence"] * 0.4), 3
    )

    result = {
        "verdict": engine["verdict"],
        "compliance_score": engine["compliance_score"],
        "violations": engine["violations"],
        "checks": engine["checks"],
        "counts": engine["counts"],
        "extracted_fields": fields,
        "physical_analysis": physical,
        "citations": [
            {
                "clause_id": c["clause_id"],
                "rule_number": c["rule_number"],
                "title": c["title"],
                "excerpt": c["text"][:320] + ("..." if len(c["text"]) > 320 else ""),
                "score": c["score"],
            }
            for c in clauses
        ],
        "product_name": fields.get("commodity_name"),
        "ocr_text": text,
        "ocr_confidence": ocr_result["confidence"],
        "reasoning": analysis["reasoning"],
        "analyst_note": analysis.get("analyst_note"),
        "confidence": confidence,
        "hallucination_coefficient": analysis["hallucination_coefficient"],
        "engine": f"{ocr_result['engine']}+{analysis['engine']}",
        "cache_hit": False,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "rule_corpus_version": store.version,
    }

    # 9. Cache for the next scan of this product -----------------------------
    if use_cache:
        cacheable = {k: v for k, v in result.items() if k != "latency_ms"}
        try:
            cache.store(db, text, cacheable)
        except Exception as exc:  # caching must never fail a scan
            log.warning("Cache store failed: %s", exc)

    return result


def _retrieval_query(fields: dict[str, Any], text: str) -> str:
    """Query the vector store with the declarations actually present, plus the
    names of the ones that are missing - absent declarations are exactly what
    the retrieved clauses need to cover."""
    present = [f"{k} {v}" for k, v in fields.items() if isinstance(v, (str, int, float))]
    missing = [
        name for name in
        ("manufacturer", "net_quantity", "mrp", "manufacture_date", "consumer_care")
        if not fields.get(name)
    ]
    parts = present + [f"missing {m} declaration" for m in missing]
    return " ".join(parts)[:2000] or text[:2000]


def _empty_result(quality: dict[str, Any], ocr_result: dict[str, Any],
                  started: float) -> dict[str, Any]:
    message = (
        quality.get("quality_message")
        or "No text could be read from this image. Capture the label panel straight on, "
        "filling the frame, in even light."
    )
    return {
        "verdict": "needs_review",
        "compliance_score": 0.0,
        "violations": [],
        "checks": [],
        "counts": {"critical": 0, "major": 0, "minor": 0, "total": 0,
                   "checks_passed": 0, "checks_total": 0},
        "extracted_fields": {},
        "physical_analysis": {**quality, "text_regions": 0},
        "citations": [],
        "product_name": None,
        "ocr_text": "",
        "ocr_confidence": 0.0,
        "reasoning": message,
        "analyst_note": None,
        "confidence": 0.0,
        "hallucination_coefficient": 0.0,
        "engine": ocr_result.get("engine", "none"),
        "cache_hit": False,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
