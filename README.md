# WellPack — Auto-Compliance Check System

**Smart India Hackathon 2026 · Problem Statement SIH26034**
Ministry of Consumer Affairs, Food & Public Distribution · Team **Double_Triple_Stack**

Scan a packaged commodity label → OCR + OpenCV physical analysis → RAG-grounded
verification against the Legal Metrology (Packaged Commodities) Rules, 2011 → a cited
pass/fail verdict, cached for the next scan and logged for regulators.

This is a **working prototype**, not a mock: real OCR, real millimetre and contrast
measurement, a real retrieval index over the statutory text, and a real rule engine.
It runs with **zero API keys and zero cloud accounts**.

---

## Quick start

Two terminals.

```bash
# 1. backend  →  http://localhost:8000  (API docs at /docs)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. frontend →  http://localhost:3000
cd frontend
npm install
npm run dev
```

> **If the admin pages sit on "Loading…"** the dev server's HMR websocket is being
> blocked (a proxy, VPN or corporate network will do this), which stops React from
> hydrating. `npm run build && npm start` has no HMR socket and is unaffected.

On first run the backend creates `wellpack.db`, seeds the 13 Legal Metrology clauses,
embeds them into the vector store, and creates two portal accounts.

### Populate a demo dataset

```bash
cd backend
python tools/make_sample_labels.py   # 5 synthetic labels: 1 compliant, 4 failing
python tools/seed_demo.py            # scans them + files 3 citizen reports
```

### Verify the pipeline end to end

```bash
cd backend
python tools/run_pipeline_check.py
```

Runs all five labels through the full pipeline and asserts the expected verdict for
each, plus a semantic-cache round-trip. Current status: **all checks pass**.

### Portal accounts

| Email | Password | Role |
|---|---|---|
| `admin@wellpack.gov.in` | `wellpack2026` | admin |
| `inspector@wellpack.gov.in` | `inspect2026` | inspector |

---

## What it actually checks

| Rule | Check |
|---|---|
| 6(1)(a) | Manufacturer / packer / importer, with a complete address (PIN code present) |
| 6(1)(b) | Common or generic name of the commodity |
| 6(1)(c) | Net quantity present, correctly labelled, in metric units |
| 6(1)(d) | Month and year of manufacture, packing or import |
| 6(1)(e) | MRP present **and** carrying "inclusive of all taxes" |
| 6(1)(f) | Consumer care details with a reachable contact channel |
| 6(1)(g) | Country of origin on imported packages |
| 9(1) | Text/background contrast ≥ 3:1 (WCAG relative luminance) |
| 9(3) | Character height ≥ the Second Schedule minimum for the panel area |
| 5 | Metric expression thresholds (1000 g → kg, 1000 ml → l); non-metric units rejected |
| 18(1) | More than one MRP visible on the package |

Score = `100 − Σ severity weight` (critical 30, major 15, minor 6).
Verdicts: `compliant` · `partial` (minor defects only) · `non_compliant` · `needs_review`.

---

## Stack

| Layer | Technology | Note |
|---|---|---|
| Frontend | Next.js 16 (App Router) + Tailwind v4 | Consumer scan flow + admin portal |
| Backend | Python FastAPI | One service; the pipeline is explicit, not framework-hidden |
| Vision | OpenCV | Blur/glare gate, mm character height, WCAG contrast |
| OCR | RapidOCR (ONNX, PP-OCRv6) | Bundled models, no system binary, runs offline |
| RAG | In-process vector store over the clause corpus | Pinecone-swappable |
| Cache | Semantic cache, cosine similarity | Redis-swappable |
| Data | SQLAlchemy → SQLite | PostgreSQL via `DATABASE_URL` |
| LLM | Anthropic `claude-opus-5` (optional) | Narrates only; never decides the verdict |

Nothing in the pipeline requires a credential. Configure the managed tier when you want
it — see `backend/.env.example`.

---

## The three claimed innovations, and where they live

**Dynamic RAG pipeline.** Rules are data, not code. Any change through
`/api/rules` (create, edit, toggle, delete, or a policy-document upload)
re-embeds the corpus *and* invalidates the semantic cache, so the next scan is verified
against the new text with no redeploy. Demo it in 20 seconds: deactivate a clause in
**Admin → Rule corpus**, then re-run a scan.

**Semantic caching.** Cache lookup is cosine similarity over the label embedding, not a
file hash — so a *different photograph of the same product* is still a hit. The cache is
persisted, so it stays warm across restarts.

**Multi-modal verification.** Pixel-level measurement (millimetre glyph heights, WCAG
contrast per text region) and statutory-text comprehension feed a single verdict.

**Bounding the LLM.** The deterministic rule engine decides every verdict. The LLM only
writes the explanation, and its output is scored for citation drift, finding drift and
confidence drift — the *hallucination coefficient*, returned on every scan. Above 0.35
the narrative is discarded and the engine's own summary is shown, so a hallucinated
clause can never surface as a legal finding. See `docs/ARCHITECTURE.md`.

---

## API surface

`POST /api/scans` · `POST /api/scans/precheck` · `GET /api/scans` ·
`GET /api/scans/{id}` · `POST /api/scans/{id}/rescan` ·
`GET|POST|PUT|DELETE /api/rules` · `POST /api/rules/upload` ·
`GET /api/rules/retrieve/preview` · `GET|POST|PATCH /api/reports` ·
`GET /api/analytics` · `GET /api/analytics/system` · `POST /api/auth/login`

Interactive docs at `http://localhost:8000/docs`.

---

## Status against the progress report

| Milestone | Status |
|---|---|
| OCR + rule-engine prototype | **Complete** — validated against the sample set |
| RAG pipeline & vector DB integration | **Complete** — clause corpus indexed, retrieval wired into verification |
| Admin dashboard & reporting | **Complete** — rule management, inspection monitoring, violation queue |
| End-to-end scan-to-verdict pilot | **Complete** — `tools/run_pipeline_check.py`, all checks passing |

Remaining from the original plan: the React Native client (the web scan flow uses
`capture="environment"`, so a phone browser opens the camera directly) and validation
against photographs of real retail packaging rather than synthetic labels.

See `docs/ARCHITECTURE.md` for the pipeline, the bounding model, and the production swaps.
