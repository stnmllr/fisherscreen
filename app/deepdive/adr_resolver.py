from __future__ import annotations

from dataclasses import dataclass

from app.errors import DeepDiveError

# Heuristic from negative-filters-status.md §3.1 / Master ADR-1: a "." in the
# ticker marks a non-US listing (e.g. NOVO-B.CO, SAP.DE). US tickers have none.
_EU_MARKER = "."


@dataclass(frozen=True)
class ResolvedTicker:
    ticker: str
    adr_ticker: str | None
    cik: str
    form_type: str


class ADRResolver:
    """Static ADR-table resolver (Master ADR-1). Dynamic resolution is B.2."""

    def __init__(self, table: dict[str, dict[str, str]]) -> None:
        self._table = {k.upper(): v for k, v in table.items()}

    def resolve(self, ticker: str) -> ResolvedTicker:
        key = ticker.upper()
        entry = self._table.get(key)
        if entry is not None:
            return ResolvedTicker(
                ticker=ticker,
                adr_ticker=entry["adr_ticker"],
                cik=entry["cik"],
                form_type=entry["form_type"],
            )
        if _EU_MARKER in ticker:
            raise DeepDiveError(
                f"Ticker {ticker} is not in the ADR table and looks non-US "
                f"(contains '{_EU_MARKER}'). Add an entry to data/adr_table.json "
                f"or pick a US-listed ticker. Dynamic ADR resolution is Phase B.2."
            )
        # US passthrough: 10-K, CIK resolved later by the EDGAR client (B.1-3).
        return ResolvedTicker(ticker=ticker, adr_ticker=None, cik="", form_type="10-K")
