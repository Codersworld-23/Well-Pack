"""Citizen and inspector violation reports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Report, Scan
from ..schemas import ReportIn, ReportOut, ReportUpdate

router = APIRouter(prefix="/api/reports", tags=["reports"])

CRITICAL_PRIORITY_SCORE = 50.0


@router.post("", response_model=ReportOut, status_code=201)
def create_report(payload: ReportIn, db: Session = Depends(get_db)):
    """File a report, optionally attaching a scan as evidence."""
    scan = db.get(Scan, payload.scan_id) if payload.scan_id else None
    if payload.scan_id and not scan:
        raise HTTPException(404, "Referenced scan not found")

    # Triage from the attached evidence: a scan with critical violations
    # reaches an inspector ahead of an unevidenced complaint.
    priority = "medium"
    if scan:
        critical = [v for v in (scan.violations or []) if v.get("severity") == "critical"]
        if critical or scan.compliance_score < CRITICAL_PRIORITY_SCORE:
            priority = "high"
        elif scan.verdict == "compliant":
            priority = "low"

    report = Report(
        scan_id=payload.scan_id,
        product_name=payload.product_name or (scan.product_name if scan else None),
        reporter_name=payload.reporter_name,
        reporter_contact=payload.reporter_contact,
        retailer=payload.retailer,
        location=payload.location,
        category=payload.category,
        description=payload.description,
        priority=priority,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("", response_model=list[ReportOut])
def list_reports(status: str | None = None, priority: str | None = None,
                 limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(Report).order_by(desc(Report.created_at))
    if status:
        query = query.filter(Report.status == status)
    if priority:
        query = query.filter(Report.priority == priority)
    return query.limit(min(limit, 300)).all()


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@router.patch("/{report_id}", response_model=ReportOut)
def update_report(report_id: str, payload: ReportUpdate, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(report, field, value)
    db.commit()
    db.refresh(report)
    return report


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    db.delete(report)
    db.commit()
