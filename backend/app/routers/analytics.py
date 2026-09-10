"""Admin analytics over the logged scan and report data."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RuleClause, Report, Scan
from ..schemas import AnalyticsOut
from ..services.cache import cache
from ..services.rag import store

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsOut)
def analytics(days: int = 30, db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    scans = db.query(Scan).filter(Scan.created_at >= since).all()
    total = len(scans)

    compliant = sum(1 for s in scans if s.verdict == "compliant")
    non_compliant = sum(1 for s in scans if s.verdict == "non_compliant")
    partial = sum(1 for s in scans if s.verdict == "partial")
    needs_review = sum(1 for s in scans if s.verdict == "needs_review")

    # Violation frequency by clause - what regulators act on.
    violation_counter: Counter[tuple[str, str, str]] = Counter()
    severity_counter: Counter[str] = Counter()
    for scan in scans:
        for violation in scan.violations or []:
            violation_counter[(
                violation.get("clause_id", "?"),
                violation.get("rule_number", "?"),
                violation.get("title", "Unknown"),
            )] += 1
            severity_counter[violation.get("severity", "major")] += 1

    top_violations = [
        {"clause_id": cid, "rule_number": rule, "title": title, "count": count}
        for (cid, rule, title), count in violation_counter.most_common(8)
    ]

    # Daily scan volume with compliance split.
    by_day: dict[str, dict[str, int]] = {}
    for offset in range(days - 1, -1, -1):
        key = (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%d")
        by_day[key] = {"date": key, "scans": 0, "compliant": 0, "non_compliant": 0}
    for scan in scans:
        key = scan.created_at.strftime("%Y-%m-%d")
        if key in by_day:
            by_day[key]["scans"] += 1
            if scan.verdict == "compliant":
                by_day[key]["compliant"] += 1
            elif scan.verdict == "non_compliant":
                by_day[key]["non_compliant"] += 1

    latencies = [s.latency_ms for s in scans if s.latency_ms]
    cache_hits = sum(1 for s in scans if s.cache_hit)

    return AnalyticsOut(
        total_scans=total,
        compliant=compliant,
        non_compliant=non_compliant,
        needs_review=needs_review + partial,
        compliance_rate=round(compliant / total * 100, 1) if total else 0.0,
        avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        cache_hit_rate=round(cache_hits / total * 100, 1) if total else 0.0,
        open_reports=db.query(Report).filter(Report.status == "open").count(),
        total_reports=db.query(Report).count(),
        active_clauses=db.query(RuleClause).filter(RuleClause.active.is_(True)).count(),
        top_violations=top_violations,
        scans_by_day=list(by_day.values()),
        verdict_split=[
            {"verdict": "compliant", "count": compliant},
            {"verdict": "partial", "count": partial},
            {"verdict": "non_compliant", "count": non_compliant},
            {"verdict": "needs_review", "count": needs_review},
        ],
        severity_split=[
            {"severity": key, "count": severity_counter.get(key, 0)}
            for key in ("critical", "major", "minor")
        ],
    )


@router.get("/system")
def system_status(db: Session = Depends(get_db)):
    """Live view of the RAG corpus and semantic cache - shown on the dashboard."""
    from ..services import ocr
    from ..config import settings

    return {
        "vector_store": {
            "clauses_indexed": store.size,
            "corpus_version": store.version,
            "embedding_dim": settings.embedding_dim,
            "backend": "pinecone" if settings.pinecone_api_key else "in-process",
        },
        "semantic_cache": {
            "entries": cache.size,
            "hits": cache.hits,
            "misses": cache.misses,
            "hit_rate": cache.hit_rate,
            "threshold": settings.cache_similarity_threshold,
            "backend": "redis" if settings.redis_url else "in-process+db",
        },
        "ocr_engine": ocr.engine_name(),
        "llm": {
            "model": settings.llm_model,
            "configured": bool(settings.openai_api_key),
            "endpoint": settings.openai_base_url,
            "mode": "rag+llm" if settings.openai_api_key else "rag+rule-engine-fallback",
        },
        "database": settings.database_url.split("://")[0],
        "totals": {
            "scans": db.query(func.count(Scan.id)).scalar() or 0,
            "reports": db.query(func.count(Report.id)).scalar() or 0,
            "clauses": db.query(func.count(RuleClause.id)).scalar() or 0,
        },
    }
