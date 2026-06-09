"""Punkt 1 GATE-B follow-up: verify the 2 names the VALUE floor newly caught
(BPOST.BR, ONTEX.BR) are genuine <EUR1M-value (low-price/high-share) — correct
catches, not a bug — and report their market cap (severity). $0 (warm cache —
populated by the cold run). Run: uv run python scripts\\diagnose_newly_caught.py"""
from __future__ import annotations

from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline
from app.services.yfinance_client import YFinanceClientImpl

NAMES = ["BPOST.BR", "ONTEX.BR"]


def main() -> None:
    yf = build_screener_pipeline()
    raw = YFinanceClientImpl()
    print(f"{'ticker':10} {'ccy':4} {'price':>9} {'avgVol':>11} {'value_EURm':>11} {'mcap_EURb':>10}")
    for t in NAMES:
        rec = ScreenerRecord.from_yfinance_info(t, yf.get_ticker_info(t))
        fx = raw.get_fx_rate(rec.currency)
        value = rec.avg_daily_volume * rec.price * fx
        mcap = (rec.market_cap * fx) if rec.market_cap else None
        print(f"{t:10} {str(rec.currency):4} {rec.price:>9.2f} {rec.avg_daily_volume:>11.0f} "
              f"{value/1e6:>11.3f} {(mcap/1e9 if mcap else 0):>10.2f}")
    print("\nExpect value < 1.0M (correct catch) and mcap < 3B (BENIGN severity).")


if __name__ == "__main__":
    main()
