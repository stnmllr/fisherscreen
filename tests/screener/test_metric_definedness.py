from app.models.screener_record import ScreenerRecord
from app.screener.metric_definedness import is_gross_margin_undefined_info_only


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


from app.screener.metric_definedness import classify_waterfall, WaterfallVerdict


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
