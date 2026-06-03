"""INDEPENDENT universe re-resolution — throwaway audit instrument.

NOT the Tool-A pipeline codepath. Read-only. Resolves every symbol in the
CURRENT data/universe.json (N=1349, post EU-correction commit eb37dd7) directly
against yfinance (raw yf.Ticker(t).info) and captures exactly the fields the
basis filter consumes. Two passes separate transient yfinance throttling/404s
from genuine non-resolution.

This is the falsification instrument for the cold-run claim
"yfinance_unresolved = 0 (all 1349 resolve)". It does NOT trust the pipeline
aggregate — it rebuilds the resolved set from the primary source.

Output: re_resolution.json  (one record per symbol, raw)
Run:    uv run python docs/superpowers/audits/2026-06-03-universe-completeness/re_resolution.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yfinance as yf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
UNIVERSE = ROOT / "data" / "universe.json"
OUT = HERE / "re_resolution.json"

# Exactly the fields ScreenerRecord.from_yfinance_info + the basis filters read.
FIELDS = ("marketCap", "currency", "averageVolume", "grossMargins",
          "revenueGrowth", "shortName", "longName", "sector", "quoteType")


def probe(ticker: str) -> dict:
    rec: dict = {"ticker": ticker}
    try:
        info = yf.Ticker(ticker).info
    except Exception as exc:  # noqa: BLE001 - audit must capture every failure mode
        rec.update(resolved=False, error=repr(exc)[:200], keys=0)
        return rec
    if not info:
        rec.update(resolved=False, error="empty_info", keys=0)
        return rec
    keys = len(info)
    rec["keys"] = keys
    for f in FIELDS:
        rec[f] = info.get(f)
    name = info.get("shortName") or info.get("longName")
    # A degraded single-key dict is not a real resolution. Mirror the pipeline's
    # effective bar: a usable record needs a name or a market cap and real depth.
    rec["resolved"] = keys > 5 and bool(name or info.get("marketCap"))
    return rec


# --- throttle-resilient settings ---------------------------------------------
# yfinance throttles by cumulative request rate: a naive sweep hit a hard cliff
# at ~764 requests (everything after instant-404'd). We pace, chunk with
# cooldowns to let the throttle window reset, trip-detect consecutive failures,
# and run multiple low-rate retry passes. Genuine 404s fail EVERY pass; throttle
# victims recover once the rate drops.
INITIAL_WAIT = 30    # IP recovered (11-ticker probe clean); no long penalty wait
PACE = 1.2           # seconds between requests (~ pipeline's 1.25s/ticker cadence)
CHUNK = 120          # requests per chunk
CHUNK_COOLDOWN = 30  # seconds between chunks
TRIP_FAILS = 12      # consecutive fails -> assume throttled
TRIP_COOLDOWN = 300  # seconds to wait out a tripped throttle
RETRY_PASSES = 2     # extra passes over still-failing symbols
PASS_COOLDOWN = 180  # seconds between retry passes


def sweep(tickers: list[str], results: dict[str, dict], label: str) -> None:
    t0 = time.time()
    consec = 0
    for i, t in enumerate(tickers, 1):
        r = probe(t)
        results[t] = r
        if r["resolved"]:
            consec = 0
        else:
            consec += 1
            if consec >= TRIP_FAILS:
                ok = sum(1 for v in results.values() if v["resolved"])
                print(f"[reres] {label} THROTTLE TRIP @ {i} (resolved={ok}) "
                      f"-> cooldown {TRIP_COOLDOWN}s", flush=True)
                time.sleep(TRIP_COOLDOWN)
                consec = 0
        time.sleep(PACE)
        if i % CHUNK == 0:
            ok = sum(1 for v in results.values() if v["resolved"])
            print(f"[reres] {label} {i}/{len(tickers)} resolved={ok} "
                  f"elapsed={time.time()-t0:.0f}s -> chunk cooldown", flush=True)
            time.sleep(CHUNK_COOLDOWN)


def main() -> int:
    tickers = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    total = len(tickers)
    assert len(set(tickers)) == total, "universe has duplicates"
    print(f"[reres] universe N={total} (throttle-resilient); initial "
          f"cooldown {INITIAL_WAIT}s to clear penalty box", flush=True)
    time.sleep(INITIAL_WAIT)

    results: dict[str, dict] = {}
    sweep(tickers, results, "pass1")

    # Retry passes: only the still-unresolved, at low rate, with long cooldowns.
    for p in range(1, RETRY_PASSES + 1):
        failed = sorted(t for t, r in results.items() if not r["resolved"])
        ok = total - len(failed)
        print(f"[reres] pass{p} start: {len(failed)} unresolved (resolved={ok}) "
              f"-> cooldown {PASS_COOLDOWN}s", flush=True)
        if not failed:
            break
        time.sleep(PASS_COOLDOWN)
        for j, t in enumerate(failed, 1):
            r2 = probe(t)
            if r2["resolved"]:
                r2[f"recovered_pass{p}"] = True
                results[t] = r2
            else:
                results[t][f"retried_pass{p}"] = True
            time.sleep(PACE)
            if j % CHUNK == 0:
                time.sleep(CHUNK_COOLDOWN)

    ok = sum(1 for r in results.values() if r["resolved"])
    OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    still = sorted(t for t, r in results.items() if not r["resolved"])
    print(f"[reres] DONE resolved={ok}/{total} failed={total-ok}", flush=True)
    print(f"[reres] still-unresolved: {still}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
