"""
Acceptance test for the V3 basis-filter fix — basis-filter stage only.
Uses real YFinanceClientImpl (free, no API key) against a curated sample.
Covers: FX conversion, US/EU region counts, no exceptions.

Gemini-scoring (Top-50 US check) requires the full pipeline run — see local_acceptance_run.py.

Usage: uv run python scripts/acceptance_basis_filter.py
"""
from __future__ import annotations

import logging
import sys

from app.screener.runner import run_basis_filter
from app.services.yfinance_client import YFinanceClientImpl

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# Sample: 15 large-cap US tickers + 10 EU tickers
# Chosen to span currencies (USD, EUR, GBP, CHF, DKK) and sectors
US_SAMPLE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "JPM", "JNJ", "V", "PG", "KO",
    "XOM", "UNH", "NVDA", "MA", "HD",
]
EU_SAMPLE = [
    "NOVO-B.CO",  # DKK
    "SAP.DE",     # EUR
    "ASML.AS",    # EUR
    "ALV.DE",     # EUR
    "ROG.SW",     # CHF
    "AZN.L",      # GBP
    "NESN.SW",    # CHF
    "MC.PA",      # EUR
    "SIE.DE",     # EUR
    "AIR.PA",     # EUR
]

ALL_TICKERS = US_SAMPLE + EU_SAMPLE


def main() -> None:
    yfinance = YFinanceClientImpl()

    print(f"\nRunning basis filter on {len(ALL_TICKERS)} tickers "
          f"(US={len(US_SAMPLE)}, EU={len(EU_SAMPLE)})")
    print("=" * 60)

    records = run_basis_filter(ALL_TICKERS, yfinance).passed

    # Analyse results
    passed_us = [r for r in records if "." not in r.ticker]
    passed_eu = [r for r in records if "." in r.ticker]

    print("\n=== RESULT ===")
    print(f"Passed basis filter: {len(records)}/{len(ALL_TICKERS)}")
    print(f"  US passed: {len(passed_us)}/{len(US_SAMPLE)}")
    print(f"  EU passed: {len(passed_eu)}/{len(EU_SAMPLE)}")

    if passed_us:
        print(f"\nUS tickers that passed ({len(passed_us)}):")
        for r in passed_us:
            print(f"  {r.ticker:12s}  market_cap_eur={r.market_cap_eur/1e9:.1f}B"
                  f"  gross_margin={r.gross_margin!r}"
                  f"  rev_growth={r.revenue_growth_yoy!r}")
    else:
        print("\n  !! NO US TICKERS PASSED — BID/ASK FIX MAY NOT BE EFFECTIVE")

    if passed_eu:
        print(f"\nEU tickers that passed ({len(passed_eu)}):")
        for r in passed_eu:
            print(f"  {r.ticker:12s}  market_cap_eur={r.market_cap_eur/1e9:.1f}B"
                  f"  gross_margin={r.gross_margin!r}"
                  f"  rev_growth={r.revenue_growth_yoy!r}")

    # Criteria check
    ok_us_count = len(passed_us) >= 5  # expect most US large-caps to pass
    ok_no_crash = True  # if we got here, no exception
    ok_fx = all(r.market_cap_eur is not None for r in records)

    print("\n=== ACCEPTANCE CRITERIA ===")
    print(f"  [{'OK' if ok_no_crash else 'FAIL'}] No exceptions during run")
    print(f"  [{'OK' if ok_us_count else 'FAIL'}] >= 5 US large-caps pass filter (got {len(passed_us)})")
    print(f"  [{'OK' if ok_fx else 'FAIL'}] All passed records have market_cap_eur set")

    if not (ok_us_count and ok_fx):
        sys.exit(1)

    print("\nBasis-filter acceptance: PASS")
    print("Next step: run scripts/local_acceptance_run.py for full Gemini-scored Top-50 check")


if __name__ == "__main__":
    main()
