"""Semantic cache.

A previously scanned product returns its verdict without re-running the LLM or
the retrieval step. Lookup is by cosine similarity over the label embedding, not
by exact hash, so a different photo of the same product still hits.

Backed by the database so warm entries survive a restart; set REDIS_URL to move
the hot path into Redis with the same interface.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Any

import numpy as np

from ..config import settings
from .rag import cosine, embed

log = logging.getLogger(__name__)


def fingerprint(text: str) -> str:
    """Stable identity for a label, robust to OCR whitespace noise."""
    normalised = " ".join(sorted(text.lower().split()))
    return hashlib.sha256(normalised.encode()).hexdigest()[:32]


class SemanticCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._vectors: list[np.ndarray] = []
        self._entries: list[dict[str, Any]] = []
        self.hits = 0
        self.misses = 0

    def load(self, db) -> int:
        """Warm the in-memory index from persisted entries.

        Entries produced by an earlier analysis version are deleted rather than
        loaded. The pipeline rejects a stale-version payload anyway, but lookup
        returns only the single closest match - so leaving one in the index lets
        it permanently shadow the fresh entry for the same product, and the
        cache would never hit again after an upgrade.
        """
        from ..models import CacheEntry

        stale = 0
        with self._lock:
            self._vectors.clear()
            self._entries.clear()
            for row in db.query(CacheEntry).all():
                payload = row.payload or {}
                if payload.get("analysis_version") != settings.analysis_version:
                    db.delete(row)
                    stale += 1
                    continue
                self._vectors.append(np.asarray(row.embedding, dtype=np.float32))
                self._entries.append({
                    "fingerprint": row.fingerprint,
                    "payload": row.payload,
                    "id": row.id,
                })
        if stale:
            db.commit()
            log.info("Dropped %d cache entry/entries from a previous analysis version", stale)
        return len(self._entries)

    def lookup(self, text: str) -> dict[str, Any] | None:
        """Return a cached verdict for a semantically equivalent label."""
        if not text.strip():
            return None

        query = np.asarray(embed(text), dtype=np.float32)
        with self._lock:
            if not self._vectors:
                self.misses += 1
                return None

            scores = [cosine(query, vector) for vector in self._vectors]
            best = int(np.argmax(scores))
            if scores[best] >= settings.cache_similarity_threshold:
                self.hits += 1
                entry = self._entries[best]
                log.info("Semantic cache hit (similarity %.3f)", scores[best])
                return {**entry["payload"], "cache_similarity": round(scores[best], 4)}

        self.misses += 1
        return None

    def store(self, db, text: str, payload: dict[str, Any]) -> None:
        from ..models import CacheEntry

        if not text.strip():
            return
        vector = embed(text)
        entry = CacheEntry(
            fingerprint=fingerprint(text),
            embedding=vector,
            payload=payload,
        )
        db.add(entry)
        db.commit()

        with self._lock:
            self._vectors.append(np.asarray(vector, dtype=np.float32))
            self._entries.append({
                "fingerprint": entry.fingerprint,
                "payload": payload,
                "id": entry.id,
            })

    def invalidate(self, db) -> None:
        """Drop every entry - called when the rule corpus changes, because a
        verdict cached under the old rules is no longer authoritative."""
        from ..models import CacheEntry

        db.query(CacheEntry).delete()
        db.commit()
        with self._lock:
            self._vectors.clear()
            self._entries.clear()
        log.info("Semantic cache invalidated after rule change")

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 3) if total else 0.0


cache = SemanticCache()
