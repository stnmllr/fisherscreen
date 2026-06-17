"""$0-Akzeptanz B-Fast (kein Gemini): US-Pfad (AVGO) + EU-ADR-Pfad (OpenFIGI).
Loest Ticker NICHT in der statischen Tabelle dynamisch auf, zieht das Annual
Filing, und prueft fail-loud fuer einen reinen EU-Titel ohne ADR.

EU-1 ist das PFLICHT-GATE: NOVO-B.CO ueber den LIVE-Pfad (Override umgangen) muss
die Ground-Truth-CIK 0000353278 finden — verifiziert die Variantenleiter gegen
den dokumentierten Pre-Flight-Miss.

Vor dem Lauf den ADR-Cache leeren, damit EU-1 den Live-Pfad testet (cmd.exe):
  del cache\\adr_resolved.json
  set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
  uv run python scripts\\acceptance_adr_resolution.py
"""
from __future__ import annotations

import sys

from app.deepdive.compose import (
    build_adr_resolver, build_eu_resolver, build_filing_fetcher)
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

    # Case EU-1 (PFLICHT-GATE): NVO variant ladder against the documented pre-flight
    # miss, anchored on the static-table ground-truth CIK. Bypass the override table
    # (call the EU resolver directly) so the LIVE path is what's tested. Clear the
    # ADR cache before the run (see docstring) so this is not served from cache.
    eu = build_eu_resolver()
    nvo = eu("NOVO-B.CO")
    print(f"[eu1] NOVO-B.CO live -> adr={nvo.adr_ticker} cik={nvo.cik} form={nvo.form_type}")
    assert nvo.cik == "0000353278", f"NVO ground-truth CIK mismatch: {nvo.cik}"

    # Case EU-2: SAP.DE full resolve -> fetch (20-F ADR, not in table).
    sap = resolver.resolve("SAP.DE")
    print(f"[eu2] SAP.DE -> adr={sap.adr_ticker} cik={sap.cik} form={sap.form_type}")
    assert sap.cik == "0001000184" and sap.form_type == "20-F"
    sap_raw = fetcher.get(sap.cik, sap.form_type, use_cache=True)
    print(f"[eu2] filing fetched: {sap_raw.accession_number} ({len(sap_raw.document_text)} chars)")

    # Case EU-3: ULVR.L fresh filer (not in pre-flight set) -> US ADR UL.
    ulvr = resolver.resolve("ULVR.L")
    print(f"[eu3] ULVR.L -> adr={ulvr.adr_ticker} cik={ulvr.cik} form={ulvr.form_type}")
    assert ulvr.adr_ticker and ulvr.cik

    print("\nACCEPTANCE OK: US + EU-ADR resolve/fetch; EU-no-ADR fails loud; "
          "NVO ground-truth gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
