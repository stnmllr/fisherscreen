from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from app.deepdive.adr_resolver import ResolvedTicker, no_sec_source
from app.deepdive.peer_suggest import PeerSuggestion
from app.deepdive.preflight import (
    SYMBOL_PATTERN,
    PreflightResult,
    SymbolCheck,
    format_preflight,
    is_valid_symbol,
    normalize_symbol,
    parse_peer_arg,
    run_preflight,
)
from app.errors import DataSourceError, DeepDiveError, DegradedDataError

_INFO = {
    "NOVO-B.CO": {
        "shortName": "Novo Nordisk A/S",
        "currency": "DKK",
        "marketCap": 1_200_000_000_000,
    },
    "AAPL": {"longName": "Apple Inc.", "currency": "USD", "marketCap": 3e12},
    "LLY": {"shortName": "Eli Lilly", "currency": "USD", "marketCap": 7e11},
    "PFE": {"shortName": "Pfizer", "currency": "USD", "marketCap": 1.5e11},
    "MRK": {"shortName": "Merck", "currency": "USD", "marketCap": 2.5e11},
    "EDV.L": {"shortName": "Endeavour", "currency": "GBP", "marketCap": "n/a"},
}


class FakeYF:
    def __init__(self, info: dict[str, Any] | None = None, errors=None) -> None:
        self.info = dict(_INFO if info is None else info)
        self.errors: dict[str, Exception] = dict(errors or {})
        self.calls: list[str] = []

    def get_ticker_info(self, ticker: str) -> dict[str, Any]:
        self.calls.append(ticker)
        if ticker in self.errors:
            raise self.errors[ticker]
        if ticker not in self.info:
            raise DataSourceError(f"yfinance returned empty info for {ticker}")
        return self.info[ticker]


class FakeResolver:
    def __init__(self, result: Any = None, exc: Exception | None = None) -> None:
        self.result = result
        self.exc = exc
        self.calls: list[str] = []

    def resolve(self, ticker: str) -> ResolvedTicker:
        self.calls.append(ticker)
        if self.exc is not None:
            raise self.exc
        return self.result


class MapCheck:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls = 0

    def __call__(self) -> bool:
        self.calls += 1
        return self.available


_FULL_ADR = ResolvedTicker("NOVO-B.CO", "NVO", "0000353278", "20-F")
_FULL_US = ResolvedTicker("AAPL", None, "0000320193", "10-K")
_QUANT = no_sec_source(
    "EDV.L", reason="not_sec_registrant", note="Kein SEC-Registrant (Test)"
)


def _run(
    ticker="NOVO-B.CO",
    peers=None,
    *,
    resolver=None,
    yf=None,
    edgar=None,
    suggest=None,
):
    return run_preflight(
        ticker,
        ["LLY", "PFE", "MRK"] if peers is None else peers,
        resolver=resolver or FakeResolver(_FULL_ADR),
        yfinance=yf or FakeYF(),
        edgar_map_available=edgar or MapCheck(),
        suggest=suggest,
    )


# --- symbols ---------------------------------------------------------------


def test_normalize_symbol_strips_and_uppercases():
    assert normalize_symbol("  novo-b.co ") == "NOVO-B.CO"


@pytest.mark.parametrize(
    "symbol", ["AAPL", "BRK-B", "NOVO-B.CO", "EURUSD=X", "7203.T", "A" * 20]
)
def test_is_valid_symbol_accepts(symbol):
    assert is_valid_symbol(symbol)


@pytest.mark.parametrize(
    "symbol", ["", "--site", "-X", ".CO", "A B", "AAPL;", "A" * 21, "ÄPL"]
)
def test_is_valid_symbol_rejects(symbol):
    assert not is_valid_symbol(symbol)


def test_is_valid_symbol_normalizes_first():
    assert is_valid_symbol(" aapl ")


def test_symbol_pattern_is_the_spec_pattern():
    assert SYMBOL_PATTERN.pattern == r"^[A-Z0-9][A-Z0-9.\-=]{0,19}$"


# --- happy paths -----------------------------------------------------------


def test_full_dossier_via_adr():
    yf = FakeYF()
    edgar = MapCheck()
    r = _run(yf=yf, edgar=edgar)
    assert r.dossier_kind == "full"
    assert r.dossier_note == "20-F via ADR NVO (CIK 0000353278)"
    assert r.can_start is True
    assert r.needs_quant_only_ack is False
    assert r.no_sec_source_reason is None
    assert r.ticker == SymbolCheck(
        symbol="NOVO-B.CO",
        ok=True,
        name="Novo Nordisk A/S",
        currency="DKK",
        market_cap=1.2e12,
        message="gefunden: Novo Nordisk A/S",
    )
    assert [p.symbol for p in r.peers] == ["LLY", "PFE", "MRK"]
    assert all(p.ok for p in r.peers)
    assert yf.calls == ["NOVO-B.CO", "LLY", "PFE", "MRK"]
    # the map is only consulted on a DeepDiveError for an undotted ticker
    assert edgar.calls == 0


def test_full_dossier_table_self_mapping_omits_via_adr():
    # data/adr_table.json maps MSFT -> adr_ticker "MSFT": not an ADR.
    resolver = FakeResolver(ResolvedTicker("msft", "MSFT", "0000789019", "10-K"))
    yf = FakeYF(info={**_INFO, "MSFT": {"shortName": "Microsoft"}})
    r = _run("msft", resolver=resolver, yf=yf)
    assert r.dossier_note == "10-K (CIK 0000789019)"
    assert r.can_start


def test_full_dossier_us_without_adr_uses_long_name():
    r = _run("aapl", resolver=FakeResolver(_FULL_US))
    assert r.ticker.symbol == "AAPL"
    assert r.ticker.name == "Apple Inc."
    assert r.dossier_note == "10-K (CIK 0000320193)"
    assert r.can_start


def test_inputs_are_normalized_before_any_call():
    yf = FakeYF()
    resolver = FakeResolver(_FULL_ADR)
    r = _run(" novo-b.co ", [" lly", "pfe ", "Mrk"], resolver=resolver, yf=yf)
    assert resolver.calls == ["NOVO-B.CO"]
    assert yf.calls == ["NOVO-B.CO", "LLY", "PFE", "MRK"]
    assert r.can_start


def test_quant_only_needs_ack():
    r = _run("EDV.L", resolver=FakeResolver(_QUANT))
    assert r.dossier_kind == "quant_only"
    assert r.dossier_note == "Kein SEC-Registrant (Test)"
    assert r.no_sec_source_reason == "not_sec_registrant"
    assert r.needs_quant_only_ack is True
    assert r.can_start is True
    # non-numeric marketCap is reported as missing, not crashed on
    assert r.ticker.market_cap is None


def test_result_is_json_serialisable():
    r = _run()
    payload = json.dumps(dataclasses.asdict(r))
    assert json.loads(payload)["ticker"]["symbol"] == "NOVO-B.CO"
    assert isinstance(r, PreflightResult)


# --- ticker failures -------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [DataSourceError("boom"), DegradedDataError("degraded")],
)
def test_ticker_unknown_to_yfinance_means_no_dossier_and_no_resolver(exc):
    resolver = FakeResolver(_FULL_ADR)
    r = _run(yf=FakeYF(errors={"NOVO-B.CO": exc}), resolver=resolver)
    assert r.ticker.ok is False
    assert str(exc) in r.ticker.message
    assert r.dossier_kind == "none"
    assert r.can_start is False
    assert r.needs_quant_only_ack is False
    assert resolver.calls == []
    # peers are still checked and reported
    assert all(p.ok for p in r.peers)


def test_ticker_empty_info_is_not_ok():
    r = _run(yf=FakeYF(info={**_INFO, "NOVO-B.CO": {}}))
    assert r.ticker.ok is False
    assert r.dossier_kind == "none"


def test_invalid_ticker_symbol_makes_no_network_call():
    yf = FakeYF()
    resolver = FakeResolver(_FULL_ADR)
    r = _run("--site", yf=yf, resolver=resolver)
    assert r.ticker.ok is False
    assert "ungültig" in r.ticker.message
    assert r.dossier_kind == "none"
    assert "--site" not in yf.calls
    assert resolver.calls == []


def test_resolver_deepdiveerror_with_map_available_is_none():
    edgar = MapCheck(available=True)
    r = _run(
        "AAPL",
        resolver=FakeResolver(exc=DeepDiveError("US ticker AAPL not found")),
        edgar=edgar,
    )
    assert r.dossier_kind == "none"
    assert "US ticker AAPL not found" in r.dossier_note
    assert "BRK-B" in r.dossier_note
    assert "data/adr_table.json" in r.dossier_note
    assert r.can_start is False
    assert edgar.calls == 1


def test_resolver_deepdiveerror_with_map_unavailable_is_unknown():
    r = _run(
        "AAPL",
        resolver=FakeResolver(exc=DeepDiveError("not found")),
        edgar=MapCheck(available=False),
    )
    assert r.dossier_kind == "unknown"
    assert "Quelle nicht erreichbar" in r.dossier_note
    assert "SEC-Tickerliste" in r.dossier_note
    assert r.can_start is False
    assert r.needs_quant_only_ack is False


def test_resolver_deepdiveerror_for_dotted_ticker_skips_map_check():
    edgar = MapCheck(available=False)
    r = _run(resolver=FakeResolver(exc=DeepDiveError("nope")), edgar=edgar)
    assert r.dossier_kind == "none"
    assert edgar.calls == 0


def test_resolver_datasourceerror_is_unknown_not_none():
    r = _run(resolver=FakeResolver(exc=DataSourceError("OpenFIGI 503")))
    assert r.dossier_kind == "unknown"
    assert r.dossier_note.startswith("Quelle nicht erreichbar, später erneut prüfen")
    assert "OpenFIGI 503" in r.dossier_note
    assert r.can_start is False


# --- peers -----------------------------------------------------------------


def test_one_invalid_peer_reported_others_still_checked():
    yf = FakeYF(errors={"PFE": DegradedDataError("degraded info for PFE")})
    r = _run(yf=yf)
    assert [p.ok for p in r.peers] == [True, False, True]
    assert "degraded info for PFE" in r.peers[1].message
    assert yf.calls == ["NOVO-B.CO", "LLY", "PFE", "MRK"]
    assert r.dossier_kind == "full"
    assert r.can_start is False


def test_duplicate_peer_case_insensitive_flagged_without_second_call():
    yf = FakeYF()
    r = _run(peers=["LLY", "lly", "MRK"], yf=yf)
    assert [p.ok for p in r.peers] == [True, False, True]
    assert "doppelt" in r.peers[1].message.lower()
    assert yf.calls.count("LLY") == 1
    assert r.can_start is False


def test_peer_equal_to_ticker_flagged():
    yf = FakeYF()
    r = _run(peers=["novo-b.co", "PFE", "MRK"], yf=yf)
    assert r.peers[0].ok is False
    assert r.peers[0].symbol == "NOVO-B.CO"
    assert "Ticker" in r.peers[0].message
    assert yf.calls.count("NOVO-B.CO") == 1  # only the ticker check
    assert r.can_start is False


def test_empty_peer_is_missing_slot_not_failing_row():
    yf = FakeYF()
    r = _run(peers=["LLY", "  ", "MRK"], yf=yf)
    assert [p.symbol for p in r.peers] == ["LLY", "MRK"]
    assert all(p.ok for p in r.peers)
    assert r.missing_peer_slots == [2]
    assert "" not in yf.calls
    assert r.can_start is False


def test_invalid_peer_symbol_flagged_without_call():
    yf = FakeYF()
    r = _run(peers=["LLY", "--site", "MRK"], yf=yf)
    assert r.peers[1].ok is False
    assert "ungültig" in r.peers[1].message
    assert "--SITE" not in yf.calls


def test_too_few_peers_listed_as_missing_slots():
    r = _run(peers=["LLY"])
    assert [p.symbol for p in r.peers] == ["LLY"]
    assert r.missing_peer_slots == [2, 3]
    assert r.peer_suggestions == []
    assert r.suggestion_note is None  # no suggest callable injected
    assert r.can_start is False


def test_no_peers_at_all():
    r = _run(peers=[])
    assert r.peers == []
    assert r.missing_peer_slots == [1, 2, 3]
    assert r.can_start is False


def test_empty_entry_beyond_third_is_ignored():
    r = _run(peers=["LLY", "PFE", "MRK", " "])
    assert len(r.peers) == 3
    assert r.missing_peer_slots == []
    assert r.can_start is True


def test_too_many_peers_extras_flagged_without_call():
    yf = FakeYF(info={**_INFO, "ABBV": {"shortName": "AbbVie"}})
    r = _run(peers=["LLY", "PFE", "MRK", "ABBV"], yf=yf)
    assert len(r.peers) == 4
    assert [p.ok for p in r.peers] == [True, True, True, False]
    assert "genau 3" in r.peers[3].message
    assert "ABBV" not in yf.calls
    assert r.can_start is False


# --- can_start / ack matrix -------------------------------------------------


@pytest.mark.parametrize(
    "resolver, peer_ok, expect_start, expect_ack",
    [
        (FakeResolver(_FULL_ADR), True, True, False),
        (FakeResolver(_FULL_ADR), False, False, False),
        (FakeResolver(_QUANT), True, True, True),
        (FakeResolver(_QUANT), False, False, True),
        (FakeResolver(exc=DeepDiveError("x")), True, False, False),
        (FakeResolver(exc=DataSourceError("x")), True, False, False),
    ],
)
def test_can_start_and_ack_matrix(resolver, peer_ok, expect_start, expect_ack):
    errors = {} if peer_ok else {"MRK": DataSourceError("gone")}
    r = _run(resolver=resolver, yf=FakeYF(errors=errors))
    assert r.can_start is expect_start
    assert r.needs_quant_only_ack is expect_ack


# --- text rendering ----------------------------------------------------------


def test_format_preflight_full():
    text = format_preflight(_run())
    assert "Vorprüfung NOVO-B.CO" in text
    assert "Novo Nordisk A/S" in text
    assert "Vollständiges Dossier: 20-F via ADR NVO" in text
    assert "Start möglich: ja" in text


def test_format_preflight_quant_only_mentions_ack():
    text = format_preflight(_run("EDV.L", resolver=FakeResolver(_QUANT)))
    assert "Nur Quant-Dossier" in text
    assert "Bestätigung" in text


def test_format_preflight_none_and_unknown():
    none_text = format_preflight(_run(resolver=FakeResolver(exc=DeepDiveError("nope"))))
    assert "Kein Dossier möglich" in none_text
    assert "Start möglich: nein" in none_text
    unknown_text = format_preflight(
        _run(resolver=FakeResolver(exc=DataSourceError("x")))
    )
    assert "Quelle nicht erreichbar" in unknown_text


def test_format_preflight_shows_missing_slots_and_peer_errors():
    r = _run(
        peers=["LLY", "", "--x"],
        yf=FakeYF(info={**_INFO, "LLY": {"shortName": "L"}}),
    )
    text = format_preflight(r)
    assert "Peer 1  LLY" in text
    assert "Peer 2  fehlt" in text
    assert "Peer 3  --X" in text
    assert "FEHLER" in text
    assert "L | - | -" in text  # missing currency / market cap


def test_format_preflight_invalid_empty_ticker():
    assert "Vorprüfung (leer)" in format_preflight(_run(" "))


# --- peer suggestions ---------------------------------------------------------

_SAF_INFO = {
    **_INFO,
    "SAF.PA": {
        "shortName": "Safran",
        "currency": "EUR",
        "marketCap": 1e11,
        "industry": "Aerospace & Defense",
        "sector": "Industrials",
    },
    "AIR.PA": {"shortName": "Airbus", "industry": "Aerospace & Defense"},
    "RHM.DE": {"shortName": "Rheinmetall", "industry": "Aerospace & Defense"},
}
_SAF_FULL = ResolvedTicker("SAF.PA", "SAFRY", "0000000001", "20-F")
_SUGGESTION = PeerSuggestion(
    "HO.PA", "Thales", 4e10, "industry", "Aerospace & Defense", "2026-10-20T08:00"
)


class FakeSuggest:
    def __init__(self, result=None, exc=None) -> None:
        self.result = [_SUGGESTION] if result is None else result
        self.exc = exc
        self.calls: list[tuple[SymbolCheck, list[str]]] = []

    def __call__(self, ticker_check, exclude):
        self.calls.append((ticker_check, exclude))
        if self.exc is not None:
            raise self.exc
        return self.result


def _run_saf(peers, suggest, info=None, ticker="SAF.PA"):
    return _run(
        ticker,
        peers,
        resolver=FakeResolver(_SAF_FULL),
        yf=FakeYF(info=info or _SAF_INFO),
        suggest=suggest,
    )


def test_ticker_check_carries_industry_and_sector():
    r = _run_saf(["AIR.PA", "RHM.DE", "LLY"], None)
    assert r.ticker.industry == "Aerospace & Defense"
    assert r.ticker.sector == "Industrials"
    assert r.peers[2].industry is None


def test_suggestions_offered_for_missing_slots():
    suggest = FakeSuggest()
    r = _run_saf(["air.pa", "RHM.DE", ""], suggest)
    assert r.missing_peer_slots == [3]
    assert r.peer_suggestions == [_SUGGESTION]
    assert r.suggestion_note is None
    assert r.can_start is False
    ((check, exclude),) = suggest.calls
    assert check.symbol == "SAF.PA"
    assert exclude == ["SAF.PA", "AIR.PA", "RHM.DE"]


def test_no_suggest_call_when_all_slots_filled():
    suggest = FakeSuggest()
    r = _run_saf(["AIR.PA", "RHM.DE", "LLY"], suggest)
    assert suggest.calls == []
    assert r.peer_suggestions == []
    assert r.suggestion_note is None
    assert r.can_start is True


def test_no_suggestions_when_ticker_not_ok():
    suggest = FakeSuggest()
    r = _run_saf(["AIR.PA"], suggest, ticker="NOPE.PA")
    assert suggest.calls == []
    assert r.peer_suggestions == []
    assert r.suggestion_note is None


def test_ticker_without_industry_gets_note():
    suggest = FakeSuggest()
    r = _run_saf(["LLY"], suggest, info=_INFO, ticker="NOVO-B.CO")
    assert suggest.calls == []
    assert r.suggestion_note == "keine Branche bekannt — kein Vorschlag"


def test_suggest_source_failure_is_not_empty():
    r = _run_saf(["AIR.PA"], FakeSuggest(exc=DataSourceError("Firestore down")))
    assert r.peer_suggestions == []
    assert r.suggestion_note == "Vorschläge nicht abrufbar (Quelle nicht erreichbar)"


def test_suggest_empty_result_note():
    r = _run_saf(["AIR.PA"], FakeSuggest(result=[]))
    assert r.peer_suggestions == []
    assert r.suggestion_note == "keine passenden Titel im Universum gefunden"


def test_result_with_suggestions_is_json_serialisable():
    r = _run_saf(["AIR.PA"], FakeSuggest())
    payload = json.loads(json.dumps(dataclasses.asdict(r)))
    assert payload["peer_suggestions"][0]["symbol"] == "HO.PA"
    assert payload["missing_peer_slots"] == [2, 3]


def test_format_preflight_lists_suggestions_and_note():
    text = format_preflight(_run_saf(["AIR.PA"], FakeSuggest()))
    assert "Peer 2  fehlt — Vorschlag unten" in text
    assert "Peer-Vorschläge" in text
    assert "HO.PA" in text and "Thales" in text and "Stand 2026-10-20" in text
    assert "Branche: Aerospace & Defense" in text
    sector = PeerSuggestion("GE", None, None, "sector", None, None)
    text = format_preflight(_run_saf(["AIR.PA"], FakeSuggest(result=[sector])))
    assert "Sektor: -" in text and "Stand unbekannt" in text
    text = format_preflight(_run_saf(["AIR.PA"], FakeSuggest(result=[])))
    assert "Peer-Vorschläge: keine passenden Titel" in text


# --- CLI peer parsing ---------------------------------------------------------


def test_parse_peer_arg_accepts_one_to_three():
    assert parse_peer_arg(" lly, ,pfe ") == ["LLY", "PFE"]
    assert parse_peer_arg("A,B,C") == ["A", "B", "C"]


@pytest.mark.parametrize("raw", ["", " , ", "A,B,C,D"])
def test_parse_peer_arg_rejects(raw):
    with pytest.raises(DeepDiveError, match="1 bis 3"):
        parse_peer_arg(raw)
