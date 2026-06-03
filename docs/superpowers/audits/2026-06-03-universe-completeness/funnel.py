"""Independent funnel reconstruction — throwaway audit instrument.

Reads re_resolution.json (raw yfinance probe of the CURRENT 1349 universe) and
replays the basis-filter stage with the EXACT pipeline semantics, WITHOUT
calling the pipeline:

  * from_yfinance_info coercion:  marketCap/averageVolume `... or None`
    (so 0 / falsy collapses to None == fail)
  * FX:  get_fx_rate uses `{cur}EUR=X`, `regularMarketPrice or price`
  * basis fail order:  volume -> market_cap(EUR) -> gross_margin -> revenue_growth
    (filters._get_fail_reason); first failing gate wins the attribution

Emits stage counts, a per-symbol drop CSV, and the basis-passed list. EDGAR /
Gemini stages are NOT replayed here (they need EDGAR) — those are reconciled
against the raw Cloud Run logs in the report.

Run AFTER re_resolution.py:
  uv run python docs/superpowers/audits/2026-06-03-universe-completeness/funnel.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import yfinance as yf

HERE = Path(__file__).resolve().parent
RES = json.loads((HERE / "re_resolution.json").read_text("utf-8"))

# Mirror app/screener/filters.py thresholds exactly.
MIN_MC_EUR = 2_000_000_000
MIN_VOL = 100_000
MIN_GM = 0.30
MIN_RG = 0.0


def coerce(v):
    """Replicate `info.get(x) or None`: 0 / '' / falsy -> None."""
    return v or None


# --- FX, pipeline method: {cur}EUR=X, regularMarketPrice or price -------------
currencies = sorted({d.get("currency") for d in RES.values()
                     if d["resolved"] and d.get("currency")})
fx: dict[str, float | None] = {"EUR": 1.0}
for c in currencies:
    if c in fx:
        continue
    try:
        info = yf.Ticker(f"{c}EUR=X").info
        fx[c] = info.get("regularMarketPrice") or info.get("price")
    except Exception:  # noqa: BLE001
        fx[c] = None
print("FX (pipeline {cur}EUR=X):")
for c in sorted(fx):
    print(f"  {c:6} -> {fx[c]}")
print()


def mc_eur(d: dict):
    mc = coerce(d.get("marketCap"))
    cur = d.get("currency")
    if mc is None or cur is None:
        return None
    rate = fx.get(cur)
    if rate is None:
        return None
    return mc * rate


# --- replay basis filter ------------------------------------------------------
resolved = {t: d for t, d in RES.items() if d["resolved"]}
unresolved = sorted(t for t, d in RES.items() if not d["resolved"])

drop_rows: list[tuple[str, str, str]] = []  # (symbol, stage_dropped, reason)
for t in unresolved:
    err = RES[t].get("error", "")
    drop_rows.append((t, "yfinance_resolution", f"unresolved: {err}"))

passed: list[str] = []
for t, d in sorted(resolved.items()):
    vol = coerce(d.get("averageVolume"))
    mce = mc_eur(d)
    gm = d.get("grossMargins")
    rg = d.get("revenueGrowth")
    # exact pipeline fail order
    if vol is None or vol < MIN_VOL:
        drop_rows.append((t, "basis_filter", "avg_volume"))
    elif mce is None:
        # pipeline attributes None market_cap_eur to the market_cap gate
        note = "market_cap(fx_or_mc_missing)" if fx.get(d.get("currency")) is None else "market_cap"
        drop_rows.append((t, "basis_filter", note))
    elif mce < MIN_MC_EUR:
        drop_rows.append((t, "basis_filter", "market_cap"))
    elif gm is None or gm < MIN_GM:
        drop_rows.append((t, "basis_filter", "gross_margin"))
    elif rg is None or rg < MIN_RG:
        drop_rows.append((t, "basis_filter", "revenue_growth"))
    else:
        passed.append(t)

# --- counts -------------------------------------------------------------------
N = len(RES)
us = lambda xs: sum(1 for t in xs if "." not in t)  # noqa: E731
eu = lambda xs: sum(1 for t in xs if "." in t)       # noqa: E731

by_reason: dict[str, int] = {}
for _, _, r in drop_rows:
    key = r.split(":")[0] if r.startswith("unresolved") else r
    by_reason[key] = by_reason.get(key, 0) + 1

print("=== INDEPENDENT FUNNEL (universe -> resolution -> basis_filter) ===")
print(f"N_universe                 {N}   (US {us(RES)} / EU {eu(RES)})")
print(f"  - unresolved (yfinance)  -{len(unresolved)}")
print(f"resolved                   {len(resolved)}")
basis_drops = [r for r in drop_rows if r[1] == 'basis_filter']
for reason in ("avg_volume", "market_cap", "market_cap(fx_or_mc_missing)",
               "gross_margin", "revenue_growth"):
    n = sum(1 for _, _, rr in basis_drops if rr == reason)
    if n:
        print(f"  - basis: {reason:28} -{n}")
print(f"basis_passed               {len(passed)}   (US {us(passed)} / EU {eu(passed)})")
print()
print(f"drop rows total            {len(drop_rows)}  (= {len(unresolved)} unresolved "
      f"+ {len(basis_drops)} basis)")
print(f"reconcile: {len(resolved)} resolved - {len(basis_drops)} basis-dropped "
      f"= {len(resolved)-len(basis_drops)} (== basis_passed {len(passed)}? "
      f"{len(resolved)-len(basis_drops)==len(passed)})")

# --- artifacts ----------------------------------------------------------------
with (HERE / "funnel_drops.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["symbol", "stage_dropped", "reason"])
    w.writerows(sorted(drop_rows))

(HERE / "funnel_summary.json").write_text(json.dumps({
    "N_universe": N,
    "unresolved": unresolved,
    "resolved": len(resolved),
    "basis_passed": sorted(passed),
    "basis_passed_count": len(passed),
    "basis_passed_us": us(passed), "basis_passed_eu": eu(passed),
    "drop_reason_counts": by_reason,
    "fx": fx,
}, indent=1, default=str), "utf-8")
print("\nwrote funnel_drops.csv + funnel_summary.json")
