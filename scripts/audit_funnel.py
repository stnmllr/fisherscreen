"""Independent funnel reconstruction from audit_resolution.json.

Replicates the basis-filter thresholds + FX method of the pipeline
(app/screener/filters.py + runner._resolve_market_cap_eur) WITHOUT calling
the pipeline. Produces stage counts and explicit drop lists.
"""
from __future__ import annotations

import json
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
RES = json.loads((ROOT / "output-test" / "audit_resolution.json").read_text("utf-8"))

MIN_MC_EUR = 2_000_000_000
MIN_VOL = 100_000
MIN_GM = 0.30
MIN_RG = 0.0

# distinct currencies among resolved
curs = sorted({d.get("currency") for d in RES.values() if d["resolved"]},
              key=lambda x: (x is None, x))
fx: dict = {}
for c in curs:
    if c is None:
        continue
    if c == "EUR":
        fx[c] = 1.0
        continue
    try:
        info = yf.Ticker(f"{c}EUR=X").info
        fx[c] = info.get("regularMarketPrice") or info.get("price")
    except Exception as exc:  # noqa: BLE001
        fx[c] = None
print("FX rates (pipeline method {cur}EUR=X):")
for c in curs:
    print(f"  {str(c):6} -> {fx.get(c)}")
print()


def mc_eur(d: dict):
    mc = d.get("marketCap")
    cur = d.get("currency")
    if mc is None or cur is None:
        return None
    rate = fx.get(cur)
    if rate is None:
        return None
    return mc * rate


resolved = {t: d for t, d in RES.items() if d["resolved"]}
not_resolved = {t: d for t, d in RES.items() if not d["resolved"]}

drops = {"resolution": sorted(not_resolved),
         "fx_or_mc_missing": [], "avg_volume": [], "market_cap": [],
         "gross_margin": [], "revenue_growth": []}
passed = []
for t, d in resolved.items():
    vol = d.get("averageVolume")
    gm = d.get("grossMargins")
    rg = d.get("revenueGrowth")
    mce = mc_eur(d)
    # pipeline fail order: volume -> market_cap -> gross_margin -> revenue_growth
    if vol is None or vol < MIN_VOL:
        drops["avg_volume"].append(t); continue
    if mce is None:
        drops["fx_or_mc_missing"].append(t); continue
    if mce < MIN_MC_EUR:
        drops["market_cap"].append(t); continue
    if gm is None or gm < MIN_GM:
        drops["gross_margin"].append(t); continue
    if rg is None or rg < MIN_RG:
        drops["revenue_growth"].append(t); continue
    passed.append(t)

N = len(RES)
print("=== INDEPENDENT FUNNEL (free stages only; no EDGAR/Gemini) ===")
print(f"N_universe                     {N}")
print(f"  drop: resolution (404/empty) -{len(drops['resolution'])}")
print(f"resolved                       {len(resolved)}")
print(f"  drop: avg_volume             -{len(drops['avg_volume'])}")
print(f"  drop: fx/market_cap missing  -{len(drops['fx_or_mc_missing'])}")
print(f"  drop: market_cap <2bn EUR    -{len(drops['market_cap'])}")
print(f"  drop: gross_margin <30%      -{len(drops['gross_margin'])}")
print(f"  drop: revenue_growth <0      -{len(drops['revenue_growth'])}")
print(f"passes basis (pre-EDGAR)       {len(passed)}")
print()
print("currency=None among resolved:",
      sorted(t for t, d in resolved.items() if d.get("currency") is None))
print("currency junk (=='3.3'):",
      sorted(t for t, d in resolved.items() if d.get("currency") == "3.3"))
print()
# persist
out = {"fx": fx, "stage_counts": {
    "N_universe": N, "resolved": len(resolved), "passes_basis": len(passed)},
    "drops": drops, "passes_basis_list": sorted(passed)}
(ROOT / "output-test" / "audit_funnel.json").write_text(
    json.dumps(out, indent=1), "utf-8")
print("wrote output-test/audit_funnel.json")
print("passes_basis (US no-dot):", sum(1 for t in passed if "." not in t),
      "| EU:", sum(1 for t in passed if "." in t))
