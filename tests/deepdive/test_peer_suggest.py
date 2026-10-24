from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from app.deepdive.peer_suggest import PeerSuggestion, suggest_peers
from app.deepdive.preflight import SymbolCheck
from app.errors import DataSourceError

COLL = "dev_ticker_cache"


def _target(
    symbol="SAF.PA",
    industry="Aerospace & Defense",
    sector="Industrials",
    mcap=1e11,
    currency="EUR",
):
    return SymbolCheck(
        symbol=symbol,
        ok=True,
        name="Safran",
        currency=currency,
        market_cap=mcap,
        message="gefunden: Safran",
        industry=industry,
        sector=sector,
    )


def _doc(
    industry="Aerospace & Defense",
    sector="Industrials",
    mcap=None,
    currency="EUR",
    **extra,
):
    data: dict[str, Any] = {
        "industry": industry,
        "sector": sector,
        "currency": currency,
        **extra,
    }
    if mcap is not None:
        data["marketCap"] = mcap
    return data


class FakeFirestore:
    def __init__(self, rows: dict[tuple[str, str], list[tuple[str, dict]]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str, Any, int]] = []

    def query_equal(self, collection, field, value, limit):
        self.calls.append((collection, field, value, limit))
        return list(self.rows.get((field, value), []))


# EUR per unit of currency — YFinanceClient.get_fx_rate semantics.
_RATES = {"EUR": 1.0, "USD": 0.9, "SEK": 0.09, "GBP": 1.2}


class FakeFx:
    def __init__(self, rates=None, failing=()) -> None:
        self.rates = dict(_RATES if rates is None else rates)
        self.failing = set(failing)
        self.calls: list[str] = []

    def __call__(self, currency: str) -> float:
        self.calls.append(currency)
        if currency in self.failing:
            raise DataSourceError(f"No FX rate found for {currency}EUR=X")
        return self.rates[currency]


def _suggest(fs, target=None, exclude=(), universe=None, limit=5, fx=None):
    return suggest_peers(
        target or _target(),
        list(exclude),
        firestore=fs,
        collection=COLL,
        universe=frozenset(universe if universe is not None else _UNIVERSE),
        fx_rate=fx or FakeFx(),
        limit=limit,
    )


_UNIVERSE = {"SAF.PA", "AIR.PA", "RHM.DE", "BA.L", "HO.PA", "MTX.DE", "GE", "RTX"}


def test_industry_candidates_sorted_by_market_cap_distance_and_limited():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("SAF.PA", _doc(mcap=1e11)),  # the ticker itself
                ("AIR.PA", _doc(mcap=1.3e11, shortName="Airbus", _cached_at="t1")),
                ("RHM.DE", _doc(mcap=8e10, longName="Rheinmetall AG")),
                ("BA.L", _doc(mcap=2e10)),
                ("HO.PA", _doc(mcap=4e10)),
                ("MTX.DE", _doc(mcap=1.5e10)),
                ("GE", _doc(mcap=2e11)),
                ("XYZ", _doc(mcap=1e11)),  # not in the universe
            ]
        }
    )
    out = _suggest(fs, limit=5)
    assert [s.symbol for s in out] == ["RHM.DE", "AIR.PA", "GE", "HO.PA", "BA.L"]
    assert all(s.match == "industry" for s in out)
    assert out[1] == PeerSuggestion(
        symbol="AIR.PA",
        name="Airbus",
        market_cap=1.3e11,
        match="industry",
        industry="Aerospace & Defense",
        cached_at="t1",
        currency="EUR",
    )
    assert out[0].name == "Rheinmetall AG"
    assert out[0].cached_at is None
    # one industry query is enough when it yields >= 3 candidates
    assert fs.calls == [(COLL, "industry", "Aerospace & Defense", 200)]


def test_excluded_symbols_are_dropped_case_insensitive():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("AIR.PA", _doc(mcap=1e11)),
                ("RHM.DE", _doc(mcap=1e11)),
                ("GE", _doc(mcap=1e11)),
                ("RTX", _doc(mcap=1e11)),
            ]
        }
    )
    out = _suggest(fs, exclude=["saf.pa", " air.pa "])
    assert [s.symbol for s in out] == ["GE", "RHM.DE", "RTX"]


def test_missing_or_invalid_market_cap_sorts_last():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("AIR.PA", _doc()),
                ("RHM.DE", _doc(mcap="n/a")),
                ("GE", _doc(mcap=0)),
                ("RTX", _doc(mcap=5e11)),
            ]
        }
    )
    out = _suggest(fs)
    assert [s.symbol for s in out] == ["RTX", "AIR.PA", "GE", "RHM.DE"]
    assert [s.market_cap for s in out] == [5e11, None, None, None]


def test_target_without_market_cap_sorts_by_symbol():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("RTX", _doc(mcap=5e11)),
                ("AIR.PA", _doc(mcap=1e11)),
                ("GE", _doc()),
            ]
        }
    )
    out = _suggest(fs, target=_target(mcap=None))
    assert [s.symbol for s in out] == ["AIR.PA", "RTX", "GE"]


def test_sector_tops_up_when_industry_has_fewer_than_three():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [("AIR.PA", _doc(mcap=1e11))],
            ("sector", "Industrials"): [
                ("AIR.PA", _doc(mcap=1e11)),  # already suggested via industry
                ("SAF.PA", _doc(mcap=1e11)),  # the ticker
                ("GE", _doc(industry="Conglomerates", mcap=2e11)),
                ("RTX", _doc(industry="Conglomerates", mcap=9e11)),
            ],
        }
    )
    out = _suggest(fs)
    assert [(s.symbol, s.match) for s in out] == [
        ("AIR.PA", "industry"),
        ("GE", "sector"),
        ("RTX", "sector"),
    ]
    assert out[1].industry == "Conglomerates"
    assert fs.calls[1] == (COLL, "sector", "Industrials", 200)


def test_sector_top_up_respects_limit():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [("AIR.PA", _doc(mcap=1e11))],
            ("sector", "Industrials"): [
                ("GE", _doc(mcap=1e11)),
                ("RTX", _doc(mcap=1e11)),
                ("BA.L", _doc(mcap=1e11)),
            ],
        }
    )
    assert len(_suggest(fs, limit=2)) == 2


def test_no_sector_means_no_top_up():
    fs = FakeFirestore({})
    assert _suggest(fs, target=_target(sector=None)) == []
    assert len(fs.calls) == 1


def test_no_industry_returns_empty_without_query():
    fs = FakeFirestore({})
    assert _suggest(fs, target=_target(industry=None)) == []
    assert fs.calls == []


def test_firestore_failure_propagates():
    class Broken:
        def query_equal(self, *args):
            raise DataSourceError("Firestore down")

    with pytest.raises(DataSourceError):
        _suggest(Broken())


def test_suggestion_is_json_serialisable():
    s = PeerSuggestion("AIR.PA", None, None, "sector", None, None)
    assert json.loads(json.dumps(dataclasses.asdict(s)))["match"] == "sector"


# --- currency handling ----------------------------------------------------------


def test_mixed_currencies_ranked_in_eur_and_each_rate_fetched_once():
    # Target SAF.PA: 1e11 EUR. Raw numbers would rank SAAB (1.1e12 SEK) last and
    # the 1.2e11 USD names first; in EUR SAAB is ~0.99e11 -> closest.
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("RTX", _doc(mcap=1.2e11, currency="USD")),  # 1.08e11 EUR
                ("GE", _doc(mcap=3e11, currency="USD")),  # 2.7e11 EUR
                ("SAAB-B.ST", _doc(mcap=1.1e12, currency="SEK")),  # 0.99e11 EUR
                ("AIR.PA", _doc(mcap=1.5e11)),  # 1.5e11 EUR
            ]
        }
    )
    fx = FakeFx()
    out = _suggest(fs, universe=_UNIVERSE | {"SAAB-B.ST"}, fx=fx)
    assert [s.symbol for s in out] == ["SAAB-B.ST", "RTX", "AIR.PA", "GE"]
    # reported cap stays in its own currency; the label travels with it
    assert (out[0].market_cap, out[0].currency) == (1.1e12, "SEK")
    assert sorted(fx.calls) == ["EUR", "SEK", "USD"]


def test_target_in_other_currency_is_converted_too():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("AIR.PA", _doc(mcap=9e10)),  # 9e10 EUR
                ("RTX", _doc(mcap=5e11, currency="USD")),  # 4.5e11 EUR
            ]
        }
    )
    # Target 1e11 USD = 9e10 EUR -> AIR.PA is the exact match.
    out = _suggest(fs, target=_target(symbol="LMT", currency="USD"))
    assert [s.symbol for s in out] == ["AIR.PA", "RTX"]


def test_failed_fx_rate_sorts_those_candidates_last_without_abort():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("RTX", _doc(mcap=1e11, currency="USD")),
                ("GE", _doc(mcap=1e11, currency="USD")),
                ("AIR.PA", _doc(mcap=5e12)),
            ]
        }
    )
    fx = FakeFx(failing={"USD"})
    out = _suggest(fs, fx=fx)
    assert [s.symbol for s in out] == ["AIR.PA", "GE", "RTX"]
    assert fx.calls.count("USD") == 1  # failure is remembered, not retried


def test_non_positive_rate_counts_as_unknown():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("RTX", _doc(mcap=1e11, currency="USD")),
                ("AIR.PA", _doc(mcap=5e12)),
            ]
        }
    )
    out = _suggest(fs, fx=FakeFx(rates={**_RATES, "USD": 0.0}))
    assert [s.symbol for s in out] == ["AIR.PA", "RTX"]


def test_failed_fx_for_target_falls_back_to_symbol_order():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("RTX", _doc(mcap=1e11, currency="USD")),
                ("AIR.PA", _doc(mcap=5e12)),
                ("GE", _doc(currency="USD")),
            ]
        }
    )
    target = _target(symbol="LMT", currency="CHF")
    out = _suggest(fs, target=target, fx=FakeFx(failing={"CHF"}))
    assert [s.symbol for s in out] == ["AIR.PA", "RTX", "GE"]


def test_missing_currency_counts_as_unknown():
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("RTX", _doc(mcap=1e11, currency=None)),
                ("AIR.PA", _doc(mcap=5e12)),
            ]
        }
    )
    out = _suggest(fs)
    assert [s.symbol for s in out] == ["AIR.PA", "RTX"]
    assert out[1].currency is None


def test_legacy_gbp_pence_label_uses_gbp_rate_and_major_unit_cap():
    # A cache doc from before minor-unit normalization says "GBp", but its
    # marketCap is already in pounds: only the label is mapped, no /100.
    fs = FakeFirestore(
        {
            ("industry", "Aerospace & Defense"): [
                ("BA.L", _doc(mcap=8.4e10, currency="GBp")),  # 1.008e11 EUR
                ("AIR.PA", _doc(mcap=1.2e11)),
            ]
        }
    )
    fx = FakeFx()
    out = _suggest(fs, fx=fx)
    assert [s.symbol for s in out] == ["BA.L", "AIR.PA"]
    assert (out[0].market_cap, out[0].currency) == (8.4e10, "GBP")
    assert "GBp" not in fx.calls and "GBP" in fx.calls
