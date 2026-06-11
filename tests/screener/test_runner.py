from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

import pytest

from app.errors import DataSourceError, DegradedDataError, FilterConfigError
from app.models.definedness import DefinednessOutcome
from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.screener.runner import (
    BasisFilterResult,
    ResolveReason,
    _assess_definedness_basket,
    _resolve_market_cap_eur,
    run_basis_filter,
)
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
    # SHRK has a negative TTM, so the pre-pass fetches its income statement. A falling
    # newest-first revenue series makes it a real gamma decline (CAGR < 0, down_years >= 2)
    # -> dropped on the revenue_growth viability floor. GOOD has positive TTM (no fetch).
    infos = {
        "GOOD": _PASSING_INFO,
        "SHRK": {**_PASSING_INFO, "revenueGrowth": -0.10},  # declining revenue
    }
    stmts = {"SHRK": _make_revenue_stmt([60.0, 80.0, 90.0, 100.0])}  # newest-first, falling
    mock_yf = _make_full_yf_mock(infos, stmts=stmts)
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


# --- 0b: resolution data-quality divert ---


class _CfgYF:
    """Configurable per-ticker yfinance fake for 0b divert tests."""
    def __init__(self, infos):
        self._infos = infos
    def get_ticker_info(self, ticker):
        return self._infos[ticker]
    def get_fx_rate(self, currency):
        if currency == "NOFX":
            raise DataSourceError("fx down")
        return 1.0


def _info(**kw):
    base = {"shortName": "X", "quoteType": "EQUITY", "marketCap": 5e9,
            "averageVolume": 5e5, "currentPrice": 100.0, "currency": "EUR",
            "grossMargins": 0.5, "revenueGrowth": 0.1, "sector": "Technology"}
    base.update(kw)
    return base


def test_resolve_reason_branches():
    fx = {}
    r = ScreenerRecord.from_yfinance_info("OK", _info())
    assert _resolve_market_cap_eur(r, _CfgYF({}), fx)[1] == ResolveReason.OK
    r = ScreenerRecord.from_yfinance_info("Z", _info(marketCap=0))
    assert _resolve_market_cap_eur(r, _CfgYF({}), fx)[1] == ResolveReason.NO_RAW_MC
    r = ScreenerRecord.from_yfinance_info("Z", _info(currency=None))
    assert _resolve_market_cap_eur(r, _CfgYF({}), fx)[1] == ResolveReason.NO_CURRENCY
    r = ScreenerRecord.from_yfinance_info("Z", _info(currency="NOFX"))
    assert _resolve_market_cap_eur(r, _CfgYF({}), {})[1] == ResolveReason.NO_FX


def test_resolve_mc_first_precedence():
    r = ScreenerRecord.from_yfinance_info("Z", _info(marketCap=None, currency=None))
    assert _resolve_market_cap_eur(r, _CfgYF({}), {})[1] == ResolveReason.NO_RAW_MC


def test_divert_no_symbol_data_and_fx():
    infos = {
        "OK":  _info(),
        "ATO": _info(marketCap=7.28e8),
        "NOMC": _info(marketCap=0),
        "NOCUR": _info(currency=None),
        "NOVOL": _info(averageVolume=0),
        "NOFX": _info(currency="NOFX"),
    }
    res = run_basis_filter(list(infos), _CfgYF(infos))
    nsd = {r.ticker: r.resolution_detail for r in res.no_symbol_data}
    assert nsd == {"NOMC": "NO_RAW_MC", "NOCUR": "NO_CURRENCY", "NOVOL": "NO_VOLUME"}
    assert [r.ticker for r in res.fx_unavailable] == ["NOFX"]
    assert "ATO" in [r.ticker for r in res.resolved]
    assert "ATO" not in [r.ticker for r in res.no_symbol_data]
    assert "OK" in [r.ticker for r in res.resolved]


def test_fx_rate_carried_on_resolved_record():
    infos = {"OK": _info(currency="USD")}
    res = run_basis_filter(["OK"], _CfgYF(infos))
    rec = res.resolved[0]
    assert rec.fx_rate == 1.0


def test_divert_no_price():
    infos = {
        "NOPX": _info(currentPrice=0, regularMarketPrice=0),
        "NOPX2": _info(currentPrice=None, regularMarketPrice=None),
        "OK": _info(),
    }
    res = run_basis_filter(list(infos), _CfgYF(infos))
    nsd = {r.ticker: r.resolution_detail for r in res.no_symbol_data}
    assert nsd == {"NOPX": "NO_PRICE", "NOPX2": "NO_PRICE"}
    assert "OK" in [r.ticker for r in res.resolved]


def test_divert_precedence_volume_before_price():
    infos = {"Z": _info(averageVolume=0, currentPrice=0, regularMarketPrice=0)}
    res = run_basis_filter(["Z"], _CfgYF(infos))
    assert res.no_symbol_data[0].resolution_detail == "NO_VOLUME"


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
                "currentPrice": 100.0, "currency": "EUR", "grossMargins": 0.5,
                "revenueGrowth": 0.1, "sector": "Technology"}
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


def test_run_filter_preview_writes_funnel_artifacts_when_output_dir_given(tmp_path):
    import json

    from app.screener.runner import run_filter_preview

    mock_yf = _make_yf_mock({**_PASSING_INFO, "sector": "Technology"})
    mock_edgar = _clean_edgar_mock()
    mock_edgar.get_cik.return_value = "0000320193"

    run_filter_preview(
        ["BIGC"], mock_yf, mock_edgar, output_dir=tmp_path, run_month="2026-06"
    )

    summary_path = tmp_path / "Universum" / "2026-06-funnel_summary.json"
    dropouts_path = tmp_path / "Universum" / "2026-06-dropouts.csv"
    assert summary_path.exists()
    assert dropouts_path.exists()

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    stages = {s["stage"]: s for s in payload["stages"]}

    assert "scoring" in stages
    assert stages["scoring"]["ran"] is False  # dry-run: scored=None
    assert "crosshits" in stages
    assert stages["crosshits"]["ran"] is False


def test_run_filter_preview_writes_nothing_without_output_dir(tmp_path):
    from app.screener.filter_report import FilterReport
    from app.screener.runner import run_filter_preview

    mock_yf = _make_yf_mock({**_PASSING_INFO, "sector": "Technology"})
    mock_edgar = _clean_edgar_mock()
    mock_edgar.get_cik.return_value = "0000320193"

    report = run_filter_preview(["BIGC"], mock_yf, mock_edgar)

    assert isinstance(report, FilterReport)
    # No output_dir → no funnel artifacts written anywhere under tmp_path.
    assert not (tmp_path / "Universum").exists()
    assert list(tmp_path.rglob("*-funnel_summary.json")) == []
    assert list(tmp_path.rglob("*-dropouts.csv")) == []


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


# --- CT-A definedness pre-pass ---


def _make_income_stmt(
    total_revenue: float | None,
    cost_of_revenue: float | None,
    gross_profit: float | None,
) -> "pd.DataFrame":
    """Minimal income_stmt fixture with one date column."""
    data: dict = {}
    if total_revenue is not None:
        data["Total Revenue"] = total_revenue
    if cost_of_revenue is not None:
        data["Cost Of Revenue"] = cost_of_revenue
    if gross_profit is not None:
        data["Gross Profit"] = gross_profit
    return pd.DataFrame({"2024": data})


def _suspect_info(**overrides) -> dict:
    """Base info for a suspect (Financial sector) ticker that passes volume+cap."""
    base = {
        "shortName": "Financial Corp",
        "currency": "EUR",
        "marketCap": 5_000_000_000,
        "averageVolume": 500_000,
        "currentPrice": 100.0,
        "grossMargins": None,         # None -> suspect basket
        "revenueGrowth": 0.05,
        "sector": "Financial Services",
        "industry": "Banks - Diversified",
    }
    base.update(overrides)
    return base


def _non_suspect_info(**overrides) -> dict:
    """Base info for a non-suspect (Technology, positive gm) ticker."""
    base = {
        "shortName": "Tech Corp",
        "currency": "EUR",
        "marketCap": 5_000_000_000,
        "averageVolume": 500_000,
        "currentPrice": 100.0,
        "grossMargins": 0.60,
        "revenueGrowth": 0.10,
        "sector": "Technology",
        "industry": "Software",
    }
    base.update(overrides)
    return base


def _make_full_yf_mock(infos: dict, stmts: dict | None = None) -> MagicMock:
    """YFinance mock supporting get_ticker_info, get_fx_rate, get_annual_statements."""
    mock = MagicMock()
    mock.get_ticker_info.side_effect = lambda t: infos[t]
    mock.get_fx_rate.return_value = 1.0
    if stmts is not None:
        mock.get_annual_statements.side_effect = lambda t: (stmts.get(t), None, None)
    else:
        mock.get_annual_statements.side_effect = DataSourceError("no stmt")
    return mock


def test_prepass_sets_defined_for_bank_with_real_waterfall():
    """A bank with a genuine income_stmt waterfall -> DEFINED (continues to gross_margin gate)."""
    stmt = _make_income_stmt(1_000.0, 300.0, 700.0)
    infos = {"BANK": _suspect_info()}
    yf = _make_full_yf_mock(infos, stmts={"BANK": stmt})

    result = run_basis_filter(["BANK"], yf)
    rec = result.resolved[0]
    # waterfall is DEFINED; gross_margin=None -> fails gross_margin gate, not metric_na
    assert rec.definedness is DefinednessOutcome.DEFINED
    assert rec.filter_failed_reason != "metric_na"


def test_prepass_sets_metrik_na_for_bank_without_cogs():
    """A bank with no Cost Of Revenue row -> waterfall UNDEFINED -> METRIK_NA."""
    stmt = _make_income_stmt(1_000.0, None, None)
    infos = {"BANK": _suspect_info()}
    yf = _make_full_yf_mock(infos, stmts={"BANK": stmt})

    result = run_basis_filter(["BANK"], yf)
    rec = result.resolved[0]
    assert rec.definedness is DefinednessOutcome.METRIK_NA
    assert rec.filter_failed_reason == "metric_na"


def test_prepass_sets_unassessable_on_fetch_failure():
    """Income statement fetch failure -> UNASSESSABLE -> 'statement_unavailable' reason."""
    infos = {"BANK": _suspect_info()}
    mock = MagicMock()
    mock.get_ticker_info.side_effect = lambda t: infos[t]
    mock.get_fx_rate.return_value = 1.0
    mock.get_annual_statements.side_effect = DataSourceError("timeout")

    result = run_basis_filter(["BANK"], mock)
    rec = result.resolved[0]
    assert rec.definedness is DefinednessOutcome.UNASSESSABLE
    assert rec.filter_failed_reason == "statement_unavailable"


def test_prepass_leaves_non_suspect_at_none():
    """A non-suspect (Technology, positive gm) record must NOT be assessed -> None."""
    infos = {"TECH": _non_suspect_info()}
    mock = MagicMock()
    mock.get_ticker_info.side_effect = lambda t: infos[t]
    mock.get_fx_rate.return_value = 1.0

    result = run_basis_filter(["TECH"], mock)
    rec = result.resolved[0]
    assert rec.definedness is None
    # get_annual_statements must NOT have been called for non-suspect records
    mock.get_annual_statements.assert_not_called()


def test_prepass_reit_shortcircuit_no_fetch():
    """REIT in gics_industry -> METRIK_NA without fetching the income statement."""
    infos = {"REI": _suspect_info(sector="Real Estate", industry="REIT - Retail")}
    mock = MagicMock()
    mock.get_ticker_info.side_effect = lambda t: infos[t]
    mock.get_fx_rate.return_value = 1.0

    result = run_basis_filter(["REI"], mock)
    rec = result.resolved[0]
    assert rec.definedness is DefinednessOutcome.METRIK_NA
    mock.get_annual_statements.assert_not_called()


def test_prepass_volume_failer_skipped_no_fetch():
    """Volume-failing record is not in the suspect basket ∩ cap+vol survivors -> no fetch."""
    infos = {"ILLIQUID": _suspect_info(averageVolume=1)}  # fails volume gate
    mock = MagicMock()
    mock.get_ticker_info.side_effect = lambda t: infos[t]
    mock.get_fx_rate.return_value = 1.0

    result = run_basis_filter(["ILLIQUID"], mock)
    rec = result.resolved[0]
    assert rec.definedness is None
    mock.get_annual_statements.assert_not_called()


def _suspect_record(**overrides) -> ScreenerRecord:
    """A suspect-basket record that passes market_cap (volume controllable via overrides)."""
    base = dict(
        ticker="SUSPECT",
        name="Financial Corp",
        currency="EUR",
        market_cap=5_000_000_000,
        market_cap_eur=5_000_000_000,
        avg_daily_volume=500_000,
        price=100.0,
        fx_rate=1.0,
        gross_margin=None,  # None -> suspect basket
        revenue_growth_yoy=0.05,
        gics_sector="Financial Services",
        gics_industry="Banks - Diversified",
    )
    base.update(overrides)
    return ScreenerRecord(**base)


def test_assess_basket_propagates_filterconfigerror_no_silent_none():
    """An invariant-violation FilterConfigError in the volume gate MUST propagate —
    a swallowed throw would leave definedness=None (DEFINED-by-default silent pass)."""
    # fx_rate=None -> _avg_daily_value_eur returns None -> passes_volume_filter raises.
    record = _suspect_record(fx_rate=None)
    yf = MagicMock()

    with pytest.raises(FilterConfigError):
        _assess_definedness_basket([record], yf)

    # The throw must NOT have been swallowed into a non-assessed pass.
    assert record.definedness is None  # never reached the assessment
    yf.get_annual_statements.assert_not_called()


def test_assess_basket_propagates_arbitrary_exception():
    """Catch-all removal, not FilterConfigError-specific: any exception propagates."""
    import app.screener.runner as runner_module

    record = _suspect_record()
    yf = MagicMock()

    def _boom(_rec):
        raise RuntimeError("filter exploded")

    original = runner_module.passes_volume_filter
    runner_module.passes_volume_filter = _boom
    try:
        with pytest.raises(RuntimeError):
            _assess_definedness_basket([record], yf)
    finally:
        runner_module.passes_volume_filter = original

    yf.get_annual_statements.assert_not_called()


def test_assess_basket_datasourceerror_still_unassessable():
    """Regression: an income-statement DataSourceError -> UNASSESSABLE (not None, not METRIK_NA)."""
    record = _suspect_record()
    yf = MagicMock()
    yf.get_annual_statements.side_effect = DataSourceError("timeout")

    _assess_definedness_basket([record], yf)

    assert record.definedness is DefinednessOutcome.UNASSESSABLE


# --- Punkt-3 revenue-growth trajectory pre-pass ---


def _make_revenue_stmt(revs_newest_first: list[float]):
    import pandas as pd
    cols = {str(2024 - i): {"Total Revenue": v} for i, v in enumerate(revs_newest_first)}
    return pd.DataFrame(cols)


def _growth_info(ttm, gm=0.5, **ov):
    # a clean non-suspect record (positive gm so it clears the gross-margin gate) with a
    # settable revenueGrowth; gm>=0.30 so the record reaches the revenue_growth pre-pass.
    info = _non_suspect_info(**ov)
    info["revenueGrowth"] = ttm
    info["grossMargins"] = gm
    return info


def test_revenue_prepass_no_fetch_when_ttm_positive():
    infos = {"GROW": _growth_info(0.05)}
    mock = _make_full_yf_mock(infos)  # get_annual_statements raises if called
    result = run_basis_filter(["GROW"], mock)
    mock.get_annual_statements.assert_not_called()
    assert result.resolved[0].revenue_growth_pass_reason == "TTM_PASS"


def test_revenue_prepass_fetches_and_drops_gamma():
    infos = {"DECL": _growth_info(-0.05)}
    stmts = {"DECL": _make_revenue_stmt([70.0, 80.0, 90.0, 100.0])}  # newest-first, falling
    mock = _make_full_yf_mock(infos, stmts=stmts)
    result = run_basis_filter(["DECL"], mock)
    mock.get_annual_statements.assert_called_once_with("DECL")
    rec = result.resolved[0]
    assert rec.revenue_growth_definedness is DefinednessOutcome.DEFINED
    assert rec.filter_failed_reason == "revenue_growth"
    assert rec.filter_passed_basis is False


def test_revenue_prepass_fetch_threshold_tracks_min_revenue_growth(monkeypatch):
    # If the floor is recalibrated above 0, a record with 0 <= TTM < floor must STILL be
    # fetched+assessed by the pre-pass (not skipped), because the gate will not TTM_PASS it.
    import app.screener.filters as _filters
    monkeypatch.setattr(_filters, "MIN_REVENUE_GROWTH", 0.05)
    infos = {"MID": _growth_info(0.02)}  # 0 <= 0.02 < 0.05
    stmts = {"MID": _make_revenue_stmt([60.0, 80.0, 90.0, 100.0])}  # falling -> gamma decline
    mock = _make_full_yf_mock(infos, stmts=stmts)
    result = run_basis_filter(["MID"], mock)
    mock.get_annual_statements.assert_called_once_with("MID")  # was fetched, not skipped
    rec = result.resolved[0]
    assert rec.revenue_growth_definedness is DefinednessOutcome.DEFINED
    assert rec.filter_failed_reason == "revenue_growth"  # assessed -> gamma drop


def test_revenue_prepass_fetches_and_rescues_positive_cagr():
    infos = {"RESC": _growth_info(-0.05)}
    stmts = {"RESC": _make_revenue_stmt([130.0, 90.0, 105.0, 100.0])}  # net growth, choppy
    mock = _make_full_yf_mock(infos, stmts=stmts)
    result = run_basis_filter(["RESC"], mock)
    rec = result.resolved[0]
    assert rec.revenue_growth_pass_reason == "TRAJECTORY_RESCUE"
    assert rec.filter_passed_basis is True


def test_revenue_prepass_fetch_failure_unassessable_pass():
    infos = {"FAIL": _growth_info(-0.05)}
    mock = MagicMock()
    mock.get_ticker_info.side_effect = lambda t: infos[t]
    mock.get_fx_rate.return_value = 1.0
    mock.get_annual_statements.side_effect = DataSourceError("timeout")
    result = run_basis_filter(["FAIL"], mock)
    rec = result.resolved[0]
    assert rec.revenue_growth_definedness is DefinednessOutcome.UNASSESSABLE
    assert rec.revenue_growth_pass_reason == "UNASSESSABLE_PASS"
    assert rec.filter_passed_basis is True


def test_revenue_prepass_missing_ttm_fetches_and_drops():
    infos = {"NONE": _growth_info(None)}
    stmts = {"NONE": _make_revenue_stmt([60.0, 80.0, 90.0, 100.0])}
    mock = _make_full_yf_mock(infos, stmts=stmts)
    result = run_basis_filter(["NONE"], mock)
    mock.get_annual_statements.assert_called_once_with("NONE")
    assert result.resolved[0].filter_failed_reason == "revenue_growth"


def test_revenue_prepass_no_fetch_when_gross_margin_fails():
    infos = {"LOWGM": _growth_info(-0.05, gm=0.05)}  # gm below 0.30 floor
    mock = _make_full_yf_mock(infos)
    result = run_basis_filter(["LOWGM"], mock)
    mock.get_annual_statements.assert_not_called()
    assert result.resolved[0].filter_failed_reason == "gross_margin"
