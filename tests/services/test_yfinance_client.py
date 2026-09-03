from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.errors import DataSourceError, DegradedDataError
from app.models.deep_dive_record import ForwardEstimates
from app.services.yfinance_client import YFinanceClientImpl


def test_degraded_dict_raises_degraded_data_error():
    client = YFinanceClientImpl()
    with patch("app.services.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.info = {"symbol": "ZZZZ", "exchange": "NMS"}
        with pytest.raises(DegradedDataError):
            client.get_ticker_info("ZZZZ")


def test_degraded_data_error_is_data_source_error():
    # Subclass invariant: all existing `except DataSourceError` must still catch it.
    assert issubclass(DegradedDataError, DataSourceError)


def test_get_isin_returns_isin_string():
    client = YFinanceClientImpl()
    with patch("app.services.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.isin = "FR0000131104"
        assert client.get_isin("BNP.PA") == "FR0000131104"


def test_get_isin_returns_none_when_absent_or_dash():
    client = YFinanceClientImpl()
    with patch("app.services.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.isin = "-"  # yfinance sentinel for "no isin"
        assert client.get_isin("ZZZZ") is None


def test_get_isin_raises_data_source_error_on_exception():
    client = YFinanceClientImpl()
    with patch("app.services.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = Exception("network error")
        with pytest.raises(DataSourceError, match="yfinance isin failed"):
            client.get_isin("BADTICKER")


def _estimate_frame(growth_by_period):
    """Build a yfinance-shaped estimate DataFrame (index='period')."""
    rows = {
        p: {
            "avg": 1.0,
            "low": 0.5,
            "high": 1.5,
            "numberOfAnalysts": 10,
            "growth": g,
            "currency": "USD",
        }
        for p, g in growth_by_period.items()
    }
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "period"
    return df


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_returns_info_dict(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {"shortName": "Apple Inc.", "marketCap": 3_000_000_000_000}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_ticker_info("AAPL")

    mock_yf.Ticker.assert_called_once_with("AAPL")
    assert result["shortName"] == "Apple Inc."
    assert result["marketCap"] == 3_000_000_000_000


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_raises_data_source_error_on_empty(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="empty info"):
        client.get_ticker_info("BADTICKER")


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_raises_on_degraded_dict_no_name_no_marketcap(mock_yf):
    # yfinance HTTP 404 often returns a non-empty but degraded dict with no
    # usable identity/valuation — must be rejected as silent attrition.
    mock_ticker = MagicMock()
    mock_ticker.info = {"symbol": "X", "currency": "USD"}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="degraded info"):
        client.get_ticker_info("X")


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_resolves_with_name_only(mock_yf):
    # shortName present → real security resolved, even without marketCap.
    mock_ticker = MagicMock()
    mock_ticker.info = {"shortName": "Some Co"}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_ticker_info("X")

    assert result == {"shortName": "Some Co"}


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_resolves_with_marketcap_only(mock_yf):
    # marketCap present → real security resolved, even without a name.
    mock_ticker = MagicMock()
    mock_ticker.info = {"marketCap": 5_000_000_000}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_ticker_info("X")

    assert result == {"marketCap": 5_000_000_000}


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_resolves_with_longname(mock_yf):
    # longName present → real security resolved.
    mock_ticker = MagicMock()
    mock_ticker.info = {"longName": "Some Long Co", "symbol": "X"}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_ticker_info("X")

    assert result == {"longName": "Some Long Co", "symbol": "X"}


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_raises_data_source_error_on_exception(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="yfinance failed"):
        client.get_ticker_info("AAPL")


@patch("app.services.yfinance_client.yf")
def test_get_historical_returns_dataframe(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame({"Close": [100.0, 101.0]})
    # A real dict, not the MagicMock auto-attribute: the adapter checks
    # isinstance(..., Mapping) on purpose, so a MagicMock trips the fail-loud path.
    mock_ticker.history_metadata = {"currency": "USD"}
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_historical("AAPL", "1mo")

    mock_ticker.history.assert_called_once_with(period="1mo")
    assert len(result) == 2


@patch("app.services.yfinance_client.yf")
def test_get_historical_raises_data_source_error_on_exception(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="yfinance history failed"):
        client.get_historical("AAPL", "1mo")


@patch("app.services.yfinance_client.yf")
def test_get_financials_returns_dataframe(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.financials = pd.DataFrame({"Revenue": [394_000_000_000]})
    mock_yf.Ticker.return_value = mock_ticker

    client = YFinanceClientImpl()
    result = client.get_financials("AAPL")

    assert len(result) == 1


@patch("app.services.yfinance_client.yf")
def test_get_financials_raises_data_source_error_on_exception(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    client = YFinanceClientImpl()

    with pytest.raises(DataSourceError, match="yfinance financials failed"):
        client.get_financials("AAPL")


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_parses_growth_for_cy_and_ny(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.earnings_estimate = _estimate_frame(
        {"0q": 0.20, "+1q": 0.08, "0y": 0.1714, "+1y": 0.1023}
    )
    mock_ticker.revenue_estimate = _estimate_frame(
        {"0q": 0.15, "+1q": 0.11, "0y": 0.1485, "+1y": 0.0809}
    )
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert isinstance(fe, ForwardEstimates)
    assert fe.eps_growth_cy == 0.1714
    assert fe.eps_growth_ny == 0.1023
    assert fe.revenue_growth_cy == 0.1485
    assert fe.revenue_growth_ny == 0.0809


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_missing_index_yields_none_fields(mock_yf):
    mock_ticker = MagicMock()
    # only 0y present for EPS, revenue frame missing +1y
    mock_ticker.earnings_estimate = _estimate_frame({"0y": 0.17})
    mock_ticker.revenue_estimate = _estimate_frame({"0y": 0.14, "0q": 0.1})
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert fe.eps_growth_cy == 0.17
    assert fe.eps_growth_ny is None
    assert fe.revenue_growth_cy == 0.14
    assert fe.revenue_growth_ny is None


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_missing_growth_column_yields_none(mock_yf):
    mock_ticker = MagicMock()
    df = pd.DataFrame.from_dict(
        {"0y": {"avg": 1.0}, "+1y": {"avg": 2.0}}, orient="index"
    )
    df.index.name = "period"
    mock_ticker.earnings_estimate = df
    mock_ticker.revenue_estimate = df
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert fe.eps_growth_cy is None
    assert fe.revenue_growth_ny is None


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_nan_growth_yields_none(mock_yf):
    import numpy as np

    mock_ticker = MagicMock()
    mock_ticker.earnings_estimate = _estimate_frame({"0y": np.nan, "+1y": 0.10})
    mock_ticker.revenue_estimate = _estimate_frame({"0y": 0.14, "+1y": np.nan})
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert fe.eps_growth_cy is None
    assert fe.eps_growth_ny == 0.10
    assert fe.revenue_growth_cy == 0.14
    assert fe.revenue_growth_ny is None


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_none_frames_yield_all_none(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.earnings_estimate = None
    mock_ticker.revenue_estimate = None
    mock_yf.Ticker.return_value = mock_ticker

    fe = YFinanceClientImpl().get_forward_estimates("AAPL")

    assert isinstance(fe, ForwardEstimates)
    assert fe.eps_growth_cy is None and fe.eps_growth_ny is None
    assert fe.revenue_growth_cy is None and fe.revenue_growth_ny is None


@patch("app.services.yfinance_client.yf")
def test_get_forward_estimates_hard_failure_raises_data_source_error(mock_yf):
    mock_yf.Ticker.side_effect = Exception("network error")

    with pytest.raises(DataSourceError, match="forward estimates failed"):
        YFinanceClientImpl().get_forward_estimates("AAPL")


def test_get_weekly_close_5y_returns_date_price_pairs(monkeypatch):
    import pandas as pd
    from app.services import yfinance_client as mod

    idx = pd.to_datetime(["2020-06-01", "2020-06-08", "2020-06-15"])
    frame = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=idx)

    class _T:
        history_metadata = {"currency": "USD"}

        def __init__(self, t):
            pass

        def history(self, period, interval, auto_adjust):
            assert period == "5y" and interval == "1wk" and auto_adjust is True
            return frame

    monkeypatch.setattr(mod.yf, "Ticker", _T)
    out = mod.YFinanceClientImpl().get_weekly_close_5y("X")
    assert out[0][1] == 100.0 and out[-1][1] == 102.0
    assert str(out[0][0]) == "2020-06-01"


def test_get_weekly_close_5y_empty_frame_returns_empty(monkeypatch):
    import pandas as pd
    from app.services import yfinance_client as mod

    class _T:
        def __init__(self, t):
            pass

        def history(self, period, interval, auto_adjust):
            return pd.DataFrame()

    monkeypatch.setattr(mod.yf, "Ticker", _T)
    assert mod.YFinanceClientImpl().get_weekly_close_5y("X") == []


def test_get_splits_returns_date_ratio_pairs(monkeypatch):
    import pandas as pd
    from app.services import yfinance_client as mod

    s = pd.Series([20.0], index=pd.to_datetime(["2022-07-18"]))

    class _T:
        def __init__(self, t):
            pass

        @property
        def splits(self):
            return s

    monkeypatch.setattr(mod.yf, "Ticker", _T)
    out = mod.YFinanceClientImpl().get_splits("X")
    assert out == [(out[0][0], 20.0)]
    assert str(out[0][0]) == "2022-07-18"


def test_get_splits_empty_returns_empty(monkeypatch):
    import pandas as pd
    from app.services import yfinance_client as mod

    class _T:
        def __init__(self, t):
            pass

        @property
        def splits(self):
            return pd.Series(dtype=float)

    monkeypatch.setattr(mod.yf, "Ticker", _T)
    assert mod.YFinanceClientImpl().get_splits("X") == []


# --------------------------------------------------------------------------
# Minor-unit (GBp) normalization — `info` payloads
# --------------------------------------------------------------------------

# A GSK.L-shaped `info`: quoted per-share prices in pence, everything else already
# in pounds, all under a single "GBp" currency label. Values are deliberately all
# distinct so a key mix-up cannot pass unnoticed.
_GBP_PRICE_PENCE = {
    "currentPrice": 1500.0,
    "regularMarketPrice": 1501.0,
    "previousClose": 1495.0,
    "open": 1498.0,
    "dayHigh": 1510.0,
    "dayLow": 1490.0,
    "bid": 1499.5,
    "ask": 1500.5,
    "fiftyTwoWeekHigh": 1720.0,
    "fiftyTwoWeekLow": 1230.0,
    "targetMeanPrice": 1800.0,
    "targetMedianPrice": 1795.0,
    "targetHighPrice": 2100.0,
    "targetLowPrice": 1400.0,
    "fiftyDayAverage": 1550.0,
    "twoHundredDayAverage": 1480.0,
}

# The same `info` dict, already in the major unit (pounds). Rescaling any of these
# would corrupt it by a factor of 100 — that asymmetry is the entire point.
_GBP_MAJOR_UNIT = {
    "marketCap": 60_000_000_000,
    "totalDebt": 20_000_000_000,
    "totalCash": 5_000_000_000,
    "enterpriseValue": 75_000_000_000,
    "freeCashflow": 4_000_000_000,
    "netIncomeToCommon": 4_300_000_000,
    "bookValue": 3.20,
    "dividendRate": 0.68,
    "trailingEps": 1.05,
    "forwardEps": 1.62,
    "revenuePerShare": 7.61,
    "totalCashPerShare": 1.22,
    "trailingPE": 14.29,
    "forwardPE": 9.26,
    "payoutRatio": 0.647,
    "dividendYield": 4.53,
    "grossMargins": 0.714,
}


def _gbp_info(**overrides):
    """Build a London-listing `info` dict as yfinance hands it over (unnormalized)."""
    info = {
        "shortName": "GSK plc",
        "currency": "GBp",
        "financialCurrency": "GBP",
        **_GBP_MAJOR_UNIT,
        **_GBP_PRICE_PENCE,
    }
    info.update(overrides)
    return info


def _info_client(mock_yf, info):
    mock_ticker = MagicMock()
    mock_ticker.info = info
    mock_yf.Ticker.return_value = mock_ticker
    return YFinanceClientImpl()


def test_price_keys_whitelist_is_fully_covered_by_the_gbp_fixture():
    """Curation fence: every key in the adapter whitelist is exercised below.

    _PRICE_KEYS is a curated list, not a heuristic. Adding a key there without
    extending this fixture would leave the new key untested — exactly the silent
    gap the table exists to close."""
    from app.services.yfinance_client import _PRICE_KEYS

    assert set(_GBP_PRICE_PENCE) == set(_PRICE_KEYS)
    assert len(_PRICE_KEYS) == 16


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_rescales_price_keys_and_leaves_major_unit_alone(mock_yf):
    """The asymmetry IS the contract: inside one London `info` dict the quoted
    per-share prices are pence and must be divided by 100, while marketCap,
    totalDebt, totalCash, trailingEps, bookValue, dividendRate and every ratio are
    already in pounds and must survive unchanged. Both halves are asserted here on
    purpose — splitting them invites a later "simplification" that rescales
    everything and corrupts the major-unit fields by a factor of 100."""
    client = _info_client(mock_yf, _gbp_info())

    result = client.get_ticker_info("GSK.L")

    assert result["currency"] == "GBP"
    for key, pence in _GBP_PRICE_PENCE.items():
        assert result[key] == pytest.approx(pence / 100), f"{key} not rescaled"
    for key, expected in _GBP_MAJOR_UNIT.items():
        assert result[key] == expected, f"{key} must NOT be rescaled"
    # Spelled out for the headline fields the defect was reported against.
    assert result["currentPrice"] == pytest.approx(15.00)
    assert result["marketCap"] == 60_000_000_000
    assert result["trailingEps"] == 1.05
    assert result["bookValue"] == 3.20


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_does_not_mutate_the_source_dict(mock_yf):
    """The adapter returns a copy; the dict yfinance handed over stays untouched,
    so a caller holding the original never sees half-normalized values."""
    raw = _gbp_info()
    client = _info_client(mock_yf, raw)

    result = client.get_ticker_info("GSK.L")

    assert result is not raw
    assert raw["currency"] == "GBp"
    assert raw["currentPrice"] == 1500.0
    assert raw["marketCap"] == 60_000_000_000


@pytest.mark.parametrize("currency", ["EUR", "USD"])
@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_passes_non_minor_currency_through_untouched(mock_yf, currency):
    """Non-minor listings keep the very object yfinance returned — no copy, no
    rescale, no relabel."""
    raw = _gbp_info(currency=currency)
    client = _info_client(mock_yf, raw)

    result = client.get_ticker_info("ASML.AS")

    assert result is raw
    assert result["currency"] == currency
    assert result["currentPrice"] == 1500.0
    assert result["marketCap"] == 60_000_000_000


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_passes_none_and_non_numeric_price_values_through(mock_yf):
    """yfinance omits or blanks price fields for illiquid titles; None, strings and
    absent keys must survive instead of blowing up on the division."""
    raw = _gbp_info(bid=None, ask="", targetMeanPrice="n/a")
    del raw["dayHigh"]
    client = _info_client(mock_yf, raw)

    result = client.get_ticker_info("GSK.L")

    assert result["bid"] is None
    assert result["ask"] == ""
    assert result["targetMeanPrice"] == "n/a"
    assert "dayHigh" not in result
    assert result["currentPrice"] == pytest.approx(15.00)  # the rest still normalizes


@patch("app.services.yfinance_client.yf")
def test_get_ticker_info_does_not_rescale_bool_price_values(mock_yf):
    """bool is a subclass of int: an unguarded numeric check would turn True into
    0.01 and invent a price out of a flag."""
    raw = _gbp_info(bid=True, ask=False)
    client = _info_client(mock_yf, raw)

    result = client.get_ticker_info("GSK.L")

    assert result["bid"] is True
    assert result["ask"] is False


def test_is_unnormalised_payload_flags_only_minor_unit_currencies():
    """The stored currency is the vintage tell — no schema marker exists."""
    from app.services.yfinance_client import is_unnormalised_payload

    assert is_unnormalised_payload({"currency": "GBp"}) is True
    assert is_unnormalised_payload({"currency": "GBP"}) is False
    assert is_unnormalised_payload({"currency": "USD"}) is False
    assert is_unnormalised_payload({"currency": None}) is False
    assert is_unnormalised_payload({}) is False


# --------------------------------------------------------------------------
# Minor-unit normalization — the price series (second, independent source)
# --------------------------------------------------------------------------


def _weekly_frame(closes):
    idx = pd.to_datetime([f"2020-06-{1 + 7 * i:02d}" for i in range(len(closes))])
    return pd.DataFrame({"Close": list(closes)}, index=idx)


def _patch_ticker(monkeypatch, ticker_obj):
    from app.services import yfinance_client as mod

    monkeypatch.setattr(mod.yf, "Ticker", lambda t: ticker_obj)
    return mod


class _WeeklyTicker:
    """yf.Ticker stand-in for the weekly-history path."""

    def __init__(self, frame, metadata):
        self._frame = frame
        self.history_metadata = metadata

    def history(self, period, interval, auto_adjust):
        return self._frame


class _WeeklyMetadataTripwire(_WeeklyTicker):
    """Reading history_metadata at all fails the test."""

    @property
    def history_metadata(self):  # pragma: no cover - must never be reached
        raise AssertionError("metadata read before the empty-frame check")

    @history_metadata.setter
    def history_metadata(self, value):
        pass


def test_get_weekly_close_5y_normalizes_pence_to_pounds(monkeypatch):
    """Same quoted unit as `info`, so the same divisor: 1500p -> 15.00 GBP."""
    mod = _patch_ticker(
        monkeypatch,
        _WeeklyTicker(_weekly_frame([1500.0, 1501.0, 1490.0]), {"currency": "GBp"}),
    )

    out = mod.YFinanceClientImpl().get_weekly_close_5y("GSK.L")

    assert [p for _, p in out] == pytest.approx([15.00, 15.01, 14.90])
    assert str(out[0][0]) == "2020-06-01"


def test_get_weekly_close_5y_leaves_non_minor_currency_untouched(monkeypatch):
    mod = _patch_ticker(
        monkeypatch,
        _WeeklyTicker(_weekly_frame([600.0, 610.0]), {"currency": "EUR"}),
    )

    out = mod.YFinanceClientImpl().get_weekly_close_5y("ASML.AS")

    assert [p for _, p in out] == pytest.approx([600.0, 610.0])


def test_get_weekly_close_5y_empty_frame_returns_empty_without_reading_metadata(
    monkeypatch,
):
    """Delisted tickers keep their old meaning ([]) — the empty check precedes the
    metadata read, so an empty frame must never reach the fail-loud path."""
    mod = _patch_ticker(monkeypatch, _WeeklyMetadataTripwire(pd.DataFrame(), None))

    assert mod.YFinanceClientImpl().get_weekly_close_5y("DEAD.L") == []


@pytest.mark.parametrize(
    "metadata",
    [None, object(), "GBp", {}, {"currency": None}, {"currency": ""}],
    ids=["absent", "not-a-mapping", "string", "no-key", "none-value", "empty-string"],
)
def test_get_weekly_close_5y_raises_when_metadata_carries_no_currency(
    monkeypatch, metadata
):
    """Fail loud: an unlabelled series returned as if normalized is precisely the
    silent factor-100 this change removes. An abort is recoverable, a 100x error
    reported as `complete` is not."""
    mod = _patch_ticker(
        monkeypatch, _WeeklyTicker(_weekly_frame([1500.0, 1501.0]), metadata)
    )

    with pytest.raises(DataSourceError, match="carries no currency"):
        mod.YFinanceClientImpl().get_weekly_close_5y("GSK.L")


class _HistoryTicker:
    """yf.Ticker stand-in for the generic history path."""

    def __init__(self, frame, metadata):
        self._frame = frame
        self.history_metadata = metadata

    def history(self, period):
        return self._frame


class _HistoryMetadataTripwire(_HistoryTicker):
    """Reading history_metadata at all fails the test."""

    @property
    def history_metadata(self):  # pragma: no cover - must never be reached
        raise AssertionError("metadata read before the empty-frame check")

    @history_metadata.setter
    def history_metadata(self, value):
        pass


def _ohlcv_frame():
    idx = pd.to_datetime(["2024-01-05", "2024-01-12"])
    return pd.DataFrame(
        {
            "Open": [1498.0, 1502.0],
            "High": [1510.0, 1515.0],
            "Low": [1490.0, 1495.0],
            "Close": [1500.0, 1505.0],
            "Adj Close": [1495.0, 1500.0],
            "Volume": [1_000_000, 2_000_000],
            "Dividends": [17.0, 0.0],
            "Stock Splits": [0.0, 2.0],
        },
        index=idx,
    )


def test_get_historical_normalizes_price_columns_for_a_pence_listing(monkeypatch):
    """Dividends belongs in the rescaled set empirically, not by analogy: for GSK.L
    four consecutive history dividends sum to 68.00 against
    info["dividendRate"] == 0.68 — a ratio of exactly 100.0000, while ASML.AS gives
    exactly 1.0000. Volume (a count) and Stock Splits (a ratio) carry no currency
    and must stay untouched."""
    mod = _patch_ticker(
        monkeypatch, _HistoryTicker(_ohlcv_frame(), {"currency": "GBp"})
    )

    out = mod.YFinanceClientImpl().get_historical("GSK.L", "1y")

    assert list(out["Open"]) == pytest.approx([14.98, 15.02])
    assert list(out["High"]) == pytest.approx([15.10, 15.15])
    assert list(out["Low"]) == pytest.approx([14.90, 14.95])
    assert list(out["Close"]) == pytest.approx([15.00, 15.05])
    assert list(out["Adj Close"]) == pytest.approx([14.95, 15.00])
    assert list(out["Dividends"]) == pytest.approx([0.17, 0.0])
    assert list(out["Volume"]) == [1_000_000, 2_000_000]
    assert list(out["Stock Splits"]) == pytest.approx([0.0, 2.0])


def test_get_historical_leaves_non_minor_currency_frame_untouched(monkeypatch):
    frame = _ohlcv_frame()
    mod = _patch_ticker(monkeypatch, _HistoryTicker(frame, {"currency": "EUR"}))

    out = mod.YFinanceClientImpl().get_historical("ASML.AS", "1y")

    assert out is frame
    assert list(out["Close"]) == pytest.approx([1500.0, 1505.0])


def test_get_historical_empty_frame_returns_without_reading_metadata(monkeypatch):
    """An empty frame (delisted) is a valid result and must not reach the fail-loud
    metadata check."""
    empty = pd.DataFrame()
    mod = _patch_ticker(monkeypatch, _HistoryMetadataTripwire(empty, None))

    assert mod.YFinanceClientImpl().get_historical("DEAD.L", "1y") is empty


def test_get_historical_raises_when_metadata_carries_no_currency(monkeypatch):
    mod = _patch_ticker(monkeypatch, _HistoryTicker(_ohlcv_frame(), {}))

    with pytest.raises(DataSourceError, match="carries no currency"):
        mod.YFinanceClientImpl().get_historical("GSK.L", "1y")
