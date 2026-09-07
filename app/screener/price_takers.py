"""Price-taker marking for the Tool-A crosshits report.

A price taker sells at a price it does not set. In a commodity upcycle that
turns all three Tool-A axes green at once -- growth, profitability and
resilience all improve without anything changing about the business -- and the
title surfaces as a crosshit it has no Fisher claim to. Seven of the 24
crosshits in September 2026 were of that kind.

This module labels those titles. It does not filter them and it does not touch
a score: the judgement stays with the reader, the report just stops hiding the
question. Key is the yfinance `industry` field (the finer of the two levels
yfinance offers), plus a short ticker override list for the cases where the
industry label is too coarse to separate a price taker from its neighbours.

Unlike `industry_group_map`, an absent file here is FAIL LOUD. There, a missing
rollup leaves an arm dormant -- a visible no-op. Here it would print "nein"
beside every title in a monthly report, which is not a missing label but a
false one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.errors import FilterConfigError

_DEFAULT_PATH = Path("data/price_takers.json")
_ARMS = ("industries", "tickers")


@dataclass(frozen=True)
class PriceTakerTable:
    """Two arms, both exact-match: yfinance industry labels, and single tickers."""

    industries: frozenset[str]
    tickers: frozenset[str]


def load_price_takers(path: Path | None = None) -> PriceTakerTable:
    """Load and validate the price-taker table.

    Raises FilterConfigError on an absent file, unreadable JSON, a missing arm,
    an arm that is not a list, or any non-string entry. The `_meta` block is
    documentation and is ignored.
    """
    p = path or _DEFAULT_PATH
    if not p.exists():
        raise FilterConfigError(
            f"price_takers table missing at {p} -- refusing to mark every title "
            "as 'nein', which would be a false label rather than a missing one"
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FilterConfigError(f"price_takers unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise FilterConfigError("price_takers: top level is not an object")
    arms: dict[str, frozenset[str]] = {}
    for arm in _ARMS:
        if arm not in data:
            raise FilterConfigError(f"price_takers: missing '{arm}'")
        values = data[arm]
        if not isinstance(values, list):
            raise FilterConfigError(f"price_takers: '{arm}' is not a list")
        for value in values:
            if not isinstance(value, str):
                raise FilterConfigError(f"price_takers: non-string entry in '{arm}'")
        arms[arm] = frozenset(values)
    return PriceTakerTable(industries=arms["industries"], tickers=arms["tickers"])


def is_price_taker(ticker: str, industry: str | None, table: PriceTakerTable) -> bool:
    """Exact match on either arm. A title without an industry stays unmarked --
    absence of evidence is not a label."""
    if ticker in table.tickers:
        return True
    return industry is not None and industry in table.industries
