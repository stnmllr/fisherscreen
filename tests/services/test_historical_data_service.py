from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.historical_data_service import HistoricalDataServiceImpl


def _yf_with_frames():
    yf = MagicMock()
    cols = [
        pd.Timestamp("2024-12-31"),
        pd.Timestamp("2023-12-31"),
        pd.Timestamp("2022-12-31"),
        pd.Timestamp("2021-12-31"),
        pd.Timestamp("2020-12-31"),
    ]
    income = pd.DataFrame(
        {
            c: v
            for c, v in zip(
                cols,
                [
                    {
                        "Total Revenue": 1000,
                        "Gross Profit": 800,
                        "Operating Income": 400,
                    },
                    {
                        "Total Revenue": 900,
                        "Gross Profit": 700,
                        "Operating Income": 350,
                    },
                    {
                        "Total Revenue": 800,
                        "Gross Profit": 600,
                        "Operating Income": 300,
                    },
                    {
                        "Total Revenue": 700,
                        "Gross Profit": 520,
                        "Operating Income": 250,
                    },
                    {
                        "Total Revenue": 600,
                        "Gross Profit": 450,
                        "Operating Income": 200,
                    },
                ],
            )
        }
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
    cols = [
        pd.Timestamp("2024-12-31"),
        pd.Timestamp("2023-12-31"),
        pd.Timestamp("2022-12-31"),
    ]
    income = pd.DataFrame(
        {
            c: {
                "Total Revenue": 1000,
                "Gross Profit": 800,
                "Operating Income": 400,
                "EBIT": 420,
                "Interest Expense": -30,
            }
            for c in cols
        }
    )
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
    income = pd.DataFrame(
        {
            c: {"Total Revenue": 100, "Gross Profit": 80, "Operating Income": 44}
            for c in cols
        }
    )  # no EBIT
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
        pd.DataFrame(
            {
                c: {"Total Revenue": 100, "Gross Profit": 80, "Operating Income": 40}
                for c in cols
            }
        ),
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
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )
    yf.get_ticker_info.return_value = {}
    svc = HistoricalDataServiceImpl(yfinance=yf)
    s = svc.get_annual_series("X")
    assert s["years"] == []
    assert s["complete"] is False


def test_missing_row_in_nonempty_frame_warns(caplog):
    import logging

    yf = MagicMock()
    cols = [
        pd.Timestamp("2024-12-31"),
        pd.Timestamp("2023-12-31"),
        pd.Timestamp("2022-12-31"),
    ]
    income = pd.DataFrame(
        {c: {"Total Revenue": 100, "Operating Income": 40} for c in cols}
    )  # NO "Gross Profit" row
    yf.get_annual_statements.return_value = (
        income,
        pd.DataFrame({c: {"Repurchase Of Capital Stock": 0} for c in cols}),
        pd.DataFrame({c: {"Share Issued": 1} for c in cols}),
    )
    yf.get_ticker_info.return_value = {"financialCurrency": "USD"}
    svc = HistoricalDataServiceImpl(yfinance=yf)
    with caplog.at_level(
        logging.WARNING, logger="app.services.historical_data_service"
    ):
        s = svc.get_annual_series("X")
    assert s["gross_margin"] == [None, None, None]
    assert s["revenue"] == [100, 100, 100]
    assert "Gross Profit" in caplog.text


def _yf_full_for_valuation():
    from datetime import date, timedelta

    yf = MagicMock()
    cols = [
        pd.Timestamp("2024-12-31"),
        pd.Timestamp("2023-12-31"),
        pd.Timestamp("2022-12-31"),
    ]
    income = pd.DataFrame(
        {
            c: {
                "Total Revenue": 1000,
                "Gross Profit": 800,
                "Operating Income": 400,
                "EBIT": 420,
                "Interest Expense": -30,
                "Net Income": 300,
                "Diluted EPS": 3.0,
            }
            for c in cols
        }
    )
    cash = pd.DataFrame(
        {c: {"Repurchase Of Capital Stock": -50, "Free Cash Flow": 250} for c in cols}
    )
    bal = pd.DataFrame(
        {
            c: {
                "Share Issued": 2000,
                "Total Debt": 100,
                "Cash And Cash Equivalents": 500,
            }
            for c in cols
        }
    )
    yf.get_annual_statements.return_value = (income, cash, bal)
    yf.get_ticker_info.return_value = {"financialCurrency": "USD", "currency": "USD"}
    yf.get_weekly_close_5y.return_value = [
        (date(2022, 1, 1) + timedelta(days=7 * i), 60.0) for i in range(160)
    ]
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
    with caplog.at_level(
        logging.WARNING, logger="app.services.historical_data_service"
    ):
        s = HistoricalDataServiceImpl(yfinance=yf).get_annual_series("X")
    vh = s["valuation_history"]
    assert vh.pe.status == "na_data"
    assert s["years"] == [2024, 2023, 2022]


# ==========================================================================
# Regression fence: minor-unit normalization across the whole
# adapter -> historical_data_service -> valuation_history seam.
#
# Before the change, GBP-reporting London titles were protected only BY
# ACCIDENT: info["currency"] was "GBp", financialCurrency "GBP", and
# "GBp" != "GBP" made the FX gate in valuation_history fire, so the bands were
# honestly reported as skipped_fx. Relabelling info to "GBP" opens that gate.
# If a future refactor normalizes `info` but not the weekly price series, the
# gate stays open and pence prices flow into price/eps and price*shares — a
# silent factor-100 error reported as `complete`. Nothing else in the suite
# catches that, because every other test either mocks the client (so no
# normalization happens at all) or checks only one of the two halves.
#
# These tests therefore drive the REAL YFinanceClientImpl over a stubbed
# yf.Ticker: both halves of the normalization have to be present for the
# numbers below to come out.
# ==========================================================================

_FY_COLS = [
    "2024-12-31",
    "2023-12-31",
    "2022-12-31",
]


class _StubTicker:
    """yf.Ticker stand-in serving a full London-listing response.

    Prices (info + history) are quoted in pence; the statements are in the
    financial currency and are not affected by minor units.
    """

    def __init__(self, info, weekly):
        self.info = info
        self._weekly = weekly
        self.history_metadata = {"currency": info["currency"]}
        cols = [pd.Timestamp(c) for c in _FY_COLS]
        self.income_stmt = pd.DataFrame(
            {
                c: {
                    "Total Revenue": 30_000_000_000,
                    "Gross Profit": 20_000_000_000,
                    "Operating Income": 6_000_000_000,
                    "EBIT": 6_000_000_000,
                    "Interest Expense": -1_000_000_000,
                    "Net Income": 4_000_000_000,
                    "Diluted EPS": 1.00,  # GBP per share, NOT pence
                }
                for c in cols
            }
        )
        self.cashflow = pd.DataFrame(
            {
                c: {
                    "Repurchase Of Capital Stock": -1_000_000_000,
                    "Free Cash Flow": 3_000_000_000,
                }
                for c in cols
            }
        )
        self.balance_sheet = pd.DataFrame(
            {
                c: {
                    "Share Issued": 4_000_000_000,
                    "Total Debt": 20_000_000_000,
                    "Cash And Cash Equivalents": 5_000_000_000,
                }
                for c in cols
            }
        )

    @property
    def splits(self):
        return pd.Series(dtype=float)

    def history(self, period=None, interval=None, auto_adjust=None):
        return self._weekly


def _pence_weekly_frame(pence=1500.0, weeks=160, start="2023-04-03"):
    """Weekly closes as yfinance quotes them for a London listing: pence."""
    idx = pd.date_range(start=start, periods=weeks, freq="7D")
    return pd.DataFrame({"Close": [pence] * weeks}, index=idx)


def _london_service(monkeypatch, financial_currency):
    from app.services import yfinance_client as mod

    info = {
        "shortName": "GSK plc",
        "currency": "GBp",  # yfinance's minor-unit label
        "financialCurrency": financial_currency,
        "marketCap": 60_000_000_000,  # already pounds
        "currentPrice": 1500.0,  # pence
        "trailingEps": 1.00,  # already pounds
    }
    ticker = _StubTicker(info, _pence_weekly_frame())
    monkeypatch.setattr(mod.yf, "Ticker", lambda t: ticker)
    return HistoricalDataServiceImpl(yfinance=mod.YFinanceClientImpl())


def test_gbp_reporting_london_title_computes_multiples_from_normalized_prices(
    monkeypatch,
):
    """GSK.L shape: quoted in pence, reporting in GBP.

    The adapter relabels currency GBp -> GBP, so the FX gate no longer fires and
    the bands are computed for real. They must be computed from POUNDS: with a
    15.00 GBP price and 1.00 GBP diluted EPS the P/E is 15, in the plausible tens.
    Un-normalized pence prices would yield 1500 — arithmetically silent, reported
    as `complete`, and wrong by exactly the factor this change removes."""
    svc = _london_service(monkeypatch, financial_currency="GBP")

    vh = svc.get_annual_series("GSK.L")["valuation_history"]

    assert vh.pe.status == "complete"  # the gate is open now, not skipped_fx
    assert vh.pe.median == pytest.approx(15.0)
    assert vh.pe.median < 100, "P/E in the hundreds means pence prices leaked in"
    # implied shares 4e9 -> mcap 60e9, EV 75e9, EBIT 6e9
    assert vh.ev_ebit.median == pytest.approx(12.5)
    assert vh.fcf_yield.median == pytest.approx(0.05)


def test_london_multiples_are_not_the_pence_valued_ones(monkeypatch):
    """The explicit counter-value. Spelled out separately so a failure message
    names the defect instead of just an off-by-100 number."""
    svc = _london_service(monkeypatch, financial_currency="GBP")

    vh = svc.get_annual_series("GSK.L")["valuation_history"]

    assert vh.pe.median != pytest.approx(1500.0), "prices still in pence"
    assert vh.ev_ebit.median != pytest.approx(1002.5, rel=1e-3), "prices in pence"


def test_usd_reporting_london_title_still_skipped_fx(monkeypatch):
    """EDV.L shape: quoted in pence, reporting in USD. Normalization fixes the
    minor-unit mismatch but not the genuine cross-currency one, so the bands must
    still be honestly skipped rather than computed against a USD EPS."""
    svc = _london_service(monkeypatch, financial_currency="USD")

    vh = svc.get_annual_series("EDV.L")["valuation_history"]

    assert vh.pe.status == "skipped_fx"
    assert vh.ev_ebit.status == "skipped_fx"
    assert vh.fcf_yield.status == "skipped_fx"
    assert vh.pe.median is None
