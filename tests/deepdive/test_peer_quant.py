import logging
from unittest.mock import MagicMock

from app.deepdive.peer_quant import load_peer_quants
from app.errors import DataSourceError


def _info(**over):
    base = {
        "shortName": "Pfizer", "trailingPE": 12.0, "forwardPE": 11.0,
        "operatingMargins": 0.25, "grossMargins": 0.65,
        "revenueGrowth": 0.03, "freeCashflow": 1.5e10,
        "marketCap": 1.6e11,
    }
    base.update(over)
    return base


def test_loader_maps_all_fields():
    yf = MagicMock()
    yf.get_ticker_info.return_value = _info()
    [pq] = load_peer_quants(["PFE"], yf)
    assert pq.ticker == "PFE"
    assert pq.name == "Pfizer"
    assert pq.trailing_pe == 12.0
    assert pq.forward_pe == 11.0
    assert pq.operating_margin == 0.25
    assert pq.gross_margin == 0.65
    assert pq.revenue_growth_yoy == 0.03
    assert pq.free_cashflow == 1.5e10
    assert pq.market_cap == 1.6e11


def test_loader_missing_keys_become_none():
    yf = MagicMock()
    yf.get_ticker_info.return_value = {"shortName": "Thin Co"}
    [pq] = load_peer_quants(["THIN"], yf)
    assert pq.ticker == "THIN"
    assert pq.name == "Thin Co"
    assert pq.trailing_pe is None
    assert pq.market_cap is None


def test_loader_failsoft_per_peer_on_data_source_error(caplog):
    yf = MagicMock()

    def _side(t):
        if t == "BAD":
            raise DataSourceError("boom")
        return _info(shortName=f"name-{t}")

    yf.get_ticker_info.side_effect = _side
    with caplog.at_level(logging.WARNING, logger="app.deepdive.peer_quant"):
        peers = load_peer_quants(["LLY", "BAD", "MRK"], yf)
    assert [p.ticker for p in peers] == ["LLY", "BAD", "MRK"]
    bad = peers[1]
    assert bad.ticker == "BAD"
    assert bad.name is None and bad.trailing_pe is None
    # the others survive intact
    assert peers[0].name == "name-LLY"
    assert peers[2].name == "name-MRK"
    assert "BAD" in caplog.text
