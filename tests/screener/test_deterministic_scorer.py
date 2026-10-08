import pytest

from app.models.screener_record import ScreenerRecord
from app.screener.deterministic_scorer import score_record


def _scored(**kw):
    r = ScreenerRecord(ticker="X", **kw)
    score_record(r)
    return r


def test_top_decile_profitability_scores_5():
    r = _scored(
        input_percentiles={
            "operating_margin": 92.0,
            "return_on_invested_capital": 88.0,
        },
        operating_margin=0.4,
        return_on_invested_capital=0.3,
    )
    assert r.gemini_dimensions["profitability"] == 5


def test_negative_operating_margin_red_flags_to_zero():
    r = _scored(input_percentiles={"operating_margin": 95.0}, operating_margin=-0.05)
    assert r.gemini_dimensions["profitability"] == 0


def test_high_debt_to_equity_alone_no_longer_red_flags_resilience():
    # d/e 350 % with modest net debt/EBITDA: buyback cosmetics, not distress
    r = _scored(
        input_percentiles={"gross_margin": 80.0},
        gross_margin=0.5,
        debt_to_equity=350.0,
        total_debt=1.0e9,
        total_cash=0.5e9,
        ebitda=1.0e9,
    )
    assert r.gemini_dimensions["resilience"] > 0
    assert r.resilience_red_flag is None


def test_growth_capped_by_consistency():
    # P92 median growth -> anchor 5, but ratio 0.25 -> cap 3
    r = _scored(
        input_percentiles={"revenue_growth_median": 92.0},
        revenue_growth_median=0.3,
        growth_consistency=0.25,
    )
    assert r.gemini_dimensions["growth"] == 3


def test_unassessable_consistency_caps_growth_at_4_and_flags_low():
    r = _scored(
        input_percentiles={"revenue_growth_median": 99.0},
        revenue_growth_median=0.3,
        growth_consistency=None,
    )
    assert r.gemini_dimensions["growth"] == 4
    assert r.data_confidence == "low"


def test_missing_axis_inputs_score_3_and_listed_as_gap():
    r = _scored(input_percentiles={}, growth_consistency=1.0)
    assert r.gemini_dimensions["profitability"] == 3
    assert "operating_margin/return_on_invested_capital" in r.gemini_data_gaps


def test_sentinels_and_weakest_dimension():
    r = _scored(
        input_percentiles={
            "revenue_growth_yoy": 95.0,
            "operating_margin": 30.0,
            "gross_margin": 95.0,
        },
        revenue_growth_yoy=0.3,
        operating_margin=0.1,
        gross_margin=0.7,
        growth_consistency=1.0,
    )
    assert r.gemini_dimensions["management"] == 3
    assert r.gemini_dimensions["innovation"] == 3
    # profitability is the lone low merit axis (P30 -> 2)
    assert r.gemini_weakest_dimension == "profitability"


def test_evidence_cites_absolute_and_percentile():
    r = _scored(
        input_percentiles={
            "operating_margin": 82.0,
            "return_on_invested_capital": 79.0,
        },
        operating_margin=0.18,
        return_on_invested_capital=0.22,
        growth_consistency=1.0,
    )
    assert "18.0%" in r.gemini_evidence["profitability"]
    assert "P82" in r.gemini_evidence["profitability"]


class _FakeRevenueCache:
    def __init__(self, series):
        self._series = series

    def get_revenue_series(self, ticker):
        return self._series.get(ticker, [])


class _FakeTracker:
    def __init__(self):
        self.calls = []

    def record_ticker(self, tin, tout):
        self.calls.append((tin, tout))


def test_lower_leverage_scores_higher_resilience():
    # identical gross_margin percentile; net cash beats 3.5x net debt/EBITDA
    low_lev = _scored(
        input_percentiles={"gross_margin": 50.0},
        gross_margin=0.4,
        total_debt=0.0,
        total_cash=1.0e9,
        ebitda=1.0e9,
    )
    high_lev = _scored(
        input_percentiles={"gross_margin": 50.0},
        gross_margin=0.4,
        total_debt=3.5e9,
        total_cash=0.0,
        ebitda=1.0e9,
    )
    assert (
        low_lev.gemini_dimensions["resilience"]
        > high_lev.gemini_dimensions["resilience"]
    )


def test_growth_data_gap_when_no_percentile():
    r = _scored(
        input_percentiles={"operating_margin": 50.0},
        operating_margin=0.1,
        growth_consistency=1.0,
    )
    assert r.gemini_dimensions["growth"] == 3
    assert "revenue_growth_median" in r.gemini_data_gaps
    assert "revenue_growth_yoy" in r.gemini_data_gaps


def test_partial_evidence_axes_flagged():
    # profitability has only operating_margin percentile (ROIC absent) -> partial;
    # resilience has both gross_margin + a leverage band -> not partial
    r = _scored(
        input_percentiles={"operating_margin": 80.0, "gross_margin": 60.0},
        operating_margin=0.2,
        gross_margin=0.5,
        total_debt=1.0e9,
        total_cash=0.0,
        ebitda=1.0e9,
        growth_consistency=1.0,
    )
    assert r.partial_evidence_axes == ["profitability"]


def test_no_partial_when_both_inputs_present():
    r = _scored(
        input_percentiles={
            "operating_margin": 80.0,
            "return_on_invested_capital": 75.0,
            "gross_margin": 60.0,
        },
        operating_margin=0.2,
        return_on_invested_capital=0.2,
        gross_margin=0.5,
        total_debt=1.0e9,
        total_cash=0.0,
        ebitda=1.0e9,
        growth_consistency=1.0,
    )
    assert r.partial_evidence_axes == []


def test_run_deterministic_scoring_end_to_end():
    from app.screener.deterministic_scorer import run_deterministic_scoring

    recs = [
        ScreenerRecord(
            ticker=f"I{i}",
            gics_sector="Industrials",
            operating_margin=0.1 + i * 0.001,
            total_revenue=1000.0,
            gross_margin=0.3,
            debt_to_equity=40.0,
            total_debt=100.0 + i,
            total_cash=50.0,
            revenue_growth_yoy=0.05 + i * 0.001,
        )
        for i in range(30)
    ]
    # a stale value must be recomputed, never trusted
    recs[0].return_on_invested_capital = 99.0
    cache = _FakeRevenueCache({r.ticker: [100.0, 110.0, 120.0, 130.0] for r in recs})
    tracker = _FakeTracker()
    out = run_deterministic_scoring(recs, cache, tracker)
    assert all(r.gemini_dimensions is not None for r in out)
    assert all(r.growth_consistency == 1.0 for r in out)
    assert tracker.calls == [(0, 0)] * 30  # LLM-free: zero tokens per ticker
    # ROIC is computed before the percentiles, so it is ranked
    assert out[0].return_on_invested_capital == pytest.approx(100.0 / 300.0)
    assert out[0].roic_missing_reason is None
    assert all("return_on_invested_capital" in r.input_percentiles for r in out)


def test_run_deterministic_scoring_records_missing_roic_reason():
    from app.screener.deterministic_scorer import run_deterministic_scoring

    rec = ScreenerRecord(ticker="NOREV", operating_margin=0.2, total_debt=10.0)
    run_deterministic_scoring(
        [rec], _FakeRevenueCache({"NOREV": [1.0, 2.0, 3.0, 4.0]}), _FakeTracker()
    )
    assert rec.return_on_invested_capital is None
    assert rec.roic_missing_reason == "no_ebit"
    assert "return_on_invested_capital" not in rec.input_percentiles
    assert "roic" in rec.gemini_data_gaps


# --- resilience: net debt / EBITDA on fixed absolute bands -------------------
#
# Debt/equity measured buyback cosmetics: MA (tiny book equity) scored 0, TDG
# (6x net debt/EBITDA, negative equity -> D/E excluded) scored 5. Leverage is now
# net debt / EBITDA against fixed bands; red flag above 4.0x.

_EBITDA = 1.0e9


def _lev(ratio: float | None = None, gm_p: float | None = None, **kw):
    """Record with net debt = ratio x EBITDA (no cash) and an optional gross-margin
    percentile."""
    fields = dict(kw)
    if ratio is not None:
        fields.setdefault("total_debt", ratio * _EBITDA)
        fields.setdefault("total_cash", 0.0)
        fields.setdefault("ebitda", _EBITDA)
    pcts = {} if gm_p is None else {"gross_margin": gm_p}
    if gm_p is not None:
        fields.setdefault("gross_margin", 0.5)
    return _scored(input_percentiles=pcts, growth_consistency=1.0, **fields)


@pytest.mark.parametrize(
    "ratio,band,score",
    [
        (0.0, 100, 5),
        (0.01, 85, 5),
        (1.0, 85, 5),
        (1.01, 65, 4),
        (2.0, 65, 4),
        (2.01, 45, 4),
        (3.0, 45, 4),
        (3.01, 25, 3),
        (4.0, 25, 3),
    ],
)
def test_leverage_band_boundaries(ratio, band, score):
    # gross margin P100 -> score = percentile_to_score((band + 100) / 2)
    r = _lev(ratio, gm_p=100.0)
    assert f"band {band})" in r.gemini_evidence["resilience"]
    assert r.gemini_dimensions["resilience"] == score
    assert r.resilience_red_flag is None


def test_just_above_four_is_a_red_flag():
    r = _lev(4.01, gm_p=95.0)
    assert r.gemini_dimensions["resilience"] == 0
    assert r.resilience_red_flag == "net_debt_to_ebitda_above_4"


def test_band_is_averaged_with_gross_margin_percentile():
    # (85 + 64) / 2 = 74.5 -> 4
    r = _lev(0.3, gm_p=64.0, gross_margin=0.68)
    assert r.gemini_dimensions["resilience"] == 4
    assert r.partial_evidence_axes == []
    assert r.gemini_evidence["resilience"] == (
        "gross margin 68.0% (P64), net debt/EBITDA 0.3x (band 85)"
    )


def test_net_cash_gets_full_band():
    r = _lev(
        gm_p=58.0, gross_margin=0.67, total_debt=0.0, total_cash=1.2e9, ebitda=_EBITDA
    )
    # (100 + 58) / 2 = 79 -> 4
    assert r.gemini_dimensions["resilience"] == 4
    assert r.gemini_evidence["resilience"] == (
        "gross margin 67.0% (P58), net cash (net debt/EBITDA -1.2x, band 100)"
    )


def test_red_flag_evidence_cites_the_ratio():
    r = _lev(6.0, gm_p=91.0, gross_margin=0.60)
    assert r.gemini_dimensions["resilience"] == 0
    assert r.gemini_evidence["resilience"] == (
        "gross margin 60.0% (P91), net debt/EBITDA 6.0x — RED FLAG > 4.0x"
    )


def test_net_debt_with_nonpositive_ebitda_is_a_red_flag():
    r = _lev(gm_p=80.0, total_debt=2.0e9, total_cash=0.5e9, ebitda=-1.0e8)
    assert r.gemini_dimensions["resilience"] == 0
    assert r.resilience_red_flag == "net_debt_with_nonpositive_ebitda"
    assert r.gemini_evidence["resilience"].endswith(
        "net debt with EBITDA <= 0 — RED FLAG"
    )


def test_net_cash_with_nonpositive_ebitda_is_capped_neutral():
    r = _lev(gm_p=95.0, total_debt=0.0, total_cash=1.0e9, ebitda=0.0)
    assert r.gemini_dimensions["resilience"] == 3
    assert r.resilience_red_flag is None
    assert r.data_confidence == "low"
    assert "capped at 3" in r.gemini_evidence["resilience"]


def test_ibkr_case_missing_ebitda_caps_resilience_at_3_not_5():
    """Broker: gross margin P95 would score 5 on its own; a missing leverage
    input must never score better than neutral."""
    r = _lev(gm_p=95.0, gross_margin=0.95, total_debt=1.0e10, total_cash=5.0e10)
    assert r.gemini_dimensions["resilience"] == 3
    assert r.resilience_red_flag is None
    assert "ebitda" in r.gemini_data_gaps
    assert r.data_confidence == "low"
    assert r.gemini_evidence["resilience"] == (
        "gross margin 95.0% (P95), net debt/EBITDA n/a (no EBITDA) — capped at 3"
    )


def test_missing_leverage_keeps_a_weak_gross_margin_score():
    # cap only lowers: P20 gross margin alone -> 2, stays 2
    r = _lev(gm_p=20.0, ebitda=None)
    assert r.gemini_dimensions["resilience"] == 2


def test_missing_debt_and_cash_is_a_net_debt_gap():
    r = _lev(gm_p=50.0, ebitda=_EBITDA)
    assert r.gemini_dimensions["resilience"] == 3
    assert "net_debt" in r.gemini_data_gaps
    assert r.data_confidence == "low"


def test_one_of_debt_or_cash_is_enough_for_net_debt():
    # only cash known -> net debt = -cash -> net cash band
    r = _lev(total_cash=1.0e9, ebitda=_EBITDA)
    assert "band 100" in r.gemini_evidence["resilience"]
    r = _lev(total_debt=1.5e9, ebitda=_EBITDA)
    assert "net debt/EBITDA 1.5x (band 65)" in r.gemini_evidence["resilience"]


def test_no_resilience_inputs_at_all_scores_3():
    r = _lev()
    assert r.gemini_dimensions["resilience"] == 3
    assert {"net_debt", "ebitda"} <= set(r.gemini_data_gaps)


def test_missing_gross_margin_percentile_caps_band_at_3_and_is_partial():
    r = _lev(0.5)
    assert r.gemini_dimensions["resilience"] == 3  # band 85 alone would be 4
    assert r.partial_evidence_axes == ["resilience"]
    assert "gross_margin" in r.gemini_data_gaps
    assert r.data_confidence == "low"
    assert r.gemini_evidence["resilience"] == (
        "gross margin n/a, net debt/EBITDA 0.5x (band 85) — capped at 3"
    )


def test_net_cash_with_missing_gross_margin_scores_3_not_5():
    r = _lev(total_debt=0.0, total_cash=1.0e9, ebitda=_EBITDA)
    assert r.gemini_dimensions["resilience"] == 3
    assert "capped at 3" in r.gemini_evidence["resilience"]


def test_missing_gross_margin_cap_never_raises_a_weak_band():
    r = _lev(3.5)  # band 25 alone -> 2, stays 2
    assert r.gemini_dimensions["resilience"] == 2


def test_red_flag_with_missing_gross_margin_stays_zero_without_cap_note():
    r = _lev(6.0)
    assert r.gemini_dimensions["resilience"] == 0
    assert "gross_margin" in r.gemini_data_gaps
    assert "capped" not in r.gemini_evidence["resilience"]


def test_gross_margin_without_leverage_is_partial():
    r = _lev(gm_p=60.0, ebitda=None)
    assert "resilience" in r.partial_evidence_axes


@pytest.mark.parametrize("sector", ["Utilities", "Real Estate"])
def test_structural_sectors_get_band_zero_instead_of_red_flag(sector):
    # (0 + 80) / 2 = 40 -> 3
    r = _lev(5.5, gm_p=80.0, gross_margin=0.4, gics_sector=sector)
    assert r.resilience_red_flag is None
    assert r.gemini_dimensions["resilience"] == 3
    assert r.gemini_evidence["resilience"] == (
        "gross margin 40.0% (P80), net debt/EBITDA 5.5x "
        "(band 0, structural sector — no red flag)"
    )


@pytest.mark.parametrize("sector", ["Utilities", "Real Estate"])
def test_structural_sectors_exempt_for_nonpositive_ebitda_too(sector):
    r = _lev(
        gm_p=80.0, total_debt=1.0e9, total_cash=0.0, ebitda=-1.0, gics_sector=sector
    )
    assert r.resilience_red_flag is None
    assert r.gemini_dimensions["resilience"] == 3
    assert "structural sector — no red flag" in r.gemini_evidence["resilience"]


def test_ma_like_case_high_debt_to_equity_low_net_leverage_is_not_flagged():
    # MA: D/E ~440 % (tiny book equity) but net debt/EBITDA ~0.6
    r = _lev(0.6, gm_p=90.0, debt_to_equity=440.0, gics_sector="Financial Services")
    assert r.resilience_red_flag is None
    assert r.gemini_dimensions["resilience"] == 4  # (85 + 90) / 2 = 87.5 -> 4


def test_tdg_like_case_negative_equity_high_net_leverage_is_flagged():
    # TDG: negative book equity (D/E < 0) used to slip past; 6x net debt/EBITDA
    r = _lev(6.0, gm_p=95.0, debt_to_equity=-300.0, gics_sector="Industrials")
    assert r.resilience_red_flag == "net_debt_to_ebitda_above_4"
    assert r.gemini_dimensions["resilience"] == 0


def test_red_flag_is_cleared_on_rescore():
    r = _lev(6.0, gm_p=95.0)
    assert r.resilience_red_flag is not None
    r.total_debt = 0.5 * _EBITDA
    score_record(r)
    assert r.resilience_red_flag is None


# --- profitability: operating margin + ROIC ------------------------------------
#
# ROE measured buyback cosmetics: book equity shrinks to ~0 or below (FTNT ROE
# 117 %, 31 red flags from negative equity alone). ROIC replaces it.


def _prof(
    op_p: float | None = 95.0,
    roic_p: float | None = 95.0,
    *,
    roic: float | None = 0.3,
    reason: str | None = None,
    sector: str | None = "Technology",
    op: float = 0.3,
):
    pcts = {}
    if op_p is not None:
        pcts["operating_margin"] = op_p
    if roic_p is not None:
        pcts["return_on_invested_capital"] = roic_p
    return _scored(
        input_percentiles=pcts,
        operating_margin=op,
        return_on_invested_capital=roic,
        roic_missing_reason=reason,
        gics_sector=sector,
        growth_consistency=1.0,
    )


def test_roe_no_longer_participates_in_profitability():
    r = _scored(
        input_percentiles={"operating_margin": 95.0, "return_on_equity": 5.0},
        operating_margin=0.3,
        return_on_equity=-2.0,  # negative book equity: cosmetic, not a loss
        return_on_invested_capital=0.4,
        growth_consistency=1.0,
    )
    # ROIC has no percentile here -> op margin alone; ROE is ignored entirely
    assert r.gemini_dimensions["profitability"] == 5
    assert "ROE" not in r.gemini_evidence["profitability"]


def test_profitability_averages_op_margin_and_roic_percentiles():
    # mean(P95, P45) = 70 -> 4
    r = _prof(95.0, 45.0)
    assert r.gemini_dimensions["profitability"] == 4
    assert "roic" not in r.gemini_data_gaps
    assert "profitability" not in r.partial_evidence_axes


def test_negative_roic_red_flags_to_zero():
    r = _prof(95.0, 2.0, roic=-0.05)
    assert r.gemini_dimensions["profitability"] == 0


def test_negative_equity_with_positive_ebit_is_scored_not_flagged():
    from app.screener.roic import annotate_roic

    rec = ScreenerRecord(
        ticker="NEGEQ",
        operating_margin=0.1,
        total_revenue=100.0,
        total_debt=20.0,
        debt_to_equity=-200.0,  # equity -10
        total_cash=5.0,  # IC 5
        growth_consistency=1.0,
    )
    annotate_roic([rec])
    rec.input_percentiles = {
        "operating_margin": 90.0,
        "return_on_invested_capital": 90.0,
    }
    score_record(rec)
    assert rec.return_on_invested_capital == pytest.approx(2.0)
    assert rec.gemini_dimensions["profitability"] == 5
    assert "ROIC 200.0% (P90)" in rec.gemini_evidence["profitability"]


def test_ic_nonpositive_outside_financials_runs_on_op_margin_alone():
    # FTNT/BKNG: EBIT > 0 with invested capital <= 0 = near-zero capital need
    r = _prof(95.0, None, roic=None, reason="invested_capital_nonpositive")
    assert r.gemini_dimensions["profitability"] == 5
    ev = r.gemini_evidence["profitability"]
    assert "ROIC n/a (invested capital <= 0)" in ev
    assert "capped" not in ev
    # still a data gap, mirroring the simulation
    assert "roic" in r.gemini_data_gaps
    assert r.data_confidence == "low"
    assert r.partial_evidence_axes == ["profitability"]


def test_ic_nonpositive_in_financial_services_is_capped():
    # IBKR, XTB.WA: invested capital <= 0 is client money, not capital-light
    r = _prof(
        95.0,
        None,
        roic=None,
        reason="invested_capital_nonpositive",
        sector="Financial Services",
    )
    assert r.gemini_dimensions["profitability"] == 3
    assert r.gemini_evidence["profitability"].endswith(" — capped at 3")


def test_financial_services_sector_set_is_fixed():
    from app.screener.deterministic_scorer import ROIC_IC_NONPOSITIVE_CAPPED_SECTORS

    assert ROIC_IC_NONPOSITIVE_CAPPED_SECTORS == frozenset({"Financial Services"})


@pytest.mark.parametrize(
    "reason,text",
    [
        ("no_ebit", "ROIC n/a (no EBIT)"),
        ("no_equity", "ROIC n/a (no equity)"),
        ("no_debt_cash", "ROIC n/a (no debt/cash data)"),
        (None, "ROIC n/a"),
    ],
)
def test_other_missing_reasons_cap_at_3(reason, text):
    r = _prof(95.0, None, roic=None, reason=reason)
    assert r.gemini_dimensions["profitability"] == 3
    ev = r.gemini_evidence["profitability"]
    assert ev == f"op margin 30.0% (P95), {text} — capped at 3"
    assert "roic" in r.gemini_data_gaps
    assert r.data_confidence == "low"


def test_missing_roic_cap_never_raises_a_lower_score():
    # op margin P20 -> 2; the cap only lowers
    r = _prof(20.0, None, roic=None, reason="no_equity")
    assert r.gemini_dimensions["profitability"] == 2
    assert "capped" not in r.gemini_evidence["profitability"]


def test_missing_roic_cap_does_not_lift_a_red_flag():
    r = _prof(95.0, None, roic=None, reason="no_equity", op=-0.1)
    assert r.gemini_dimensions["profitability"] == 0
    assert "capped" not in r.gemini_evidence["profitability"]


def test_missing_roic_is_gap_even_without_percentiles():
    r = _prof(None, None, roic=None, reason="no_ebit")
    assert r.gemini_dimensions["profitability"] == 3
    assert "operating_margin/return_on_invested_capital" in r.gemini_data_gaps
    assert "roic" in r.gemini_data_gaps


def test_evidence_cites_op_margin_and_roic():
    r = _prof(82.0, 79.0, roic=0.22, op=0.18)
    assert (
        r.gemini_evidence["profitability"] == "op margin 18.0% (P82), ROIC 22.0% (P79)"
    )


# --- growth: median annual revenue growth, quarterly YoY only as fallback ----
#
# A single quarter used to decide growth: MA/V sat at 3 on one soft quarter,
# VAR.OL (+103 %) and AKER.OL (+361 %) reached 5 on one quarterly spike. The
# median annual growth of the fiscal-year series drives the axis now.


def _growth(
    median_p: float | None = None,
    yoy_p: float | None = None,
    median: float | None = None,
    yoy: float | None = None,
    consistency: float | None = 1.0,
):
    pcts = {}
    if median_p is not None:
        pcts["revenue_growth_median"] = median_p
    if yoy_p is not None:
        pcts["revenue_growth_yoy"] = yoy_p
    return _scored(
        input_percentiles=pcts,
        revenue_growth_median=median,
        revenue_growth_yoy=yoy,
        growth_consistency=consistency,
    )


def test_median_percentile_drives_growth_not_the_quarter():
    # MA-like: strong multi-year median, one soft quarter -> scored on the median
    r = _growth(median_p=92.0, yoy_p=20.0, median=0.12, yoy=0.01)
    assert r.gemini_dimensions["growth"] == 5
    assert "revenue_growth_median" not in r.gemini_data_gaps


def test_quarterly_spike_does_not_lift_a_modest_median():
    # VAR.OL-like: +103 % quarter, modest median -> the median decides
    r = _growth(median_p=45.0, yoy_p=99.0, median=0.05, yoy=1.03)
    assert r.gemini_dimensions["growth"] == 3


def test_missing_median_falls_back_to_yoy_capped_at_3():
    r = _growth(yoy_p=99.0, yoy=3.61, consistency=None)
    assert r.gemini_dimensions["growth"] == 3
    assert "revenue_growth_median" in r.gemini_data_gaps
    assert "revenue_growth_yoy" not in r.gemini_data_gaps
    assert r.data_confidence == "low"


def test_missing_median_cap_never_raises_a_low_yoy():
    r = _growth(yoy_p=10.0, yoy=-0.2, consistency=None)
    assert r.gemini_dimensions["growth"] == 1


def test_both_growth_inputs_missing_scores_neutral_3():
    r = _growth(consistency=None)
    assert r.gemini_dimensions["growth"] == 3
    assert "revenue_growth_median" in r.gemini_data_gaps
    assert "revenue_growth_yoy" in r.gemini_data_gaps


def test_consistency_cap_still_applies_to_the_median():
    # P95 median -> 5, ratio 0.5 -> cap 4
    r = _growth(median_p=95.0, median=0.25, consistency=0.5)
    assert r.gemini_dimensions["growth"] == 4


def test_growth_evidence_with_median():
    r = _growth(median_p=92.0, yoy_p=20.0, median=0.123, yoy=0.012, consistency=1.0)
    assert r.gemini_evidence["growth"] == (
        "rev growth median 12.3% (P92), consistency 1.00, latest quarter YoY 1.2%"
    )


def test_growth_evidence_with_median_and_missing_quarter():
    r = _growth(median_p=60.0, median=0.05, consistency=0.67)
    assert r.gemini_evidence["growth"] == (
        "rev growth median 5.0% (P60), consistency 0.67, latest quarter YoY n/a"
    )


def test_growth_evidence_without_median_notes_the_cap_when_it_lowered():
    r = _growth(yoy_p=99.0, yoy=1.03, consistency=None)
    assert r.gemini_evidence["growth"] == (
        "rev growth median n/a (<4 GJ), latest quarter YoY 103.0% (P99)"
        " — capped at 3"
    )


def test_growth_evidence_without_median_no_cap_note_when_not_lowered():
    r = _growth(yoy_p=50.0, yoy=0.04, consistency=None)
    assert r.gemini_evidence["growth"] == (
        "rev growth median n/a (<4 GJ), latest quarter YoY 4.0% (P50)"
    )


def test_growth_evidence_without_any_growth_input():
    r = _growth(consistency=None)
    assert r.gemini_evidence["growth"] == (
        "rev growth median n/a (<4 GJ), latest quarter YoY n/a"
    )


def test_run_deterministic_scoring_sets_median_from_series():
    from app.screener.deterministic_scorer import run_deterministic_scoring

    long_ = ScreenerRecord(ticker="LONG", revenue_growth_yoy=0.5)
    short = ScreenerRecord(ticker="SHORT", revenue_growth_yoy=0.5)
    cache = _FakeRevenueCache(
        {"LONG": [8.94, 1.86, 2.23, 2.65], "SHORT": [1.0, 2.0, 3.0]}
    )
    run_deterministic_scoring([long_, short], cache, _FakeTracker())
    assert long_.revenue_growth_median == pytest.approx(2.65 / 2.23 - 1)
    assert "revenue_growth_median" in long_.input_percentiles
    assert short.revenue_growth_median is None
    assert "revenue_growth_median" not in short.input_percentiles
    assert short.gemini_dimensions["growth"] <= 3


# --- price-taker annotation ----------------------------------------------------


def test_run_deterministic_scoring_flags_price_takers_from_both_arms():
    from app.screener.deterministic_scorer import run_deterministic_scoring
    from app.screener.price_takers import PriceTakerTable

    table = PriceTakerTable(industries=frozenset({"Gold"}), tickers=frozenset({"MU"}))
    gold = ScreenerRecord(ticker="NEM", gics_industry="Gold", operating_margin=0.2)
    mu = ScreenerRecord(
        ticker="MU", gics_industry="Semiconductors", operating_margin=0.2
    )
    nvda = ScreenerRecord(
        ticker="NVDA", gics_industry="Semiconductors", operating_margin=0.2
    )
    recs = [gold, mu, nvda]
    cache = _FakeRevenueCache({r.ticker: [1.0, 2.0, 3.0, 4.0] for r in recs})
    run_deterministic_scoring(recs, cache, _FakeTracker(), price_takers=table)
    assert (gold.price_taker, mu.price_taker, nvda.price_taker) == (
        True,
        True,
        False,
    )


def test_price_taker_flag_leaves_scores_untouched():
    """Price takers stay in the scoring cohort: same scores with and without."""
    from app.screener.deterministic_scorer import run_deterministic_scoring
    from app.screener.price_takers import PriceTakerTable

    def cohort():
        return [
            ScreenerRecord(
                ticker=f"T{i}",
                gics_sector="Basic Materials",
                gics_industry="Gold" if i % 3 == 0 else "Chemicals",
                operating_margin=0.05 + i * 0.01,
                gross_margin=0.2 + i * 0.01,
                total_revenue=1000.0,
                total_debt=100.0,
                total_cash=50.0,
                ebitda=200.0,
            )
            for i in range(20)
        ]

    cache = _FakeRevenueCache({f"T{i}": [1.0, 2.0, 3.0, 4.0] for i in range(20)})
    empty = PriceTakerTable(industries=frozenset(), tickers=frozenset())
    gold = PriceTakerTable(industries=frozenset({"Gold"}), tickers=frozenset())
    a = run_deterministic_scoring(cohort(), cache, _FakeTracker(), price_takers=empty)
    b = run_deterministic_scoring(cohort(), cache, _FakeTracker(), price_takers=gold)
    assert [r.gemini_dimensions for r in a] == [r.gemini_dimensions for r in b]
    assert [r.input_percentiles for r in a] == [r.input_percentiles for r in b]
    assert sum(r.price_taker for r in b) == 7


def test_run_deterministic_scoring_loads_the_committed_table_by_default():
    """The simulation calls without the parameter and must get the exclusion."""
    from app.screener.deterministic_scorer import run_deterministic_scoring

    rec = ScreenerRecord(ticker="NEM", gics_industry="Gold", operating_margin=0.2)
    run_deterministic_scoring(
        [rec], _FakeRevenueCache({"NEM": [1.0, 2.0, 3.0, 4.0]}), _FakeTracker()
    )
    assert rec.price_taker is True
