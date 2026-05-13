from app.models.screener_record import ScreenerRecord
from app.screener.filters import (
    apply_basis_filters,
    passes_liquidity_filter,
    passes_market_cap_filter,
    passes_penny_stock_filter,
    passes_volume_filter,
)


def _record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "market_cap": 500_000_000,
        "avg_daily_volume": 200_000,
        "price": 50.0,
        "bid": 49.8,
        "ask": 50.2,
    }
    return ScreenerRecord(**{**defaults, **kwargs})


# --- market cap ---

def test_market_cap_passes_above_threshold():
    assert passes_market_cap_filter(_record(market_cap=300_000_001)) is True


def test_market_cap_passes_at_exact_threshold():
    assert passes_market_cap_filter(_record(market_cap=300_000_000)) is True


def test_market_cap_fails_below_threshold():
    assert passes_market_cap_filter(_record(market_cap=299_999_999)) is False


def test_market_cap_fails_when_none():
    assert passes_market_cap_filter(_record(market_cap=None)) is False


# --- volume ---

def test_volume_passes_above_threshold():
    assert passes_volume_filter(_record(avg_daily_volume=100_001)) is True


def test_volume_passes_at_exact_threshold():
    assert passes_volume_filter(_record(avg_daily_volume=100_000)) is True


def test_volume_fails_below_threshold():
    assert passes_volume_filter(_record(avg_daily_volume=99_999)) is False


def test_volume_fails_when_none():
    assert passes_volume_filter(_record(avg_daily_volume=None)) is False


# --- penny stock ---

def test_penny_stock_passes_at_one_dollar():
    assert passes_penny_stock_filter(_record(price=1.0)) is True


def test_penny_stock_fails_below_one_dollar():
    assert passes_penny_stock_filter(_record(price=0.99)) is False


def test_penny_stock_fails_when_price_none():
    assert passes_penny_stock_filter(_record(price=None)) is False


# --- liquidity (bid-ask spread) ---

def test_liquidity_passes_tight_spread():
    # spread = (50.1 - 49.9) / 50.0 = 0.4%
    assert passes_liquidity_filter(_record(bid=49.9, ask=50.1)) is True


def test_liquidity_fails_wide_spread():
    # spread = (55.0 - 45.0) / 50.0 = 20%
    assert passes_liquidity_filter(_record(bid=45.0, ask=55.0)) is False


def test_liquidity_fails_when_bid_is_none():
    assert passes_liquidity_filter(_record(bid=None, ask=50.0)) is False


def test_liquidity_fails_when_ask_is_none():
    assert passes_liquidity_filter(_record(bid=49.9, ask=None)) is False


def test_liquidity_fails_when_bid_is_zero():
    assert passes_liquidity_filter(_record(bid=0.0, ask=50.0)) is False


# --- apply_basis_filters ---

def test_apply_basis_filters_returns_only_passing_records():
    passing = _record(ticker="GOOD")
    failing = _record(ticker="SMALL", market_cap=100_000)

    result = apply_basis_filters([passing, failing])

    assert len(result) == 1
    assert result[0].ticker == "GOOD"
    assert result[0].filter_passed_basis is True


def test_apply_basis_filters_sets_failed_reason():
    record = _record(ticker="SMALL", market_cap=100_000)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "market_cap"


def test_apply_basis_filters_sets_failed_reason_avg_volume():
    record = _record(ticker="ILLIQUID", avg_daily_volume=10)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "avg_volume"


def test_apply_basis_filters_sets_failed_reason_liquidity():
    # passes market_cap, volume, penny_stock but fails wide bid-ask
    record = _record(ticker="SPREAD", bid=45.0, ask=55.0)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "liquidity"


def test_apply_basis_filters_sets_filter_passed_basis_false_on_failure():
    record = _record(ticker="SMALL", market_cap=100_000)
    apply_basis_filters([record])
    assert record.filter_passed_basis is False


def test_apply_basis_filters_checks_filters_in_order():
    # fails both market_cap and volume — reason should be market_cap (first checked)
    record = _record(ticker="DOUBLE_FAIL", market_cap=100_000, avg_daily_volume=10)
    apply_basis_filters([record])
    assert record.filter_failed_reason == "market_cap"


def test_apply_basis_filters_returns_empty_for_all_failures():
    records = [_record(ticker="PENNY", price=0.50)]
    assert apply_basis_filters(records) == []


def test_apply_basis_filters_returns_empty_list_for_empty_input():
    assert apply_basis_filters([]) == []


# --- apply_edgar_filters ---


def _edgar_record(**kwargs) -> ScreenerRecord:
    defaults = {
        "ticker": "TEST",
        "cik": "0000320193",
        "market_cap": 500_000_000,
        "avg_daily_volume": 200_000,
        "price": 50.0,
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
