"""INDEPENDENT universe re-resolution — NOT the Tool-A pipeline codepath.

Read-only audit script. Resolves every symbol in data/universe.json directly
against yfinance (raw yf.Ticker(t).info), captures the fields the basis filter
uses, and writes a JSON artifact for funnel reconciliation.

Two-pass design: failures from pass 1 are retried in pass 2 to separate
transient throttling from genuinely non-resolving symbols.

Output: output-test/audit_resolution.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
UNIVERSE = ROOT / "data" / "universe.json"
OUT = ROOT / "output-test" / "audit_resolution.json"

FIELDS = ("marketCap", "currency", "averageVolume", "grossMargins",
          "revenueGrowth", "shortName", "longName", "sector", "quoteType")


def probe(ticker: str) -> dict:
    rec: dict = {"ticker": ticker}
    try:
        info = yf.Ticker(ticker).info
    except Exception as exc:  # noqa: BLE001 - audit must capture every failure mode
        rec.update(resolved=False, error=repr(exc)[:160], keys=0)
        return rec
    if not info:
        rec.update(resolved=False, error="empty_info", keys=0)
        return rec
    keys = len(info)
    rec["keys"] = keys
    for f in FIELDS:
        rec[f] = info.get(f)
    name = info.get("shortName") or info.get("longName")
    # single-key / degraded dict == not really resolved
    rec["resolved"] = keys > 5 and bool(name or info.get("marketCap"))
    return rec


def main() -> None:
    tickers = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    total = len(tickers)
    print(f"[audit] universe N={total}", flush=True)

    results: dict[str, dict] = {}
    t0 = time.time()
    for i, t in enumerate(tickers, 1):
        results[t] = probe(t)
        if i % 50 == 0:
            ok = sum(1 for r in results.values() if r["resolved"])
            print(f"[audit] pass1 {i}/{total} resolved={ok} elapsed={time.time()-t0:.0f}s", flush=True)

    # Pass 2: retry pass-1 failures (transient throttle separation)
    failed = [t for t, r in results.items() if not r["resolved"]]
    print(f"[audit] pass1 done: {len(failed)} failures -> retry", flush=True)
    time.sleep(5)
    for j, t in enumerate(failed, 1):
        r2 = probe(t)
        if r2["resolved"]:
            r2["recovered_pass2"] = True
            results[t] = r2
        else:
            results[t]["retried_pass2"] = True
        if j % 25 == 0:
            print(f"[audit] pass2 {j}/{len(failed)}", flush=True)

    ok = sum(1 for r in results.values() if r["resolved"])
    OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print(f"[audit] DONE resolved={ok}/{total} failed={total-ok} -> {OUT}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
