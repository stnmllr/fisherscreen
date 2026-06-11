"""Punkt-3 grounding: characterise the records the revenue_growth gate drops.

The gate is a flat hard knock-out: pass iff info['revenueGrowth'] (a single TTM-YoY
decimal snapshot) >= MIN_REVENUE_GROWTH (0.0). Punkt 3 asks whether to replace it with
a smoothed/scored form. This script grounds that design question in the real drop cohort,
answering Stephan's three framing questions:

  Q2 (sector clustering): which sectors/industries dominate the drop set?
  Q1 (depth/duration):    is the dip a single bad TTM year on an intact multi-year
                          uptrend, or a genuine multi-year shrinker?  (--with-trend)
  Q3 (false-negative est): how many look like plausible Fisher compounders momentarily
                          dinged vs. legitimate structural decliners? (manual, from the
                          enriched CSV — this script supplies the evidence, not the verdict)

Two stages, gated so the cheap cohort is confirmed before the heavier fetch:

  Stage 1 (default, $0, warm .info cache): run_basis_filter over the universe with the
    REAL activated config (build_sector_median_table() + live GROSS_MARGIN_RELATIVE_K),
    isolate records whose filter_failed_reason == "revenue_growth", and for each
    reconstruct whether its gross-margin clearance was ABSOLUTE_PASS or RELATIVE_RESCUE
    (the RELATIVE_RESCUE subset == the low-margin cyclicals Punkt 2 just surfaced).
    Emits a sector/industry histogram, large-cap REVIEW flags, and a per-ticker CSV.

  Stage 2 (--with-trend, live yfinance income_stmt fetch for the drop cohort only):
    pull annual "Total Revenue" across all available fiscal years, compute the
    multi-year trajectory (per-year YoY, oldest->newest CAGR, count of down years) and
    classify SINGLE_YEAR_DIP vs MULTI_YEAR_DECLINE vs INSUFFICIENT_DATA. Enriches the CSV.

Run:
    uv run python scripts\\diagnose_revenue_growth_drops.py
    uv run python scripts\\diagnose_revenue_growth_drops.py --with-trend

$0 (yfinance is free). Read-only. NO Gemini, NO deploy. Runs OUTSIDE pytest, so the
dormant-arm autouse fixture does not apply — this exercises the real activated config.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from app.errors import DataSourceError
from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord
from app.screener import filters
from app.screener.compose import build_screener_pipeline, build_sector_median_table
from app.screener.filters import gross_margin_pass_reason
from app.screener.revenue_trajectory import classify_revenue_trajectory, is_gamma_decline
from app.screener.runner import run_basis_filter
from app.services.income_statement import extract_revenue_series

UNIVERSE = Path("data/universe.json")
OUT_DIR = Path("docs/superpowers/audits/2026-06-10-punkt-3-revenue-growth")
CSV_PATH = OUT_DIR / "revenue_growth_drops.csv"

# Funnel's large-cap severity threshold for the growth gate: a big mature firm can
# genuinely shrink, so a >10B drop is flagged REVIEW (worth a human eyeball), not benign.
LARGE_CAP_GROWTH_EUR = 10_000_000_000


def _pct(x: float | None) -> str:
    return f"{x * 100:+.1f}%" if x is not None else "n/a"


def collect_drops() -> tuple[list[ScreenerRecord], object, float | None]:
    """Stage 1: run the real activated basis filter, return the revenue_growth drops."""
    tickers: list[str] = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    yf = build_screener_pipeline()  # warm cache (Firestore-backed)
    print(f"Universe: {len(tickers)} tickers — running basis filter (warm cache)...")
    result = run_basis_filter(tickers, yf)

    table = build_sector_median_table()
    k = filters.GROSS_MARGIN_RELATIVE_K
    print(
        f"Activated config: table={'loaded' if table else 'ABSENT'}, "
        f"GROSS_MARGIN_RELATIVE_K={k}"
    )
    print(
        f"resolved={len(result.resolved)} passed_basis={len(result.passed)} "
        f"unresolved={len(result.unresolved)}\n"
    )

    drops = [
        r for r in result.resolved if r.filter_failed_reason == "revenue_growth"
    ]
    return drops, list(result.passed), table, k


def summarise(drops: list[ScreenerRecord], table: object, k: float | None) -> None:
    total = len(drops)
    print("=" * 72)
    print(f"REVENUE_GROWTH DROPS: {total}")
    print("=" * 72)

    # ABSOLUTE_PASS vs RELATIVE_RESCUE: the RELATIVE_RESCUE subset is the low-margin
    # cyclical cohort Punkt 2 surfaced (gm rescued by the relative arm, then killed here).
    rescue = [
        r for r in drops
        if gross_margin_pass_reason(r, table, k) == "RELATIVE_RESCUE"
    ]
    print(
        f"  gross-margin clearance: ABSOLUTE_PASS={total - len(rescue)}  "
        f"RELATIVE_RESCUE={len(rescue)} (Punkt-2 low-margin cyclicals)"
    )
    # Two distinct failure modes hide under one reason code: a genuine negative-growth
    # judgement, vs. a MISSING yfinance field (revenueGrowth=None -> gate returns False).
    # The latter is a data-availability artefact, not a growth verdict — Punkt 3 must
    # not conflate them. Surface the split.
    missing = [r for r in drops if r.revenue_growth_yoy is None]
    print(
        f"  failure mode: NEGATIVE_GROWTH={total - len(missing)}  "
        f"MISSING_DATA={len(missing)} (revenueGrowth=None, not a growth verdict)"
    )
    if missing:
        print("    missing-data drops: " + ", ".join(sorted(r.ticker for r in missing)))
    print()

    print("By GICS sector:")
    for sector, n in Counter(r.gics_sector or "?" for r in drops).most_common():
        print(f"    {n:>4}  {sector}")

    print("\nBy GICS industry (top 15):")
    for industry, n in Counter(
        r.gics_industry or "?" for r in drops
    ).most_common(15):
        print(f"    {n:>4}  {industry}")

    large = sorted(
        (r for r in drops if (r.market_cap_eur or 0) >= LARGE_CAP_GROWTH_EUR),
        key=lambda r: r.market_cap_eur or 0,
        reverse=True,
    )
    print(f"\nLarge-cap drops (>10B EUR, funnel-flagged REVIEW): {len(large)}")
    for r in large:
        print(
            f"    {r.ticker:<12} {(r.name or '')[:30]:<30} "
            f"mc={r.market_cap_eur / 1e9:>6.1f}B  gm={_pct(r.gross_margin)}  "
            f"rev_growth_yoy={_pct(r.revenue_growth_yoy)}  {r.gics_sector or ''}"
        )


def fetch_trend(ticker: str, yf: object) -> dict:
    """Stage 2: pull multi-year annual Total Revenue and classify via the PRODUCTION gamma
    core (`extract_revenue_series` + `classify_revenue_trajectory` + `is_gamma_decline`), so
    the diagnostic and the live gate share one semantics. `trend_class` mirrors the gate
    outcome on the TTM<0/None branch:
      DECLINE_DROP      - DEFINED and gamma (CAGR<0 AND down_years>=2): the only drop.
      TRAJECTORY_RESCUE - DEFINED but not gamma (positive CAGR or single down-year).
      UNASSESSABLE_PASS - <4 GJ (criterion could not apply) -> floor pass.
      FETCH_FAILED      - income_stmt fetch raised; in prod this is UNASSESSABLE->pass too,
                          kept distinct here for audit visibility."""
    try:
        income_stmt = yf.get_annual_statements(ticker)[0]
    except DataSourceError:
        return {"trend_class": "FETCH_FAILED", "revenues": [], "cagr": None, "down_years": None}

    revenues = extract_revenue_series(income_stmt)
    cagr, down_years, defn = classify_revenue_trajectory(revenues)
    if defn is DefinednessOutcome.UNASSESSABLE:
        trend_class = "UNASSESSABLE_PASS"
    elif is_gamma_decline(cagr, down_years):
        trend_class = "DECLINE_DROP"
    else:
        trend_class = "TRAJECTORY_RESCUE"

    return {
        "trend_class": trend_class,
        "revenues": revenues,
        "cagr": cagr,
        "down_years": down_years,
    }


def full_sweep(passed: list[ScreenerRecord]) -> None:
    """Residuum derivation X, directly as TTM>=0 AND CAGR<0 AND down_years>=2 over the survivors.

    The slip-through candidates are EXACTLY the survivors the lazy gate never re-checked —
    those tagged `revenue_growth_pass_reason == "TTM_PASS"` (TTM>=0). For each, fetch the
    multi-year trajectory fresh and keep it iff it is a genuine gamma decline. Survivors
    tagged TRAJECTORY_RESCUE / UNASSESSABLE_PASS were already re-checked by the gate and
    cannot slip, so they are excluded by construction (not by a trajectory re-test).

    Three invariants are asserted so the printed number, the gamma rule, and the frozen
    provenance blob describe ONE identical set (catches alpha-vs-gamma drift between the
    diagnostic and the spec/docs): every slip row satisfies gamma; the CSV row count equals
    the printed X; the survivor base is derived explicitly from pass_reason. $0.
    """
    base = Counter(r.revenue_growth_pass_reason for r in passed)
    print(f"\n=== FULL SWEEP: {len(passed)} basis survivors ===")
    print("survivor base by revenue_growth_pass_reason (derives the 731->839 shift):")
    for reason, n in base.most_common():
        print(f"    {n:>4}  {reason}")
    print("    (TTM_PASS = TTM>=0, never re-checked -> the only slip-through candidates;")
    print("     TRAJECTORY_RESCUE / UNASSESSABLE_PASS were re-checked and cannot slip.)")

    yf = build_screener_pipeline()
    slip: list[tuple] = []
    for r in passed:
        if r.revenue_growth_pass_reason != "TTM_PASS":
            continue  # re-checked by the gate already -> not a slip candidate
        t = fetch_trend(r.ticker, yf)
        if t["trend_class"] == "DECLINE_DROP":  # gamma on a fresh multi-year fetch
            slip.append((r.ticker, r.name or "", (r.market_cap_eur or 0) / 1e9,
                         r.revenue_growth_yoy, t["cagr"], t["down_years"]))

    # INVARIANT 1 — every slip row is gamma (CAGR<0 AND down_years>=2). A violation means the
    # sweep classifier and the spec rule diverged (the exact alpha-vs-gamma drift to catch).
    for tk, _nm, _mc, _yoy, cagr, dy in slip:
        assert cagr is not None and cagr < 0 and (dy or 0) >= 2, (
            f"slip row {tk} violates gamma: cagr={cagr} down_years={dy}"
        )

    large = sum(1 for s in slip if s[2] >= 10)
    print(f"\nX (slip-through residuum) = {len(slip)} survivors (TTM>=0 AND gamma), {large} >=10B")
    for tk, nm, mc, yoy, cagr, dy in sorted(slip, key=lambda s: -s[2]):
        ttm = 0.0 if yoy == 0 else yoy  # normalise -0.0 so no reviewer trips over signed zero
        print(
            f"    {tk:<12} {nm[:28]:<28} mc={mc:>6.1f}B  "
            f"ttm_yoy={_pct(ttm)}  cagr={_pct(cagr)}  down_years={dy}"
        )
    out = OUT_DIR / "full_sweep_slipthrough.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "name", "market_cap_eur_b", "ttm_yoy", "multiyear_cagr", "down_years"])
        for tk, nm, mc, yoy, cagr, dy in slip:
            ttm = 0.0 if yoy == 0 else yoy
            w.writerow([tk, nm, round(mc, 2), ttm, cagr, dy])
    # INVARIANT 2 — the frozen blob row count equals the printed X (number == blob).
    written = sum(1 for _ in out.open(encoding="utf-8")) - 1
    assert written == len(slip), f"blob has {written} rows, X={len(slip)}"
    print(f"\nWrote {len(slip)} slip-through rows -> {out}  (every row gamma; count==X)")


def main() -> None:
    with_trend = "--with-trend" in sys.argv
    do_full_sweep = "--full-sweep" in sys.argv
    write_drops = "--write-drops" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    drops, passed, table, k = collect_drops()
    if not drops:
        print("No revenue_growth drops found — cache cold or config dormant. Aborting.")
        sys.exit(1)

    summarise(drops, table, k)

    if do_full_sweep:
        full_sweep(passed)

    rows = []
    for r in drops:
        row = {
            "ticker": r.ticker,
            "name": r.name or "",
            "gics_sector": r.gics_sector or "",
            "gics_industry": r.gics_industry or "",
            "market_cap_eur_b": round((r.market_cap_eur or 0) / 1e9, 2),
            "gross_margin": r.gross_margin,
            "revenue_growth_yoy": r.revenue_growth_yoy,
            "gm_clearance": gross_margin_pass_reason(r, table, k),
            "large_cap_review": (r.market_cap_eur or 0) >= LARGE_CAP_GROWTH_EUR,
        }
        rows.append(row)

    if with_trend:
        print("\n--- Stage 2: fetching multi-year revenue for the drop cohort ---")
        yf_trend = build_screener_pipeline()
        class_counter: Counter = Counter()
        for row in rows:
            t = fetch_trend(row["ticker"], yf_trend)
            row["trend_class"] = t["trend_class"]
            row["multiyear_cagr"] = round(t["cagr"], 4) if t["cagr"] is not None else None
            row["down_years"] = t["down_years"]
            row["n_years"] = len(t["revenues"])
            class_counter[t["trend_class"]] += 1
            print(
                f"    {row['ticker']:<12} {t['trend_class']:<18} "
                f"CAGR={_pct(t['cagr'])}  down_years={t['down_years']}  "
                f"yoy_snapshot={_pct(row['revenue_growth_yoy'])}"
            )
        print("\nTrajectory classification:")
        for cls, n in class_counter.most_common():
            print(f"    {n:>4}  {cls}")

    # The drop-cohort CSV is the FROZEN vintage-2026-06 provenance fixture (189 rows, the
    # pre-Punkt-3 flat-gate cohort that the hermetic acceptance test locks against). Post-ship
    # this script runs the NEW gate and would write only the live gamma-drops (~81), clobbering
    # the fixture — so the write is OFF by default. Pass --write-drops only to deliberately
    # re-vintage it.
    if write_drops:
        fieldnames = list(rows[0].keys())
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nWrote {len(rows)} rows -> {CSV_PATH}")
    else:
        print(
            f"\n(drop-cohort CSV write SKIPPED — {CSV_PATH.name} is the frozen vintage fixture; "
            "pass --write-drops to re-vintage)"
        )


if __name__ == "__main__":
    main()
