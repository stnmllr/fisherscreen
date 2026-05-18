import pytest

from app.deepdive.adr_resolver import ADRResolver, ResolvedTicker
from app.errors import DeepDiveError


def _resolver(table=None):
    if table is None:
        table = {"NOVO-B.CO": {"adr_ticker": "NVO", "cik": "0000353278", "form_type": "20-F"}}
    return ADRResolver(table=table)


def test_resolves_eu_adr_entry():
    r = _resolver().resolve("NOVO-B.CO")
    assert r == ResolvedTicker(ticker="NOVO-B.CO", adr_ticker="NVO",
                               cik="0000353278", form_type="20-F")


def test_is_case_insensitive_on_ticker():
    assert _resolver().resolve("novo-b.co").cik == "0000353278"


def test_us_ticker_passthrough_when_not_in_table():
    # US ticker absent from ADR table -> passthrough, 10-K, no adr_ticker.
    r = _resolver().resolve("AAPL")
    assert r.adr_ticker is None
    assert r.form_type == "10-K"
    assert r.ticker == "AAPL"
    assert r.cik == ""  # CIK resolution for US passthrough is B.1-3's edgar concern


def test_unknown_eu_ticker_raises_actionable_error():
    with pytest.raises(DeepDiveError, match="not in the ADR table"):
        _resolver().resolve("SAP.DE")


def test_di_mockable_via_injected_table():
    r = ADRResolver(table={"X.CO": {"adr_ticker": "X", "cik": "0000000001",
                                    "form_type": "20-F"}})
    assert r.resolve("X.CO").adr_ticker == "X"
