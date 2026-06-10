"""Grounding probe for CT-B (Punkt 2): dump the exact yfinance gics_industry
strings, their per-industry population count and median gross margin over the
cleaned universe, and which GICS sector each rolls into. Marks THIN industries
(count < n_min) — those are the ones that today fall to the multimodal sector
catch-all and that the CT-B industry->industry-group backbone must map (or leave
fail-safe).

Read-only, warm cache, $0 (no Gemini, no income_stmt fetch). Excludes the current
METRIK_NA set (metrik_na_tickers.json) to approximate the cleaned universe A2 uses.

Run: uv run python scripts\\diagnose_industry_histogram.py
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline

UNIVERSE = Path("data/universe.json")
METRIK_NA_JSON = Path(
    "docs/superpowers/audits/2026-06-09-2-gross-margin-floor/metrik_na_tickers.json"
)
N_MIN = 8


def _is_financial_or_reit(rec: ScreenerRecord) -> bool:
    sector = rec.gics_sector or ""
    return "Financ" in sector or "Real Estate" in sector


def main() -> None:
    tickers: list[str] = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    metrik_na: set[str] = set()
    if METRIK_NA_JSON.exists():
        metrik_na = set(json.loads(METRIK_NA_JSON.read_text(encoding="utf-8"))["metrik_na"])

    yf_cached = build_screener_pipeline()

    # group industry -> (sector, [gross_margins])
    by_industry: dict[str, tuple[str, list[float]]] = defaultdict(lambda: ("", []))
    unresolved = 0
    for t in tickers:
        if t in metrik_na:
            continue
        try:
            info = yf_cached.get_ticker_info(t)
        except (DataSourceError, DegradedDataError):
            unresolved += 1
            continue
        rec = ScreenerRecord.from_yfinance_info(t, info)
        # cleaned proxy: drop Financials/REITs and gm<=0/None (same as A2/A3)
        if _is_financial_or_reit(rec) or rec.gross_margin is None or rec.gross_margin <= 0:
            continue
        ind = rec.gics_industry or "(none)"
        sec, gms = by_industry[ind]
        by_industry[ind] = (rec.gics_sector or "(none)", gms + [rec.gross_margin])

    print(f"Cleaned universe industries: {len(by_industry)} ({unresolved} unresolved)\n")

    # Sort: by sector, then thin-first within sector
    rows = []
    for ind, (sec, gms) in by_industry.items():
        n = len(gms)
        med = statistics.median(gms)
        spread = (max(gms) - min(gms)) if n > 1 else 0.0
        rows.append((sec, ind, n, med, spread, min(gms), max(gms)))

    rows.sort(key=lambda r: (r[0], -r[2]))

    print(f"{'THIN?':<6}{'Sector':<26}{'Industry':<44}{'n':>4}{'med':>8}{'min':>8}{'max':>8}{'spread':>8}")
    print("-" * 112)
    thin_by_sector: dict[str, list[tuple[str, int, float]]] = defaultdict(list)
    for sec, ind, n, med, spread, lo, hi in rows:
        thin = n < N_MIN
        mark = "THIN" if thin else ""
        print(f"{mark:<6}{sec:<26}{ind:<44}{n:>4}{med:>8.3f}{lo:>8.3f}{hi:>8.3f}{spread:>8.3f}")
        if thin:
            thin_by_sector[sec].append((ind, n, med))

    print("\n=== THIN industries (n < n_min=8) grouped by sector — the CT-B mapping candidates ===")
    for sec in sorted(thin_by_sector):
        inds = thin_by_sector[sec]
        total = sum(n for _, n, _ in inds)
        print(f"\n{sec}  (total thin pop={total} across {len(inds)} industries):")
        for ind, n, med in sorted(inds, key=lambda x: -x[1]):
            print(f"    {ind:<44} n={n:<3} med={med:.3f}")


if __name__ == "__main__":
    main()
