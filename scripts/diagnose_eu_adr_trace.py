"""Diagnose (one-off): why does `deepdive EDV.L` fail at the SEC-CIK step?

Traces the real EU-ADR chain for one ticker end to end and prints the raw
finding at every boundary — yfinance reference name, OpenFIGI home identity,
the issuer's US lines, the picked ADR line, and the SEC company_tickers lookup.
Additionally scans the SEC ticker map by ISSUER TITLE, to separate "the picked
symbol is not in the map" from "this issuer is not an SEC registrant at all".

Aufruf (cmd.exe):
  set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
  uv run python scripts\diagnose_eu_adr_trace.py EDV.L
"""

from __future__ import annotations

import json
import sys

import httpx

from app.config import settings
from app.deepdive.eu_adr_resolution import (
    _same_issuer,
    find_home_identity,
    home_exch_codes,
    issuer_name,
    local_symbol_variants,
    norm_issuer,
    pick_us_adr_line,
    US_EXCH,
)
from app.services.edgar_client import EdgarClientImpl
from app.services.openfigi_client import OpenFIGIClientImpl
from app.services.yfinance_client import YFinanceClientImpl

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def main() -> int:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "EDV.L"
    ua = settings.edgar_user_agent
    print(f"===== {ticker} =====")

    yf = YFinanceClientImpl()
    info = yf.get_ticker_info(ticker)
    ref = info.get("longName") or info.get("shortName")
    print(f"[1] yfinance ref name : {ref!r}")
    print(f"    norm             : {norm_issuer(ref or '')!r}")
    print(f"    exchange/currency : {info.get('exchange')} / {info.get('currency')}")

    figi = OpenFIGIClientImpl(api_key=getattr(settings, "openfigi_api_key", "") or "")
    print(f"[2] home exch codes  : {home_exch_codes(ticker)}")
    print(f"    symbol variants  : {local_symbol_variants(ticker)}")
    ident = find_home_identity(ticker, norm_issuer(ref or ""), openfigi=figi)
    print(f"    home identity    : {json.dumps(ident, ensure_ascii=False)}")

    ident_norm = norm_issuer(issuer_name(ident["name"]))
    lines = figi.search_issuer(ident["name"])
    print(f"[3] search_issuer({ident['name']!r}) -> {len(lines)} lines")
    edgar = EdgarClientImpl(user_agent=ua)
    for ln in lines:
        exch = (ln.get("exchCode") or "").strip()
        mark = "US" if exch in US_EXCH else "  "
        print(
            f"    {mark} {str(ln.get('ticker')):10} {exch:4} "
            f"type={ln.get('securityType2')!r} name={ln.get('name')!r}"
        )
    # `pick_us_adr_line` lost its optional name filter when the `search_issuer`
    # fallback went; this trace still walks the search path, whose full-text hits
    # can belong to a different issuer, so it applies the filter itself and keeps
    # printing what it always printed.
    picked = pick_us_adr_line(
        [ln for ln in lines if _same_issuer(ln.get("name", ""), ident_norm)]
    )
    print(f"[4] picked US line   : {json.dumps(picked, ensure_ascii=False)}")
    if picked is None:
        return 0

    us_ticker = (picked.get("ticker") or "").strip()
    print(f"[5] edgar.get_cik({us_ticker!r}) -> {edgar.get_cik(us_ticker)!r}")

    # Is the ISSUER an SEC registrant under any symbol?
    raw = httpx.get(SEC_TICKERS_URL, headers={"User-Agent": ua}, timeout=25).json()
    needle = (ref or "").upper().split()[0]
    hits = [
        (v["ticker"], v["cik_str"], v["title"])
        for v in raw.values()
        if needle in str(v.get("title", "")).upper()
    ]
    print(f"[6] company_tickers titles containing {needle!r}: {len(hits)}")
    for t, cik, title in hits[:25]:
        print(f"    {t:10} CIK {cik:<10} {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
