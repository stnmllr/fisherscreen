from __future__ import annotations


def _clean(series: list[float | None]) -> list[float] | None:
    if not series or any(v is None or v != v for v in series):  # v != v is True for NaN
        return None
    return [float(v) for v in series]  # type: ignore[arg-type]


def compute_cagr(revenue_newest_first: list[float | None]) -> float | None:
    s = _clean(revenue_newest_first)
    if s is None or len(s) < 2:
        return None
    newest, oldest = s[0], s[-1]
    if newest <= 0 or oldest <= 0:
        return None
    span = len(s) - 1
    return (newest / oldest) ** (1 / span) - 1


def compute_margin_slope(margin_newest_first: list[float | None]) -> float | None:
    s = _clean(margin_newest_first)
    if s is None or len(s) < 2:
        return None
    # x = years ascending oldest->newest (reverse of input order)
    ys = list(reversed(s))
    n = len(ys)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def compute_dilution_pct(shares_newest_first: list[float | None]) -> float | None:
    s = _clean(shares_newest_first)
    if s is None or len(s) < 2:
        return None
    newest, oldest = s[0], s[-1]
    if newest <= 0 or oldest <= 0:
        return None
    return (newest - oldest) / oldest


def compute_buyback_intensity(
    buyback_cashflow_newest_first: list[float | None],
    market_cap: float | None,
) -> float | None:
    s = _clean(buyback_cashflow_newest_first)
    if s is None or not s or not market_cap:
        return None
    return abs(sum(s)) / market_cap
