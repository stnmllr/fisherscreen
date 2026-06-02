from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.errors import DataSourceError
from app.models.screener_record import ScreenerRecord

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient


@dataclass(frozen=True)
class GoingConcernDrop:
    ticker: str
    cik: str | None
    accession_number: str | None
    file_type: str | None
    file_date: str | None


@dataclass
class FilterReport:
    going_concern_drops: list[GoingConcernDrop]
    edgar_skipped_no_cik: list[str]
    edgar_skipped_data_source_error: list[str]

    def total_skipped(self) -> int:
        return len(self.edgar_skipped_no_cik) + len(self.edgar_skipped_data_source_error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "going_concern_drops": [
                {
                    "ticker": drop.ticker,
                    "cik": drop.cik,
                    "accession_number": drop.accession_number,
                    "file_type": drop.file_type,
                    "file_date": drop.file_date,
                }
                for drop in self.going_concern_drops
            ],
            "edgar_skipped": {
                "no_cik": {
                    "count": len(self.edgar_skipped_no_cik),
                    "tickers": list(self.edgar_skipped_no_cik),
                },
                "data_source_error": {
                    "count": len(self.edgar_skipped_data_source_error),
                    "tickers": list(self.edgar_skipped_data_source_error),
                },
            },
        }

    def log(self, logger: logging.Logger) -> None:
        for drop in self.going_concern_drops:
            logger.warning(
                "filter_report: going_concern drop ticker=%s cik=%s accession=%s file_type=%s file_date=%s",
                drop.ticker,
                drop.cik,
                drop.accession_number,
                drop.file_type,
                drop.file_date,
            )
        logger.info(
            "filter_report: edgar_skipped total=%d no_cik=%d %s data_source_error=%d %s",
            self.total_skipped(),
            len(self.edgar_skipped_no_cik),
            self.edgar_skipped_no_cik,
            len(self.edgar_skipped_data_source_error),
            self.edgar_skipped_data_source_error,
        )


def build_filter_report(
    records: list[ScreenerRecord],
    edgar: EdgarClient,
) -> FilterReport:
    going_concern_drops: list[GoingConcernDrop] = []
    edgar_skipped_no_cik: list[str] = []
    edgar_skipped_data_source_error: list[str] = []

    for record in records:
        if record.edgar_skipped:
            if record.edgar_skipped_reason == "no_cik":
                edgar_skipped_no_cik.append(record.ticker)
            elif record.edgar_skipped_reason == "data_source_error":
                edgar_skipped_data_source_error.append(record.ticker)
            continue

        if (
            record.filter_passed_edgar is False
            and record.filter_failed_reason == "going_concern"
        ):
            try:
                hit = edgar.going_concern_hit(record.cik)
            except DataSourceError:
                hit = None
            going_concern_drops.append(
                GoingConcernDrop(
                    ticker=record.ticker,
                    cik=record.cik,
                    accession_number=hit.accession_number if hit else None,
                    file_type=hit.file_type if hit else None,
                    file_date=hit.file_date if hit else None,
                )
            )

    return FilterReport(
        going_concern_drops=going_concern_drops,
        edgar_skipped_no_cik=edgar_skipped_no_cik,
        edgar_skipped_data_source_error=edgar_skipped_data_source_error,
    )
