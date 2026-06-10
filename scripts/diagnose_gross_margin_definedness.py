"""Gate-A calibration probe A1 (Punkt 2): classify gross-margin definedness edges
to decide the runtime predicate (.info-only vs waterfall) and produce the METRIK_NA
exclusion set used by A2 for clean-universe median computation.

Run: uv run python scripts\\diagnose_gross_margin_definedness.py

Chain position: A1 -> A2 -> A3. A2 MUST run after A1; A1 writes the METRIK_NA set
to docs/superpowers/audits/2026-06-09-2-gross-margin-floor/metrik_na_tickers.json
and A2 loads that file — no re-derivation in A2.

A1's METRIK_NA set MIRRORS the runtime decision: it is built from
assess_definedness (the production single-source 3-state CT-A decision), NOT from
classify_waterfall alone. This matters for the REIT positive-edge (Property C): an
equity REIT has a real rent-minus-opex waterfall (classifies DEFINED), but the
runtime diverts it to METRIK_NA via the "REIT" short-circuit in assess_definedness.
The raw classify_waterfall verdict is still computed per ticker for the diagnostic
table and the null_edge/positive_edge tallies (they need DEFINED vs DEFINED_NEGATIVE
vs UNDEFINED granularity); the contrast verdict=DEFINED but outcome=METRIK_NA is the
Property-C evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline
from app.screener.metric_definedness import (
    WaterfallVerdict,
    assess_definedness,
    classify_waterfall,
)
from app.services.income_statement import extract_waterfall_inputs
from app.services.yfinance_client import YFinanceClientImpl

UNIVERSE = Path("data/universe.json")
AUDIT_DIR = Path("docs/superpowers/audits/2026-06-09-2-gross-margin-floor")
METRIK_NA_JSON = AUDIT_DIR / "metrik_na_tickers.json"


def _is_financial_or_reit(record: ScreenerRecord) -> bool:
    """True when the record belongs to a sector without a genuine COGS waterfall."""
    sector = record.gics_sector or ""
    return "Financ" in sector or "Real Estate" in sector


def main() -> None:
    tickers: list[str] = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    yf_cached = build_screener_pipeline()
    yf_raw = YFinanceClientImpl()

    # Build ScreenerRecords from the warm cache (cheap, $0)
    records: dict[str, ScreenerRecord] = {}
    unresolved: list[str] = []
    for t in tickers:
        try:
            info = yf_cached.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            unresolved.append(t)
            continue
        records[t] = ScreenerRecord.from_yfinance_info(t, info)

    print(f"Universe loaded: {len(records)} records, {len(unresolved)} unresolved")

    # Basket: Financials/REITs + any ticker with gm is None or gm <= 0
    basket: list[ScreenerRecord] = []
    seen: set[str] = set()
    for rec in records.values():
        if _is_financial_or_reit(rec) or rec.gross_margin is None or rec.gross_margin <= 0:
            basket.append(rec)
            seen.add(rec.ticker)

    print(f"\nBasket size: {len(basket)} tickers")
    print(
        "(Financials/REITs union gm<=0 union gm=None — "
        "includes the ~29 Financials with positive .info gm)"
    )

    total = len(basket)
    print(
        f"\nNOTE: now fetching {total} live income_stmt calls via yfinance — "
        "this takes a few minutes. Per-ticker progress lines follow.\n"
        "yfinance may emit HTTP-error lines for delisted/odd symbols — those are harmless noise.",
        flush=True,
    )

    # Per-basket ticker: fetch income_stmt, classify waterfall, decide outcome, tally edges
    null_edge: list[tuple[str, str, float | None, WaterfallVerdict]] = []  # gm<=0, classified DEFINED_NEGATIVE
    positive_edge: list[tuple[str, str, float | None, WaterfallVerdict]] = []  # gm>0 Financial, classified UNDEFINED
    metrik_na_set: set[str] = set()      # outcome is METRIK_NA (== what the runner diverts; includes REITs)
    unassessable_set: set[str] = set()   # outcome is UNASSESSABLE (fetch failure) — NOT METRIK_NA
    rows: list[dict] = []

    for i, rec in enumerate(sorted(basket, key=lambda r: r.ticker), start=1):
        t = rec.ticker

        # Broad per-ticker fetch tolerance: A1 is a BULK sweep over ~287 tickers and
        # must NOT abort on one bad symbol (deliberate script/runtime difference — the
        # production runner is fail-loud, this diagnostic is fail-soft). A caught fetch
        # error => treat the statement as unavailable (statement_available=False).
        income_stmt = None
        fetch_error: str | None = None
        try:
            income_stmt, _cf, _bal = yf_raw.get_annual_statements(t)
        except Exception as exc:
            fetch_error = str(exc) or type(exc).__name__

        statement_available, revenue, cor, gp, cor_present = extract_waterfall_inputs(income_stmt)

        if fetch_error:
            rows.append({
                "ticker": t,
                "sector": rec.gics_sector or "",
                "gm_info": rec.gross_margin,
                "revenue": None,
                "cor": None,
                "gp": None,
                "verdict": f"FETCH_ERROR: {fetch_error[:80]}",
            })
            # A caught fetch error feeds statement_available=False -> outcome UNASSESSABLE
            # (unless REIT short-circuits first). Track distinctly; never in metrik_na_set.
            outcome = assess_definedness(
                rec.gics_industry, False, None, None, None, False
            )
            if outcome is DefinednessOutcome.METRIK_NA:
                metrik_na_set.add(t)
            elif outcome is DefinednessOutcome.UNASSESSABLE:
                unassessable_set.add(t)
            print(f"[{i}/{total}] {t:<14} FETCH_ERROR", flush=True)
            continue

        # Raw waterfall verdict: kept for the diagnostic table + edge tallies (needs the
        # DEFINED vs DEFINED_NEGATIVE vs UNDEFINED granularity).
        verdict = classify_waterfall(revenue, cor, gp, cor_present)
        # Runtime single-source 3-state decision (REIT short-circuit + waterfall). A1's
        # METRIK_NA set is built from this so it == what the runner diverts.
        outcome = assess_definedness(
            rec.gics_industry, statement_available, revenue, cor, gp, cor_present
        )
        print(f"[{i}/{total}] {t:<14} {verdict.value:<18} outcome={outcome.value}", flush=True)

        rows.append({
            "ticker": t,
            "sector": rec.gics_sector or "",
            "gm_info": rec.gross_margin,
            "revenue": revenue,
            "cor": cor,
            "gp": gp,
            "verdict": verdict.value,
        })

        if outcome is DefinednessOutcome.METRIK_NA:
            metrik_na_set.add(t)
        elif outcome is DefinednessOutcome.UNASSESSABLE:
            unassessable_set.add(t)

        gm = rec.gross_margin
        # NULL edge: a gm<=0 ticker that has a REAL waterfall (not just a financial no-COGS case)
        if (gm is None or gm <= 0) and verdict == WaterfallVerdict.DEFINED_NEGATIVE:
            null_edge.append((t, rec.gics_sector or "", gm, verdict))

        # POSITIVE edge: a Financial/REIT with positive .info gm that waterfall classifies UNDEFINED
        if _is_financial_or_reit(rec) and (gm is not None and gm > 0) and verdict == WaterfallVerdict.UNDEFINED:
            positive_edge.append((t, rec.gics_sector or "", gm, verdict))

    # Error summary (coverage check before writing METRIK_NA). FETCH_ERROR is the
    # display row for a caught fetch exception; UNASSESSABLE is the runtime outcome
    # (fetch failure or missing statement) — tracked distinctly and NEVER folded into
    # the METRIK_NA set (distinguish-failure-from-empty-result).
    fetch_error_count = sum(1 for row in rows if str(row["verdict"]).startswith("FETCH_ERROR"))
    print(f"\nFetch errors (display rows): {fetch_error_count}/{total} tickers", flush=True)
    print(f"UNASSESSABLE outcomes (fetch/statement unavailable): {len(unassessable_set)}/{total}", flush=True)

    # Print the table
    print(
        f"\n{'Ticker':<14} {'Sector':<30} {'GM_info':>8} "
        f"{'Revenue':>14} {'COR':>14} {'GP':>14} {'Verdict':<20}"
    )
    print("-" * 120)
    for row in rows:
        gm_str = f"{row['gm_info']:.4f}" if row["gm_info"] is not None else "None"
        rev_str = f"{row['revenue']/1e9:.2f}B" if row["revenue"] is not None else "None"
        cor_str = f"{row['cor']/1e9:.2f}B" if row["cor"] is not None else "None"
        gp_str = f"{row['gp']/1e9:.2f}B" if row["gp"] is not None else "None"
        print(
            f"{row['ticker']:<14} {row['sector']:<30} {gm_str:>8} "
            f"{rev_str:>14} {cor_str:>14} {gp_str:>14} {row['verdict']:<20}"
        )

    # Tally the two edges
    print(f"\n=== NULL EDGE (gm<=0 but waterfall=DEFINED_NEGATIVE — real industrial negative-margin) ===")
    print(f"Count: {len(null_edge)}")
    for t, sec, gm, v in null_edge:
        print(f"  {t:<14} sector={sec:<30} gm_info={gm}")

    print(f"\n=== POSITIVE EDGE (Financial/REIT with gm>0 but waterfall=UNDEFINED — spurious-positive) ===")
    print(f"Count: {len(positive_edge)}")
    for t, sec, gm, v in positive_edge:
        print(f"  {t:<14} sector={sec:<30} gm_info={gm:.4f}")

    # METRIK_NA set == the runtime decision: built from assess_definedness outcomes
    # (REIT short-circuit + waterfall UNDEFINED), NOT from classify_waterfall alone.
    # This now correctly includes REITs (verdict=DEFINED but outcome=METRIK_NA) so the
    # set matches what the runner diverts. UNASSESSABLE (fetch failure) is excluded by
    # construction. The .info-only proxy is kept only for contrast.
    metrik_na_runtime = set(metrik_na_set)
    metrik_na_info_proxy = {
        rec.ticker
        for rec in records.values()
        if rec.gross_margin is None or rec.gross_margin <= 0
    }

    print(f"\n=== METRIK_NA set ===")
    print(f"  Runtime-based (assess_definedness, incl. REITs): {len(metrik_na_runtime)} tickers")
    print(f"  UNASSESSABLE (excluded, fetch/statement unavailable): {len(unassessable_set)} tickers")
    print(f"  .info-only proxy (gm is None or gm<=0): {len(metrik_na_info_proxy)} tickers")
    print(
        "  A2 consumes the runtime-based set from metrik_na_tickers.json "
        "(written below). DEFINED_NEGATIVE tickers stay in the universe; "
        "the median is robust to occasional negative outliers."
    )

    # Emit METRIK_NA set for A2 consumption (runtime-based, mirrors assess_definedness)
    METRIK_NA_JSON.parent.mkdir(parents=True, exist_ok=True)
    METRIK_NA_JSON.write_text(
        json.dumps({"metrik_na": sorted(metrik_na_runtime)}, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {len(metrik_na_runtime)} METRIK_NA tickers -> {METRIK_NA_JSON}")

    # Decision note
    both_empty = len(null_edge) == 0 and len(positive_edge) == 0
    print("\n=== DECISION NOTE ===")
    if both_empty:
        print(
            "Both edges empty -> .info-only predicate holds: "
            "gm is None or gm <= 0 correctly identifies METRIK_NA. "
            "No CT-A flip needed."
        )
    else:
        print(
            "Non-empty edge(s) detected -> flip to waterfall predicate (CT-A): "
            "replace is_gross_margin_undefined_info_only with classify_waterfall "
            "to avoid misclassification. See null_edge and positive_edge tallies above."
        )


if __name__ == "__main__":
    main()
