from app.models.screener_record import ScreenerRecord
from app.screener.filters import (
    apply_basis_filters,
    passes_gross_margin_filter,
    passes_market_cap_filter,
    passes_revenue_growth_filter,
    passes_volume_filter,
)


def _record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "market_cap_eur": 5_000_000_000,  # 5B EUR — well above €2B threshold
        "avg_daily_volume": 200_000,
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


# --- volume (unchanged: >= 100k avg daily) ---

def test_volume_passes_above_threshold():
    assert passes_volume_filter(_record(avg_daily_volume=100_001)) is True


def test_volume_passes_at_exact_threshold():
    assert passes_volume_filter(_record(avg_daily_volume=100_000)) is True


def test_volume_fails_below_threshold():
    assert passes_volume_filter(_record(avg_daily_volume=99_999)) is False


def test_volume_fails_when_none():
    assert passes_volume_filter(_record(avg_daily_volume=None)) is False


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
