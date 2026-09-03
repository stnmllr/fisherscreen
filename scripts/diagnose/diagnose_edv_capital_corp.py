"""Diagnose (one-off): CIK + filing history of 'ENDEAVOUR MINING CAPITAL CORP'."""
from __future__ import annotations
import re, json, httpx
from app.config import settings
ua = {"User-Agent": settings.edgar_user_agent}
html = httpx.get(
    "https://www.sec.gov/cgi-bin/browse-edgar",
    params={"action": "getcompany", "company": "endeavour min", "type": "",
            "dateb": "", "owner": "include", "count": "40"},
    headers=ua, timeout=30, follow_redirects=True).text
ciks = sorted(set(re.findall(r"CIK=(\d{10})", html)))
print("CIKs:", ciks)
for cik in ciks:
    d = httpx.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                  headers=ua, timeout=30).json()
    rec = d.get("filings", {}).get("recent", {})
    forms, dates = rec.get("form", []), rec.get("filingDate", [])
    print(f"\n{cik} {d.get('name')!r} tickers={d.get('tickers')} "
          f"exchanges={d.get('exchanges')} sic={d.get('sicDescription')!r}")
    print("  filings total:", len(forms))
    print("  newest 10:", list(zip(forms, dates))[:10])
    print("  annual forms:", sorted({f for f in forms if f in ("10-K", "20-F", "40-F")}))
