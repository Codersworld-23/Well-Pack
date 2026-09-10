# WellPack — Architecture

Problem Statement **SIH26034** · Legal Metrology (Packaged Commodities) Rules, 2011.

## Scan-to-verdict pipeline

```
 photo
   │
   ├─ 1. Ingest & pre-process ......... vision.capture_quality()
   │      Laplacian blur variance + specular-glare blob detection.
   │      A degraded capture is rejected before any backend cost is incurred
   │      (POST /api/scans/precheck is the same gate, callable from the client).
   │
   ├─ 2. OCR ......................... ocr.extract()
   │      RapidOCR (ONNX, PP-OCRv6). Returns text + per-region quad boxes +
   │      confidence — boxes are what make the physical checks possible.
   │
   ├─ 3. Semantic cache lookup ....... cache.lookup()
   │      Cosine similarity over the label embedding. A different photo of the
   │      same product still hits, so retrieval + LLM are skipped entirely.
   │
   ├─ 4. Extraction .................. extractor.extract_fields()
   │      Rule 6(1) declarations parsed out of the OCR text with OCR-tolerant
   │      patterns (Rs/RS/INR/₹, "Nel Wt", missing decimals).
   │
   ├─ 5. Physical analysis ........... vision.analyse()
   │      Character height in mm vs the Second Schedule; WCAG relative-luminance
   │      contrast of ink against paper, per declaration region.
   │
   ├─ 6. RAG retrieval ............... rag.store.query()
   │      Hashed TF-IDF embedding over the live clause corpus. Queries carry the
   │      declarations found *and the names of the ones missing* — absent
   │      declarations are exactly what the retrieved clauses must cover.
   │
   ├─ 7. Rule engine ................. rule_engine.evaluate()
   │      THE AUTHORITY ON THE VERDICT. Machine-verifiable checks, each paired
   │      with the clause retrieved in step 6 and scored by severity weight.
   │
   ├─ 8. LLM narrative ............... llm.verify()
   │      Explains the position over the retrieved clauses. Scored against the
   │      engine; above the bound the narrative is discarded (see below).
   │
   └─ 9. Verdict → cached → logged to PostgreSQL/SQLite for admin analytics.
```

## The three claimed innovations, and where they live

### Dynamic RAG pipeline — nothing is hardcoded
`routers/rules.py` → `_refresh()` runs on every clause create, edit, toggle,
delete and policy upload. It re-embeds the whole corpus (`rag.reindex_from_db`)
**and invalidates the semantic cache**, because a verdict cached under the old
rules is no longer authoritative. The next scan is verified against the new
corpus with no redeploy. `POST /api/scans/{id}/rescan` re-runs a stored image
against the current corpus, which is how you demonstrate this in 20 seconds.

### Semantic caching
`services/cache.py`. Entries are persisted so a restart keeps the cache warm.
Lookup is cosine similarity (threshold `CACHE_THRESHOLD`, default 0.94), not an
exact hash, so a *different photograph of the same product* is a hit. Backed by
the database by default; `REDIS_URL` moves the hot path to Redis.

### Multi-modal verification
`services/vision.py` measures the label physically — millimetre character
heights against the Second Schedule table and WCAG contrast ratios per text
region — while `services/rag.py` + `services/rule_engine.py` handle the
statutory text. Both feed one verdict. The two halves are not separate tools
producing separate reports.

## RAG-grounded LLM decision (the legal-hallucination mitigation)

The presentation promises a "hallucination coefficient" that keeps legal
verdicts rigorously bounded. Concretely, in `services/llm.py`:

1. The **deterministic rule engine measures evidence and remains the offline
   fallback**. The LLM receives those measurements, OCR, and clauses retrieved
   from the ingested PDF corpus, then returns the structured verdict, score,
   checks, and violations.
2. Its output is grounded by validating every cited clause and violation against
   the retrieved clauses. It is also scored on grounding drift:
   - **citation drift** — clause_ids cited that were never retrieved,
   - **entity drift** — numbers in the summary absent from OCR/extracted fields,
   - **decision drift** — difference from the independent engine hint.
3. Invalid or ungrounded model output is discarded and the deterministic
   fallback is shown. A hallucinated clause cannot reach a user as a legal
   finding.

The coefficient is returned on every scan and surfaced in the UI.

Without `OPENAI_API_KEY` (or when the OpenAI-compatible endpoint is unavailable)
the pipeline runs fully using a deterministic summary and fallback verdict.

## Verdict model

| Verdict | Meaning |
|---|---|
| `compliant` | No violations. Every mandatory declaration present and legible. |
| `partial` | Minor/technical defects only (unit expression, wording) — no mandatory declaration defeated. |
| `non_compliant` | At least one critical or major contravention. Punishable under Rule 32. |
| `needs_review` | Capture quality too low to support a confident negative verdict. |

Score = `100 − Σ severity weight` (critical 30, major 15, minor 6).

## Data model

`scans` (verdict, extracted fields, physical measurements, violations,
citations, latency, cache flag) · `rule_clauses` (the versioned corpus, seed +
admin) · `reports` (citizen/inspector alerts, auto-triaged from attached scan
evidence) · `users` · `cache_entries` (persisted semantic cache).

## Swapping in the production tier

Every managed dependency in the presentation has a working local stand-in and a
single seam to replace it:

| Presented | Prototype default | Seam |
|---|---|---|
| AWS Textract / Cloud Vision | RapidOCR ONNX | `services/ocr.py` — same `{text, box, confidence}` contract |
| Pinecone / Milvus | in-process numpy index | `rag.VectorStore.upsert/query` |
| Redis | DB-backed cache | `cache.SemanticCache`, set `REDIS_URL` |
| PostgreSQL | SQLite | set `DATABASE_URL` |
| LangChain orchestration | `services/pipeline.py` | explicit, ~9 steps, no framework needed at this size |
