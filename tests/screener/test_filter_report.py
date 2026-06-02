from unittest.mock import MagicMock

from app.errors import DataSourceError
from app.models.screener_record import ScreenerRecord
from app.screener.filter_report import (
    FilterReport,
    GoingConcernDrop,
    build_filter_report,
)
from app.services.edgar_client import GoingConcernHit


def _gc_dropped_record(ticker: str = "ZZZ", cik: str = "0000111111") -> ScreenerRecord:
    return ScreenerRecord(
        ticker=ticker,
        cik=cik,
        filter_passed_basis=True,
        filter_passed_edgar=False,
        filter_failed_reason="going_concern",
    )


def _no_cik_skip_record(ticker: str = "NOCIK") -> ScreenerRecord:
    return ScreenerRecord(
        ticker=ticker,
        cik=None,
        filter_passed_basis=True,
        edgar_skipped=True,
        edgar_skipped_reason="no_cik",
    )


def _dse_skip_record(ticker: str = "DSE") -> ScreenerRecord:
    return ScreenerRecord(
        ticker=ticker,
        cik="0000222222",
        filter_passed_basis=True,
        edgar_skipped=True,
        edgar_skipped_reason="data_source_error",
    )


def test_build_report_produces_going_concern_drop_with_hit_detail():
    record = _gc_dropped_record(ticker="ZZZ", cik="0000111111")
    edgar = MagicMock()
    edgar.going_concern_hit.return_value = GoingConcernHit(
        accession_number="0000111111-26-000005",
        file_type="10-K",
        file_date="2026-01-15",
    )

    report = build_filter_report([record], edgar)

    edgar.going_concern_hit.assert_called_once_with("0000111111")
    assert len(report.going_concern_drops) == 1
    drop = report.going_concern_drops[0]
    assert isinstance(drop, GoingConcernDrop)
    assert drop.ticker == "ZZZ"
    assert drop.cik == "0000111111"
    assert drop.accession_number == "0000111111-26-000005"
    assert drop.file_type == "10-K"
    assert drop.file_date == "2026-01-15"


def test_skip_aggregate_splits_no_cik_and_data_source_error():
    records = [
        _no_cik_skip_record("NOCIK1"),
        _no_cik_skip_record("NOCIK2"),
        _dse_skip_record("DSE1"),
    ]
    edgar = MagicMock()

    report = build_filter_report(records, edgar)

    assert report.edgar_skipped_no_cik == ["NOCIK1", "NOCIK2"]
    assert report.edgar_skipped_data_source_error == ["DSE1"]
    assert report.total_skipped() == 3
    # no going-concern drops here → going_concern_hit never invoked
    edgar.going_concern_hit.assert_not_called()


def test_going_concern_hit_data_source_error_yields_drop_with_none_detail():
    record = _gc_dropped_record(ticker="BOOM", cik="0000999999")
    edgar = MagicMock()
    edgar.going_concern_hit.side_effect = DataSourceError("efts down")

    report = build_filter_report([record], edgar)

    assert len(report.going_concern_drops) == 1
    drop = report.going_concern_drops[0]
    assert drop.ticker == "BOOM"
    assert drop.cik == "0000999999"
    assert drop.accession_number is None
    assert drop.file_type is None
    assert drop.file_date is None


def test_to_dict_returns_documented_json_shape():
    gc = _gc_dropped_record(ticker="ZZZ", cik="0000111111")
    edgar = MagicMock()
    edgar.going_concern_hit.return_value = GoingConcernHit(
        accession_number="0000111111-26-000005",
        file_type="10-Q",
        file_date="2026-02-01",
    )
    records = [gc, _no_cik_skip_record("NOCIK1"), _dse_skip_record("DSE1")]

    report = build_filter_report(records, edgar)
    payload = report.to_dict()

    assert payload["going_concern_drops"] == [
        {
            "ticker": "ZZZ",
            "cik": "0000111111",
            "accession_number": "0000111111-26-000005",
            "file_type": "10-Q",
            "file_date": "2026-02-01",
        }
    ]
    assert payload["edgar_skipped"] == {
        "no_cik": {"count": 1, "tickers": ["NOCIK1"]},
        "data_source_error": {"count": 1, "tickers": ["DSE1"]},
    }


def test_report_log_emits_warning_per_drop_and_info_summary(caplog):
    import logging

    gc = _gc_dropped_record(ticker="ZZZ", cik="0000111111")
    edgar = MagicMock()
    edgar.going_concern_hit.return_value = GoingConcernHit(
        accession_number="acc", file_type="10-K", file_date="2026-01-01"
    )
    records = [gc, _no_cik_skip_record("NOCIK1")]
    report = build_filter_report(records, edgar)

    logger = logging.getLogger("app.screener.filter_report")
    with caplog.at_level(logging.INFO, logger="app.screener.filter_report"):
        report.log(logger)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(warnings) == 1
    assert "ZZZ" in warnings[0].getMessage()
    assert len(infos) >= 1
