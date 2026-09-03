"""Diagnose (one-off): is Endeavour Mining plc an SEC registrant at all?

company_tickers.json only lists registrants that HAVE a ticker mapping, so its
miss alone does not prove "no CIK". This queries EDGAR's company search by name
(the authoritative registrant index) and prints every match.
"""

from __future__ import annotations

import sys

import httpx

from app.config import settings

URL = "https://www.sec.gov/cgi-bin/browse-edgar"


def main() -> int:
    name = " ".join(sys.argv[1:]) or "endeavour mining"
    r = httpx.get(
        URL,
        params={
            "action": "getcompany",
            "company": name,
            "type": "",
            "dateb": "",
            "owner": "include",
            "count": "40",
            "output": "",
        },
        headers={"User-Agent": settings.edgar_user_agent},
        timeout=30,
        follow_redirects=True,
    )
    print("HTTP", r.status_code)
    print(r.text[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
