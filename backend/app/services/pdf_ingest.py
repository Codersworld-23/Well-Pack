"""Parse a PDF policy document into RuleClause rows.

Shared by the /api/rules/upload endpoint and the startup seed so the same
extraction logic is used regardless of how a PDF enters the system.

Chunking notes
--------------
An earlier version split on any line beginning with a number, which shredded
these circulars: page numbers, dates and list bullets all became "clauses",
producing rows titled `W9M` or `AshrdhacAgya`. Those junk vectors then
out-ranked the real Legal Metrology clauses at retrieval time.

The chunker below instead builds paragraph-grouped passages of a retrieval-
friendly size, keeps the statutory rule reference when the passage cites one,
and discards OCR noise before it ever reaches the vector store.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Target passage size. Large enough to carry a whole requirement with its
# context, small enough that cosine similarity stays discriminative.
MIN_CHUNK_CHARS = 200
MAX_CHUNK_CHARS = 1400

# A passage citing a rule/section number: "rule 6(1)(e)", "Rule 9(3)", "section 18".
RULE_REF_RE = re.compile(
    r"\b(?:rule|section|clause)\s+(\d{1,3}(?:\s*\(\s*\w{1,3}\s*\))*)", re.IGNORECASE
)

# Page furniture that carries no legal signal.
BOILERPLATE_RE = re.compile(
    r"^(?:page\s*\d+|\d+\s*(?:of|/)\s*\d+|f\.?\s*no\.?.*|tel(?:e)?(?:phone)?[:.].*|"
    r"e-?mail[:.].*|website[:.].*|www\..*|http\S*|"
    r"government of india|ministry of consumer affairs.*|department of consumer affairs.*|"
    r"krishi bhawan.*|new delhi.*|dated?[:.\s].*|yours faithfully.*|copy to.*)$",
    re.IGNORECASE,
)


def _extract_text(path: Path) -> str:
    """Return the full text of a PDF, falling back to OCR on image-only pages."""
    import fitz  # PyMuPDF
    import numpy as np

    from .ocr import extract as ocr_extract

    parts: list[str] = []
    doc = fitz.open(str(path))
    try:
        for page in doc:
            text = page.get_text().strip()
            if len(text) < 50:
                # Render at 2x so OCR sees enough pixels to be reliable.
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                if pix.n == 4:  # RGBA -> RGB
                    img = img[:, :, :3]
                elif pix.n == 1:  # grayscale -> 3-channel
                    img = np.repeat(img, 3, axis=2)
                text = ocr_extract(img)["text"]
            parts.append(text)
    finally:
        doc.close()
    return "\n\n".join(parts)


def _normalise(raw: str) -> str:
    """Repair the usual PDF-to-text damage before chunking."""
    # Join words hyphenated across a line break.
    raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw)
    # Collapse runs of spaces/tabs but keep paragraph breaks meaningful.
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def _is_noise(text: str) -> bool:
    """True for OCR garbage and page furniture that must not become a clause."""
    stripped = text.strip()
    if len(stripped) < MIN_CHUNK_CHARS // 4:
        return True
    letters = sum(c.isalpha() for c in stripped)
    # Real legal prose is overwhelmingly alphabetic; scanned-signature noise
    # ("W9M", "AshrdhacAgya") and number tables are not.
    if letters / max(1, len(stripped)) < 0.55:
        return True
    # Needs at least a handful of real words to be a retrievable passage.
    if len(re.findall(r"\b[a-zA-Z]{3,}\b", stripped)) < 8:
        return True
    return False


def _paragraphs(raw: str) -> list[str]:
    out: list[str] = []
    for block in raw.split("\n\n"):
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip() and not BOILERPLATE_RE.match(line.strip())
        ]
        if lines:
            out.append(" ".join(lines))
    return out


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9(\"'])")


def _split_long(para: str) -> list[str]:
    """Break an oversized paragraph into sentence-grouped passages.

    Several of these circulars are one unbroken block of text, so paragraph
    splitting alone would emit a single giant chunk and discard the rest of the
    document. Grouping whole sentences keeps each passage self-contained and
    quotable as evidence.
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(para) if s.strip()]
    if not sentences:
        return []

    passages: list[str] = []
    buffer: list[str] = []
    length = 0
    for sentence in sentences:
        # A single sentence longer than the budget is emitted whole rather than
        # being cut mid-clause.
        if len(sentence) > MAX_CHUNK_CHARS:
            if buffer:
                passages.append(" ".join(buffer))
                buffer, length = [], 0
            passages.append(sentence)
            continue
        buffer.append(sentence)
        length += len(sentence) + 1
        if length >= MAX_CHUNK_CHARS:
            passages.append(" ".join(buffer))
            buffer, length = [], 0
    if buffer:
        tail = " ".join(buffer)
        # Fold a short trailing remnant back into the previous passage.
        if passages and len(tail) < MIN_CHUNK_CHARS:
            passages[-1] = f"{passages[-1]} {tail}"
        else:
            passages.append(tail)
    return passages


def _chunks(raw: str) -> list[tuple[str, str]]:
    """Split raw text into (rule_number, passage) pairs.

    Paragraphs are accumulated until the passage reaches a retrieval-friendly
    size, then flushed. The rule number is the first statutory reference the
    passage cites, so a citation like "rule 6(1)(e)" is preserved and becomes
    searchable; passages citing nothing get a sequential ordinal.
    """
    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    ordinal = 0

    def emit(passage: str) -> None:
        nonlocal ordinal
        passage = passage.strip()
        if not passage or _is_noise(passage):
            return
        ordinal += 1
        ref = RULE_REF_RE.search(passage)
        number = re.sub(r"\s+", "", ref.group(1)) if ref else f"P{ordinal}"
        chunks.append((number, passage))

    def flush() -> None:
        nonlocal buffer
        if buffer:
            passage, buffer = " ".join(buffer), []
            emit(passage)

    for para in _paragraphs(raw):
        if len(para) > MAX_CHUNK_CHARS:
            flush()
            for piece in _split_long(para):
                emit(piece)
            continue
        buffer.append(para)
        if sum(len(p) for p in buffer) >= MIN_CHUNK_CHARS:
            flush()
    flush()
    return chunks


def _title_for(passage: str, number: str) -> str:
    """A human-readable clause title: the first real sentence of the passage."""
    sentence = re.split(r"(?<=[.;:])\s", passage.strip(), maxsplit=1)[0]
    sentence = re.sub(r"\s+", " ", sentence).strip(" .;:-")
    if len(sentence) < 12 or len(sentence) > 140:
        sentence = re.sub(r"\s+", " ", passage.strip())[:120].rstrip()
    return sentence or f"Rule {number}"


def stem_for(name: str) -> str:
    """The clause_id prefix component derived from a document's filename."""
    return re.sub(r"[^A-Za-z0-9]+", "-", name)[:24]


def ingest_text(raw: str, stem: str, db: "Session", *, source: str = "dataset") -> int:
    """Chunk *raw* document text into clauses and insert the new ones.

    Shared by the startup dataset seed and the admin upload endpoint so both
    paths produce identically-shaped clauses; the upload route previously had
    its own copy of this loop and drifted from it.
    """
    from ..models import RuleClause

    prefix = f"UP-{stem}-"
    created = 0
    seen_in_batch: set[str] = set()  # guard against duplicate rule numbers
    for index, (number, body) in enumerate(_chunks(raw), start=1):
        # The index keeps two passages citing the same rule from colliding.
        clause_id = f"{prefix}{number}-{index}".replace(" ", "")[:64]
        if clause_id in seen_in_batch:
            continue
        if db.query(RuleClause).filter(RuleClause.clause_id == clause_id).first():
            continue
        seen_in_batch.add(clause_id)
        db.add(
            RuleClause(
                clause_id=clause_id,
                rule_number=number,
                title=_title_for(body, number),
                text=body[:6000],
                field="general",
                severity="major",
                source=source,
            )
        )
        created += 1

    if created:
        db.commit()
    return created


def ingest_pdf_file(path: Path, db: "Session") -> int:
    """Parse *path* and insert any new clauses into the database.

    Returns the number of clauses created (0 if all already exist).
    Skips the file entirely (no OCR, no parsing) if it has been ingested before.
    """
    from ..models import RuleClause

    stem = stem_for(path.stem)

    # Fast skip: if ANY clause from this PDF is already in the DB, the file has
    # been ingested before. Don't re-open or re-OCR it.
    if db.query(RuleClause).filter(RuleClause.clause_id.like(f"UP-{stem}-%")).first():
        return 0

    raw = _normalise(_extract_text(path))
    if not raw.strip():
        log.warning("pdf_ingest: no text extracted from %s", path.name)
        return 0

    return ingest_text(raw, stem, db, source="dataset")


def extract_pdf_stream(data: bytes) -> str:
    """Normalised text from an in-memory PDF, OCRing image-only pages."""
    import fitz  # PyMuPDF
    import numpy as np

    from .ocr import extract as ocr_extract

    parts: list[str] = []
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        for page in doc:
            text = page.get_text().strip()
            if len(text) < 50:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                if pix.n == 4:
                    img = img[:, :, :3]
                elif pix.n == 1:
                    img = np.repeat(img, 3, axis=2)
                text = ocr_extract(img)["text"]
            parts.append(text)
    finally:
        doc.close()
    return _normalise("\n\n".join(parts))
