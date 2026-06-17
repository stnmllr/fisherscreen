"""$0-Akzeptanz B-Fast US-Pfad (kein Gemini): loest ein US-Ticker NICHT in der
statischen Tabelle dynamisch auf und zieht sein Annual Filing; prueft, dass ein
reiner EU-Titel ohne ADR fail-loud scheitert.

Aufruf (cmd.exe):
  set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
  uv run python scripts\\acceptance_adr_resolution.py
"""
from __future__ import annotations

import sys

from app.deepdive.compose import build_adr_resolver, build_filing_fetcher
from app.errors import DeepDiveError

US_TICKER = "AVGO"   # US 10-K filer, NOT in data/adr_table.json
EU_NO_ADR = "RMV.L"  # pure-EU, no US ADR -> must fail loud


def main() -> int:
    resolver = build_adr_resolver()
    fetcher = build_filing_fetcher()

    # Case 1: US dynamic resolution + filing fetch (NO synthesis -> $0).
    r = resolver.resolve(US_TICKER)
    print(f"[case1] {US_TICKER} -> cik={r.cik} form={r.form_type} adr={r.adr_ticker}")
    assert r.cik and r.cik != "" and r.adr_ticker is None
    raw = fetcher.get(r.cik, r.form_type, use_cache=True)
    print(f"[case1] filing fetched: accession={raw.accession_number} "
          f"date={raw.filing_date} chars={len(raw.document_text)}")
    assert len(raw.document_text) > 1000

    # Case 3: pure-EU no-ADR -> fail loud (DeepDiveError, not a wrong match).
    try:
        resolver.resolve(EU_NO_ADR)
        print(f"[case3] FAIL: {EU_NO_ADR} resolved but should have failed loud")
        return 1
    except DeepDiveError as exc:
        print(f"[case3] OK fail-loud: {exc}")

    print("\nACCEPTANCE OK: US-path resolves + fetches; EU-no-ADR fails loud.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
