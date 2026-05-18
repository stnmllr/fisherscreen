from unittest.mock import MagicMock

import pandas as pd

from app.services.historical_data_service import HistoricalDataServiceImpl


def _yf_with_frames():
    yf = MagicMock()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"),
            pd.Timestamp("2022-12-31"), pd.Timestamp("2021-12-31"),
            pd.Timestamp("2020-12-31")]
    income = pd.DataFrame(
        {c: v for c, v in zip(cols, [
            {"Total Revenue": 1000, "Gross Profit": 800, "Operating Income": 400},
            {"Total Revenue": 900, "Gross Profit": 700, "Operating Income": 350},
            {"Total Revenue": 800, "Gross Profit": 600, "Operating Income": 300},
            {"Total Revenue": 700, "Gross Profit": 520, "Operating Income": 250},
            {"Total Revenue": 600, "Gross Profit": 450, "Operating Income": 200},
        ])}
    )
    cash = pd.DataFrame({c: {"Repurchase Of Capital Stock": -50} for c in cols})
    bal = pd.DataFrame({c: {"Share Issued": 2000} for c in cols})
    yf.get_annual_statements.return_value = (income, cash, bal)
    yf.get_ticker_info.return_value = {"financialCurrency": "DKK"}
    return yf


def test_extracts_five_year_series():
    svc = HistoricalDataServiceImpl(yfinance=_yf_with_frames())
    s = svc.get_annual_series("NOVO-B.CO")
    assert s["financial_currency"] == "DKK"
    assert s["years"] == [2024, 2023, 2022, 2021, 2020]
    assert s["revenue"] == [1000, 900, 800, 700, 600]
    assert s["shares_outstanding"] == [2000, 2000, 2000, 2000, 2000]
    assert s["buyback_cashflow"] == [-50, -50, -50, -50, -50]


def test_partial_series_when_fewer_years():
    yf = _yf_with_frames()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31")]
    yf.get_annual_statements.return_value = (
        pd.DataFrame({c: {"Total Revenue": 100, "Gross Profit": 80,
                          "Operating Income": 40} for c in cols}),
        pd.DataFrame({c: {"Repurchase Of Capital Stock": 0} for c in cols}),
        pd.DataFrame({c: {"Share Issued": 1} for c in cols}),
    )
    svc = HistoricalDataServiceImpl(yfinance=yf)
    s = svc.get_annual_series("X")
    assert len(s["years"]) == 2
    assert s["complete"] is False  # <3 years


def test_empty_frames_yield_empty_series_no_crash():
    yf = MagicMock()
    yf.get_annual_statements.return_value = (
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    yf.get_ticker_info.return_value = {}
    svc = HistoricalDataServiceImpl(yfinance=yf)
    s = svc.get_annual_series("X")
    assert s["years"] == []
    assert s["complete"] is False


def test_missing_row_in_nonempty_frame_warns(caplog):
    import logging
    yf = MagicMock()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"),
            pd.Timestamp("2022-12-31")]
    income = pd.DataFrame({c: {"Total Revenue": 100, "Operating Income": 40}
                           for c in cols})  # NO "Gross Profit" row
    yf.get_annual_statements.return_value = (
        income,
        pd.DataFrame({c: {"Repurchase Of Capital Stock": 0} for c in cols}),
        pd.DataFrame({c: {"Share Issued": 1} for c in cols}),
    )
    yf.get_ticker_info.return_value = {"financialCurrency": "USD"}
    svc = HistoricalDataServiceImpl(yfinance=yf)
    with caplog.at_level(logging.WARNING,
                         logger="app.services.historical_data_service"):
        s = svc.get_annual_series("X")
    assert s["gross_margin"] == [None, None, None]
    assert s["revenue"] == [100, 100, 100]
    assert "Gross Profit" in caplog.text
