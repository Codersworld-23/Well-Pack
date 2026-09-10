"""Seed the rule corpus with the PDFs in the dataset folder.

Usage: python tools/seed_pdfs.py [api_base]
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "dataset"


def main() -> int:
    if not DATASET_DIR.exists():
        print(f"Dataset directory not found at {DATASET_DIR}")
        return 1

    pdfs = list(DATASET_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {DATASET_DIR}")
        return 1

    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        try:
            client.get("/docs") # Simple check, since /health doesn't seem to be explicitly in README
        except Exception as exc:
            print(f"API not reachable at {BASE}: {exc}")
            return 1

        total_clauses = 0
        for pdf in pdfs:
            print(f"Uploading {pdf.name}...")
            with pdf.open("rb") as handle:
                response = client.post(
                    "/api/rules/upload",
                    files={"file": (pdf.name, handle, "application/pdf")},
                )
            
            if response.status_code != 200:
                print(f"Failed to upload {pdf.name}: {response.text}")
                continue
                
            body = response.json()
            created = body.get("clauses_created", 0)
            total_clauses += created
            print(f"Success: {body.get('message', f'Created {created} clauses.')}")

        print(f"\nFinished processing {len(pdfs)} PDFs. Total clauses created: {total_clauses}.")
        
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
