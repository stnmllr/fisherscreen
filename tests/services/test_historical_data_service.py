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


def test_extracts_ebit_and_interest_expense_rows():
    yf = MagicMock()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"),
            pd.Timestamp("2022-12-31")]
    income = pd.DataFrame({c: {"Total Revenue": 1000, "Gross Profit": 800,
                               "Operating Income": 400, "EBIT": 420,
                               "Interest Expense": -30} for c in cols})
    yf.get_annual_statements.return_value = (
        income,
        pd.DataFrame({c: {"Repurchase Of Capital Stock": 0} for c in cols}),
        pd.DataFrame({c: {"Share Issued": 1} for c in cols}),
    )
    yf.get_ticker_info.return_value = {"financialCurrency": "USD"}
    s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    assert s["ebit"] == [420, 420, 420]
    assert s["interest_expense"] == [-30, -30, -30]


def test_ebit_falls_back_to_operating_income_when_absent():
    yf = MagicMock()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31")]
    income = pd.DataFrame({c: {"Total Revenue": 100, "Gross Profit": 80,
                               "Operating Income": 44} for c in cols})  # no EBIT
    yf.get_annual_statements.return_value = (
        income,
        pd.DataFrame({c: {"Repurchase Of Capital Stock": 0} for c in cols}),
        pd.DataFrame({c: {"Share Issued": 1} for c in cols}),
    )
    yf.get_ticker_info.return_value = {"financialCurrency": "USD"}
    s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    assert s["ebit"] == [44, 44]


def test_ebit_and_interest_expense_none_filled_when_rows_absent():
    yf = _yf_with_frames()  # frames have Operating Income but no EBIT/Interest
    s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    # EBIT falls back to Operating Income
    assert s["ebit"] == [400, 350, 300, 250, 200]
    # Interest Expense absent entirely -> None-filled, no crash
    assert s["interest_expense"] == [None, None, None, None, None]


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


def _yf_full_for_valuation():
    from datetime import date, timedelta
    yf = MagicMock()
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"),
            pd.Timestamp("2022-12-31")]
    income = pd.DataFrame({c: {
        "Total Revenue": 1000, "Gross Profit": 800, "Operating Income": 400,
        "EBIT": 420, "Interest Expense": -30,
        "Net Income": 300, "Diluted EPS": 3.0} for c in cols})
    cash = pd.DataFrame({c: {"Repurchase Of Capital Stock": -50,
                             "Free Cash Flow": 250} for c in cols})
    bal = pd.DataFrame({c: {"Share Issued": 2000, "Total Debt": 100,
                            "Cash And Cash Equivalents": 500} for c in cols})
    yf.get_annual_statements.return_value = (income, cash, bal)
    yf.get_ticker_info.return_value = {"financialCurrency": "USD",
                                       "currency": "USD"}
    yf.get_weekly_close_5y.return_value = [
        (date(2022, 1, 1) + timedelta(days=7 * i), 60.0) for i in range(160)]
    yf.get_splits.return_value = []
    return yf


def test_extracts_valuation_fundamental_rows():
    yf = _yf_full_for_valuation()
    s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    assert s["net_income"] == [300, 300, 300]
    assert s["diluted_eps"] == [3.0, 3.0, 3.0]
    assert s["free_cashflow"] == [250, 250, 250]
    assert s["total_debt"] == [100, 100, 100]
    assert s["cash"] == [500, 500, 500]


def test_valuation_history_key_present_and_computed():
    yf = _yf_full_for_valuation()
    s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    vh = s["valuation_history"]
    assert vh.pe.status in ("complete", "partial")
    assert vh.pe.median is not None


def test_valuation_history_failsoft_on_price_pull_error(caplog):
    import logging
    from app.errors import DataSourceError
    yf = _yf_full_for_valuation()
    yf.get_weekly_close_5y.side_effect = DataSourceError("boom")
    with caplog.at_level(logging.WARNING,
                         logger="app.services.historical_data_service"):
        s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    vh = s["valuation_history"]
    assert vh.pe.status == "na_data"
    assert s["years"] == [2024, 2023, 2022]
