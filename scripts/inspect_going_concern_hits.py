"""Inspect the CIK-scoped EFTS hits for candidate going-concern filers.

Free, read-only. Explains the per-CIK `value` count and lets us confirm the
phrase sits in genuine in-window 10-K/10-Q filings (not stale/boilerplate).
"""

import time
from datetime import date, timedelta

import httpx

from app.services.edgar_client import EdgarClientImpl

USER_AGENT = "FisherScreen/1.0 stn.mueller@gmail.com"
MONTHS = 24
HEADERS = {"User-Agent": USER_AGENT}

CANDIDATES = {
    "FNGR": "1602409",
    "FRQN": "1624517",
    "AWI": "7431",
}


def scoped_hits(cik: str) -> dict:
    startdt = (date.today() - timedelta(days=MONTHS * 30)).isoformat()
    padded = cik.zfill(10)
    # full-text search (not search-index) returns per-hit metadata we can read
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        "?q=%22raise+substantial+doubt%22&forms=10-K,10-Q"
        f"&dateRange=custom&startdt={startdt}&ciks={padded}"
    )
    time.sleep(0.5)
    resp = httpx.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    today = date.today().isoformat()
    startdt = (date.today() - timedelta(days=MONTHS * 30)).isoformat()
    print(f"window: startdt={startdt} (no enddt)   today={today}\n")
    for ticker, cik in CANDIDATES.items():
        data = scoped_hits(cik)
        total = data.get("hits", {}).get("total", {})
        hits = data.get("hits", {}).get("hits", [])
        print(f"### {ticker}  CIK {cik}  total={total}  hits_on_page={len(hits)}")
        for h in hits[:12]:
            src = h.get("_source", {})
            ft = src.get("file_type")
            fd = src.get("file_date")
            names = "; ".join(src.get("display_names", []))
            print(f"    {str(ft):<10} {str(fd):<12} {names[:70]}")
        print()


if __name__ == "__main__":
    main()
