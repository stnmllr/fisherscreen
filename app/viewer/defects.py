"""Dated table of known data defects in generated dossiers.

Replaces the statically suppressed metric list of the original spec. A
defect never removes a value from the rendered page — omitting a number
claims "there is none" while the dossier plainly shows one. It only
attaches a marker plus an explanatory note.

Two consequences of "the viewer does not compute":

* Membership is decided by metric key, ticker and `quant_date` alone. The
  value itself is never inspected, so a plausible-looking number inside a
  known-buggy window is marked too (KO's 2.6 % dividend yield is correct
  and still gets a marker). The notes are worded accordingly: they talk
  about the run, not about the number.
* `defects_for` never raises. It is called once per rendered cell; an
  exception there would take down a whole page over a footnote.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Final

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DataDefect:
    """One known defect of one metric.

    `tickers` None means "every ticker"; `quant_date_until` None means the
    fix has not landed yet, so every dossier is affected.
    """

    metric_key: str
    tickers: frozenset[str] | None
    quant_date_until: date | None
    note: str


_DIVIDEND_YIELD_FIXED_AFTER: Final[date] = date(2026, 6, 1)

_ARGX: Final[str] = "ARGX"

_ARGX_EV_NOTE: Final[str] = (
    "Für ARGX rechnet Yahoo den Enterprise Value mit floatShares "
    "(1,56 Mrd.) statt sharesOutstanding (62,6 Mio.) — Faktor ~27. "
    "Größenordnungs-Referenz: EV/EBIT ≈ 46,4 und EV/Sales ≈ 14,3. "
    "Andere Titel sind nicht betroffen und deshalb nicht markiert."
)

_DIVIDEND_YIELD_NOTE: Final[str] = (
    "Dossiers aus diesem Zeitraum hatten einen bekannten Div-Yield-Bug: "
    "yfinance lieferte Prozentwerte, die als Ratio weiterverarbeitet wurden. "
    "Behoben in quant_join._resolve_dividend_yield; Läufe ab 2026-06-02 sind "
    "nicht betroffen. Der angezeigte Wert ist unverändert der aus dem Dossier."
)

KNOWN_DATA_DEFECTS: Final[tuple[DataDefect, ...]] = (
    DataDefect(
        metric_key="dividend_yield",
        tickers=None,
        quant_date_until=_DIVIDEND_YIELD_FIXED_AFTER,
        note=_DIVIDEND_YIELD_NOTE,
    ),
    DataDefect(
        metric_key="total_shareholder_yield",
        tickers=None,
        quant_date_until=_DIVIDEND_YIELD_FIXED_AFTER,
        note=(
            "Enthält den Div-Yield als Summand: Dossiers aus diesem Zeitraum "
            "hatten den bekannten Div-Yield-Bug (Prozentwert als Ratio "
            "weiterverarbeitet), der Buyback-Anteil ist davon unberührt."
        ),
    ),
    DataDefect(
        metric_key="debt_to_equity",
        tickers=None,
        quant_date_until=None,
        note=(
            "Einheiten-Mismatch: yfinance liefert D/E in Prozentpunkten, das "
            "Dossier rendert den Rohwert einheitenlos. »D/E 0.6« meint hier "
            "0,6 %, nicht 60 %. Kein Fix gelandet — Wert entsprechend lesen."
        ),
    ),
    DataDefect(
        metric_key="ev_ebit",
        tickers=frozenset({_ARGX}),
        quant_date_until=None,
        note=_ARGX_EV_NOTE,
    ),
    DataDefect(
        metric_key="ev_sales",
        tickers=frozenset({_ARGX}),
        quant_date_until=None,
        note=_ARGX_EV_NOTE,
    ),
    DataDefect(
        metric_key="valuation_range",
        tickers=None,
        quant_date_until=None,
        note=(
            "Die Range-Zeile stellt den .info-Enterprise-Value (TTM) einem "
            "selbst gerechneten EV (Median) gegenüber — zwei verschiedene "
            "EV-Definitionen in einem Vergleich. Die TTM- und die "
            "Median-Spalte sind daher nicht direkt gegeneinander lesbar."
        ),
    ),
)


def _applies(defect: DataDefect, ticker: str, quant_date: date) -> bool:
    if defect.tickers is not None and ticker not in defect.tickers:
        return False
    return defect.quant_date_until is None or quant_date <= defect.quant_date_until


def defects_for(ticker: str, quant_date: date | None) -> dict[str, DataDefect]:
    """Known defects for one dossier, keyed by metric key. Empty dict = clean.

    A dossier without `quant_date` cannot be placed on the timeline at all,
    so no entry is claimed for it — a marker whose window we cannot check
    would be a guess. Every dossier the parser accepts carries the field.
    """
    if quant_date is None:
        return {}
    return {
        defect.metric_key: defect
        for defect in KNOWN_DATA_DEFECTS
        if _applies(defect, ticker, quant_date)
    }
