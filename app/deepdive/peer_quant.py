from __future__ import annotations

import logging
from typing import Any

from app.errors import DataSourceError
from app.models.deep_dive_record import PeerQuant

logger = logging.getLogger(__name__)


def _peer_from_info(ticker: str, info: dict[str, Any]) -> PeerQuant:
    return PeerQuant(
        ticker=ticker,
        name=info.get("shortName"),
        trailing_pe=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        operating_margin=info.get("operatingMargins"),
        gross_margin=info.get("grossMargins"),
        revenue_growth_yoy=info.get("revenueGrowth"),
        free_cashflow=info.get("freeCashflow"),
        market_cap=info.get("marketCap"),
    )


def load_peer_quants(tickers: list[str], yfinance: Any) -> list[PeerQuant]:
    """Load a thin quant snapshot per peer from yfinance `.info`.

    Fail-soft per peer: if `get_ticker_info` raises DataSourceError for one
    peer, that peer is returned ticker-only (rest None) and a WARNING is
    logged — a deep dive must not die because one peer is thin.
    """
    peers: list[PeerQuant] = []
    for t in tickers:
        try:
            info = yfinance.get_ticker_info(t)
        except DataSourceError as exc:
            logger.warning(
                "peer_quant: %s info unavailable — %s (ticker-only)", t, exc)
            peers.append(PeerQuant(ticker=t))
            continue
        peers.append(_peer_from_info(t, info))
    return peers
