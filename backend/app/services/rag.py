"""RAG tier - embeddings, vector store and clause retrieval.

The default store is an in-process numpy matrix over a hashed TF-IDF embedding:
deterministic, dependency-free and fast enough for the clause corpus, so the
prototype needs no Pinecone key. `VectorStore` is the seam - swapping in
Pinecone or Milvus means implementing `upsert`/`query` against the same shape.

The store is rebuilt from the database whenever a clause is created, edited or
deactivated, which is what makes the pipeline dynamic: an admin upload changes
verification behaviour on the next scan, with no redeploy.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from typing import Any

import numpy as np

from ..config import settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Legal boilerplate carries no retrieval signal.
STOPWORDS = frozenset("""
a an the of in on for to and or be is are was were shall not no any such this that these those
by with as at from it its which who whom whose than then there here have has had may can will
""".split())


def _tokens(text: str) -> list[str]:
    words = [w for w in _TOKEN_RE.findall(text.lower()) if w not in STOPWORDS and len(w) > 1]
    # Character trigrams on longer words give robustness to OCR damage.
    grams: list[str] = []
    for word in words:
        if len(word) > 5:
            grams.extend(word[i:i + 3] for i in range(len(word) - 2))
    return words + grams


def _bucket(token: str, dim: int) -> int:
    return int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big") % dim


def embed(text: str, dim: int | None = None) -> list[float]:
    """Hashed TF-IDF-style embedding, L2-normalised for cosine similarity."""
    dim = dim or settings.embedding_dim
    vector = np.zeros(dim, dtype=np.float32)
    tokens = _tokens(text)
    if not tokens:
        return vector.tolist()

    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1

    for token, count in counts.items():
        # Sublinear term frequency damps repeated statutory phrasing.
        vector[_bucket(token, dim)] += 1.0 + math.log(count)

    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector /= norm
    return vector.tolist()


def cosine(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom else 0.0


class VectorStore:
    """In-process cosine-similarity index over the active clause corpus."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._matrix: np.ndarray = np.zeros((0, settings.embedding_dim), dtype=np.float32)
        self._meta: list[dict[str, Any]] = []
        self.version = 0

    def rebuild(self, clauses: list[dict[str, Any]]) -> int:
        """Re-embed the whole corpus. Called on every admin rule change."""
        with self._lock:
            vectors = []
            meta = []
            for clause in clauses:
                document = f"{clause['title']} {clause['text']} rule {clause['rule_number']}"
                vectors.append(embed(document))
                meta.append(clause)
            self._matrix = (
                np.asarray(vectors, dtype=np.float32)
                if vectors
                else np.zeros((0, settings.embedding_dim), dtype=np.float32)
            )
            self._meta = meta
            self.version += 1
            return len(meta)

    def query(self, text: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Retrieve the clauses most relevant to an extracted label."""
        top_k = top_k or settings.retrieval_top_k
        with self._lock:
            if not self._meta:
                return []
            query_vector = np.asarray(embed(text), dtype=np.float32)
            scores = self._matrix @ query_vector
            order = np.argsort(-scores)[:top_k]
            return [
                {**self._meta[int(i)], "score": round(float(scores[int(i)]), 4)}
                for i in order
                if scores[int(i)] > 0
            ]

    def query_for_field(self, field: str, text: str, top_k: int = 2) -> list[dict[str, Any]]:
        """Retrieve clauses scoped to one declaration field."""
        with self._lock:
            indices = [i for i, m in enumerate(self._meta) if m.get("field") == field]
            if not indices:
                return []
            query_vector = np.asarray(embed(text), dtype=np.float32)
            scored = sorted(
                ((float(self._matrix[i] @ query_vector), i) for i in indices),
                reverse=True,
            )
            return [
                {**self._meta[i], "score": round(score, 4)} for score, i in scored[:top_k]
            ]

    def get(self, clause_id: str) -> dict[str, Any] | None:
        with self._lock:
            return next((m for m in self._meta if m["clause_id"] == clause_id), None)

    @property
    def size(self) -> int:
        return len(self._meta)


store = VectorStore()


def reindex_from_db(db) -> int:
    """Rebuild the vector store from the active clauses in PostgreSQL/SQLite."""
    from ..models import RuleClause

    rows = db.query(RuleClause).filter(RuleClause.active.is_(True)).all()
    return store.rebuild([
        {
            "clause_id": row.clause_id,
            "rule_number": row.rule_number,
            "title": row.title,
            "text": row.text,
            "field": row.field,
            "severity": row.severity,
        }
        for row in rows
    ])
