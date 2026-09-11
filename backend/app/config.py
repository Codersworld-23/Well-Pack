"""Runtime configuration. Every external dependency degrades to a local
implementation so the prototype runs with zero credentials."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    # Production environments may inject variables directly.
    pass


class Settings:
    # --- storage -------------------------------------------------------
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'wellpack.db'}")
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))

    # --- vector store / RAG --------------------------------------------
    # Set PINECONE_API_KEY to swap the in-process store for Pinecone.
    pinecone_api_key: str | None = os.getenv("PINECONE_API_KEY")
    pinecone_index: str = os.getenv("PINECONE_INDEX", "wellpack-legal-metrology")
    embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "768"))
    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))

    # --- semantic cache -------------------------------------------------
    # Set REDIS_URL to back the semantic cache with Redis instead of memory.
    redis_url: str | None = os.getenv("REDIS_URL")
    cache_similarity_threshold: float = float(os.getenv("CACHE_THRESHOLD", "0.94"))
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL", "86400"))

    # --- RAG + LLM ------------------------------------------------------
    # The retrieved PDF clauses are sent to this OpenAI-compatible endpoint.
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://aicredits.in/v1")
    if not openai_base_url.startswith(("http://", "https://")):
        openai_base_url = f"https://{openai_base_url}"
    openai_base_url = openai_base_url.rstrip("/")
    llm_model: str = os.getenv("OPENAI_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
    # Bump whenever the analysis changes meaningfully: the semantic cache only
    # reuses a verdict whose analysis_version matches, so this is what stops
    # verdicts produced by the previous logic from being served after an upgrade.
    # v2: LLM decides (was silently falling back to the regex engine), retrieval
    # augmented with every governing clause, OCR-damage-tolerant extraction.
    analysis_version: str = os.getenv("ANALYSIS_VERSION", "rag-llm-v2")

    # --- vision ---------------------------------------------------------
    blur_threshold: float = float(os.getenv("BLUR_THRESHOLD", "55.0"))
    glare_threshold: float = float(os.getenv("GLARE_THRESHOLD", "0.055"))
    min_contrast_ratio: float = float(os.getenv("MIN_CONTRAST_RATIO", "3.0"))
    # Assumed physical width (mm) of a scanned package face, used to convert
    # pixel heights to millimetres when no reference marker is present.
    assumed_package_width_mm: float = float(os.getenv("PACKAGE_WIDTH_MM", "90.0"))

    # --- auth -----------------------------------------------------------
    # No hardcoded fallback: this repository is public, so a committed default
    # would be a known signing key on any deployment that forgot to set
    # JWT_SECRET. Unset means a fresh random key per process - tokens simply
    # stop validating across restarts, which is correct for local development
    # and impossible to forge.
    jwt_secret: str = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
    jwt_ttl_hours: int = int(os.getenv("JWT_TTL_HOURS", "12"))

    cors_origins: list[str] = (
        os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
