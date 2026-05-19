from app.deepdive.valuation_block import render_valuation_block
from app.models.deep_dive_record import (
    ForwardEstimates,
    HistoricalSeries,
    PointInTimeQuant,
    QuantSnapshot,
    TrendMetrics,
)


def _qs(forward=None, **pit_over):
    pit = PointInTimeQuant(ticker="X", currency="DKK", **pit_over)
    return QuantSnapshot(
        point_in_time=pit,
        historical_series=HistoricalSeries(
            years=[2024, 2023, 2022, 2021, 2020],
            revenue=[1.0e9, 9.0e8, 8.0e8, 7.0e8, 6.0e8]),
        trend_metrics=TrendMetrics(buyback_intensity_5y=0.10),
        forward_estimates=forward,
    )


def test_heading_is_stage2a_text_no_roadmap_jargon():
    out = render_valuation_block(_qs())
    assert out.startswith(
        "## Bewertung & Kapitalstruktur (TTM-Stand, ohne historischen "
        "5J-Vergleich)")
    assert "B.2" not in out
    assert "B.2.1" not in out


def test_full_block_with_all_inputs():
    out = render_valuation_block(_qs(
        trailing_pe=30.0, forward_pe=25.0, enterprise_value=2.1e10,
        ebit=2.0e9, free_cashflow=1.5e9, market_cap=3.0e10,
        total_debt=2.0e9, total_cash=5.0e9, debt_to_equity=40.0,
        current_ratio=1.5, interest_expense=-7.0e7,
        dividend_yield=0.024, payout_ratio=0.30))
    assert "P/E trail. 30.0" in out
    assert "P/E fwd 25.0" in out
    assert "EV/EBIT 10.5" in out                 # 2.1e10 / 2.0e9
    assert "EV/Sales 21.0" in out                # 2.1e10 / 1000
    assert "FCF-Yield 5.0%" in out               # 1.5e9 / 3.0e10
    assert "Div-Yield 2.4%" in out
    assert "Payout 30.0%" in out
    assert "Total Debt 2,000,000,000 DKK" in out
    assert "Cash 5,000,000,000 DKK" in out
    assert "D/E 40.0" in out
    assert "Current Ratio 1.5" in out
    # interest coverage = 2.0e9 / 7.0e7 = 28.57 -> 28.6, mandatory (FY)
    assert "Interest Coverage 28.6× (FY)" in out


def test_derived_na_reasons():
    out = render_valuation_block(_qs(
        trailing_pe=10.0, ebit=1.0e9, free_cashflow=1.0e9))
    # EV missing
    assert "EV/EBIT n/a (EV fehlt)" in out
    assert "EV/Sales n/a (EV fehlt)" in out
    # market cap missing -> FCF-Yield reason
    assert "FCF-Yield n/a (Market Cap fehlt)" in out
    # raw missing P/E forward renders plain n/a
    assert "P/E fwd n/a" in out


def test_ev_ebit_zero_and_missing_ebit_reasons():
    out0 = render_valuation_block(_qs(enterprise_value=1e10, ebit=0.0))
    assert "EV/EBIT n/a (EBIT=0)" in out0
    out1 = render_valuation_block(_qs(enterprise_value=1e10))
    assert "EV/EBIT n/a (EBIT fehlt)" in out1


def test_ev_sales_revenue_missing_reason():
    qs = _qs(enterprise_value=1e10)
    qs.historical_series = HistoricalSeries(years=[], revenue=[])
    out = render_valuation_block(qs)
    assert "EV/Sales n/a (Revenue fehlt)" in out


def test_interest_coverage_missing_reason():
    out = render_valuation_block(_qs(ebit=1e9))
    assert "Interest Coverage n/a (Interest Expense fehlt)" in out


def test_tsy_formula_text_and_annualization():
    # buyback_intensity_5y cumulative 0.10 over 5 years -> 0.02 annual
    out = render_valuation_block(_qs(dividend_yield=0.024))
    assert "Total Shareholder Yield 4.4% (Div 2.4% aktuell + Ø 5J Buyback 2.0%)" in out


def test_tsy_marks_missing_component():
    qs = _qs()  # no dividend_yield
    out = render_valuation_block(qs)
    assert "Total Shareholder Yield" in out
    assert "Div n/a aktuell" in out


def test_consensus_line_happy_path_with_implied_upside():
    out = render_valuation_block(_qs(
        price=100.0, recommendation_key="buy", target_mean_price=111.0,
        target_median_price=110.0, number_of_analyst_opinions=42))
    assert ("Analyst Consensus: buy · Target: 111.00 (Median 110.0) · "
            "42 Analysten · Upside 11.0%") in out


def test_consensus_strict_na_when_target_mean_missing():
    # other consensus fields present, but no target_mean_price -> whole line n/a
    out = render_valuation_block(_qs(
        price=100.0, recommendation_key="buy",
        number_of_analyst_opinions=42, target_median_price=110.0))
    assert "Analyst Consensus: n/a" in out
    assert "buy ·" not in out
    assert "Upside" not in out


def test_consensus_upside_na_when_price_missing():
    out = render_valuation_block(_qs(
        recommendation_key="hold", target_mean_price=111.0,
        number_of_analyst_opinions=10))
    assert "Upside n/a (Kurs fehlt)" in out
    assert "Analyst Consensus: hold · Target: 111.00" in out


def test_consensus_upside_na_when_price_zero():
    out = render_valuation_block(_qs(
        price=0.0, recommendation_key="hold", target_mean_price=111.0))
    assert "Upside n/a (Kurs fehlt)" in out


def test_consensus_fallbacks_for_missing_optional_subfields():
    out = render_valuation_block(_qs(price=100.0, target_mean_price=120.0))
    # recommendation_key/median/opinions missing -> n/a sub-tokens, line still built
    assert ("Analyst Consensus: n/a · Target: 120.00 (Median n/a) · "
            "n/a Analysten · Upside 20.0%") in out


def test_forward_line_happy_path_generic_period_labels():
    fe = ForwardEstimates(
        revenue_growth_cy=0.1485, revenue_growth_ny=0.0809,
        eps_growth_cy=0.1714, eps_growth_ny=0.1023)
    out = render_valuation_block(_qs(forward=fe))
    # _fmt_pct == f"{v:.1%}"; 0.1485 -> "14.8%" (float repr rounding)
    assert ("Forward-Konsens: Revenue 14.8% (lfd. GJ), 8.1% (Folge-GJ) · "
            "EPS 17.1% (lfd. GJ)") in out
    # honest generic labels — no fabricated calendar years
    assert "FY26e" not in out
    assert "FY27e" not in out


def test_forward_line_partial_fields_render_per_field_na():
    fe = ForwardEstimates(revenue_growth_cy=0.10)
    out = render_valuation_block(_qs(forward=fe))
    assert ("Forward-Konsens: Revenue 10.0% (lfd. GJ), n/a (Folge-GJ) · "
            "EPS n/a (lfd. GJ)") in out


def test_forward_line_na_when_estimates_absent():
    out = render_valuation_block(_qs(forward=None))
    assert "Forward-Konsens: n/a" in out


def test_forward_line_na_when_all_fields_none():
    out = render_valuation_block(_qs(forward=ForwardEstimates()))
    assert "Forward-Konsens: n/a" in out


def test_stage2a_lines_still_present_regression_guard():
    out = render_valuation_block(_qs(
        trailing_pe=30.0, forward_pe=25.0, enterprise_value=2.1e10,
        ebit=2.0e9, free_cashflow=1.5e9, market_cap=3.0e10,
        price=100.0, target_mean_price=111.0,
        forward=ForwardEstimates(eps_growth_cy=0.17)))
    assert out.startswith(
        "## Bewertung & Kapitalstruktur (TTM-Stand, ohne historischen "
        "5J-Vergleich)")
    assert "Bewertung: P/E trail. 30.0" in out
    assert "Kapitalstruktur: Total Debt" in out
    assert "Total Shareholder Yield" in out
    # new lines appended AFTER Kapitalstruktur line
    lines = out.splitlines()
    kap_idx = next(i for i, l in enumerate(lines)
                   if l.startswith("Kapitalstruktur:"))
    cons_idx = next(i for i, l in enumerate(lines)
                    if l.startswith("Analyst Consensus:"))
    fwd_idx = next(i for i, l in enumerate(lines)
                   if l.startswith("Forward-Konsens:"))
    assert kap_idx < cons_idx < fwd_idx


def test_currency_blank_when_absent():
    pit = PointInTimeQuant(ticker="X", total_debt=1.0e9)
    qs = QuantSnapshot(point_in_time=pit)
    out = render_valuation_block(qs)
    assert "Total Debt 1,000,000,000 " in out  # ccy blank, no crash
