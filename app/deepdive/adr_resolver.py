from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from app.errors import DeepDiveError

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient

# Heuristic from negative-filters-status.md §3.1 / Master ADR-1: a "." in the
# ticker marks a non-US listing (e.g. NOVO-B.CO, SAP.DE). US tickers have none.
#
# PRECONDITION: tickers are yfinance/Yahoo-suffix style (the convention used by
# data/universe.json) — US class shares are "BRK-B", NOT "BRK.B". Under that
# convention a "." reliably marks a non-US exchange suffix. Feeding a dotted US
# class-share ticker (BRK.B) would raise DeepDiveError; that is acceptable and
# matches the ADR-1 heuristic. The marker routes dotted EU tickers to the dynamic
# OpenFIGI EU-ADR resolver (delegate `eu_resolver`, wired in PR #43); it is a
# routing signal, not a fallback awaiting removal.
_EU_MARKER = "."


@dataclass(frozen=True)
class ResolvedTicker:
    ticker: str
    adr_ticker: str | None
    cik: str
    form_type: str


class ADRResolver:
    """Resolver: static ADR table (override, Master ADR-1) -> US-path CIK
    resolution via the EDGAR client -> dynamic EU-ADR resolution (OpenFIGI,
    delegated to `eu_resolver`, wired in PR #43) for dotted EU tickers."""

    def __init__(
        self,
        table: dict[str, dict[str, str]],
        edgar: "EdgarClient",
        eu_resolver: Callable[[str], ResolvedTicker],
    ) -> None:
        self._table = {k.upper(): v for k, v in table.items()}
        self._edgar = edgar
        self._eu_resolver = eu_resolver

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
            # Dynamic EU-ADR resolution (OpenFIGI). The delegate raises DeepDiveError
            # for a genuine no-US-ADR (EU-Native gap, Phase 2) or DataSourceError on
            # a transient API failure — failure != empty, never a silent wrong match.
            return self._eu_resolver(ticker)
        # US path: resolve the CIK + detect the annual form from EDGAR.
        cik = self._edgar.get_cik(ticker)
        if not cik:
            raise DeepDiveError(
                f"US ticker {ticker} not found in the SEC company_tickers map — "
                f"check the symbol or add an ADR table entry."
            )
        form = self._edgar.detect_annual_form(cik)
        if form is None:
            raise DeepDiveError(
                f"{ticker} (CIK {cik}) files neither 10-K nor 20-F in recent "
                f"submissions — not deep-dive-eligible (other forms are Phase 2)."
            )
        return ResolvedTicker(
            ticker=ticker, adr_ticker=None, cik=cik.zfill(10), form_type=form
        )
