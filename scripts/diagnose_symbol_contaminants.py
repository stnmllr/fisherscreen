"""Diagnose: enumerate non-EQUITY symbol contaminants across the universe and
support ISIN-anchored verification of correction candidates. $0 probe (yfinance
only). Diagnostic script — the pure helpers below are unit-tested; the live
main() is a probe like scripts/trigger_cold_dry_run.py (added in a later task).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from typing import Any

from app.errors import DataSourceError, DegradedDataError
from app.services.yfinance_client import YFinanceClientImpl


def classify_info(info: dict[str, Any]) -> str:
    """EQUITY | CONTAMINANT | INCONCLUSIVE from a yfinance .info dict.

    - quoteType == 'EQUITY'         -> EQUITY (clean)
    - quoteType present & != EQUITY  -> CONTAMINANT (e.g. MUTUALFUND)
    - quoteType missing/None/empty   -> INCONCLUSIVE (transient hiccup; retry/manual)
    """
    if not info:
        return "INCONCLUSIVE"
    quote_type = info.get("quoteType")
    if not quote_type:
        return "INCONCLUSIVE"
    return "EQUITY" if quote_type == "EQUITY" else "CONTAMINANT"


def isin_matches(a: str | None, b: str | None) -> bool:
    """True iff both ISINs are present and equal (normalized). Missing or
    whitespace-only -> False (caller falls back to name-match + manual confirmation)."""
    if not a or not b:
        return False
    a_norm, b_norm = a.strip().upper(), b.strip().upper()
    if not a_norm or not b_norm:
        return False
    return a_norm == b_norm


def _probe_one(client: YFinanceClientImpl, ticker: str, retries: int = 2) -> dict[str, Any]:
    """Return {ticker, status, quoteType, isin, shortName, longName}. Retries on
    INCONCLUSIVE with linear backoff so a yfinance hiccup is not baked as a verdict."""
    last: dict[str, Any] = {}
    for attempt in range(retries + 1):
        try:
            info = client.get_ticker_info(ticker)
        except DegradedDataError:
            return {"ticker": ticker, "status": "DEGRADED", "quoteType": None,
                    "isin": None, "shortName": None, "longName": None}
        except DataSourceError:
            info = {}
        status = classify_info(info)
        last = {"ticker": ticker, "status": status,
                "quoteType": info.get("quoteType"),
                "isin": None, "shortName": info.get("shortName"),
                "longName": info.get("longName")}
        if status != "INCONCLUSIVE":
            try:
                last["isin"] = client.get_isin(ticker)
            except DataSourceError:
                last["isin"] = None
            return last
        time.sleep(1.0 * (attempt + 1))  # linear backoff between retries
    return last


def _enumerate(client: YFinanceClientImpl, tickers: list[str]) -> list[dict[str, Any]]:
    rows = [_probe_one(client, t) for t in tickers]
    contaminants = [r for r in rows if r["status"] == "CONTAMINANT"]
    inconclusive = [r for r in rows if r["status"] == "INCONCLUSIVE"]
    print(f"probed={len(rows)} contaminant={len(contaminants)} "
          f"inconclusive={len(inconclusive)} "
          f"equity={sum(1 for r in rows if r['status']=='EQUITY')} "
          f"degraded={sum(1 for r in rows if r['status']=='DEGRADED')}", file=sys.stderr)
    return rows


def _verify(client: YFinanceClientImpl, proposal: dict[str, str]) -> None:
    """proposal: {contaminant_ticker: candidate_ticker}. Prints per pair whether the
    candidate is EQUITY and whether ISINs match (name shown for manual fallback)."""
    for bad, good in proposal.items():
        c = _probe_one(client, bad)
        g = _probe_one(client, good)
        match = isin_matches(c.get("isin"), g.get("isin"))
        print(json.dumps({
            "contaminant": bad, "candidate": good,
            "candidate_status": g["status"],
            "isin_contaminant": c.get("isin"), "isin_candidate": g.get("isin"),
            "isin_match": match,
            "name_contaminant": c.get("shortName"),
            "name_candidate": g.get("longName") or g.get("shortName"),
        }, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["enumerate", "verify"])
    parser.add_argument("--universe", default="data/universe.json")
    parser.add_argument("--proposal", help="JSON file {bad: good} for verify mode")
    parser.add_argument("--out", help="CSV output path for enumerate mode")
    args = parser.parse_args()

    client = YFinanceClientImpl()
    if args.mode == "enumerate":
        tickers = json.loads(open(args.universe, encoding="utf-8").read())
        rows = _enumerate(client, tickers)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["ticker", "status", "quoteType",
                                                  "isin", "shortName", "longName"])
                w.writeheader()
                w.writerows(rows)
            print(f"wrote {args.out}", file=sys.stderr)
    else:
        proposal = json.loads(open(args.proposal, encoding="utf-8").read())
        _verify(client, proposal)


if __name__ == "__main__":
    main()
