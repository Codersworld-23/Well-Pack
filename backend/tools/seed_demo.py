"""Populate the running API with demo scans and citizen reports.

Usage: python tools/seed_demo.py [api_base]
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SAMPLES = Path(__file__).resolve().parent.parent / "samples"

SCANS = [
    ("compliant_label.png", "consumer"),
    ("missing_declarations.png", "consumer"),
    ("low_contrast.png", "inspector"),
    ("undersized_text.png", "inspector"),
    ("non_metric.png", "consumer"),
    ("missing_declarations.png", "inspector"),
]

REPORTS = [
    {
        "product_name": "Crunchy Bites Potato Wafers",
        "reporter_name": "Ananya Rao",
        "reporter_contact": "ananya.rao@example.in",
        "retailer": "Sharma General Store",
        "location": "Pune, Maharashtra",
        "category": "labelling",
        "description": "No MRP printed anywhere on the pack and no date of manufacture. "
                       "The shopkeeper charged Rs 45 with no way to verify the price.",
    },
    {
        "product_name": "Mountain Spring Packaged Drinking Water",
        "reporter_name": "Imran Sheikh",
        "reporter_contact": "9820011223",
        "retailer": "Highway Dhaba, NH-48",
        "location": "Nashik, Maharashtra",
        "category": "legibility",
        "description": "The MRP and net quantity are printed so small they are unreadable "
                       "without a magnifier.",
    },
    {
        "product_name": "Maple Crisp Breakfast Cereal",
        "reporter_name": "Kavya Menon",
        "reporter_contact": "kavya.menon@example.in",
        "retailer": "MegaMart Andheri",
        "location": "Mumbai, Maharashtra",
        "category": "quantity",
        "description": "Net weight is declared in ounces only, with no metric declaration, "
                       "and there is no country of origin on an imported pack.",
    },
]


def main() -> int:
    scan_ids: list[str] = []

    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        try:
            client.get("/health").raise_for_status()
        except Exception as exc:
            print(f"API not reachable at {BASE}: {exc}")
            return 1

        for filename, source in SCANS:
            path = SAMPLES / filename
            if not path.exists():
                print(f"skip {filename} (missing)")
                continue
            with path.open("rb") as handle:
                response = client.post(
                    "/api/scans",
                    files={"file": (filename, handle, "image/png")},
                    data={"source": source},
                )
            response.raise_for_status()
            body = response.json()
            scan_ids.append(body["id"])
            print(f"scanned {filename:28} -> {body['verdict']:14} "
                  f"score {body['compliance_score']:5}  {body['latency_ms']}ms"
                  f"{'  (cached)' if body['cache_hit'] else ''}")

        # Attach evidence: pair each report with a matching non-compliant scan.
        for index, report in enumerate(REPORTS):
            payload = dict(report)
            if index + 1 < len(scan_ids):
                payload["scan_id"] = scan_ids[index + 1]
            response = client.post("/api/reports", json=payload)
            response.raise_for_status()
            print(f"filed report {response.json()['id']} "
                  f"({response.json()['priority']} priority)")

        stats = client.get("/api/analytics").json()
        print(f"\nDashboard: {stats['total_scans']} scans, "
              f"{stats['compliance_rate']}% compliant, "
              f"{stats['open_reports']} open reports, "
              f"{stats['cache_hit_rate']}% cache hit rate")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
