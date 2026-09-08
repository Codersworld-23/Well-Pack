"""Seed the rule corpus and the default admin accounts."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .data.legal_metrology import SEED_CLAUSES
from .models import RuleClause, User
from .routers.auth import hash_password

log = logging.getLogger(__name__)

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


def run(db: Session) -> dict[str, int]:
    return {"clauses": seed_clauses(db), "users": seed_users(db)}
