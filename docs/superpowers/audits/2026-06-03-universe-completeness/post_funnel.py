"""Post-funnel independent checks — throwaway audit instrument.

Runs AFTER funnel.py. Two jobs, both independent of the pipeline:

1. RESTATEMENT-ID: the cold-run dropped 8 records at edgar_filter (GC=0,
   enforcement=no-op -> all 8 are restatements). Replicate has_restatement
   (8-K with Item 4.02 within 3y) over the US basis-passers to NAME those 8.

2. HEALTHY-LARGE-CAP SCAN (Audit 4): list basis-DROPS whose market_cap_eur is
   large (>= AUDIT_BIG_EUR) so an obviously healthy profitable large-cap that
   was dropped surfaces for manual judgement.

Output: restatement_hits.json + healthy_largecap_drops.csv
Run:    uv run python docs/superpowers/audits/2026-06-03-universe-completeness/post_funnel.py
"""
from __future__ import annotations

import csv
import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
UA = {"User-Agent": "FisherScreen-Audit stn.mueller@gmail.com"}
AUDIT_BIG_EUR = 10_000_000_000  # 10 bn EUR — "obviously large" threshold for the scan

funnel = json.loads((HERE / "funnel_summary.json").read_text("utf-8"))
res = json.loads((HERE / "re_resolution.json").read_text("utf-8"))
basis_passed = funnel["basis_passed"]
us_passers = [t for t in basis_passed if "." not in t]
print(f"basis_passed={len(basis_passed)} (US {len(us_passers)})")


# --- ticker -> CIK via EDGAR canonical map -----------------------------------
def cik_map() -> dict[str, str]:
    req = urllib.request.Request(
        "https://www.sec.gov/files/company_tickers.json", headers=UA)
    m = json.load(urllib.request.urlopen(req, timeout=30))
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in m.values()}


# --- replicate has_restatement: 8-K with Item 4.02 within `years` ------------
def has_restatement(cik: str, years: int = 3) -> bool | None:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        data = json.load(urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=30))
    except Exception:  # noqa: BLE001
        return None  # could-not-evaluate (mirrors pipeline data_source_error)
    cutoff = (date.today() - timedelta(days=years * 365)).isoformat()
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    items = recent.get("items", [])
    for form, fdate, item in zip(forms, dates, items):
        if form == "8-K" and fdate >= cutoff and "4.02" in str(item):
            return True
    return False


tmap = cik_map()
hits: list[dict] = []
no_cik = []
errors = []
for i, t in enumerate(us_passers, 1):
    cik = tmap.get(t.upper())
    if not cik:
        no_cik.append(t)
        continue
    r = has_restatement(cik)
    if r is True:
        hits.append({"ticker": t, "cik": cik})
        print(f"  RESTATEMENT: {t} (CIK {cik})")
    elif r is None:
        errors.append(t)
    time.sleep(0.12)  # ~8 req/s, polite
    if i % 100 == 0:
        print(f"  ...{i}/{len(us_passers)}")

print(f"\nrestatement hits={len(hits)} (cold-run dropped 8); "
      f"us_passers_without_cik={len(no_cik)} error={len(errors)}")
(HERE / "restatement_hits.json").write_text(json.dumps(
    {"hits": hits, "us_passers_without_cik": sorted(no_cik),
     "eval_errors": sorted(errors)}, indent=1), "utf-8")

# --- Audit 4: healthy large-cap basis-drops ----------------------------------
# Recompute market_cap_eur for dropped names from re_resolution + funnel FX.
fx = funnel["fx"]
drop_rows = []
with (HERE / "funnel_drops.csv").open(encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["stage_dropped"] != "basis_filter":
            continue
        d = res.get(row["symbol"], {})
        mc = d.get("marketCap") or None
        cur = d.get("currency")
        rate = fx.get(cur) if cur else None
        mce = mc * rate if (mc and rate) else None
        if mce and mce >= AUDIT_BIG_EUR:
            drop_rows.append((row["symbol"], round(mce / 1e9, 1), row["reason"],
                              d.get("grossMargins"), d.get("revenueGrowth"),
                              d.get("shortName")))

drop_rows.sort(key=lambda r: -r[1])
with (HERE / "healthy_largecap_drops.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["symbol", "mcap_eur_bn", "drop_reason", "gross_margin",
                "revenue_growth", "name"])
    w.writerows(drop_rows)
print(f"\nhealthy large-cap (>= {AUDIT_BIG_EUR/1e9:.0f}bn EUR) basis-drops: "
      f"{len(drop_rows)} -> healthy_largecap_drops.csv")
for r in drop_rows[:25]:
    print("  ", r)
