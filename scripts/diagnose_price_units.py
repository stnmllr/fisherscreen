"""Punkt 1 calibration follow-up: inspect raw cached fields for the suspicious
value outliers to confirm (a) the London pence trap (currency 'GBp', price in
pence while marketCap in GBP) and (b) implausibly-low averageVolume. $0 (warm
cache). Run: uv run python scripts\\diagnose_price_units.py"""
from __future__ import annotations

from app.screener.compose import build_screener_pipeline

SUSPECTS = ["GAW.L", "FLTR.L", "AZN.L", "FER.AS", "1COV.DE", "LISN.SW", "NVR"]


def main() -> None:
    yf = build_screener_pipeline()
    print(f"{'ticker':10} {'currency':9} {'price':>12} {'marketCap':>16} {'avgVol':>12}")
    for t in SUSPECTS:
        try:
            i = yf.get_ticker_info(t)
        except Exception as exc:  # noqa: BLE001
            print(f"{t:10} ERROR {exc}")
            continue
        price = i.get("currentPrice") or i.get("regularMarketPrice")
        print(f"{t:10} {str(i.get('currency')):9} {str(price):>12} "
              f"{str(i.get('marketCap')):>16} {str(i.get('averageVolume')):>12}")


if __name__ == "__main__":
    main()
