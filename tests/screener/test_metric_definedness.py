from app.models.screener_record import ScreenerRecord
from app.screener.metric_definedness import (
    WaterfallVerdict,
    classify_waterfall,
    is_gross_margin_undefined_info_only,
)


def _rec(gm):
    return ScreenerRecord(ticker="T", gross_margin=gm)


def test_none_margin_is_undefined():
    assert is_gross_margin_undefined_info_only(_rec(None)) is True


def test_zero_margin_is_undefined():
    assert is_gross_margin_undefined_info_only(_rec(0.0)) is True


def test_negative_margin_is_undefined_info_only():
    # .info-only default cannot distinguish structural-undefined from real-negative;
    # Gate-A A1 verifies the gm<=0 basket holds no real industrial negative-marger.
    assert is_gross_margin_undefined_info_only(_rec(-0.05)) is True


def test_positive_margin_is_defined():
    assert is_gross_margin_undefined_info_only(_rec(0.20)) is False


def test_real_waterfall_is_defined():
    # Daten-/Indexhaus: rev>cor>0, gp == rev - cor, gp > 0
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=300.0,
                           gross_profit=700.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.DEFINED


def test_bank_no_cost_of_revenue_row_is_undefined():
    # gm<=0 Bank: keine echte COGS-Zeile -> UNDEFINED (Null-Kante)
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=None,
                           gross_profit=None, cost_of_revenue_present=False)
    assert v is WaterfallVerdict.UNDEFINED


def test_spurious_positive_insurer_is_undefined():
    # Versicherer/REIT: gp ~ rev, cor ~ 0 (claims woanders gebucht) -> UNDEFINED trotz gm>0 (Positiv-Kante)
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=0.0,
                           gross_profit=995.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.UNDEFINED


def test_real_industrial_negative_marger_is_defined_negative():
    # echter Wasserfall, aber unter Selbstkosten: cor>rev -> FAIL, nicht NA
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=1100.0,
                           gross_profit=-100.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.DEFINED_NEGATIVE


def test_inconsistent_waterfall_is_undefined():
    # gp weicht stark von rev-cor ab -> Struktur nicht vertrauenswürdig -> UNDEFINED
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=300.0,
                           gross_profit=200.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.UNDEFINED


def test_present_flag_true_but_cor_value_is_none_is_undefined():
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=None,
                           gross_profit=700.0, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.UNDEFINED


def test_present_flag_true_cor_set_gross_profit_none_is_undefined():
    v = classify_waterfall(total_revenue=1000.0, cost_of_revenue=300.0,
                           gross_profit=None, cost_of_revenue_present=True)
    assert v is WaterfallVerdict.UNDEFINED


from app.screener.metric_definedness import is_metric_na


def test_reit_industry_is_metric_na_even_if_waterfall_defined():
    # pure equity REIT: rent - opex satisfies the waterfall, but Fisher framework n/a
    assert is_metric_na("REIT - Residential", total_revenue=1000.0, cost_of_revenue=400.0,
                        gross_profit=600.0, cost_of_revenue_present=True) is True


def test_real_estate_services_not_metric_na_when_waterfall_defined():
    # CBRE/JLL style: real brokerage COGS, no "REIT" in industry -> evaluated normally
    assert is_metric_na("Real Estate Services", total_revenue=1000.0, cost_of_revenue=400.0,
                        gross_profit=600.0, cost_of_revenue_present=True) is False


def test_undefined_waterfall_is_metric_na():
    # bank/insurer: no genuine COGS -> METRIK_NA
    assert is_metric_na("Banks - Diversified", total_revenue=1000.0, cost_of_revenue=None,
                        gross_profit=None, cost_of_revenue_present=False) is True


def test_defined_waterfall_not_metric_na():
    assert is_metric_na("Specialty Chemicals", total_revenue=1000.0, cost_of_revenue=700.0,
                        gross_profit=300.0, cost_of_revenue_present=True) is False


def test_defined_negative_not_metric_na():
    # real negative margin (cor>rev): NOT METRIK_NA -> must fail gross_margin downstream
    assert is_metric_na("Steel", total_revenue=1000.0, cost_of_revenue=1100.0,
                        gross_profit=-100.0, cost_of_revenue_present=True) is False


def test_reit_industry_with_undefined_waterfall_is_metric_na():
    assert is_metric_na("REIT - Specialty", total_revenue=1000.0, cost_of_revenue=None,
                        gross_profit=None, cost_of_revenue_present=False) is True


def test_none_industry_falls_back_to_waterfall():
    assert is_metric_na(None, total_revenue=1000.0, cost_of_revenue=700.0,
                        gross_profit=300.0, cost_of_revenue_present=True) is False
