"""Pre-Flight (Brainstorm B-Fast, ADR-BF-3): laesst sich der Pfad
EU-Yahoo-Ticker -> OpenFIGI US-ADR-Linie -> SEC-CIK fuer 20-F-ADR-Filer
zuverlaessig aufloesen? Go/No-Go-Gate fuer den EU-ADR-Pfad.

Druckt Rohbefund pro Filer. KEIN Pass/Fail-Assert — der Mensch liest die
Ausgabe und faellt das Verdikt im Diagnostic-Report.

Aufruf (cmd.exe):
  set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
  uv run python scripts\\preflight_adr_resolution.py
"""
from __future__ import annotations

import json
import sys

import httpx

from app.services.edgar_client import EdgarClientImpl
from app.config import settings

FIGI_URL = "https://api.openfigi.com/v3/"
US_EXCH = {"US", "UN", "UW", "UQ", "UR", "UA", "UV", "PQ"}

# (yahoo_ticker, local_symbol, home_exchCode) — 20-F-ADR-Filer.
FILERS = [
    ("NOVO-B.CO", "NOVO B", "DC"),
    ("ASML.AS", "ASML", "NA"),
    ("SAP.DE", "SAP", "GY"),
]


def _figi(path: str, payload) -> object:
    r = httpx.post(FIGI_URL + path, json=payload,
                   headers={"Content-Type": "application/json"}, timeout=25)
    r.raise_for_status()
    return r.json()


def _home_identity(local: str, exch: str) -> dict:
    res = _figi("mapping", [{"idType": "TICKER", "idValue": local,
                             "exchCode": exch, "securityType2": "Common Stock"}])
    data = (res[0] or {}).get("data") if isinstance(res, list) and res else None
    return data[0] if data else {"_warning": "no home identity"}


def _us_lines(issuer_name: str) -> list[dict]:
    res = _figi("search", {"query": issuer_name, "marketSecDes": "Equity"})
    out = []
    for d in (res.get("data", []) if isinstance(res, dict) else []):
        if (d.get("exchCode") or "").strip() in US_EXCH:
            out.append({"ticker": d.get("ticker"), "exchCode": d.get("exchCode"),
                        "name": d.get("name"), "securityType2": d.get("securityType2"),
                        "shareClassFIGI": d.get("shareClassFIGI")})
    return out


def main() -> int:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    for yahoo, local, exch in FILERS:
        print(f"\n===== {yahoo} (local {local!r}, home {exch}) =====")
        ident = _home_identity(local, exch)
        print("home identity:", json.dumps(ident, ensure_ascii=False))
        name = ident.get("name", "")
        lines = _us_lines(name) if name else []
        print(f"US-listed lines ({len(lines)}):")
        for ln in lines:
            cik = edgar.get_cik((ln.get("ticker") or "").strip())
            print(f"  {ln['ticker']:8} {ln['exchCode']:4} cik={cik} "
                  f"type={ln['securityType2']} name={ln['name']!r}")
    print("\nRead the output, then fill the diagnostic report + Go/No-Go verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
