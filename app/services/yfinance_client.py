from collections.abc import Mapping
from typing import Any, Protocol

import yfinance as yf

from app.errors import DataSourceError, DegradedDataError
from app.models.deep_dive_record import ForwardEstimates

# Minor-unit quote normalization: some exchanges quote per-share prices in a minor unit
# while marketCap and every other absolute figure is already in the major unit. London
# (GBp = pence) is the live case; ZAc (SA cents), ILA (Israeli agorot) are the same
# class — add when such a listing actually appears.
_MINOR_UNIT: dict[str, tuple[str, int]] = {"GBp": ("GBP", 100)}

# Quoted per-share price keys in a yfinance `info` dict. This is a CURATED WHITELIST,
# not a heuristic over key names — do not widen it by pattern matching. Verified against
# EDV.L, GSK.L, TSCO.L, SHEL.L (controls ASML.AS, AAPL) via three independent
# self-consistency identities: within one London `info` dict only these keys are in
# pence, while marketCap, totalDebt, totalCash, enterpriseValue, bookValue, trailingEps,
# dividendRate, revenuePerShare and every ratio are already in pounds. Rescaling any of
# those would corrupt them by a factor of 100.
#
# A new consumer of a price-shaped `info` key MUST add that key here: an unlisted price
# key silently stays in pence under a "GBP" label — the exact bug this table closes.
_PRICE_KEYS: frozenset[str] = frozenset(
    {
        "currentPrice",
        "regularMarketPrice",
        "previousClose",
        "open",
        "dayHigh",
        "dayLow",
        "bid",
        "ask",
        "fiftyTwoWeekHigh",
        "fiftyTwoWeekLow",
        "targetMeanPrice",
        "targetMedianPrice",
        "targetHighPrice",
        "targetLowPrice",
        "fiftyDayAverage",
        "twoHundredDayAverage",
    }
)

# Quoted per-share monetary columns of a yfinance history DataFrame. Same curation rule
# as _PRICE_KEYS. Volume (a count) and "Stock Splits" (a ratio) are deliberately absent.
_PRICE_COLUMNS: tuple[str, ...] = (
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Dividends",
)


def is_unnormalised_payload(info: Mapping[str, Any]) -> bool:
    """True when a stored `info` payload predates minor-unit normalization.

    A normalized payload carries the ISO code ("GBP"), an old one the minor-unit code
    ("GBp") — the currency itself is the vintage tell, so no schema marker is needed.
    Cache readers treat True as a miss and re-fetch through the normalizing client.
    """
    currency = info.get("currency")
    return isinstance(currency, str) and currency in _MINOR_UNIT


def _normalize_minor_unit(info: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with `_PRICE_KEYS` converted to the major unit and `currency`
    replaced by the ISO code. Non-minor-unit payloads are returned unchanged (the very
    object yfinance handed over). Only numeric values are rescaled; None and
    non-numeric values pass through untouched."""
    if not is_unnormalised_payload(info):
        return info
    iso, divisor = _MINOR_UNIT[info["currency"]]
    normalized = dict(info)
    normalized["currency"] = iso
    for key in _PRICE_KEYS:
        value = normalized.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        normalized[key] = value / divisor
    return normalized


def _quote_divisor(handle: Any, ticker: str) -> int:
    """Divisor converting a quoted price series to the major unit.

    The currency comes from `history_metadata`, which yfinance populates from the same
    HTTP response as the preceding `history(...)` call — no extra round trip, but it
    must be read AFTER that call on the same Ticker object.

    A missing currency is a hard failure: handing back an unlabelled series as if it
    were normalized is precisely the silent factor-100 this change removes, and
    CLAUDE.md's rule is to abort rather than continue on phantom data.
    """
    metadata = getattr(handle, "history_metadata", None)
    currency = metadata.get("currency") if isinstance(metadata, Mapping) else None
    if not isinstance(currency, str) or not currency:
        raise DataSourceError(
            f"yfinance history metadata carries no currency for {ticker} — "
            "refusing to return possibly minor-unit prices"
        )
    minor = _MINOR_UNIT.get(currency)
    return minor[1] if minor is not None else 1


def _growth_at(frame: Any, period: str) -> float | None:
    """Defensively pull the 'growth' value for a yfinance estimate
    DataFrame index label (e.g. '0y', '+1y'). Tolerates None frame,
    missing index, missing 'growth' column, NaN -> None."""
    if frame is None:
        return None
    try:
        if "growth" not in getattr(frame, "columns", []):
            return None
        if period not in frame.index:
            return None
        val = frame.loc[period, "growth"]
    except Exception:
        return None
    try:
        if val is None:
            return None
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


class YFinanceClient(Protocol):
    def get_ticker_info(self, ticker: str) -> dict[str, Any]: ...
    def get_historical(self, ticker: str, period: str) -> Any: ...
    def get_financials(self, ticker: str) -> Any: ...
    def get_annual_statements(self, ticker: str) -> Any: ...
    def get_fx_rate(self, currency: str) -> float: ...
    def get_forward_estimates(self, ticker: str) -> ForwardEstimates | None: ...
    def get_weekly_close_5y(self, ticker: str) -> list[tuple[Any, float]]: ...
    def get_splits(self, ticker: str) -> list[tuple[Any, float]]: ...
    def get_isin(self, ticker: str) -> str | None: ...


class YFinanceClientImpl:
    def get_ticker_info(self, ticker: str) -> dict[str, Any]:
        try:
            data = yf.Ticker(ticker).info
        except Exception as exc:
            raise DataSourceError(f"yfinance failed for {ticker}: {exc}") from exc
        if not data:
            raise DataSourceError(f"yfinance returned empty info for {ticker}")
        # yfinance HTTP 404 can return a non-empty but degraded dict (a few keys,
        # no identity/valuation). Treat "no name and no marketCap" as unresolved
        # so it surfaces as attrition instead of a generic missing-field drop.
        if not (data.get("shortName") or data.get("longName") or data.get("marketCap")):
            raise DegradedDataError(f"yfinance returned degraded info for {ticker}")
        # London & friends quote per-share prices in a minor unit (pence) but report
        # marketCap and every other absolute figure in the major unit, all under a
        # "GBp" currency label. Normalize here so no consumer has to know.
        return _normalize_minor_unit(data)

    def get_historical(self, ticker: str, period: str) -> Any:
        # Empty DataFrame (delisted ticker) is a valid result; callers decide how to handle it
        try:
            handle = yf.Ticker(ticker)
            frame = handle.history(period=period)
        except Exception as exc:
            raise DataSourceError(
                f"yfinance history failed for {ticker}: {exc}"
            ) from exc
        if frame is None or frame.empty:
            return frame
        divisor = _quote_divisor(handle, ticker)
        if divisor == 1:
            return frame
        normalized = frame.copy()
        for column in _PRICE_COLUMNS:
            if column in normalized.columns:
                normalized[column] = normalized[column] / divisor
        return normalized

    def get_financials(self, ticker: str) -> Any:
        # Returns a pandas DataFrame, not a dict
        try:
            return yf.Ticker(ticker).financials
        except Exception as exc:
            raise DataSourceError(
                f"yfinance financials failed for {ticker}: {exc}"
            ) from exc

    def get_annual_statements(self, ticker: str) -> Any:
        # Returns (income_stmt, cashflow, balance_sheet) DataFrames.
        try:
            t = yf.Ticker(ticker)
            return (t.income_stmt, t.cashflow, t.balance_sheet)
        except Exception as exc:
            raise DataSourceError(
                f"yfinance statements failed for {ticker}: {exc}"
            ) from exc

    def get_weekly_close_5y(self, ticker: str) -> list[tuple[Any, float]]:
        """Wöchentliche Schlusskurse über 5J, split-adj (auto_adjust=True), auf die
        Major-Unit normalisiert (London-Pence -> Pfund).
        Leerer Frame (delisted) -> []. Hard yfinance-Fehler -> DataSourceError."""
        try:
            handle = yf.Ticker(ticker)
            frame = handle.history(period="5y", interval="1wk", auto_adjust=True)
        except Exception as exc:
            raise DataSourceError(
                f"yfinance weekly history failed for {ticker}: {exc}"
            ) from exc
        if frame is None or frame.empty or "Close" not in frame.columns:
            return []
        # Second, independent price source: same quoted unit as `info`. Normalizing
        # `info` alone would open the listing-vs-financial-currency gate in
        # compute_valuation_history and feed it pence prices — a silent 100x error.
        divisor = _quote_divisor(handle, ticker)
        return [
            (idx.date(), float(v) / divisor)
            for idx, v in frame["Close"].items()
            if v is not None
        ]

    def get_splits(self, ticker: str) -> list[tuple[Any, float]]:
        """Split-Events (Ex-Datum, Ratio). Keine Splits -> []."""
        try:
            s = yf.Ticker(ticker).splits
        except Exception as exc:
            raise DataSourceError(
                f"yfinance splits failed for {ticker}: {exc}"
            ) from exc
        if s is None or len(s) == 0:
            return []
        return [(idx.date(), float(v)) for idx, v in s.items()]

    def get_isin(self, ticker: str) -> str | None:
        """Best-effort ISIN from yfinance. Returns None when absent ('-' sentinel)
        or on missing value — ISIN is a verification aid, never load-bearing alone."""
        try:
            isin = yf.Ticker(ticker).isin
        except Exception as exc:
            raise DataSourceError(f"yfinance isin failed for {ticker}: {exc}") from exc
        if not isin or isin == "-":
            return None
        return str(isin).strip().upper()

    def get_forward_estimates(self, ticker: str) -> ForwardEstimates | None:
        """Best-effort forward-consensus growth (fractions). Hard yfinance
        failure -> DataSourceError; any missing piece -> that field None."""
        try:
            t = yf.Ticker(ticker)
            eps = t.earnings_estimate
            rev = t.revenue_estimate
        except Exception as exc:
            raise DataSourceError(
                f"yfinance forward estimates failed for {ticker}: {exc}"
            ) from exc
        return ForwardEstimates(
            eps_growth_cy=_growth_at(eps, "0y"),
            eps_growth_ny=_growth_at(eps, "+1y"),
            revenue_growth_cy=_growth_at(rev, "0y"),
            revenue_growth_ny=_growth_at(rev, "+1y"),
        )

    def get_fx_rate(self, currency: str) -> float:
        """Return conversion rate from `currency` to EUR (e.g. USD → 0.92)."""
        if currency == "EUR":
            return 1.0
        fx_ticker = f"{currency}EUR=X"
        try:
            data = yf.Ticker(fx_ticker).info
            rate = data.get("regularMarketPrice") or data.get("price")
            if not rate:
                raise DataSourceError(f"No FX rate found for {fx_ticker}")
            return float(rate)
        except DataSourceError:
            raise
        except Exception as exc:
            raise DataSourceError(
                f"yfinance FX rate failed for {currency}: {exc}"
            ) from exc
