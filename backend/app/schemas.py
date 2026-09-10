"""Pydantic contracts for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Violation(BaseModel):
    field: str
    clause_id: str
    rule_number: str
    title: str
    severity: Literal["critical", "major", "minor", "info"]
    message: str
    observed: str | None = None
    expected: str | None = None


class Citation(BaseModel):
    clause_id: str
    rule_number: str
    title: str
    excerpt: str
    score: float


class ExtractedFields(BaseModel):
    manufacturer: str | None = None
    commodity_name: str | None = None
    net_quantity: str | None = None
    net_quantity_value: float | None = None
    net_quantity_unit: str | None = None
    mrp: str | None = None
    mrp_value: float | None = None
    manufacture_date: str | None = None
    expiry_date: str | None = None
    consumer_care: str | None = None
    country_of_origin: str | None = None
    fssai_licence: str | None = None
    batch_number: str | None = None


class PhysicalAnalysis(BaseModel):
    blur_score: float = 0.0
    is_blurry: bool = False
    glare_ratio: float = 0.0
    has_glare: bool = False
    image_width: int = 0
    image_height: int = 0
    estimated_pdp_area_cm2: float = 0.0
    min_required_height_mm: float = 0.0
    smallest_declaration_height_mm: float = 0.0
    undersized_declarations: list[dict[str, Any]] = Field(default_factory=list)
    min_contrast_ratio: float = 0.0
    low_contrast_declarations: list[dict[str, Any]] = Field(default_factory=list)
    text_regions: int = 0
    orb_keypoints: int = 0
    feature_richness: str = "unknown"
    uncertain_regions: list[str] = Field(default_factory=list)
    uncertain_region_count: int = 0
    ocr_preprocessed: bool = False
    quality_ok: bool = True
    quality_message: str | None = None


class ScanResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    status: str
    verdict: str | None = None
    compliance_score: float = 0.0
    confidence: float = 0.0
    ocr_confidence: float = 0.0
    hallucination_coefficient: float = 0.0
    hallucination_breakdown: dict[str, float] = Field(default_factory=dict)
    product_name: str | None = None
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    physical_analysis: dict[str, Any] = Field(default_factory=dict)
    violations: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    skipped_checks: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    ocr_text: str | None = None
    reasoning: str | None = None
    analyst_note: str | None = None
    cache_hit: bool = False
    engine: str | None = None
    latency_ms: int = 0
    image_url: str | None = None
    source: str = "consumer"
    rule_corpus_version: int | None = None


class ScanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    product_name: str | None = None
    verdict: str | None = None
    status: str
    compliance_score: float
    source: str
    cache_hit: bool
    latency_ms: int
    violation_count: int = 0
    image_url: str | None = None


class RuleClauseIn(BaseModel):
    clause_id: str | None = None
    rule_number: str
    title: str
    text: str
    field: str = "general"
    severity: Literal["critical", "major", "minor", "info"] = "major"
    active: bool = True


class RuleClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    clause_id: str
    rule_number: str
    title: str
    text: str
    field: str
    severity: str
    source: str
    active: bool
    version: int
    updated_at: datetime


class ReportIn(BaseModel):
    scan_id: str | None = None
    product_name: str | None = None
    reporter_name: str | None = None
    reporter_contact: str | None = None
    retailer: str | None = None
    location: str | None = None
    category: str = "labelling"
    description: str = ""


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    scan_id: str | None
    product_name: str | None
    reporter_name: str | None
    reporter_contact: str | None
    retailer: str | None
    location: str | None
    category: str
    description: str
    status: str
    priority: str
    resolution_note: str | None
    updated_at: datetime


class ReportUpdate(BaseModel):
    status: Literal["open", "under_review", "action_taken", "dismissed"] | None = None
    priority: Literal["low", "medium", "high"] | None = None
    resolution_note: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    name: str
    role: str
    email: str


class AnalyticsOut(BaseModel):
    total_scans: int
    compliant: int
    non_compliant: int
    needs_review: int
    compliance_rate: float
    avg_latency_ms: float
    cache_hit_rate: float
    open_reports: int
    total_reports: int
    active_clauses: int
    top_violations: list[dict[str, Any]]
    scans_by_day: list[dict[str, Any]]
    verdict_split: list[dict[str, Any]]
    severity_split: list[dict[str, Any]]
