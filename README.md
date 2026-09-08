# WellPack — Auto-Compliance Check System

**Smart India Hackathon 2026 · Problem Statement SIH26034**
Ministry of Consumer Affairs, Food & Public Distribution · Team **Double_Triple_Stack**

Scan a packaged commodity label → OCR + OpenCV physical analysis → RAG-grounded rule
verification against the Legal Metrology (Packaged Commodities) Rules, 2011 → structured
pass/fail verdict, logged for regulators.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router) + Tailwind — consumer scan flow + admin dashboard |
| Backend | Python FastAPI — OCR, computer vision, rule engine, RAG |
| Vision | OpenCV (blur/glare, font height, WCAG contrast) + RapidOCR |
| RAG | In-process vector store over Legal Metrology clauses (Pinecone-swappable) |
| Cache | Semantic cache (cosine similarity), Redis-swappable |
| Data | SQLAlchemy → SQLite by default, PostgreSQL via `DATABASE_URL` |

## Quick start

```bash
# backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev
```

Backend on http://localhost:8000 (docs at `/docs`), frontend on http://localhost:3000.

See `docs/` for architecture and API notes.
