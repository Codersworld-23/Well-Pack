# Demo script — 5 minutes

Both servers running, and `python tools/seed_demo.py` already executed.

## 1 · The consumer scan (90s)

Open **http://localhost:3000/scan**.

Upload `backend/samples/missing_declarations.png`.

Point out, in order:
- The capture is quality-checked *before* upload — blur and glare would prompt a retake
  rather than burn a backend round-trip.
- The verdict: **Non-compliant, score 10/100**.
- Four violations, each showing **observed vs required** and the rule it contravenes —
  no MRP (Rule 6(1)(e)), no manufacture date (6(1)(d)), no consumer care (6(1)(f)),
  and an address with no PIN code (6(1)(a)).
- **Physical analysis**: the panel area, the mm height actually measured, the contrast
  ratio. This is OpenCV measuring the label, not the model guessing.
- **Retrieved clauses**: the verbatim statutory text the verdict was checked against,
  with relevance scores. Nothing is hardcoded.
- **Hallucination coefficient 0.000** — the narrative matches the verified findings.

## 2 · Semantic caching (30s)

Scan the same label again. Note the **cached** chip on the result: the verdict came from
cosine-similarity lookup, not a fresh retrieval + inference pass. It is not a file hash —
a different photo of the same product also hits.

## 3 · Dynamic rules — the headline claim (60s)

Go to **Admin → Rule corpus**.

- Use **Retrieval preview** with `missing mrp declaration` to show which clauses a label
  would pull, and their scores.
- **Deactivate** `Rule 6(1)(e) — Retail sale price`. The corpus re-embeds and the
  semantic cache is cleared on the spot.
- Return to the scan log, open the same product, press **Rescan**. The MRP violation is
  gone: verification logic changed with no code change and no redeploy.
- Reactivate the clause.

Alternatively, upload a `.txt` circular under **Upload a policy document** — it is split
into clauses, embedded, and live immediately.

## 4 · The regulator's view (60s)

**Admin → Dashboard.** Scan volume, compliance rate, cache hit rate, and *most
contravened clauses* — the ranking that tells field inspection where to go. **System
status** shows the live corpus version, cache state, OCR engine and inference mode.

**Admin → Reports.** Citizen reports, auto-triaged: a report arriving with scan evidence
containing critical violations is filed **high priority** without a human reading it.
Open **View scan evidence** to jump from a complaint straight to the machine-verified
proof, then move it through `under review → action taken`.

## 5 · The honesty slide (30s)

- The rule engine decides every verdict; the LLM only explains. The hallucination
  coefficient bounds it, and above 0.35 its narrative is thrown away.
- The whole thing runs with **no API keys** — OCR, retrieval, caching and the rule engine
  are all local. The managed tier (Textract, Pinecone, Redis, PostgreSQL) is a config
  swap, not a rewrite.
- `python tools/run_pipeline_check.py` proves the five labels produce the expected
  verdicts, on demand, in front of the judges.

## Sample labels and what each proves

| File | Demonstrates |
|---|---|
| `compliant_label.png` | A fully compliant pack — 100/100, all nine checks pass |
| `missing_declarations.png` | Missing MRP, date and consumer care — critical failures |
| `low_contrast.png` | Grey-on-white declarations — Rule 9(1) contrast failure, caught by pixels |
| `undersized_text.png` | 1.05 mm text where 2 mm is required — Rule 9(3), caught by measurement |
| `non_metric.png` | Ounces on an imported pack with no country of origin — Rules 5 and 6(1)(g) |
