"""WellPack API - Auto-Compliance Check System (SIH26034)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import SessionLocal, init_db
from .routers import analytics, auth, reports, rules, scan
from .services.cache import cache
from .services.rag import reindex_from_db, store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("wellpack")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from . import seed

    init_db()
    db = SessionLocal()
    try:
        counts = seed.run(db)
        indexed = reindex_from_db(db)
        cached = cache.load(db)
        log.info(
            "WellPack ready - %d clauses indexed, %d cache entries warm, seeded %s",
            indexed, cached, counts,
        )

        # Say plainly which tier will decide verdicts. A missing key or an
        # uninstalled SDK silently downgrades every scan to the regex engine,
        # and that is far too easy to run for weeks without noticing.
        from .services import llm

        if llm.available():
            log.info("Compliance decisions: RAG-grounded LLM (%s)", settings.llm_model)
        else:
            log.warning(
                "Compliance decisions: DETERMINISTIC RULE ENGINE ONLY - the "
                "RAG-grounded LLM is unavailable. Set OPENAI_API_KEY and install "
                "requirements.txt (openai). Verdicts will rely on regex extraction "
                "and can report present declarations as missing."
            )
    finally:
        db.close()
    yield


app = FastAPI(
    title="WellPack API",
    description=(
        "Auto-Compliance Check System for packaged commodities under the Legal "
        "Metrology (Packaged Commodities) Rules, 2011. SIH26034."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")

app.include_router(scan.router)
app.include_router(rules.router)
app.include_router(reports.router)
app.include_router(analytics.router)
app.include_router(auth.router)


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "WellPack Auto-Compliance Check System",
        "problem_statement": "SIH26034",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "clauses_indexed": store.size,
        "corpus_version": store.version,
        "cache_entries": cache.size,
    }
