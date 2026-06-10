"""Shared universe-cleaning definition for the Punkt-2 calibration probes.

ONE cleaning rule consumed by A2 (median table), A3 (k-calibration) and the
dispersion/acceptance instrument, so the rescue analysis is evaluated against the
exact medians that would deploy. Previously these scripts diverged (A2 kept gm<=0
and Capital-Markets financials; the probe/A3 dropped a Financials/RealEstate
sector string and gm<=0) -> bucket medians differed -> the analysis ran against a
table that was not the one to ship. DEFECT 2 fix unifies them here.

Decisions baked in:
- METRIK_NA is ALWAYS excluded (A1's waterfall-based set already removes the
  balance-sheet financials that have no genuine COGS structure).
- NO sector-string filter. The Capital-Markets compounders (S&P Global, Moody's,
  MSCI, exchanges, asset managers) are DEFINED and must contribute to their own
  bucket median; a sector-string sweep would wrongly drop them.
- Negatives OUT by default. The median is a representativeness anchor for
  "normal-low-but-viable"; gm<=0 names are the pathological tail the gate exists
  to exclude — including them lowers the bar. include_defined_negative=True is the
  opt-in for diagnostics that deliberately want them in.
"""
from __future__ import annotations

from app.models.screener_record import ScreenerRecord


def clean_universe(
    records: list[ScreenerRecord],
    metrik_na: set[str],
    *,
    include_defined_negative: bool = False,
) -> list[ScreenerRecord]:
    """Return the cleaned subset of ``records`` for median/calibration analysis.

    Always drops ``rec.ticker in metrik_na``. By default also drops records whose
    ``gross_margin`` is None or <= 0 (negatives OUT). With
    ``include_defined_negative=True`` the gm<=0 names are kept (only a None
    gross_margin is still dropped — it has no value to bucket on); METRIK_NA stays
    excluded regardless. No sector-string filter is applied in either mode.
    """
    cleaned: list[ScreenerRecord] = []
    for rec in records:
        if rec.ticker in metrik_na:
            continue
        gm = rec.gross_margin
        if gm is None:
            continue
        if not include_defined_negative and gm <= 0:
            continue
        cleaned.append(rec)
    return cleaned
