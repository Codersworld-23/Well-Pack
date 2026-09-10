"""Structured data tier - scans, verdicts, rule clauses, citizen reports, users."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Scan(Base):
    """One label scan and its compliance verdict."""

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="consumer")  # consumer|inspector|api
    scanned_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Verdict
    status: Mapped[str] = mapped_column(String(16), default="processing", index=True)
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    compliance_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    hallucination_coefficient: Mapped[float] = mapped_column(Float, default=0.0)

    # Payloads
    product_name: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    physical_analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    violations: Mapped[list] = mapped_column(JSON, default=list)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Telemetry
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    @property
    def hallucination_breakdown(self) -> dict:
        return (self.physical_analysis or {}).get("hallucination_breakdown", {})

    reports: Mapped[list["Report"]] = relationship(back_populates="scan")


class RuleClause(Base):
    """A Legal Metrology clause in the RAG corpus. Admin-editable at runtime."""

    __tablename__ = "rule_clauses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    clause_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    rule_number: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text)
    field: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="major")
    source: Mapped[str] = mapped_column(String(32), default="seed")  # seed|admin
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Report(Base):
    """A citizen or inspector report of a non-compliant product."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    scan_id: Mapped[str | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reporter_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reporter_contact: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retailer: Mapped[str | None] = mapped_column(String(256), nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="labelling")
    description: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    scan: Mapped["Scan | None"] = relationship(back_populates="reports")


class User(Base):
    """Admin portal users - inspectors and Legal Metrology officers."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(24), default="inspector")  # admin|inspector
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CacheEntry(Base):
    """Persisted semantic cache so warm results survive a restart."""

    __tablename__ = "cache_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
