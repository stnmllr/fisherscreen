from pathlib import Path
from unittest.mock import MagicMock

from app.errors import DataSourceError
from app.models.run_record import RunRecord
from app.screener.runner import run_basis_filter
from app.services.gemini_client import GeminiScoreResult


def _make_yf_mock(info: dict) -> MagicMock:
    mock = MagicMock()
    mock.get_ticker_info.return_value = info
    return mock


_PASSING_INFO = {
    "shortName": "Big Corp",
    "currency": "USD",
    "marketCap": 500_000_000,
    "averageVolume": 200_000,
    "currentPrice": 50.0,
    "bid": 49.8,
    "ask": 50.2,
}


def test_run_returns_passing_records():
    mock_yf = _make_yf_mock(_PASSING_INFO)
    result = run_basis_filter(["BIGC"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "BIGC"
    assert result[0].filter_passed_basis is True


def test_run_skips_tickers_with_data_source_errors():
    mock_yf = MagicMock()
    mock_yf.get_ticker_info.side_effect = DataSourceError("network error")

    result = run_basis_filter(["FAIL"], mock_yf)

    assert result == []


def test_run_processes_multiple_tickers():
    mock_yf = MagicMock()

    def side_effect(ticker):
        if ticker == "GOOD":
            return _PASSING_INFO
        return {**_PASSING_INFO, "currentPrice": 0.50}  # penny stock

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["GOOD", "PENY"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_returns_empty_for_empty_ticker_list():
    mock_yf = MagicMock()
    result = run_basis_filter([], mock_yf)
    assert result == []


def test_run_continues_after_individual_data_source_error():
    mock_yf = MagicMock()

    def side_effect(ticker):
        if ticker == "FAIL":
            raise DataSourceError("bad ticker")
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["FAIL", "GOOD"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_skips_ticker_with_malformed_yfinance_data():
    # yfinance can return strings where floats are expected — Pydantic raises ValidationError
    # The runner should treat this as a per-ticker failure, not crash the whole run
    mock_yf = MagicMock()

    def side_effect(ticker):
        if ticker == "MALFORMED":
            return {**_PASSING_INFO, "marketCap": "n/a"}
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["MALFORMED", "GOOD"], mock_yf)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


# --- run_edgar_filter ---


def _passing_basis_record(ticker="TEST", cik="0000320193") -> "ScreenerRecord":
    from app.models.screener_record import ScreenerRecord
    return ScreenerRecord(
        ticker=ticker,
        cik=cik,
        market_cap=500_000_000,
        avg_daily_volume=200_000,
        price=50.0,
        filter_passed_basis=True,
    )


def _clean_edgar_mock() -> MagicMock:
    mock = MagicMock()
    mock.get_cik.return_value = None
    mock.has_restatement.return_value = False
    mock.has_going_concern.return_value = False
    mock.has_active_enforcement.return_value = False
    return mock


def test_run_edgar_filter_passes_clean_records():
    from app.screener.runner import run_edgar_filter
    record = _passing_basis_record()
    result = run_edgar_filter([record], _clean_edgar_mock())
    assert len(result) == 1
    assert result[0].filter_passed_edgar is True


def test_run_edgar_filter_skips_records_without_cik():
    from app.screener.runner import run_edgar_filter
    mock_edgar = MagicMock()
    mock_edgar.get_cik.return_value = None  # lookup also finds nothing
    record = _passing_basis_record(cik=None)
    record.cik = None

    result = run_edgar_filter([record], mock_edgar)

    mock_edgar.has_restatement.assert_not_called()
    assert len(result) == 1
    assert result[0].edgar_skipped is True
    assert result[0].filter_passed_edgar is None


def test_run_edgar_filter_populates_cik_via_lookup():
    from app.screener.runner import run_edgar_filter
    mock_edgar = _clean_edgar_mock()
    mock_edgar.get_cik.return_value = "0000320193"

    record = _passing_basis_record(cik=None)
    record.cik = None

    result = run_edgar_filter([record], mock_edgar)

    mock_edgar.get_cik.assert_called_once_with(record.ticker)
    assert record.cik == "0000320193"
    mock_edgar.has_restatement.assert_called_once()
    assert len(result) == 1
    assert result[0].filter_passed_edgar is True


def test_run_edgar_filter_skips_on_data_source_error():
    from app.screener.runner import run_edgar_filter
    mock_edgar = MagicMock()
    mock_edgar.has_restatement.side_effect = DataSourceError("network error")
    record = _passing_basis_record()

    result = run_edgar_filter([record], mock_edgar)

    assert len(result) == 1
    assert result[0].edgar_skipped is True
    assert result[0].filter_passed_edgar is None


def test_run_edgar_filter_excludes_restatement_records():
    from app.screener.runner import run_edgar_filter
    mock_edgar = _clean_edgar_mock()
    mock_edgar.has_restatement.return_value = True
    record = _passing_basis_record()

    result = run_edgar_filter([record], mock_edgar)

    assert result == []
    assert record.filter_passed_edgar is False
    assert record.filter_failed_reason == "restatement"


def test_run_edgar_filter_processes_multiple_records():
    from app.screener.runner import run_edgar_filter

    mock_edgar = _clean_edgar_mock()
    mock_edgar.has_restatement.side_effect = lambda cik, **_: cik == "0000111111"
    good = _passing_basis_record("GOOD", cik="0000320193")
    bad = _passing_basis_record("BAD", cik="0000111111")

    result = run_edgar_filter([good, bad], mock_edgar)

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_edgar_filter_continues_after_individual_error():
    from app.screener.runner import run_edgar_filter

    mock_edgar = _clean_edgar_mock()
    def restatement_side_effect(cik, **_):
        if cik == "0000111111":
            raise DataSourceError("timeout")
        return False

    mock_edgar.has_restatement.side_effect = restatement_side_effect
    error_record = _passing_basis_record("ERR", cik="0000111111")
    good_record = _passing_basis_record("GOOD", cik="0000320193")

    result = run_edgar_filter([error_record, good_record], mock_edgar)

    assert len(result) == 2  # error_record is edgar_skipped, still passes through
    tickers = {r.ticker for r in result}
    assert "GOOD" in tickers
    assert "ERR" in tickers
    assert error_record.edgar_skipped is True


def test_run_edgar_filter_returns_empty_for_empty_input():
    from app.screener.runner import run_edgar_filter
    assert run_edgar_filter([], MagicMock()) == []


# --- run_screener ---


def _scored_yfinance_mock(ticker: str) -> MagicMock:
    mock = MagicMock()
    mock.get_ticker_info.return_value = {
        "shortName": f"{ticker} Corp",
        "marketCap": 5_000_000_000,
        "averageVolume": 1_000_000,
        "currentPrice": 100.0,
        "bid": 99.9,
        "ask": 100.1,
        "sector": "Technology",
        "industry": "Software",
        "currency": "USD",
    }
    return mock


def _full_mock_suite(ticker: str = "AAPL"):
    yfinance = _scored_yfinance_mock(ticker)
    edgar = MagicMock()
    edgar.has_restatement.return_value = False
    edgar.has_going_concern.return_value = False
    edgar.has_active_enforcement.return_value = False
    gemini = MagicMock()
    gemini.score_ticker.return_value = GeminiScoreResult(
        dimensions={"growth": 4, "profitability": 4, "management": 4, "innovation": 4, "resilience": 4},
        summary="Good",
        tokens_in=500,
        tokens_out=80,
    )
    tracker = MagicMock()
    tracker.finish.return_value = RunRecord(run_id="2026-05-13T08:00:00+00:00")
    return yfinance, edgar, gemini, tracker


def test_run_screener_returns_records_run_record_and_paths(tmp_path):
    from app.screener.runner import run_screener
    yfinance, edgar, gemini, tracker = _full_mock_suite()

    records, run_record, paths = run_screener(
        tickers=["AAPL"],
        yfinance=yfinance,
        edgar=edgar,
        gemini=gemini,
        run_tracker=tracker,
        output_dir=tmp_path,
    )

    assert isinstance(records, list)
    assert isinstance(run_record, RunRecord)
    assert len(paths) == 3


def test_run_screener_creates_three_named_output_files(tmp_path):
    from app.screener.runner import run_screener
    yfinance, edgar, gemini, tracker = _full_mock_suite()

    _, _, paths = run_screener(
        tickers=["AAPL"],
        yfinance=yfinance,
        edgar=edgar,
        gemini=gemini,
        run_tracker=tracker,
        output_dir=tmp_path,
    )

    names = {p.name for p in paths}
    assert "2026-05-Dimensions.md" in names
    assert "2026-05-Crosshits.md" in names
    assert "2026-05-Changes.md" in names
