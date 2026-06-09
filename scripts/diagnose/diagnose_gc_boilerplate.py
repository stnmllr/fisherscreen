#!/usr/bin/env python3
"""SUB-PHASE 4 diagnosis (read-only, no cost): fetch the primary documents of the
5 going-concern false-positives + the FRQN positive control, and dump the textual
context around every "substantial doubt" / "going concern" occurrence so we can
characterise WHERE the phrase sits and in WHAT polarity — boilerplate (ASC-205-40
auditor-responsibility / conditional / negated) vs. a real affirmative GC finding.

NOT production code. Run: uv run python scripts/diagnose_gc_boilerplate.py
"""
from __future__ import annotations

import re
import sys
import time

import httpx
from bs4 import BeautifulSoup

from app.config import settings

# (ticker, cik, accession, form) — 5 FPs from the warm baseline + FRQN positive control.
TARGETS = [
    ("ADC", "917251", "0001558370-25-005142", "10-Q"),
    ("FR", "921825", "0000921825-25-000019", "10-K"),
    ("HIMS", "1773751", "0001773751-25-000062", "10-K"),
    ("LIVN", "1639691", "0001639691-26-000010", "10-K"),
    ("WTW", "1140536", "0000950170-25-026278", "10-K"),
    ("FRQN", "1624517", "0001829126-25-009309", "10-Q"),  # POSITIVE CONTROL: real GC
]

UA = settings.edgar_user_agent or "FisherScreen diag stn.mueller@gmail.com"
HEADERS = {"User-Agent": UA}
PHRASE = re.compile(r"substantial doubt", re.IGNORECASE)


def _primary_doc(cik: str, accession: str) -> str | None:
    padded = cik.zfill(10)
    data = httpx.get(
        f"https://data.sec.gov/submissions/CIK{padded}.json", headers=HEADERS, timeout=30
    ).json()
    recent = data.get("filings", {}).get("recent", {})
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    for i, a in enumerate(accs):
        if a == accession:
            return docs[i] if i < len(docs) else None
    return None


def _fetch_text(cik: str, accession: str, doc: str) -> str:
    acc_nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/{doc}"
    html = httpx.get(url, headers=HEADERS, timeout=60).text
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text)


def main() -> None:
    for ticker, cik, accession, form in TARGETS:
        print("\n" + "=" * 90)
        print(f"{ticker}  CIK={cik}  {accession}  {form}")
        print("=" * 90)
        try:
            doc = _primary_doc(cik, accession)
            time.sleep(0.3)
            if not doc:
                print("  !! accession not found in recent submissions / no primaryDocument")
                continue
            print(f"  primaryDocument = {doc}")
            text = _fetch_text(cik, accession, doc)
            time.sleep(0.3)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! fetch failed: {type(exc).__name__}: {exc}")
            continue

        hits = list(PHRASE.finditer(text))
        print(f"  'substantial doubt' occurrences: {len(hits)}  (doc len {len(text)} chars)")
        for n, m in enumerate(hits, 1):
            lo = max(0, m.start() - 320)
            hi = min(len(text), m.end() + 220)
            ctx = text[lo:hi].strip()
            print(f"\n  --- occ {n} (pos {m.start()}) ---")
            print(f"  …{ctx}…")


if __name__ == "__main__":
    sys.exit(main())
