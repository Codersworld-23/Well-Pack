"""Scan endpoints - the consumer/inspector scan-to-verdict path."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models import Scan
from ..schemas import ScanResult, ScanSummary
from ..services import pipeline, vision

router = APIRouter(prefix="/api/scans", tags=["scans"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
MAX_BYTES = 12 * 1024 * 1024


def _save_upload(file: UploadFile) -> Path:
    suffix = Path(file.filename or "capture.jpg").suffix.lower() or ".jpg"
    destination = settings.upload_dir / f"{uuid.uuid4().hex}{suffix}"
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    if destination.stat().st_size > MAX_BYTES:
        destination.unlink(missing_ok=True)
        raise HTTPException(413, "Image exceeds the 12 MB limit.")
    return destination


def _persist(db: Session, scan: Scan, result: dict) -> Scan:
    scan.status = "complete"
    scan.verdict = result["verdict"]
    scan.compliance_score = result["compliance_score"]
    scan.confidence = result["confidence"]
    scan.hallucination_coefficient = result["hallucination_coefficient"]
    scan.product_name = result.get("product_name")
    scan.extracted_fields = result["extracted_fields"]
    scan.physical_analysis = result["physical_analysis"]
    scan.violations = result["violations"]
    scan.citations = result["citations"]
    scan.ocr_text = result["ocr_text"]
    scan.reasoning = result["reasoning"]
    scan.cache_hit = result["cache_hit"]
    scan.engine = result["engine"]
    scan.latency_ms = result["latency_ms"]
    db.commit()
    db.refresh(scan)
    return scan


@router.post("", response_model=ScanResult)
async def create_scan(
    file: UploadFile = File(...),
    source: str = Form("consumer"),
    scanned_by: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Scan a label image and return a compliance verdict."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported image type: {file.content_type}")

    path = _save_upload(file)
    scan = Scan(
        image_path=str(path),
        image_url=f"/uploads/{path.name}",
        source=source,
        scanned_by=scanned_by,
        status="processing",
    )
    db.add(scan)
    db.commit()

    try:
        result = pipeline.run(str(path), db=db)
    except ValueError as exc:
        scan.status = "failed"
        scan.reasoning = str(exc)
        db.commit()
        raise HTTPException(422, str(exc)) from exc

    return _persist(db, scan, result)


@router.post("/precheck")
async def precheck(file: UploadFile = File(...)):
    """Edge pre-processing gate.

    The mobile client calls this (or runs the same OpenCV checks on-device)
    before committing to a full scan, so a blurred or glared capture prompts a
    retake instead of burning an OCR and LLM round-trip.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported image type: {file.content_type}")

    path = _save_upload(file)
    try:
        quality = vision.capture_quality(vision.load_image(str(path)))
    finally:
        path.unlink(missing_ok=True)
    return quality


@router.get("", response_model=list[ScanSummary])
def list_scans(
    limit: int = 50,
    offset: int = 0,
    verdict: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Scan).order_by(desc(Scan.created_at))
    if verdict:
        query = query.filter(Scan.verdict == verdict)
    if source:
        query = query.filter(Scan.source == source)

    return [
        ScanSummary(
            id=s.id,
            created_at=s.created_at,
            product_name=s.product_name,
            verdict=s.verdict,
            status=s.status,
            compliance_score=s.compliance_score,
            source=s.source,
            cache_hit=s.cache_hit,
            latency_ms=s.latency_ms,
            violation_count=len(s.violations or []),
            image_url=s.image_url,
        )
        for s in query.offset(offset).limit(min(limit, 200)).all()
    ]


@router.get("/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str, db: Session = Depends(get_db)):
    scan = db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return scan


@router.post("/{scan_id}/rescan", response_model=ScanResult)
def rescan(scan_id: str, db: Session = Depends(get_db)):
    """Re-evaluate a stored image against the current rule corpus, bypassing
    the cache. This is how an admin verifies that a policy upload changed the
    verdict without redeploying anything."""
    scan = db.get(Scan, scan_id)
    if not scan or not scan.image_path:
        raise HTTPException(404, "Scan not found")
    result = pipeline.run(scan.image_path, db=db, use_cache=False)
    return _persist(db, scan, result)


@router.delete("/{scan_id}", status_code=204)
def delete_scan(scan_id: str, db: Session = Depends(get_db)):
    scan = db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if scan.image_path:
        Path(scan.image_path).unlink(missing_ok=True)
    db.delete(scan)
    db.commit()
