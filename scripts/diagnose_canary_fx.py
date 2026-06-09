"""Punkt 1 GATE-A: verify the FX-conversion path for the 3 lowest survivors
(canaries near the EUR1M floor), which are non-EUR/non-USD (NOK/SEK). A wrong FX
direction (EUR-per-unit vs unit-per-EUR) would shift their value ~135x. Confirms
get_fx_rate returns EUR-per-1-unit (small for NOK/SEK) and the computed value
matches the histogram (~2.45M / 3.72M / 4.64M). $0 (warm cache).
Run: uv run python scripts\\diagnose_canary_fx.py"""
from __future__ import annotations

from app.models.screener_record import ScreenerRecord
from app.screener.compose import build_screener_pipeline
from app.services.yfinance_client import YFinanceClientImpl

CANARIES = ["LSG.OL", "WIHL.ST", "SWEC-B.ST"]


def main() -> None:
    yf = build_screener_pipeline()
    raw = YFinanceClientImpl()
    print(f"{'ticker':12} {'ccy':5} {'price':>10} {'avgVol':>10} {'fx(EUR/unit)':>13} {'value_EURm':>11}")
    for t in CANARIES:
        info = yf.get_ticker_info(t)
        rec = ScreenerRecord.from_yfinance_info(t, info)
        fx = raw.get_fx_rate(rec.currency)
        value = rec.avg_daily_volume * rec.price * fx
        print(f"{t:12} {str(rec.currency):5} {rec.price:>10.2f} "
              f"{rec.avg_daily_volume:>10.0f} {fx:>13.5f} {value/1e6:>11.3f}")
    print("\nSanity: NOK/SEK fx must be ~0.08-0.10 EUR per unit (NOT ~10-12). "
          "value must match histogram (LSG~2.45 WIHL~3.72 SWEC~4.64).")


if __name__ == "__main__":
    main()
