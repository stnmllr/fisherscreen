from __future__ import annotations

import statistics
from datetime import date, timedelta

from app.models.deep_dive_record import MultipleStats, ValuationHistory

# POLICY — fixiert, NICHT an Ticker-Pulls kalibriert (Spec §5).
VALUATION_COMPLETE_MIN_DENSITY = 40     # obs pro Jahr
VALUATION_PARTIAL_MIN_OBS = 52          # >= 1 Jahr wöchentlich

# DATEN-GEDECKELT — der realen GJ-Fundamental-Tiefe folgend (Task 0 / Spec §5).
# Probe-Pull: freie yfinance income_stmt = nur 4 GJ -> mit Lag ~3,1J nutzbare
# Tiefe -> 2.8 (knapp unter ~3J: complete = volle verfügbare Tiefe; IPO-junger
# 2J-Ticker bleibt korrekt partial).
VALUATION_COMPLETE_MIN_SPAN_YEARS = 2.8

# Look-ahead-Milderung: Fundamental erst ~1 Quartal nach Periodenende verfügbar.
REPORTING_LAG_DAYS = 90


def _median_p25(values: list[float]) -> tuple[float | None, float | None]:
    """Median + unteres 25-Perzentil (inclusive). Leere Liste -> (None, None);
    Einzelwert -> (v, v) (quantiles braucht >=2 Punkte)."""
    if not values:
        return None, None
    if len(values) == 1:
        return float(values[0]), float(values[0])
    med = statistics.median(values)
    p25 = statistics.quantiles(values, n=4, method="inclusive")[0]
    return float(med), float(p25)
