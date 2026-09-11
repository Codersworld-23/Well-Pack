# WellPack — Auto-Compliance Check System

**Smart India Hackathon 2026 · Problem Statement SIH26034**
Ministry of Consumer Affairs, Food & Public Distribution · Team **Double_Triple_Stack**

Scan a packaged commodity label → OCR + OpenCV physical measurement → retrieval over an
ingested corpus of the Legal Metrology (Packaged Commodities) Rules and the Department's
own circulars → an LLM compliance decision grounded in those retrieved clauses → a cited
pass/fail verdict, cached for the next scan, exportable as an inspection report and logged
for regulators.

This is a **working prototype**, not a mock: real OCR, real millimetre and contrast
measurement, a real retrieval index built from the actual policy PDFs, and a real rule
engine.

---

## Quick start

Two terminals.

```bash
# 1. backend  →  http://localhost:8000  (API docs at /docs)
cd backend
pip install -r requirements.txt
cp .env.example .env          # then set OPENAI_API_KEY — see "Two decision tiers"
uvicorn app.main:app --reload --port 8000

# 2. frontend →  http://localhost:3000
cd frontend
npm install
npm run dev
```

On first run the backend creates `wellpack.db`, seeds the 13 Legal Metrology clauses,
**ingests every PDF in `dataset/`** into the clause corpus, embeds the whole corpus into
the vector store, and creates two portal accounts. Later starts skip PDFs already ingested.

> **If the admin pages sit on "Loading…"** the dev server's HMR websocket is being
> blocked (a proxy, VPN or corporate network will do this), which stops React from
> hydrating. `npm run build && npm start` has no HMR socket and is unaffected.

### Two decision tiers — check which one you are running

Verdicts are decided by a **RAG-grounded LLM**, with the deterministic rule engine as the
offline fallback. The fallback works, but its regex extractor misses declarations that are
plainly readable on the label — a pack whose OCR reads `Nel Wt. 200 g` can be reported as
having no net quantity at all. **Set `OPENAI_API_KEY` for representative results.**

The server states the active tier in its startup log, and

```
GET /api/analytics/system   →   llm.configured / llm.mode
```

reports it live (it is also on the admin dashboard). `configured` is true only when a key
is set **and** the `openai` package is importable — a key alone silently downgrades every
scan. Any OpenAI-compatible endpoint works: set `OPENAI_BASE_URL` and `OPENAI_MODEL`.

### Populate a demo dataset

```bash
cd backend
python tools/make_sample_labels.py   # 5 synthetic labels: 1 compliant, 4 failing
python tools/seed_demo.py            # scans them + files 3 citizen reports
python tools/seed_pdfs.py            # (optional) re-push dataset/*.pdf through the API
```

`tools/seed_pdfs.py` is only for re-ingesting the policy PDFs against a running server;
startup already does it.

### Verify the pipeline end to end

```bash
cd backend
python tools/run_pipeline_check.py
```

Runs all five sample labels through the full pipeline and asserts the expected verdict for
each, plus a semantic-cache round-trip. It exercises whichever decision tier is configured,
so run it with the LLM tier enabled for a meaningful result.

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
| 9(2) | Mandatory declarations grouped on the principal display panel |
| 9(3) | Character height ≥ the Second Schedule minimum for the panel area |
| 5 | Metric expression thresholds (1000 g → kg, 1000 ml → l); non-metric units rejected |
| 18(1) | More than one MRP visible on the package |
| 32 | Penalty exposure for the contraventions found (cited, not scored) |

Score = `100 − Σ severity weight` (critical 30, major 15, minor 6, info 0) — the same
weights whichever tier decided, so a score means one thing.
Verdicts: `compliant` · `partial` (minor defects only) · `non_compliant` · `needs_review`.

A verdict is never allowed to contradict its own findings: a response labelled `compliant`
while listing a critical contravention is tightened to `non_compliant`. The verdict is only
ever tightened, never relaxed.

---

## Stack

| Layer | Technology | Note |
|---|---|---|
| Frontend | Next.js 16 (App Router) + React 19 + Tailwind v4 | Consumer scan flow + admin portal |
| Backend | Python FastAPI | One service; the pipeline is explicit, not framework-hidden |
| Vision | OpenCV | Blur/glare gate, label auto-crop, mm character height, WCAG contrast, ORB + SSIM comparison |
| OCR | RapidOCR (ONNX, PP-OCRv6) | Bundled models, no system binary, runs offline |
| PDF ingestion | PyMuPDF, with OCR fallback for image-only pages | Turns policy circulars into retrievable clauses |
| RAG | In-process vector store over the clause corpus | Pinecone-swappable (`PINECONE_API_KEY`) |
| Cache | Semantic cache, cosine similarity | Redis-swappable (`REDIS_URL`) |
| Data | SQLAlchemy → SQLite | PostgreSQL via `DATABASE_URL` |
| LLM | OpenAI-compatible (`gpt-4o-mini` by default) | Decides from retrieved clauses; deterministic fallback offline |
| Reports | ReportLab (PDF) + python-docx (DOCX) | Filing copy and editable copy from one model |

Everything but the LLM tier runs with no credential. See `backend/.env.example`.

---

## The rule corpus

`dataset/` holds the Legal Metrology policy PDFs — the Packaged Commodities Rules
amendments, the country-of-origin circulars for e-commerce, the edible-oil net-quantity
SOP, the readymade-garments advisory, and others. They are **tracked in git on purpose**
(the repo's `*.pdf` ignore carries an explicit `!dataset/*.pdf` exception): without them a
fresh clone seeds an empty index and the RAG tier has nothing to ground on.

Ingestion is not a naive split. An earlier chunker split on any line starting with a
number, which turned page numbers, dates and list bullets into "clauses" that then
out-ranked the real statutory text at retrieval time. `services/pdf_ingest.py` instead
builds paragraph-grouped passages of a retrieval-friendly size (200–1400 chars), keeps the
statutory rule reference when a passage cites one, and discards page furniture —
letterheads, `F. No.` lines, phone numbers, "yours faithfully" — before anything reaches
the vector store. Image-only pages are rasterised and OCR'd.

Admins can extend the corpus at runtime from **Admin → Rule corpus** or
`POST /api/rules/upload` (`.txt`, `.md`, `.pdf`), which uses the same ingestion path.

---

## The claimed innovations, and where they live

**Dynamic RAG pipeline.** Rules are data, not code. Any change through `/api/rules`
(create, edit, toggle, delete, or a policy-document upload) re-embeds the corpus *and*
invalidates the semantic cache, so the next scan is verified against the new text with no
redeploy. Demo it in 20 seconds: deactivate a clause in **Admin → Rule corpus**, then
re-run a scan.

**RAG-grounded LLM decision.** The deterministic engine measures the OCR/vision evidence;
the LLM receives the raw OCR text as primary evidence, those measurements as hints to
verify, and the retrieved clauses as the *only* law it may cite, then returns the verdict,
score, checks and violations. Two grounding guards matter here:

* Retrieval is `top_k` **plus** every clause the engine reasoned about (`store.augment`).
  A model may only cite clauses it was shown, so a bare top-5 retrieval left it unable to
  rule on half the mandatory declarations, and its whole decision was then discarded as
  ungrounded.
* A violation citing an unretrieved clause is dropped **individually**; the rest of the
  decision stands. Only a wholly unusable response falls back to the engine.
  `decision_source` on every result says which tier actually decided.

**Recovering what the regex missed.** The LLM returns `field_corrections` — declarations
it can read in the OCR text that `extractor.py` failed to parse. A correction is accepted
only if its digits appear in the OCR text, so a recovered declaration can never become an
invented one. The extractor itself is now OCR-damage tolerant (`Nel Wt`, `W1`,
`06 FEB 2027`, `Rs`/`INR`/`₹`), and the MRP pattern was tightened so a barcode can no
longer be read as a price.

**Semantic caching.** Cache lookup is cosine similarity over the label embedding, not a
file hash — so a *different photograph of the same product* is still a hit. The cache is
persisted, so it stays warm across restarts. Every entry carries an `analysis_version`;
entries written by an older version are deleted at load rather than served, so an upgrade
cannot leave a stale verdict permanently shadowing the fresh one.

**Multi-modal verification.** Pixel-level measurement (millimetre glyph heights, WCAG
contrast per text region) and statutory-text comprehension feed a single verdict.

**Label comparison for tampering.** `POST /api/scans/compare` takes a reference and a
target label and runs ORB feature matching plus SSIM structural similarity, returning
`authentic` · `suspicious` · `different`. It does not run the compliance pipeline — it
compares the two images as artefacts, for suspected reprints or counterfeits. API-only for
now; no UI surface yet.

See `docs/ARCHITECTURE.md` for the full pipeline and the production swaps.

---

## API surface

`POST /api/scans` · `POST /api/scans/precheck` · `POST /api/scans/compare` ·
`GET /api/scans` · `GET /api/scans/{id}` · `POST /api/scans/{id}/rescan` ·
`DELETE /api/scans/{id}` · `GET /api/scans/{id}/report?format=pdf|docx` ·
`GET|POST|PUT|DELETE /api/rules` · `PATCH /api/rules/{id}/toggle` ·
`POST /api/rules/upload` · `POST /api/rules/reindex` ·
`GET /api/rules/retrieve/preview` · `GET|POST|PATCH|DELETE /api/reports` ·
`GET /api/analytics` · `GET /api/analytics/system` ·
`POST /api/auth/login` · `GET /api/auth/me`

Interactive docs at `http://localhost:8000/docs`.

### Compliance reports

`GET /api/scans/{id}/report` renders a stored scan as an inspection report:

* `format=pdf` — fixed-layout filing copy: verdict banner, findings table with
  severity and rule number, every mandatory declaration and whether it was read,
  the clauses relied upon, reliability notes, a signature block, and the raw OCR
  transcript as an appendix.
* `format=docx` — the same report as an editable Word document, plus an "Officer
  observations" section, so an inspector can correct a misread declaration and
  record the action taken before issuing it.

Both are built from one model so the two formats cannot drift apart in content, and both
are downloadable from the scan result page.

---

## Screens

| Route | Purpose |
|---|---|
| `/` | Landing page — the four-step pipeline explained |
| `/scan` | Consumer capture flow, edge quality gate, live verdict |
| `/scan/[id]` | A stored scan: violations, physical measurements, cited clauses, report download |
| `/report` | Citizen violation report, pre-filled from a scan |
| `/admin` | Dashboard — analytics, corpus/cache/LLM system status, recent scans |
| `/admin/scans` | Scan log with verdict filters |
| `/admin/rules` | Rule corpus CRUD, policy upload, retrieval preview |
| `/admin/reports` | Citizen report queue with status and priority triage |

The scan flow uses `capture="environment"`, so a phone browser opens the camera directly.

---

## Status against the progress report

| Milestone | Status |
|---|---|
| OCR + rule-engine prototype | **Complete** — validated against the sample set |
| RAG pipeline & vector DB integration | **Complete** — statutory clauses *and* the policy PDF corpus indexed, retrieval wired into the decision |
| RAG-grounded LLM verification | **Complete** — the LLM decides from retrieved clauses; the engine is the fallback |
| Compliance report generation | **Complete** — PDF filing copy + editable DOCX |
| Admin dashboard & reporting | **Complete** — rule management, inspection monitoring, violation queue |
| End-to-end scan-to-verdict pilot | **Complete** — `tools/run_pipeline_check.py` |

Remaining from the original plan: the React Native client (the web flow opens the phone
camera directly, so this is a packaging step rather than a rebuild), a UI surface for the
label-comparison endpoint, and validation against photographs of real retail packaging
rather than synthetic labels.

See `docs/ARCHITECTURE.md` for the pipeline and the bounding model, and `docs/DEMO.md`
for the five-minute demo script.
