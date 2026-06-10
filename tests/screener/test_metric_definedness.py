from app.screener.metric_definedness import (
    DefinednessOutcome,
    WaterfallVerdict,
    assess_definedness,
    classify_waterfall,
)


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


def test_assess_reit_is_metrik_na_without_statement():
    # REIT cross-check wins, no fetch needed -> METRIK_NA even if statement unavailable
    assert assess_definedness("REIT - Residential", statement_available=False,
                              total_revenue=None, cost_of_revenue=None, gross_profit=None,
                              cost_of_revenue_present=False) is DefinednessOutcome.METRIK_NA


def test_assess_fetch_failed_is_unassessable_not_metrik_na():
    # non-REIT, statement could not be fetched -> UNASSESSABLE (divert), NOT METRIK_NA
    assert assess_definedness("Real Estate Services", statement_available=False,
                              total_revenue=None, cost_of_revenue=None, gross_profit=None,
                              cost_of_revenue_present=False) is DefinednessOutcome.UNASSESSABLE


def test_assess_statement_present_but_no_revenue_is_unassessable():
    assert assess_definedness("Banks - Diversified", statement_available=True,
                              total_revenue=None, cost_of_revenue=None, gross_profit=None,
                              cost_of_revenue_present=False) is DefinednessOutcome.UNASSESSABLE


def test_assess_bank_no_cogs_is_metrik_na():
    # statement present, revenue present, no genuine COGS row -> real UNDEFINED -> METRIK_NA
    # (distinct from the fetch-failure case above)
    assert assess_definedness("Banks - Diversified", statement_available=True,
                              total_revenue=1000.0, cost_of_revenue=None, gross_profit=None,
                              cost_of_revenue_present=False) is DefinednessOutcome.METRIK_NA


def test_assess_real_waterfall_is_defined():
    assert assess_definedness("Specialty Chemicals", statement_available=True,
                              total_revenue=1000.0, cost_of_revenue=700.0, gross_profit=300.0,
                              cost_of_revenue_present=True) is DefinednessOutcome.DEFINED


def test_assess_defined_negative_is_defined_not_metrik_na():
    # real negative margin -> DEFINED (must fail gross_margin downstream, not be excluded)
    assert assess_definedness("Steel", statement_available=True,
                              total_revenue=1000.0, cost_of_revenue=1100.0, gross_profit=-100.0,
                              cost_of_revenue_present=True) is DefinednessOutcome.DEFINED


def test_assess_real_estate_services_with_real_cogs_is_defined():
    # CBRE/JLL: no "REIT" substring, real brokerage COGS -> DEFINED
    assert assess_definedness("Real Estate Services", statement_available=True,
                              total_revenue=1000.0, cost_of_revenue=600.0, gross_profit=400.0,
                              cost_of_revenue_present=True) is DefinednessOutcome.DEFINED
