from app.models.screener_record import ScreenerRecord
from app.screener.deterministic_scorer import score_record


def _scored(**kw):
    r = ScreenerRecord(ticker="X", **kw)
    score_record(r)
    return r


def test_top_decile_profitability_scores_5():
    r = _scored(input_percentiles={"operating_margin": 92.0, "return_on_equity": 88.0},
                operating_margin=0.4, return_on_equity=0.3)
    assert r.gemini_dimensions["profitability"] == 5


def test_negative_operating_margin_red_flags_to_zero():
    r = _scored(input_percentiles={"operating_margin": 95.0}, operating_margin=-0.05)
    assert r.gemini_dimensions["profitability"] == 0


def test_high_leverage_red_flags_resilience_to_zero():
    # d/e in percent-points: 350 = 3.5x -> red flag
    r = _scored(input_percentiles={"gross_margin": 80.0}, gross_margin=0.5, debt_to_equity=350.0)
    assert r.gemini_dimensions["resilience"] == 0


def test_growth_capped_by_consistency():
    # P92 growth -> anchor 5, but ratio 0.25 -> cap 3
    r = _scored(input_percentiles={"revenue_growth_yoy": 92.0},
                revenue_growth_yoy=0.6, growth_consistency=0.25)
    assert r.gemini_dimensions["growth"] == 3


def test_unassessable_consistency_caps_growth_at_4_and_flags_low():
    r = _scored(input_percentiles={"revenue_growth_yoy": 99.0},
                revenue_growth_yoy=0.6, growth_consistency=None)
    assert r.gemini_dimensions["growth"] == 4
    assert r.data_confidence == "low"


def test_missing_axis_inputs_score_3_and_listed_as_gap():
    r = _scored(input_percentiles={}, growth_consistency=1.0)
    assert r.gemini_dimensions["profitability"] == 3
    assert "operating_margin/return_on_equity" in r.gemini_data_gaps


def test_sentinels_and_weakest_dimension():
    r = _scored(input_percentiles={"revenue_growth_yoy": 95.0, "operating_margin": 30.0,
                                   "gross_margin": 95.0},
                revenue_growth_yoy=0.3, operating_margin=0.1, gross_margin=0.7,
                growth_consistency=1.0)
    assert r.gemini_dimensions["management"] == 3
    assert r.gemini_dimensions["innovation"] == 3
    # profitability is the lone low merit axis (P30 -> 2)
    assert r.gemini_weakest_dimension == "profitability"


def test_evidence_cites_absolute_and_percentile():
    r = _scored(input_percentiles={"operating_margin": 82.0, "return_on_equity": 79.0},
                operating_margin=0.18, return_on_equity=0.22, growth_consistency=1.0)
    assert "18.0%" in r.gemini_evidence["profitability"]
    assert "P82" in r.gemini_evidence["profitability"]


class _FakeRevenueCache:
    def __init__(self, series): self._series = series
    def get_revenue_series(self, ticker): return self._series.get(ticker, [])


class _FakeTracker:
    def __init__(self): self.calls = []
    def record_ticker(self, tin, tout): self.calls.append((tin, tout))


def test_resilience_inversion_lower_leverage_scores_higher():
    # identical gross_margin percentile; lower d/e percentile (less levered) -> higher resilience
    low_lev = _scored(input_percentiles={"gross_margin": 50.0, "debt_to_equity": 20.0},
                      gross_margin=0.4, debt_to_equity=30.0)
    high_lev = _scored(input_percentiles={"gross_margin": 50.0, "debt_to_equity": 80.0},
                       gross_margin=0.4, debt_to_equity=120.0)
    assert low_lev.gemini_dimensions["resilience"] > high_lev.gemini_dimensions["resilience"]


def test_growth_data_gap_when_no_percentile():
    r = _scored(input_percentiles={"operating_margin": 50.0}, operating_margin=0.1,
                growth_consistency=1.0)
    assert r.gemini_dimensions["growth"] == 3
    assert "revenue_growth_yoy" in r.gemini_data_gaps


def test_partial_evidence_axes_flagged():
    # profitability has only operating_margin percentile (ROE absent) -> partial;
    # resilience has both gross_margin + d/e -> not partial
    r = _scored(input_percentiles={"operating_margin": 80.0, "gross_margin": 60.0,
                                   "debt_to_equity": 30.0},
                operating_margin=0.2, gross_margin=0.5, debt_to_equity=40.0,
                growth_consistency=1.0)
    assert r.partial_evidence_axes == ["profitability"]


def test_no_partial_when_both_inputs_present():
    r = _scored(input_percentiles={"operating_margin": 80.0, "return_on_equity": 75.0,
                                   "gross_margin": 60.0, "debt_to_equity": 30.0},
                operating_margin=0.2, return_on_equity=0.2, gross_margin=0.5,
                debt_to_equity=40.0, growth_consistency=1.0)
    assert r.partial_evidence_axes == []


def test_run_deterministic_scoring_end_to_end():
    from app.screener.deterministic_scorer import run_deterministic_scoring
    recs = [ScreenerRecord(ticker=f"I{i}", gics_sector="Industrials",
                           operating_margin=0.1 + i * 0.001, return_on_equity=0.1,
                           gross_margin=0.3, debt_to_equity=40.0,
                           revenue_growth_yoy=0.05 + i * 0.001) for i in range(30)]
    cache = _FakeRevenueCache({r.ticker: [100.0, 110.0, 120.0, 130.0] for r in recs})
    tracker = _FakeTracker()
    out = run_deterministic_scoring(recs, cache, tracker)
    assert all(r.gemini_dimensions is not None for r in out)
    assert all(r.growth_consistency == 1.0 for r in out)
    assert tracker.calls == [(0, 0)] * 30  # LLM-free: zero tokens per ticker
