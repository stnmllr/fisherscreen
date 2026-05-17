from datetime import datetime, timezone

from app.models.screener_record import ScreenerRecord


def test_minimal_construction():
    record = ScreenerRecord(ticker="AAPL")
    assert record.ticker == "AAPL"
    assert record.market_cap is None
    assert record.filter_passed_basis is None
    assert record.has_restatement is None


def test_screened_at_defaults_to_now():
    before = datetime.now(timezone.utc)
    record = ScreenerRecord(ticker="AAPL")
    after = datetime.now(timezone.utc)
    assert before <= record.screened_at <= after


def test_from_yfinance_info_full():
    info = {
        "shortName": "Apple Inc.",
        "currency": "USD",
        "marketCap": 3_000_000_000_000,
        "averageVolume": 60_000_000,
        "currentPrice": 195.0,
        "bid": 194.9,
        "ask": 195.1,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "cik": "0000320193",
    }
    record = ScreenerRecord.from_yfinance_info("AAPL", info)
    assert record.ticker == "AAPL"
    assert record.name == "Apple Inc."
    assert record.currency == "USD"
    assert record.market_cap == 3_000_000_000_000
    assert record.avg_daily_volume == 60_000_000
    assert record.price == 195.0
    assert record.bid == 194.9
    assert record.ask == 195.1
    assert record.gics_sector == "Technology"
    assert record.gics_industry == "Consumer Electronics"
    assert record.cik == "0000320193"


def test_from_yfinance_info_falls_back_to_regular_market_price():
    info = {"regularMarketPrice": 50.0}
    record = ScreenerRecord.from_yfinance_info("XYZ", info)
    assert record.price == 50.0


def test_from_yfinance_info_missing_fields_give_none():
    record = ScreenerRecord.from_yfinance_info("EMPTY", {})
    assert record.ticker == "EMPTY"
    assert record.name is None
    assert record.market_cap is None
    assert record.price is None


def test_from_yfinance_info_normalizes_zero_to_none():
    # yfinance returns 0 for illiquid/OTC tickers instead of omitting the field
    info = {"marketCap": 0, "averageVolume": 0}
    record = ScreenerRecord.from_yfinance_info("OTC", info)
    assert record.market_cap is None
    assert record.avg_daily_volume is None


def test_from_yfinance_info_normalizes_zero_bid_ask_to_none():
    # yfinance returns 0 for bid/ask on illiquid/OTC tickers
    info = {"bid": 0, "ask": 0}
    record = ScreenerRecord.from_yfinance_info("OTC", info)
    assert record.bid is None
    assert record.ask is None


def test_record_is_mutable():
    record = ScreenerRecord(ticker="AAPL")
    record.filter_passed_basis = True
    assert record.filter_passed_basis is True


def test_edgar_defaults():
    record = ScreenerRecord(ticker="AAPL")
    assert record.has_active_enforcement is False
    assert record.edgar_skipped is False


def test_from_yfinance_info_populates_financial_ratios():
    info = {
        "grossMargins": 0.45,
        "revenueGrowth": 0.12,
        "operatingMargins": 0.25,
        "returnOnEquity": 0.18,
        "debtToEquity": 45.0,
    }
    record = ScreenerRecord.from_yfinance_info("TEST", info)
    assert record.gross_margin == 0.45
    assert record.revenue_growth_yoy == 0.12
    assert record.operating_margin == 0.25
    assert record.return_on_equity == 0.18
    assert record.debt_to_equity == 45.0


def test_financial_ratios_default_to_none_when_missing():
    record = ScreenerRecord.from_yfinance_info("TEST", {})
    assert record.gross_margin is None
    assert record.revenue_growth_yoy is None
    assert record.operating_margin is None
    assert record.return_on_equity is None
    assert record.debt_to_equity is None


def test_gemini_dimension_fields_default_to_none():
    record = ScreenerRecord(ticker="TEST")
    assert record.gemini_dimensions is None
    assert record.gemini_summary is None


def test_gemini_dimensions_can_be_set():
    dims = {"growth": 4, "profitability": 3, "management": 4, "innovation": 5, "resilience": 3}
    record = ScreenerRecord(ticker="TEST", gemini_dimensions=dims, gemini_summary="Good company")
    assert record.gemini_dimensions["growth"] == 4
    assert record.gemini_summary == "Good company"


def test_gemini_dimensions_accepts_any_dict_values():
    # ScreenerRecord stores whatever is set — clamping/validation is GeminiClientImpl's job
    record = ScreenerRecord(ticker="TEST", gemini_dimensions={"growth": 99, "other": -1})
    assert record.gemini_dimensions == {"growth": 99, "other": -1}
