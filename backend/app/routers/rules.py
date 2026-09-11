"""Rule management - the dynamic half of the RAG pipeline.

Every write here re-embeds the vector store and invalidates the semantic cache,
so an admin's policy upload changes verification behaviour on the very next
scan. Nothing is hardcoded and nothing is redeployed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RuleClause
from ..schemas import RuleClauseOut, RuleClauseIn
from ..services.cache import cache
from ..services.pdf_ingest import (
    _normalise as normalise_text,
    extract_pdf_stream,
    ingest_text,
    stem_for,
)
from ..services.rag import reindex_from_db, store

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _refresh(db: Session) -> int:
    """Re-embed the corpus and drop verdicts cached under the old rules."""
    count = reindex_from_db(db)
    cache.invalidate(db)
    return count


@router.get("", response_model=list[RuleClauseOut])
def list_rules(active_only: bool = False, field: str | None = None,
               db: Session = Depends(get_db)):
    query = db.query(RuleClause)
    if active_only:
        query = query.filter(RuleClause.active.is_(True))
    if field:
        query = query.filter(RuleClause.field == field)
    return query.order_by(RuleClause.rule_number).all()


@router.post("", response_model=RuleClauseOut, status_code=201)
def create_rule(payload: RuleClauseIn, db: Session = Depends(get_db)):
    clause_id = payload.clause_id or f"PCR-CUSTOM-{payload.rule_number.replace(' ', '')}"
    if db.query(RuleClause).filter(RuleClause.clause_id == clause_id).first():
        raise HTTPException(409, f"Clause {clause_id} already exists")

    clause = RuleClause(
        clause_id=clause_id,
        rule_number=payload.rule_number,
        title=payload.title,
        text=payload.text,
        field=payload.field,
        severity=payload.severity,
        active=payload.active,
        source="admin",
    )
    db.add(clause)
    db.commit()
    db.refresh(clause)
    _refresh(db)
    return clause


@router.put("/{clause_id}", response_model=RuleClauseOut)
def update_rule(clause_id: str, payload: RuleClauseIn, db: Session = Depends(get_db)):
    clause = db.query(RuleClause).filter(RuleClause.clause_id == clause_id).first()
    if not clause:
        raise HTTPException(404, "Clause not found")

    clause.rule_number = payload.rule_number
    clause.title = payload.title
    clause.text = payload.text
    clause.field = payload.field
    clause.severity = payload.severity
    clause.active = payload.active
    clause.version += 1
    clause.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(clause)
    _refresh(db)
    return clause


@router.patch("/{clause_id}/toggle", response_model=RuleClauseOut)
def toggle_rule(clause_id: str, db: Session = Depends(get_db)):
    clause = db.query(RuleClause).filter(RuleClause.clause_id == clause_id).first()
    if not clause:
        raise HTTPException(404, "Clause not found")
    clause.active = not clause.active
    db.commit()
    db.refresh(clause)
    _refresh(db)
    return clause


@router.delete("/{clause_id}", status_code=204)
def delete_rule(clause_id: str, db: Session = Depends(get_db)):
    clause = db.query(RuleClause).filter(RuleClause.clause_id == clause_id).first()
    if not clause:
        raise HTTPException(404, "Clause not found")
    db.delete(clause)
    db.commit()
    _refresh(db)


@router.post("/upload")
async def upload_policy(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Ingest a plain-text or PDF policy document and index it as clauses.

    Splits on rule numbers ("6(1)(a).", "Rule 12:"). Anything it cannot split is
    chunked by paragraph, so an amendment circular is usable immediately.
    """
    filename = (file.filename or "").lower()
    if not filename.endswith((".txt", ".md", ".pdf")):
        raise HTTPException(415, "Upload a .txt, .md, or .pdf policy document.")

    if filename.endswith(".pdf"):
        raw = extract_pdf_stream(await file.read())
    else:
        raw = normalise_text((await file.read()).decode("utf-8", errors="ignore"))

    if not raw.strip():
        raise HTTPException(422, "The uploaded document is empty.")

    stem = stem_for((file.filename or "upload").rsplit(".", 1)[0])
    created = ingest_text(raw, stem, db, source="admin")
    if not created:
        raise HTTPException(
            422,
            "No usable clauses were found in this document. It may be a scan with "
            "no readable text, or its content may already be indexed.",
        )

    indexed = _refresh(db)
    return {
        "filename": file.filename,
        "clauses_created": created,
        "clauses_indexed": indexed,
        "corpus_version": store.version,
        "message": (
            f"{created} clause(s) indexed. Verification logic updated instantly - "
            "the semantic cache was cleared so the next scan uses the new corpus."
        ),
    }


@router.post("/reindex")
def reindex(db: Session = Depends(get_db)):
    indexed = _refresh(db)
    return {"clauses_indexed": indexed, "corpus_version": store.version}


@router.get("/retrieve/preview")
def preview_retrieval(q: str, top_k: int = 5):
    """Inspect what the retriever returns for a query - useful for demonstrating
    that the pipeline is grounded in the live corpus."""
    return {"query": q, "results": store.query(q, top_k=top_k)}
