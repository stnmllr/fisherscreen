"""Peer suggestions for the deep-dive pre-flight check — read-only, no Gemini.

Candidates are universe titles with the same yfinance `industry` as the ticker
(topped up with the same `sector` if the industry yields fewer than three),
taken from the yfinance info cache in Firestore and ordered by market-cap
proximity — compared in ONE currency (EUR), never raw across currencies.
Spec: docs/superpowers/specs/2026-10-24-deepdive-ui-design.md,
"Nachtrag 2026-10-24: Peer-Vorschlag bei weniger als drei Peers".
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from app.errors import DataSourceError
from app.services.yfinance_client import _MINOR_UNIT

logger = logging.getLogger(__name__)


class TickerFacts(Protocol):
    """What suggest_peers reads from preflight.SymbolCheck. A Protocol instead
    of an import, because preflight imports PeerSuggestion from this module."""

    @property
    def symbol(self) -> str: ...
    @property
    def market_cap(self) -> float | None: ...
    @property
    def currency(self) -> str | None: ...
    @property
    def industry(self) -> str | None: ...
    @property
    def sector(self) -> str | None: ...


# Upper bound per Firestore query. The cache also holds titles outside the
# current universe, so the query over-fetches and the universe filter trims.
QUERY_LIMIT = 200
_MIN_INDUSTRY_HITS = 3


@dataclass(frozen=True)
class PeerSuggestion:
    symbol: str
    name: str | None
    market_cap: float | None  # in `currency`, as reported (not converted)
    match: Literal["industry", "sector"]
    industry: str | None
    cached_at: str | None  # ISO, as-of date of the cache entry
    currency: str | None = None  # ISO code of `market_cap`


def _positive_number(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        return None
    return float(raw)


def _iso_currency(raw: Any) -> str | None:
    """ISO code for a yfinance currency label.

    Cached docs may predate minor-unit normalization and still say "GBp".
    Same rule as yfinance_client._normalize_minor_unit: only the label (and
    per-share prices) are minor-unit — marketCap is already in the major unit,
    so mapping the label is all a market-cap comparison needs."""
    if not isinstance(raw, str) or not raw:
        return None
    return _MINOR_UNIT.get(raw, (raw, 1))[0]


class _ToEur:
    """Converts market caps to EUR, one FX lookup per distinct currency.

    A failed lookup is remembered as None: those caps count as unknown and
    sort last — a missing rate must not abort the suggestions."""

    def __init__(self, fx_rate: Callable[[str], float]) -> None:
        self._fx_rate = fx_rate
        self._rates: dict[str, float | None] = {}

    def __call__(self, cap: float | None, currency: Any) -> float | None:
        iso = _iso_currency(currency)
        if cap is None or iso is None:
            return None
        if iso not in self._rates:
            try:
                rate = _positive_number(self._fx_rate(iso))
            except DataSourceError as exc:
                logger.warning("peer suggest: no FX rate for %s: %s", iso, exc)
                rate = None
            self._rates[iso] = rate
        rate = self._rates[iso]
        return None if rate is None else cap * rate


def _sort_key(
    symbol: str, cap_eur: float | None, target_eur: float | None
) -> tuple[int, float, str]:
    if cap_eur is None:
        return (1, 0.0, symbol)
    if target_eur is None:
        return (0, 0.0, symbol)
    return (0, abs(math.log(cap_eur / target_eur)), symbol)


def _candidates(
    firestore: Any,
    collection: str,
    field: str,
    value: str,
    match: Literal["industry", "sector"],
    universe: frozenset[str],
    excluded: set[str],
    target_eur: float | None,
    to_eur: _ToEur,
) -> list[PeerSuggestion]:
    # Deliberately ignores the 24 h TTL of the ticker cache: an industry
    # practically never changes and the market cap only orders the list, so a
    # stale entry is still a good suggestion. `cached_at` shows its as-of date,
    # and every accepted peer is re-checked against live yfinance anyway.
    keyed: list[tuple[tuple[int, float, str], PeerSuggestion]] = []
    for doc_id, data in firestore.query_equal(collection, field, value, QUERY_LIMIT):
        symbol = doc_id.upper()
        if symbol not in universe or symbol in excluded:
            continue
        cap = _positive_number(data.get("marketCap"))
        currency = _iso_currency(data.get("currency"))
        cached_at = data.get("_cached_at")
        suggestion = PeerSuggestion(
            symbol=symbol,
            name=data.get("shortName") or data.get("longName"),
            market_cap=cap,
            match=match,
            industry=data.get("industry"),
            cached_at=cached_at if isinstance(cached_at, str) else None,
            currency=currency,
        )
        keyed.append((_sort_key(symbol, to_eur(cap, currency), target_eur), suggestion))
    return [s for _, s in sorted(keyed, key=lambda pair: pair[0])]


def suggest_peers(
    ticker_check: TickerFacts,
    exclude: list[str],
    *,
    firestore: Any,
    collection: str,
    universe: frozenset[str],
    fx_rate: Callable[[str], float],
    limit: int = 5,
) -> list[PeerSuggestion]:
    """Return up to `limit` peer candidates for `ticker_check`.

    Excludes the ticker itself and every symbol in `exclude` (case-insensitive).
    Market caps are converted to EUR via `fx_rate(iso) -> EUR per unit`
    (YFinanceClient.get_fx_rate semantics) before the |log ratio| ordering;
    a currency whose rate cannot be fetched sorts last. Returns [] when the
    ticker has no industry. A Firestore failure propagates as DataSourceError —
    failure != empty; the caller reports it."""
    if not ticker_check.industry:
        return []
    excluded = {e.strip().upper() for e in exclude} | {ticker_check.symbol.upper()}
    to_eur = _ToEur(fx_rate)
    target_eur = to_eur(
        _positive_number(ticker_check.market_cap), ticker_check.currency
    )
    picked = _candidates(
        firestore,
        collection,
        "industry",
        ticker_check.industry,
        "industry",
        universe,
        excluded,
        target_eur,
        to_eur,
    )[:limit]
    if len(picked) < _MIN_INDUSTRY_HITS and ticker_check.sector:
        excluded |= {s.symbol for s in picked}
        picked += _candidates(
            firestore,
            collection,
            "sector",
            ticker_check.sector,
            "sector",
            universe,
            excluded,
            target_eur,
            to_eur,
        )[: limit - len(picked)]
    return picked
