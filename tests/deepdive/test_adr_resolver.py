import pytest
from unittest.mock import MagicMock

from app.deepdive.adr_resolver import ADRResolver, ResolvedTicker
from app.errors import DeepDiveError


def _resolver(table=None, edgar=None):
    if table is None:
        table = {"NOVO-B.CO": {"adr_ticker": "NVO", "cik": "0000353278", "form_type": "20-F"}}
    if edgar is None:
        edgar = MagicMock()
    return ADRResolver(table=table, edgar=edgar)


def test_resolves_eu_adr_entry():
    r = _resolver().resolve("NOVO-B.CO")
    assert r == ResolvedTicker(ticker="NOVO-B.CO", adr_ticker="NVO",
                               cik="0000353278", form_type="20-F")


def test_is_case_insensitive_on_ticker():
    assert _resolver().resolve("novo-b.co").cik == "0000353278"


def test_us_ticker_resolves_cik_and_form_via_edgar():
    edgar = MagicMock()
    edgar.get_cik.return_value = "320193"
    edgar.detect_annual_form.return_value = "10-K"
    r = _resolver(edgar=edgar).resolve("AAPL")
    assert r.adr_ticker is None
    assert r.cik == "0000320193"  # zero-padded, table-consistent
    assert r.form_type == "10-K"
    edgar.get_cik.assert_called_once_with("AAPL")


def test_us_ticker_not_in_sec_map_raises():
    edgar = MagicMock()
    edgar.get_cik.return_value = None
    with pytest.raises(DeepDiveError, match="not found in the SEC company_tickers"):
        _resolver(edgar=edgar).resolve("NOTAREAL")


def test_us_filer_without_annual_form_raises():
    edgar = MagicMock()
    edgar.get_cik.return_value = "111"
    edgar.detect_annual_form.return_value = None
    with pytest.raises(DeepDiveError, match="neither 10-K nor 20-F"):
        _resolver(edgar=edgar).resolve("WEIRD")


def test_unknown_eu_ticker_raises_postgate_message():
    with pytest.raises(DeepDiveError, match="post-gate B-Fast step"):
        _resolver().resolve("SAP.DE")


def test_di_mockable_via_injected_table():
    r = ADRResolver(table={"X.CO": {"adr_ticker": "X", "cik": "0000000001",
                                    "form_type": "20-F"}}, edgar=MagicMock())
    assert r.resolve("X.CO").adr_ticker == "X"
