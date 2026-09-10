"""Seed the rule corpus and the default admin accounts."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from .data.legal_metrology import SEED_CLAUSES
from .models import RuleClause, User
from .routers.auth import hash_password

log = logging.getLogger(__name__)

# Resolve the dataset directory relative to this file (backend/app/seed.py -> dataset/)
_DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "dataset"

DEFAULT_USERS = [
    ("admin@wellpack.gov.in", "Legal Metrology Admin", "admin", "wellpack2026"),
    ("inspector@wellpack.gov.in", "Field Inspector", "inspector", "inspect2026"),
]


def seed_clauses(db: Session) -> int:
    created = 0
    for clause in SEED_CLAUSES:
        exists = db.query(RuleClause).filter(
            RuleClause.clause_id == clause["clause_id"]
        ).first()
        if exists:
            continue
        db.add(RuleClause(source="seed", **clause))
        created += 1
    if created:
        db.commit()
        log.info("Seeded %d Legal Metrology clauses", created)
    return created


def seed_users(db: Session) -> int:
    created = 0
    for email, name, role, password in DEFAULT_USERS:
        if db.query(User).filter(User.email == email).first():
            continue
        db.add(User(email=email, name=name, role=role,
                    password_hash=hash_password(password)))
        created += 1
    if created:
        db.commit()
        log.info("Seeded %d users", created)
    return created


def seed_pdfs(db: Session) -> int:
    """Ingest every PDF in the dataset folder that has not been loaded yet.

    Uses the same parser as POST /api/rules/upload. Clauses are skipped if
    their clause_id already exists, so this is safe to call on every boot.
    """
    from .services.pdf_ingest import ingest_pdf_file

    if not _DATASET_DIR.exists():
        log.warning("seed_pdfs: dataset directory not found at %s", _DATASET_DIR)
        return 0

    pdfs = sorted(_DATASET_DIR.glob("*.pdf"))
    if not pdfs:
        log.info("seed_pdfs: no PDFs found in %s", _DATASET_DIR)
        return 0

    total = 0
    for pdf in pdfs:
        try:
            created = ingest_pdf_file(pdf, db)
            if created:
                log.info("seed_pdfs: ingested %d clause(s) from %s", created, pdf.name)
        except Exception as exc:  # noqa: BLE001
            log.warning("seed_pdfs: could not ingest %s: %s", pdf.name, exc)
            db.rollback()  # reset session so subsequent PDFs and reindex_from_db work
            created = 0
        total += created
    return total


def run(db: Session) -> dict[str, int]:
    return {
        "clauses": seed_clauses(db),
        "users": seed_users(db),
        "pdf_clauses": seed_pdfs(db),
    }
