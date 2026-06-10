"""Unit tests for the shared universe-cleaning helper (Punkt 2, CT-B calibration).

ONE cleaning definition shared by A2, A3, and the dispersion instrument so the
rescue analysis is evaluated against the same median table that would deploy.
Decision (DEFECT 2): negatives OUT by default, NO sector-string filter (the
METRIK_NA set already removes the balance-sheet financials; Capital-Markets
compounders are DEFINED and must stay).
"""
from __future__ import annotations

from app.models.screener_record import ScreenerRecord
from app.screener.universe_cleaning import clean_universe


def _rec(ticker: str, *, gm: float | None, sector: str | None = None) -> ScreenerRecord:
    return ScreenerRecord(ticker=ticker, gross_margin=gm, gics_sector=sector)


def test_metrik_na_excluded():
    recs = [_rec("AAA", gm=0.40), _rec("BBB", gm=0.50)]
    out = clean_universe(recs, {"BBB"})
    assert [r.ticker for r in out] == ["AAA"]


def test_negatives_excluded_by_default():
    recs = [_rec("POS", gm=0.40), _rec("ZERO", gm=0.0), _rec("NEG", gm=-0.10)]
    out = clean_universe(recs, set())
    assert [r.ticker for r in out] == ["POS"]


def test_none_gm_excluded_by_default():
    recs = [_rec("POS", gm=0.40), _rec("NONE", gm=None)]
    out = clean_universe(recs, set())
    assert [r.ticker for r in out] == ["POS"]


def test_negatives_kept_when_include_defined_negative_true():
    recs = [_rec("POS", gm=0.40), _rec("ZERO", gm=0.0), _rec("NEG", gm=-0.10)]
    out = clean_universe(recs, set(), include_defined_negative=True)
    assert {r.ticker for r in out} == {"POS", "ZERO", "NEG"}


def test_none_gm_still_excluded_when_include_defined_negative_true():
    # include_defined_negative keeps gm<=0, but a None gm has no value to bucket on.
    recs = [_rec("POS", gm=0.40), _rec("NONE", gm=None)]
    out = clean_universe(recs, set(), include_defined_negative=True)
    assert [r.ticker for r in out] == ["POS"]


def test_metrik_na_still_excluded_when_include_defined_negative_true():
    recs = [_rec("AAA", gm=-0.10), _rec("BBB", gm=0.50)]
    out = clean_universe(recs, {"BBB"}, include_defined_negative=True)
    assert [r.ticker for r in out] == ["AAA"]


def test_financial_sector_defined_record_not_dropped():
    # No sector-string filter: a DEFINED gm>0 Capital-Markets / Financial-Services
    # compounder (NOT in METRIK_NA) must survive cleaning.
    recs = [
        _rec("SPGI", gm=0.68, sector="Financial Services"),
        _rec("PLD", gm=0.75, sector="Real Estate"),
    ]
    out = clean_universe(recs, set())
    assert {r.ticker for r in out} == {"SPGI", "PLD"}
