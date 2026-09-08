"""End-to-end pipeline check over the sample labels.

Run: python tools/run_pipeline_check.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.WARNING)

from app import seed  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.services import pipeline  # noqa: E402
from app.services.rag import reindex_from_db, store  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

EXPECTED = {
    "compliant_label.png": "compliant",
    "missing_declarations.png": "non_compliant",
    "low_contrast.png": "non_compliant",
    "undersized_text.png": "non_compliant",
    "non_metric.png": "non_compliant",
}


def main() -> int:
    init_db()
    db = SessionLocal()
    seed.run(db)
    indexed = reindex_from_db(db)
    print(f"RAG corpus: {indexed} clauses indexed (version {store.version})\n")

    failures = 0
    for name, expected in EXPECTED.items():
        path = SAMPLES / name
        if not path.exists():
            print(f"SKIP {name} (missing - run tools/make_sample_labels.py)")
            continue

        result = pipeline.run(str(path), db=db, use_cache=False)
        verdict = result["verdict"]
        ok = verdict == expected
        failures += 0 if ok else 1

        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        print(f"      verdict={verdict} (expected {expected})  "
              f"score={result['compliance_score']}  "
              f"latency={result['latency_ms']}ms  "
              f"halluc={result['hallucination_coefficient']}")
        print(f"      product: {result.get('product_name')}")

        fields = result["extracted_fields"]
        shown = {k: fields.get(k) for k in
                 ("net_quantity", "mrp", "manufacture_date", "manufacturer", "consumer_care")}
        print(f"      extracted: {shown}")

        physical = result["physical_analysis"]
        print(f"      physical: min_height={physical.get('smallest_declaration_height_mm')}mm "
              f"(req {physical.get('min_required_height_mm')}mm) "
              f"contrast={physical.get('min_contrast_ratio')}:1 "
              f"blur={physical.get('blur_score')}")

        for violation in result["violations"]:
            print(f"      - [{violation['severity']}] Rule {violation['rule_number']}: "
                  f"{violation['message'][:95]}")
        print(f"      cites: {[c['clause_id'] for c in result['citations']]}")
        print(f"      reasoning: {result['reasoning'][:160]}")
        print()

    # Semantic cache round-trip.
    first = pipeline.run(str(SAMPLES / "compliant_label.png"), db=db)
    second = pipeline.run(str(SAMPLES / "compliant_label.png"), db=db)
    hit = second["cache_hit"]
    print(f"{'PASS' if hit else 'FAIL'}  semantic cache: "
          f"cold={first['latency_ms']}ms -> warm={second['latency_ms']}ms (hit={hit})")
    failures += 0 if hit else 1

    db.close()
    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
