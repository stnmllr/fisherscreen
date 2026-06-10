import pytest

import app.screener.filters as filters
from app.errors import FilterConfigError
from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord
from app.screener.filters import (
    _get_fail_reason,
    _node_chain,
    apply_basis_filters,
    gross_margin_pass_reason,
    passes_gross_margin_filter,
    passes_market_cap_filter,
    passes_revenue_growth_filter,
    passes_volume_filter,
)
from app.screener.sector_buckets import SectorMedianTable


def _record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "market_cap_eur": 5_000_000_000,  # 5B EUR — well above €2B threshold
        "avg_daily_volume": 200_000,
        "price": 100.0,                   # value gate primitive (Punkt 1)
        "fx_rate": 1.0,                   # value gate primitive (Punkt 1)
        "gross_margin": 0.45,             # 45% — above 30% threshold (decimal format)
        "revenue_growth_yoy": 0.05,       # 5% YoY growth — above 0%
    }
    return ScreenerRecord(**{**defaults, **kwargs})


# --- market cap (EUR, V3: >= 2B) ---

def test_market_cap_passes_above_threshold():
    assert passes_market_cap_filter(_record(market_cap_eur=2_000_000_001)) is True


def test_market_cap_passes_at_exact_threshold():
    assert passes_market_cap_filter(_record(market_cap_eur=2_000_000_000)) is True


def test_market_cap_fails_below_threshold():
    assert passes_market_cap_filter(_record(market_cap_eur=1_999_999_999)) is False


def test_market_cap_fails_when_none():
    assert passes_market_cap_filter(_record(market_cap_eur=None)) is False


# --- volume gate (Punkt 1: EUR daily-trading-value >= MIN_AVG_DAILY_VALUE_EUR) ---


def _rec(vol=500_000.0, price=100.0, fx=1.0):
    return ScreenerRecord(ticker="X", avg_daily_volume=vol, price=price, fx_rate=fx)


def test_value_floor_passes_high_value():
    assert passes_volume_filter(_rec()) is True            # 500k x 100 x 1 = 50M >= 1M


def test_value_floor_fails_low_value():
    assert passes_volume_filter(_rec(vol=5_000)) is False  # 0.5M < 1M


def test_lindt_class_few_shares_high_price_passes():
    assert passes_volume_filter(_rec(vol=175, price=95_600, fx=1.07)) is True  # ~17.9M


def test_uncalibrated_sentinel_raises(monkeypatch):
    monkeypatch.setattr(filters, "MIN_AVG_DAILY_VALUE_EUR", None)
    with pytest.raises(FilterConfigError, match="not calibrated"):
        passes_volume_filter(_rec())


def test_missing_input_raises_not_silent_drop():
    with pytest.raises(FilterConfigError, match="value uncomputable"):
        passes_volume_filter(_rec(fx=None))


def test_production_threshold_is_calibrated():
    # Guards against shipping the sentinel. The production constant must be a real,
    # calibrated value >= the broken-avgVol ceiling (so FER/1COV stay GATE_VOLUME REVIEW).
    import importlib
    import app.screener.filters as f
    importlib.reload(f)
    try:
        assert f.MIN_AVG_DAILY_VALUE_EUR is not None
        assert f.MIN_AVG_DAILY_VALUE_EUR >= 900_000
    finally:
        importlib.reload(f)


# --- gross margin (V3: >= 0.30, decimal format — 0.30 = 30%) ---

def test_gross_margin_passes_above_threshold():
    assert passes_gross_margin_filter(_record(gross_margin=0.31)) is True


def test_gross_margin_passes_at_exact_threshold():
    assert passes_gross_margin_filter(_record(gross_margin=0.30)) is True


def test_gross_margin_fails_below_threshold():
    assert passes_gross_margin_filter(_record(gross_margin=0.29)) is False


def test_gross_margin_fails_when_none():
    assert passes_gross_margin_filter(_record(gross_margin=None)) is False


def test_gross_margin_passes_high_margin():
    # SaaS / pharma typically have 70-80% gross margins
    assert passes_gross_margin_filter(_record(gross_margin=0.80)) is True


def test_gross_margin_fails_low_margin_not_30_percent_as_whole_number():
    # Regression: ensure we treat 0.29 as 29% (decimal), not 29.0 as percentage
    assert passes_gross_margin_filter(_record(gross_margin=0.29)) is False


# --- revenue growth (V3: >= 0.0 YoY) ---

def test_revenue_growth_passes_positive_growth():
    assert passes_revenue_growth_filter(_record(revenue_growth_yoy=0.05)) is True


def test_revenue_growth_passes_at_zero():
    # Flat growth (0%) still passes — only negative growth is excluded
    assert passes_revenue_growth_filter(_record(revenue_growth_yoy=0.0)) is True


def test_revenue_growth_fails_negative_growth():
    assert passes_revenue_growth_filter(_record(revenue_growth_yoy=-0.01)) is False


def test_revenue_growth_fails_when_none():
    assert passes_revenue_growth_filter(_record(revenue_growth_yoy=None)) is False


# --- apply_basis_filters ---

def test_apply_basis_filters_returns_only_passing_records():
    passing = _record(ticker="GOOD")
    failing = _record(ticker="SMALL", market_cap_eur=1_000_000_000)

    result = apply_basis_filters([passing, failing])

    assert len(result) == 1
    assert result[0].ticker == "GOOD"
    assert result[0].filter_passed_basis is True


def test_apply_basis_filters_sets_failed_reason_market_cap():
    record = _record(ticker="SMALL", market_cap_eur=1_000_000_000)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "market_cap"


def test_apply_basis_filters_sets_failed_reason_avg_volume():
    record = _record(ticker="ILLIQUID", avg_daily_volume=10)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "avg_volume"


def test_apply_basis_filters_sets_failed_reason_gross_margin():
    record = _record(ticker="LOWMARGIN", gross_margin=0.10)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "gross_margin"


def test_apply_basis_filters_sets_failed_reason_revenue_growth():
    record = _record(ticker="SHRINKING", revenue_growth_yoy=-0.05)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "revenue_growth"


def test_apply_basis_filters_sets_filter_passed_basis_false_on_failure():
    record = _record(ticker="SMALL", market_cap_eur=100_000_000)
    apply_basis_filters([record])
    assert record.filter_passed_basis is False


def test_apply_basis_filters_checks_volume_before_market_cap():
    # Volume is checked first so low-volume small-cap gets "avg_volume" as reason
    record = _record(ticker="DOUBLE_FAIL", market_cap_eur=100_000_000, avg_daily_volume=10)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "avg_volume"


def test_apply_basis_filters_returns_empty_for_all_failures():
    records = [_record(ticker="SHRINKING", revenue_growth_yoy=-0.50)]
    assert apply_basis_filters(records) == []


def test_apply_basis_filters_returns_empty_list_for_empty_input():
    assert apply_basis_filters([]) == []


# --- apply_edgar_filters ---


def _edgar_record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "cik": "0000320193",
        "market_cap_eur": 5_000_000_000,
        "avg_daily_volume": 200_000,
        "gross_margin": 0.45,
        "revenue_growth_yoy": 0.05,
        "has_restatement": False,
        "has_going_concern": False,
        "has_active_enforcement": False,
        "edgar_skipped": False,
        "filter_passed_basis": True,
    }
    return ScreenerRecord(**{**defaults, **kwargs})


def test_apply_edgar_filters_passes_clean_record():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record()
    result = apply_edgar_filters([record])
    assert len(result) == 1
    assert result[0].filter_passed_edgar is True


def test_apply_edgar_filters_fails_on_restatement():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(has_restatement=True)
    result = apply_edgar_filters([record])
    assert result == []
    assert record.filter_passed_edgar is False
    assert record.filter_failed_reason == "restatement"


def test_apply_edgar_filters_fails_on_going_concern():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(has_going_concern=True)
    result = apply_edgar_filters([record])
    assert result == []
    assert record.filter_passed_edgar is False
    assert record.filter_failed_reason == "going_concern"


def test_apply_edgar_filters_fails_on_active_enforcement():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(has_active_enforcement=True)
    result = apply_edgar_filters([record])
    assert result == []
    assert record.filter_passed_edgar is False
    assert record.filter_failed_reason == "enforcement"


def test_apply_edgar_filters_passes_through_skipped_records():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(edgar_skipped=True)
    result = apply_edgar_filters([record])
    assert len(result) == 1
    assert result[0].filter_passed_edgar is None


def test_apply_edgar_filters_checks_restatement_before_going_concern():
    from app.screener.filters import apply_edgar_filters
    record = _edgar_record(has_restatement=True, has_going_concern=True)
    apply_edgar_filters([record])
    assert record.filter_failed_reason == "restatement"


def test_apply_edgar_filters_returns_empty_for_empty_input():
    from app.screener.filters import apply_edgar_filters
    assert apply_edgar_filters([]) == []


# --- metric_na / statement_unavailable divert (Punkt 2 CT-A) ---
# The runner pre-pass sets record.definedness; filters.py reads the pre-computed field.

def test_definedness_metrik_na_diverts_to_metric_na():
    """Pre-computed METRIK_NA on a volume+cap-passing record -> reason 'metric_na'."""
    rec = _record(ticker="BANK", gross_margin=0.0, definedness=DefinednessOutcome.METRIK_NA)
    apply_basis_filters([rec])
    assert rec.filter_failed_reason == "metric_na"


def test_definedness_unassessable_diverts_to_statement_unavailable():
    """Pre-computed UNASSESSABLE (fetch failed) -> reason 'statement_unavailable'."""
    rec = _record(ticker="X", gross_margin=None, definedness=DefinednessOutcome.UNASSESSABLE)
    apply_basis_filters([rec])
    assert rec.filter_failed_reason == "statement_unavailable"


def test_definedness_defined_continues_to_gross_margin_gate():
    """DEFINED -> continues; with passing gross_margin the record passes basis."""
    rec = _record(ticker="LOW", gross_margin=0.45, definedness=DefinednessOutcome.DEFINED)
    result = apply_basis_filters([rec])
    assert rec.filter_passed_basis is True
    assert len(result) == 1


def test_definedness_none_continues_to_gross_margin_gate():
    """None (non-suspect, not assessed) -> continues; treated as DEFINED via None."""
    rec = _record(ticker="NORM", gross_margin=0.45, definedness=None)
    result = apply_basis_filters([rec])
    assert rec.filter_passed_basis is True
    assert len(result) == 1


def test_definedness_defined_low_margin_still_fails_gross_margin():
    """DEFINED with low margin -> continues past metric_na, fails gross_margin gate."""
    rec = _record(ticker="LOW", gross_margin=0.10, definedness=DefinednessOutcome.DEFINED)
    apply_basis_filters([rec])
    assert rec.filter_failed_reason == "gross_margin"


def test_volume_failer_with_unassessable_still_returns_avg_volume():
    """volume gate fires BEFORE definedness check — order must be preserved."""
    rec = _record(
        ticker="ILLIQUID",
        avg_daily_volume=10,       # fails volume gate
        definedness=DefinednessOutcome.UNASSESSABLE,
    )
    apply_basis_filters([rec])
    assert rec.filter_failed_reason == "avg_volume"


def test_get_fail_reason_order_volume_before_definedness():
    """Direct _get_fail_reason: UNASSESSABLE does not override a volume failure."""
    rec = _record(ticker="Z", avg_daily_volume=10, definedness=DefinednessOutcome.UNASSESSABLE)
    assert _get_fail_reason(rec) == "avg_volume"


# --- CT-B node chain: industry -> GICS group (NOT sector) ---
# The GICS *sector* is multimodal (the catch-all contamination CT-B kills); the
# *industry group* is the exogenous margin-blind intermediate. _node_chain rolls
# industry up to its mapped group; the sector is never consulted.

def test_node_chain_thick_industry_with_group_mapping(monkeypatch):
    monkeypatch.setattr(filters, "INDUSTRY_GROUP_MAP", {"Railroads": "Transportation"})
    rec = _record(gics_industry="Railroads", gics_sector="Industrials")
    # finest -> coarsest: [industry, group]; sector ("Industrials") is absent
    assert _node_chain(rec) == ["Railroads", "Transportation"]


def test_node_chain_industry_without_mapping_is_industry_only(monkeypatch):
    monkeypatch.setattr(filters, "INDUSTRY_GROUP_MAP", {})
    rec = _record(gics_industry="Quantum Widgets", gics_sector="Technology")
    # No group mapping -> chain is just [industry]; sector never appended (CT-B).
    assert _node_chain(rec) == ["Quantum Widgets"]


def test_node_chain_no_industry_is_empty(monkeypatch):
    monkeypatch.setattr(filters, "INDUSTRY_GROUP_MAP", {"Railroads": "Transportation"})
    rec = _record(gics_industry=None, gics_sector="Industrials")
    # No industry -> no anchor for rollup -> empty chain (sector is NOT a fallback).
    assert _node_chain(rec) == []


# --- dual-arm sector-aware gross margin floor (Punkt 2 Mechanism 2 / C3) ---

def test_absolute_arm_passes_high_margin():
    assert passes_gross_margin_filter(_record(gross_margin=0.45), table=None) is True


def test_no_table_relative_arm_dormant_below_30():
    assert passes_gross_margin_filter(
        _record(gross_margin=0.18, gics_industry="Marine Shipping"),
        table=None,
    ) is False


def test_relative_arm_rescues_at_industry_level():
    # Thick industry: the industry itself clears n_min, so the bucket resolves at
    # the industry node — the group rollup is not even consulted.
    table = SectorMedianTable(
        entries={"Marine Shipping": 0.20},
        n_min=1,
        counts={"Marine Shipping": 40},
    )
    rec = _record(gross_margin=0.18, gics_industry="Marine Shipping")
    assert passes_gross_margin_filter(rec, table=table, k=0.5) is True


def test_relative_arm_rescues_thin_industry_via_group_rollup(monkeypatch):
    # Thin industry (below n_min) WITH a group mapping rolls up to the GROUP median.
    monkeypatch.setattr(filters, "INDUSTRY_GROUP_MAP", {"Marine Shipping": "Transportation"})
    table = SectorMedianTable(
        entries={"Transportation": 0.20},          # group-level pinned median
        n_min=8,
        counts={"Marine Shipping": 3, "Transportation": 40},  # industry thin, group thick
    )
    rec = _record(gross_margin=0.18, gics_industry="Marine Shipping")
    assert passes_gross_margin_filter(rec, table=table, k=0.5) is True


def test_relative_arm_fails_safe_thin_industry_without_mapping(monkeypatch):
    # Thin industry WITHOUT a group mapping -> chain is just [industry], industry is
    # below n_min -> resolve_bucket None -> no rescue. No wrong-bucket rescue beats a
    # missing one (CT-B fail-safe). The sector is NEVER consulted as a fallback.
    monkeypatch.setattr(filters, "INDUSTRY_GROUP_MAP", {})
    table = SectorMedianTable(
        entries={"Transportation": 0.20},
        n_min=8,
        counts={"Marine Shipping": 3, "Transportation": 40},
    )
    rec = _record(gross_margin=0.18, gics_industry="Marine Shipping",
                  gics_sector="Industrials")
    assert passes_gross_margin_filter(rec, table=table, k=0.5) is False


def test_relative_arm_does_not_rescue_real_tail():
    table = SectorMedianTable(
        entries={"Marine Shipping": 0.20},
        n_min=1,
        counts={"Marine Shipping": 40},
    )
    rec = _record(gross_margin=0.05, gics_industry="Marine Shipping")
    assert passes_gross_margin_filter(rec, table=table, k=0.5) is False


def test_relative_arm_fails_safe_when_bucket_median_is_none():
    # n_min=10 but the industry bucket has only 2 peers and no group mapping ->
    # resolve_bucket returns None -> bucket_median None -> relative arm does not fire
    # (thin-industry fail-safe, spec §4).
    table = SectorMedianTable(
        entries={"Marine Shipping": 0.20},
        n_min=10,
        counts={"Marine Shipping": 2},
    )
    rec = _record(gross_margin=0.18, gics_industry="Marine Shipping")
    assert passes_gross_margin_filter(rec, table=table, k=0.5) is False


def test_determinism_independent_of_peer_membership():
    # The verdict is a fixed function of the record's gm and the PINNED median, not of
    # peer membership: the same record passes under one pinned table and fails under another.
    rec = _record(gross_margin=0.18, gics_industry="Marine Shipping")
    lenient = SectorMedianTable(entries={"Marine Shipping": 0.20}, n_min=1,
                                counts={"Marine Shipping": 40})
    strict = SectorMedianTable(entries={"Marine Shipping": 0.50}, n_min=1,
                               counts={"Marine Shipping": 40})
    # k=0.5: lenient bar = 0.10 (0.18 passes); strict bar = 0.25 (0.18 fails)
    assert passes_gross_margin_filter(rec, table=lenient, k=0.5) is True
    assert passes_gross_margin_filter(rec, table=strict, k=0.5) is False


# --- apply_basis_filters with sector table (Punkt 2 Mechanism 2 / C4) ---

def test_apply_basis_filters_rescues_with_table():
    table = SectorMedianTable(
        entries={"Marine Shipping": 0.20},
        n_min=1,
        counts={"Marine Shipping": 40},
    )
    rec = _record(ticker="MAERSK", gross_margin=0.18, gics_industry="Marine Shipping")
    result = filters.apply_basis_filters([rec], sector_table=table, relative_k=0.5)
    assert rec.filter_passed_basis is True
    assert result and result[0].ticker == "MAERSK"


# --- gross_margin_pass_reason: ABSOLUTE_PASS vs RELATIVE_RESCUE (Punkt 2 Phase E) ---
# A passing record must be auditable as either an absolute pass or a relative rescue.
# RELATIVE_RESCUE is tagged ONLY for a SUB-FLOOR name (gm < MIN_GROSS_MARGIN AND
# gm >= k*median). gm >= MIN_GROSS_MARGIN is always ABSOLUTE_PASS, never RELATIVE_RESCUE.

def _bucket_table(median=0.30, n_min=1):
    return SectorMedianTable(
        entries={"Marine Shipping": median},
        n_min=n_min,
        counts={"Marine Shipping": 40},
    )


def test_pass_reason_absolute_above_floor():
    rec = _record(gross_margin=0.40, gics_industry="Marine Shipping")
    assert gross_margin_pass_reason(rec, table=None) == "ABSOLUTE_PASS"


def test_pass_reason_relative_rescue_sub_floor():
    # gm=0.20, k=0.5, median=0.30 -> bar=0.15, 0.20>=0.15 -> rescue
    rec = _record(gross_margin=0.20, gics_industry="Marine Shipping")
    assert gross_margin_pass_reason(rec, table=_bucket_table(0.30), k=0.5) == "RELATIVE_RESCUE"


def test_pass_reason_none_sub_floor_below_relative_bar():
    # gm=0.20, k=0.5, median=0.50 -> bar=0.25, 0.20<0.25 -> fails the gate
    rec = _record(gross_margin=0.20, gics_industry="Marine Shipping")
    assert gross_margin_pass_reason(rec, table=_bucket_table(0.50), k=0.5) is None


def test_pass_reason_none_dormant_no_table():
    # sub-floor, no table -> relative arm dormant -> None
    rec = _record(gross_margin=0.20, gics_industry="Marine Shipping")
    assert gross_margin_pass_reason(rec, table=None) is None


# --- revenue_growth_outcome: pure gamma-trajectory outcome (Punkt 3 / Task 4) ---
# TTM_PASS (positive snapshot, lazy short-circuit) | DECLINE_DROP (DEFINED gamma, the
# only drop) | TRAJECTORY_RESCUE (DEFINED non-gamma) | UNASSESSABLE_PASS (criterion
# could not apply). A missing TTM is data-absence judged on the trajectory, never an
# auto-pass (the inverse of the original missing-data bug).

from app.screener.filters import revenue_growth_outcome


def _rg_rec(**kw):
    from app.models.screener_record import ScreenerRecord
    return ScreenerRecord(ticker="X", **kw)


def test_outcome_ttm_pass_positive_snapshot():
    r = _rg_rec(revenue_growth_yoy=0.01)
    assert revenue_growth_outcome(r) == "TTM_PASS"
    assert passes_revenue_growth_filter(r) is True


def test_outcome_ttm_zero_passes():
    assert revenue_growth_outcome(_rg_rec(revenue_growth_yoy=0.0)) == "TTM_PASS"


def test_outcome_decline_drop_gamma():
    r = _rg_rec(revenue_growth_yoy=-0.05, revenue_growth_definedness=DefinednessOutcome.DEFINED,
                multiyear_revenue_cagr=-0.06, revenue_down_years=2)
    assert revenue_growth_outcome(r) == "DECLINE_DROP"
    assert passes_revenue_growth_filter(r) is False


def test_outcome_trajectory_rescue_positive_cagr():
    r = _rg_rec(revenue_growth_yoy=-0.05, revenue_growth_definedness=DefinednessOutcome.DEFINED,
                multiyear_revenue_cagr=0.03, revenue_down_years=2)
    assert revenue_growth_outcome(r) == "TRAJECTORY_RESCUE"
    assert passes_revenue_growth_filter(r) is True


def test_outcome_trajectory_rescue_single_down_year():
    r = _rg_rec(revenue_growth_yoy=-0.05, revenue_growth_definedness=DefinednessOutcome.DEFINED,
                multiyear_revenue_cagr=-0.02, revenue_down_years=1)
    assert revenue_growth_outcome(r) == "TRAJECTORY_RESCUE"


def test_outcome_unassessable_pass():
    r = _rg_rec(revenue_growth_yoy=-0.05, revenue_growth_definedness=DefinednessOutcome.UNASSESSABLE)
    assert revenue_growth_outcome(r) == "UNASSESSABLE_PASS"
    assert passes_revenue_growth_filter(r) is True


def test_outcome_missing_ttm_judged_on_trajectory_drop():
    r = _rg_rec(revenue_growth_yoy=None, revenue_growth_definedness=DefinednessOutcome.DEFINED,
                multiyear_revenue_cagr=-0.10, revenue_down_years=3)
    assert revenue_growth_outcome(r) == "DECLINE_DROP"
    assert passes_revenue_growth_filter(r) is False


def test_outcome_missing_ttm_trajectory_rescue():
    r = _rg_rec(revenue_growth_yoy=None, revenue_growth_definedness=DefinednessOutcome.DEFINED,
                multiyear_revenue_cagr=0.02, revenue_down_years=2)
    assert revenue_growth_outcome(r) == "TRAJECTORY_RESCUE"


def test_outcome_missing_ttm_unassessable_pass():
    r = _rg_rec(revenue_growth_yoy=None, revenue_growth_definedness=DefinednessOutcome.UNASSESSABLE)
    assert revenue_growth_outcome(r) == "UNASSESSABLE_PASS"
    assert passes_revenue_growth_filter(r) is True


def test_pass_reason_absolute_even_when_table_present():
    # gm=0.40 clears k*median trivially but must NOT be tagged RELATIVE_RESCUE.
    rec = _record(gross_margin=0.40, gics_industry="Marine Shipping")
    assert gross_margin_pass_reason(rec, table=_bucket_table(0.30), k=0.5) == "ABSOLUTE_PASS"


def test_pass_reason_none_when_gross_margin_missing():
    rec = _record(gross_margin=None)
    assert gross_margin_pass_reason(rec, table=_bucket_table(0.30), k=0.5) is None


def test_pass_reason_none_when_bucket_median_none():
    # thin bucket, no group mapping -> bucket_median None -> no rescue
    table = SectorMedianTable(entries={"Marine Shipping": 0.20}, n_min=10,
                              counts={"Marine Shipping": 2})
    rec = _record(gross_margin=0.18, gics_industry="Marine Shipping")
    assert gross_margin_pass_reason(rec, table=table, k=0.5) is None


# --- delegation regression: passes_gross_margin_filter == (pass_reason is not None) ---

def test_passes_filter_delegates_to_pass_reason():
    table = _bucket_table(0.30)
    cases = [
        (_record(gross_margin=0.40, gics_industry="Marine Shipping"), None, None),
        (_record(gross_margin=0.40, gics_industry="Marine Shipping"), table, 0.5),
        (_record(gross_margin=0.20, gics_industry="Marine Shipping"), table, 0.5),
        (_record(gross_margin=0.20, gics_industry="Marine Shipping"),
         _bucket_table(0.50), 0.5),
        (_record(gross_margin=0.20, gics_industry="Marine Shipping"), None, None),
        (_record(gross_margin=None), table, 0.5),
    ]
    for rec, tbl, k in cases:
        expected = gross_margin_pass_reason(rec, tbl, k) is not None
        assert passes_gross_margin_filter(rec, tbl, k) is expected


# --- apply_basis_filters tags gross_margin_pass_reason on PASSING records only ---

def test_apply_basis_filters_tags_absolute_pass():
    rec = _record(ticker="ABS", gross_margin=0.45)
    apply_basis_filters([rec])
    assert rec.filter_passed_basis is True
    assert rec.gross_margin_pass_reason == "ABSOLUTE_PASS"


def test_apply_basis_filters_tags_relative_rescue():
    table = _bucket_table(0.30)
    rec = _record(ticker="RES", gross_margin=0.20, gics_industry="Marine Shipping")
    filters.apply_basis_filters([rec], sector_table=table, relative_k=0.5)
    assert rec.filter_passed_basis is True
    assert rec.gross_margin_pass_reason == "RELATIVE_RESCUE"


def test_apply_basis_filters_does_not_tag_failing_record():
    rec = _record(ticker="SMALL", market_cap_eur=1_000_000_000)  # fails market_cap
    apply_basis_filters([rec])
    assert rec.filter_passed_basis is False
    assert rec.gross_margin_pass_reason is None
