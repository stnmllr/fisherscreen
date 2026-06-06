from pathlib import Path
from unittest.mock import MagicMock

from app.errors import DataSourceError, DegradedDataError
from app.models.run_record import RunRecord
from app.screener.runner import BasisFilterResult, run_basis_filter
from app.services.gemini_client import GeminiScoreResult

_FX_USD_EUR = 0.92  # approximate USD → EUR rate for tests


def _make_yf_mock(info: dict) -> MagicMock:
    mock = MagicMock()
    mock.get_ticker_info.return_value = info
    mock.get_fx_rate.return_value = _FX_USD_EUR
    return mock


_PASSING_INFO = {
    "shortName": "Big Corp",
    "currency": "USD",
    "marketCap": 3_000_000_000,  # 3B USD × 0.92 = 2.76B EUR — above €2B threshold
    "averageVolume": 200_000,
    "currentPrice": 50.0,
    "grossMargins": 0.45,        # 45% — above 30% threshold (decimal)
    "revenueGrowth": 0.08,       # 8% YoY — above 0%
}


def test_run_returns_passing_records():
    mock_yf = _make_yf_mock(_PASSING_INFO)
    result = run_basis_filter(["BIGC"], mock_yf).passed

    assert len(result) == 1
    assert result[0].ticker == "BIGC"
    assert result[0].filter_passed_basis is True


def test_run_skips_tickers_with_data_source_errors():
    mock_yf = MagicMock()
    mock_yf.get_ticker_info.side_effect = DataSourceError("network error")

    result = run_basis_filter(["FAIL"], mock_yf).passed

    assert result == []


def test_run_processes_multiple_tickers():
    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def side_effect(ticker):
        if ticker == "GOOD":
            return _PASSING_INFO
        return {**_PASSING_INFO, "revenueGrowth": -0.10}  # declining revenue fails V3

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["GOOD", "SHRK"], mock_yf).passed

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_returns_empty_for_empty_ticker_list():
    mock_yf = MagicMock()
    result = run_basis_filter([], mock_yf).passed
    assert result == []


def test_run_continues_after_individual_data_source_error():
    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def side_effect(ticker):
        if ticker == "FAIL":
            raise DataSourceError("bad ticker")
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["FAIL", "GOOD"], mock_yf).passed

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_skips_ticker_with_malformed_yfinance_data():
    # yfinance can return strings where floats are expected — Pydantic raises ValidationError
    # The runner should treat this as a per-ticker failure, not crash the whole run
    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def side_effect(ticker):
        if ticker == "MALFORMED":
            return {**_PASSING_INFO, "marketCap": "n/a"}
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["MALFORMED", "GOOD"], mock_yf).passed

    assert len(result) == 1
    assert result[0].ticker == "GOOD"


def test_run_sets_market_cap_eur_on_record():
    # Verifies FX conversion is applied in runner (not in filter layer)
    mock_yf = _make_yf_mock(_PASSING_INFO)
    result = run_basis_filter(["BIGC"], mock_yf).passed

    assert len(result) == 1
    assert result[0].market_cap_eur is not None
    expected_eur = _PASSING_INFO["marketCap"] * _FX_USD_EUR
    assert abs(result[0].market_cap_eur - expected_eur) < 1.0


def test_run_fails_ticker_when_fx_rate_unavailable():
    # If FX lookup fails, market_cap_eur is None → fails market_cap filter
    mock_yf = MagicMock()
    mock_yf.get_ticker_info.return_value = _PASSING_INFO
    mock_yf.get_fx_rate.side_effect = DataSourceError("FX unavailable")

    result = run_basis_filter(["BIGC"], mock_yf).passed

    assert result == []


# --- ITEM 2: yfinance resolution aggregate ---


def test_run_basis_filter_returns_basis_filter_result_with_passed_and_unresolved():
    from app.screener.runner import BasisFilterResult

    mock_yf = _make_yf_mock(_PASSING_INFO)
    result = run_basis_filter(["BIGC"], mock_yf)

    assert isinstance(result, BasisFilterResult)
    assert [r.ticker for r in result.passed] == ["BIGC"]
    assert result.unresolved == []


def test_run_basis_filter_collects_unresolved_on_data_source_error():
    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def side_effect(ticker):
        if ticker in ("FAIL2", "FAIL1"):
            raise DataSourceError("bad ticker")
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["FAIL2", "GOOD", "FAIL1"], mock_yf)

    assert [r.ticker for r in result.passed] == ["GOOD"]
    # sorted, deterministic
    assert result.unresolved == ["FAIL1", "FAIL2"]


def test_run_basis_filter_collects_unresolved_on_degraded_dict():
    # Degraded yfinance 404 dict (no name/marketCap) surfaces from the client
    # as DataSourceError ("degraded info") → must land in unresolved, not pass
    # silently as a generic missing-field basis drop.
    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def side_effect(ticker):
        if ticker == "DEGRADED":
            raise DataSourceError("yfinance returned degraded info for DEGRADED")
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["DEGRADED", "GOOD"], mock_yf)

    assert [r.ticker for r in result.passed] == ["GOOD"]
    assert result.unresolved == ["DEGRADED"]


def test_run_basis_filter_collects_unresolved_on_validation_error():
    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def side_effect(ticker):
        if ticker == "MALFORMED":
            return {**_PASSING_INFO, "marketCap": "n/a"}
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect
    result = run_basis_filter(["MALFORMED", "GOOD"], mock_yf)

    assert result.unresolved == ["MALFORMED"]


def test_run_basis_filter_emits_aggregate_warning_with_count(caplog):
    import logging

    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def side_effect(ticker):
        if ticker in ("FAIL1", "FAIL2"):
            raise DataSourceError("bad ticker")
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = side_effect

    with caplog.at_level(logging.WARNING, logger="app.screener.runner"):
        run_basis_filter(["FAIL1", "GOOD", "FAIL2"], mock_yf)

    aggregate = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "unresolved by yfinance" in r.getMessage()
    ]
    assert len(aggregate) == 1
    msg = aggregate[0].getMessage()
    assert "2/3" in msg
    assert "FAIL1" in msg and "FAIL2" in msg


class _FunnelYF:
    """Resolves GOOD; raises DegradedDataError for DEGR; DataSourceError for GONE."""
    def get_ticker_info(self, ticker):
        if ticker == "DEGR":
            raise DegradedDataError("degraded")
        if ticker == "GONE":
            raise DataSourceError("404")
        return {"shortName": ticker, "marketCap": 5e9, "averageVolume": 5e5,
                "currency": "EUR", "grossMargins": 0.5, "revenueGrowth": 0.1,
                "sector": "Technology"}
    def get_fx_rate(self, currency):
        return 1.0


def test_basis_result_splits_degraded_from_unresolved():
    result = run_basis_filter(["GOOD", "DEGR", "GONE"], _FunnelYF())
    assert result.degraded == ["DEGR"]
    assert set(result.unresolved) == {"DEGR", "GONE"}  # unresolved = all that failed resolution
    assert [r.ticker for r in result.resolved] == ["GOOD"]
    assert [r.ticker for r in result.passed] == ["GOOD"]


def test_run_basis_filter_no_aggregate_warning_when_all_resolve(caplog):
    import logging

    mock_yf = _make_yf_mock(_PASSING_INFO)
    with caplog.at_level(logging.WARNING, logger="app.screener.runner"):
        run_basis_filter(["BIGC"], mock_yf)

    aggregate = [
        r for r in caplog.records if "unresolved by yfinance" in r.getMessage()
    ]
    assert aggregate == []


# --- run_edgar_filter ---


def _passing_basis_record(ticker="TEST", cik="0000320193") -> "ScreenerRecord":
    from app.models.screener_record import ScreenerRecord
    return ScreenerRecord(
        ticker=ticker,
        cik=cik,
        market_cap_eur=5_000_000_000,
        avg_daily_volume=200_000,
        gross_margin=0.45,
        revenue_growth_yoy=0.08,
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


def test_run_edgar_filter_sets_no_cik_reason_when_lookup_returns_none():
    from app.screener.runner import run_edgar_filter
    mock_edgar = MagicMock()
    mock_edgar.get_cik.return_value = None
    record = _passing_basis_record(cik=None)
    record.cik = None

    run_edgar_filter([record], mock_edgar)

    assert record.edgar_skipped is True
    assert record.edgar_skipped_reason == "no_cik"


def test_run_edgar_filter_sets_data_source_error_reason_on_edgar_failure():
    from app.screener.runner import run_edgar_filter
    mock_edgar = _clean_edgar_mock()
    mock_edgar.get_cik.return_value = "0000320193"
    mock_edgar.has_restatement.side_effect = DataSourceError("network error")
    record = _passing_basis_record()

    run_edgar_filter([record], mock_edgar)

    assert record.edgar_skipped is True
    assert record.edgar_skipped_reason == "data_source_error"


def test_run_filter_preview_runs_basis_and_edgar_returns_report():
    from app.screener.filter_report import FilterReport
    from app.screener.runner import run_filter_preview

    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def yf_side_effect(ticker):
        return _PASSING_INFO  # both tickers pass basis

    mock_yf.get_ticker_info.side_effect = yf_side_effect

    mock_edgar = _clean_edgar_mock()
    # PASS resolves a CIK and is clean; NOCIK resolves to None → no_cik skip
    def cik_side_effect(ticker):
        return "0000320193" if ticker == "PASS" else None

    mock_edgar.get_cik.side_effect = cik_side_effect

    report = run_filter_preview(["PASS", "NOCIK"], mock_yf, mock_edgar)

    assert isinstance(report, FilterReport)
    assert report.edgar_skipped_no_cik == ["NOCIK"]
    assert report.going_concern_drops == []


def test_run_filter_preview_propagates_unresolved_into_report():
    from app.screener.runner import run_filter_preview

    mock_yf = MagicMock()
    mock_yf.get_fx_rate.return_value = _FX_USD_EUR

    def yf_side_effect(ticker):
        if ticker == "GHOST":
            raise DataSourceError("404 no such ticker")
        return _PASSING_INFO

    mock_yf.get_ticker_info.side_effect = yf_side_effect

    mock_edgar = _clean_edgar_mock()
    mock_edgar.get_cik.return_value = "0000320193"

    report = run_filter_preview(["PASS", "GHOST"], mock_yf, mock_edgar)

    assert report.yfinance_unresolved == ["GHOST"]
    payload = report.to_dict()
    assert payload["yfinance_unresolved"] == {"count": 1, "tickers": ["GHOST"]}


def test_run_filter_preview_has_no_gemini_parameter():
    # Structurally cannot score: the signature must not accept a gemini client.
    import inspect

    from app.screener.runner import run_filter_preview

    params = inspect.signature(run_filter_preview).parameters
    assert "gemini" not in params           # structurally cannot score — unchanged invariant
    assert set(params) == {"tickers", "yfinance", "edgar", "output_dir", "run_month"}


# --- run_screener ---


def _scored_yfinance_mock(ticker: str) -> MagicMock:
    mock = MagicMock()
    mock.get_ticker_info.return_value = {
        "shortName": f"{ticker} Corp",
        "marketCap": 5_000_000_000,
        "averageVolume": 1_000_000,
        "currentPrice": 100.0,
        "sector": "Technology",
        "industry": "Software",
        "currency": "USD",
        "grossMargins": 0.60,
        "revenueGrowth": 0.15,
    }
    mock.get_fx_rate.return_value = _FX_USD_EUR
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
    assert len(paths) == 5  # 3 markdown + funnel_summary.json + dropouts.csv


def test_run_screener_writes_funnel_artifacts(tmp_path):
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
    assert "2026-05-funnel_summary.json" in names
    assert "2026-05-dropouts.csv" in names


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
