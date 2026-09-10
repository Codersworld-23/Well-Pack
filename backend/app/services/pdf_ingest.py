"""Parse a PDF policy document into RuleClause rows.

Shared by the /api/rules/upload endpoint and the startup seed so the same
extraction logic is used regardless of how a PDF enters the system.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

CLAUSE_SPLIT_RE = re.compile(
    r"(?m)^\s*(?:Rule\s+)?(\d+(?:\s*\(\w+\))*)[\s.:\-]+", re.IGNORECASE
)


def _extract_text(path: Path) -> str:
    """Return the full text of a PDF, falling back to OCR on image-only pages."""
    import fitz  # PyMuPDF
    import numpy as np
    from .ocr import extract as ocr_extract

    parts: list[str] = []
    doc = fitz.open(str(path))
    for page in doc:
        text = page.get_text().strip()
        if len(text) < 50:
            pix = page.get_pixmap()
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:  # RGBA -> RGB
                img = img[:, :, :3]
            text = ocr_extract(img)["text"]
        parts.append(text)
    return "\n".join(parts)


def _chunks(raw: str) -> list[tuple[str, str]]:
    """Split raw text into (rule_number, body) pairs."""
    chunks: list[tuple[str, str]] = []
    parts = CLAUSE_SPLIT_RE.split(raw)
    if len(parts) > 2:
        for i in range(1, len(parts) - 1, 2):
            number, body = parts[i].strip(), parts[i + 1].strip()
            if body:
                chunks.append((number, body))
    else:
        for i, para in enumerate(p.strip() for p in raw.split("\n\n") if p.strip()):
            chunks.append((f"U{i + 1}", para))
    return chunks


def ingest_pdf_file(path: Path, db: "Session") -> int:
    """Parse *path* and insert any new clauses into the database.

    Returns the number of clauses created (0 if all already exist).
    Skips silently if the file cannot be parsed.
    """
    from ..models import RuleClause

    raw = _extract_text(path)
    if not raw.strip():
        log.warning("pdf_ingest: no text extracted from %s", path.name)
        return 0

    stem = re.sub(r"[^A-Za-z0-9]+", "-", path.stem)[:24]
    created = 0
    seen_in_batch: set[str] = set()  # guard against duplicate rule numbers in one PDF
    for number, body in _chunks(raw):
        clause_id = f"UP-{stem}-{number}".replace(" ", "")[:64]
        if clause_id in seen_in_batch:
            continue
        if db.query(RuleClause).filter(RuleClause.clause_id == clause_id).first():
            continue
        seen_in_batch.add(clause_id)
        title = body.split(".")[0][:120] or f"Rule {number}"
        db.add(
            RuleClause(
                clause_id=clause_id,
                rule_number=number,
                title=title,
                text=body[:6000],
                field="general",
                severity="major",
                source="dataset",
            )
        )
        created += 1

    if created:
        db.commit()
    return created
