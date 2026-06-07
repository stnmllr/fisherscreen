"""0a GATE-2 acceptance follow-up: (1) tabulate where each of the 12 rehab-add
symbols landed in the dry-run dropouts (offline), confirm none died at GATE_VOLUME
and identify the survivor(s); (2) live-classify RNL.PA / GLB.IR / ML.PA to decide
0b-case (EQUITY with partial dict) vs 0a-miss (MUTUALFUND the enumeration missed).
$0. Run: uv run python scripts\\diagnose_0a_acceptance.py"""
from __future__ import annotations

import csv
from pathlib import Path

from app.errors import DataSourceError, DegradedDataError
from app.services.yfinance_client import YFinanceClientImpl
from scripts.diagnose_symbol_contaminants import classify_info

DROPOUTS = Path("output/Universum/2026-06-dropouts.csv")
REHAB_ADDS = ["AI.PA", "ATO.PA", "BNP.PA", "ACA.PA", "CAP.PA", "CA.PA",
              "EVD.DE", "BN.PA", "ENX.PA", "ML.PA", "RI.PA", "RNO.PA"]
CLASSIFY = ["RNL.PA", "GLB.IR", "ML.PA"]


def landing() -> None:
    rows = {r["ticker"]: r for r in csv.DictReader(DROPOUTS.open(encoding="utf-8"))}
    print("=== Rehab-add landing (12) ===")
    volume_deaths = []
    survivors = []
    for t in REHAB_ADDS:
        r = rows.get(t)
        if r is None:
            survivors.append(t)
            print(f"  {t:8} SURVIVED (not in dropouts -> reached edgar-remaining/688)")
            continue
        mc = r["market_cap_eur"][:6] if r["market_cap_eur"] else "-"
        print(f"  {t:8} {r['reason_code']:20} {r['severity_bucket']:7} mc={mc:7} {r['gics_sector']}")
        if r["reason_code"] == "GATE_VOLUME":
            volume_deaths.append(t)
    print(f"\nsurvivors (M): {survivors or 'NONE'}")
    print(f"died at GATE_VOLUME (would be spurious Punkt-1 bug): {volume_deaths or 'NONE'}")


def classify() -> None:
    client = YFinanceClientImpl()
    print("\n=== Live classification (0b-case vs 0a-miss) ===")
    for t in CLASSIFY:
        try:
            info = client.get_ticker_info(t)
        except DegradedDataError:
            print(f"  {t:8} DEGRADED (raises DegradedDataError)")
            continue
        except DataSourceError as exc:
            print(f"  {t:8} DataSourceError: {exc}")
            continue
        status = classify_info(info)
        verdict = ("0a-MISS (MUTUALFUND!)" if status == "CONTAMINANT"
                   else "0b-case (EQUITY, partial dict)" if status == "EQUITY"
                   else status)
        print(f"  {t:8} quoteType={info.get('quoteType')} "
              f"marketCap={info.get('marketCap')} avgVol={info.get('averageVolume')} "
              f"name={info.get('shortName') or info.get('longName')} -> {verdict}")


if __name__ == "__main__":
    landing()
    classify()
