"""iShares EXSA holdings parsing, STOXX source priority and completeness guard.

Fixtures-only: every HTTP-touching function is monkeypatched, no network is hit.
The fixtures are real iShares STOXX Europe 600 UCITS ETF (DE) (EXSA) downloads
(01 Oct 2026): one trimmed to representative rows, one complete.
"""

import json
import logging
from pathlib import Path

import httpx
import pytest

import scripts.build_universe as bu

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TRIMMED_CSV = FIXTURES / "ishares_exsa_holdings_trimmed.csv"
FULL_CSV = FIXTURES / "ishares_exsa_holdings_2026-10-01.csv"


def _read(path: Path) -> str:
    # "utf-8" (not "utf-8-sig") on purpose: httpx' response.text keeps the BOM,
    # so the parser must cope with a leading U+FEFF itself.
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def trimmed_tickers() -> list[str]:
    return bu._parse_ishares_csv(_read(TRIMMED_CSV))


# --- Parser: exchange label -> Yahoo suffix ---------------------------------


@pytest.mark.parametrize(
    "expected",
    [
        "ASML.AS",  # Euronext Amsterdam
        "BESI.AS",  # Euronext Amsterdam — missing from Wikipedia
        "SHELL.AS",  # UK-domiciled, Euronext Amsterdam listing
        "ASSA-B.ST",  # Nasdaq Omx Nordic (Stockholm) + class share
        "RAA.DE",  # Xetra — Rational, never Fraport
        "QIA.DE",  # Deutsche Boerse Xetra
        "DSY.PA",  # Nyse Euronext - Euronext Paris — missing from Wikipedia
        "HLMA.L",  # London Stock Exchange
        "RR.L",  # LSE trailing dot stripped
        "BT-A.L",  # LSE internal-dot class share
        "STMMI.MI",  # Borsa Italiana
        "NOVN.SW",  # SIX Swiss Exchange
        "NOVO-B.CO",  # Omx Nordic Exchange Copenhagen A/S
        "NDA-FI.HE",  # Nasdaq Omx Helsinki Ltd.
        "EQNR.OL",  # Oslo Bors Asa
        "SAN.MC",  # Bolsa De Madrid
        "PKO.WA",  # Warsaw Stock Exchange/Equities/Main Market
        "ETE.AT",  # Athens Exchange S.A. Cash Market
        "A5G.IR",  # Irish Stock Exchange - All Market
        "ABI.BR",  # Nyse Euronext - Euronext Brussels
        "EDP.LS",  # Nyse Euronext - Euronext Lisbon
        "EBS.VI",  # Wiener Boerse Ag
    ],
)
def test_parser_maps_exchange_to_yahoo_suffix(trimmed_tickers, expected):
    assert expected in trimmed_tickers


def test_parser_yields_exactly_the_equity_rows(trimmed_tickers):
    # 22 Equity rows in the trimmed fixture; cash + futures rows are dropped.
    assert len(trimmed_tickers) == 22
    assert len(set(trimmed_tickers)) == 22


def test_parser_maps_rational_to_raa_never_fraport(trimmed_tickers):
    assert "RAA.DE" in trimmed_tickers
    assert "FRA.DE" not in trimmed_tickers


def test_parser_drops_non_equity_rows(trimmed_tickers):
    # EUR cash (exchange "-") and the Eurex futures row (Asset Class Futures).
    assert not any(t.startswith(("EUR", "SXOZ6")) for t in trimmed_tickers)


def test_parser_handles_bom_and_preamble():
    text = _read(TRIMMED_CSV)
    assert text.startswith("﻿")
    assert bu._parse_ishares_csv(text)[0] == "ASML.AS"


def test_parser_without_bom_gives_same_result():
    text = _read(TRIMMED_CSV).lstrip("﻿")
    assert bu._parse_ishares_csv(text) == bu._parse_ishares_csv(_read(TRIMMED_CSV))


def test_nasdaq_omx_nordic_maps_to_stockholm():
    assert bu.ISHARES_EXCHANGE_SUFFIX["Nasdaq Omx Nordic"] == ".ST"


_HEADER = (
    "Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,"
    "Shares,Price,Location,Exchange,Market Currency\n"
)


def _row(ticker: str, exchange: str, asset_class: str = "Equity") -> str:
    return (
        f'"{ticker}","X","Y","{asset_class}","1.00","0.01","1.00","1.00",'
        f'"1.00","Nowhere","{exchange}","EUR"\n'
    )


def test_parser_unknown_exchange_is_counted_warning(caplog):
    csv_text = (
        _HEADER
        + _row("ASML", "Euronext Amsterdam")
        + _row("ZZZ", "Mars Exchange")
        + _row("YYY", "Mars Exchange")
    )
    with caplog.at_level(logging.WARNING, logger=bu.logger.name):
        tickers = bu._parse_ishares_csv(csv_text)
    assert tickers == ["ASML.AS"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("2" in m and "Mars Exchange" in m for m in warnings)


def test_parser_uses_exchange_not_location_column():
    # Location precedes Exchange in the real header; Location must not win.
    csv_text = _HEADER + _row("ASML", "Euronext Amsterdam")
    assert bu._parse_ishares_csv(csv_text) == ["ASML.AS"]


def test_parser_without_header_raises():
    with pytest.raises(ValueError):
        bu._parse_ishares_csv("Fund Holdings as of,x\nfoo,bar\n")


# --- Parser: full real file --------------------------------------------------


@pytest.fixture(scope="module")
def full_tickers() -> list[str]:
    return bu._parse_ishares_csv(_read(FULL_CSV))


def test_full_file_is_complete(full_tickers):
    assert len(full_tickers) >= bu.STOXX_MIN_COMPLETE
    assert len(full_tickers) >= 590


@pytest.mark.parametrize(
    "expected", ["DSY.PA", "BESI.AS", "RAA.DE", "HLMA.L", "ASSA-B.ST", "SHELL.AS"]
)
def test_full_file_contains_previously_missing(full_tickers, expected):
    assert expected in full_tickers


def test_full_file_has_no_fraport(full_tickers):
    assert "FRA.DE" not in full_tickers


def test_full_file_all_equity_rows_map(full_tickers, caplog):
    with caplog.at_level(logging.WARNING, logger=bu.logger.name):
        bu._parse_ishares_csv(_read(FULL_CSV))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(full_tickers) == 602


def test_full_file_has_no_malformed_tickers(full_tickers):
    for t in full_tickers:
        assert " " not in t
        assert ".." not in t


# --- _fetch_stoxx600_ishares -------------------------------------------------


def test_ishares_urls_point_at_exsa():
    assert len(bu.ISHARES_URLS) >= 1
    assert "251931" in bu.ISHARES_URLS[0]
    assert "EXSA_holdings" in bu.ISHARES_URLS[0]


def test_fetch_ishares_first_url_tier_b(monkeypatch):
    monkeypatch.setattr(bu, "_get", lambda url, **kw: _read(FULL_CSV))
    result = bu._fetch_stoxx600_ishares()
    assert result is not None
    tickers, tier = result
    assert tier == "ishares-b"
    assert "DSY.PA" in tickers


def test_fetch_ishares_second_url_tier_c_when_first_fails(monkeypatch):
    monkeypatch.setattr(bu, "ISHARES_URLS", ["https://one.invalid", "https://two"])

    def fake_get(url: str, **kw) -> str:
        if "one" in url:
            raise httpx.HTTPStatusError(
                "500", request=httpx.Request("GET", url), response=httpx.Response(500)
            )
        return _read(FULL_CSV)

    monkeypatch.setattr(bu, "_get", fake_get)
    result = bu._fetch_stoxx600_ishares()
    assert result is not None
    assert result[1] == "ishares-c"


def test_fetch_ishares_all_fail_returns_none(monkeypatch):
    def boom(url: str, **kw) -> str:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(bu, "_get", boom)
    assert bu._fetch_stoxx600_ishares() is None


# --- fetch_stoxx600 priority -------------------------------------------------


def test_priority_ishares_beats_wikipedia(monkeypatch):
    def wiki_must_not_run() -> list[str]:
        raise AssertionError("Wikipedia must not be fetched when iShares succeeds")

    monkeypatch.setattr(bu, "_fetch_stoxx600_wikipedia", wiki_must_not_run)
    monkeypatch.setattr(
        bu, "_fetch_stoxx600_ishares", lambda: (["DSY.PA", "RAA.DE"], "ishares-b")
    )
    assert bu.fetch_stoxx600() == (["DSY.PA", "RAA.DE"], "ishares-b")


def test_priority_wikipedia_when_ishares_fails(monkeypatch):
    monkeypatch.setattr(bu, "_fetch_stoxx600_ishares", lambda: None)
    monkeypatch.setattr(bu, "_fetch_stoxx600_wikipedia", lambda: ["SAP.DE"])
    assert bu.fetch_stoxx600() == (["SAP.DE"], "wikipedia")


def test_priority_hardcoded_when_all_fail(monkeypatch):
    monkeypatch.setattr(bu, "_fetch_stoxx600_ishares", lambda: None)
    monkeypatch.setattr(bu, "_fetch_stoxx600_wikipedia", lambda: [])
    assert bu.fetch_stoxx600() == (list(bu.STOXX_FALLBACK), "hardcoded-fallback")


# --- main(): completeness guard ----------------------------------------------


def _patch_sources(monkeypatch, stoxx: list[str], tier: str) -> None:
    monkeypatch.setattr(bu, "fetch_sp500", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(bu, "fetch_sp400", lambda: ["ZION"])
    monkeypatch.setattr(bu, "fetch_stoxx600", lambda: (stoxx, tier))


def _stoxx(n: int) -> list[str]:
    return [f"T{i:04d}.DE" for i in range(n)]


def test_threshold_constant():
    assert bu.STOXX_MIN_COMPLETE == 590


def test_guard_raises_below_threshold(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, _stoxx(467), "wikipedia")
    with pytest.raises(RuntimeError, match=r"wikipedia.*467|467.*wikipedia"):
        bu.main([], data_dir=tmp_path)
    assert not (tmp_path / "universe.json").exists()


def test_guard_raises_on_hardcoded_fallback(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, list(bu.STOXX_FALLBACK), "hardcoded-fallback")
    with pytest.raises(RuntimeError, match="hardcoded-fallback"):
        bu.main([], data_dir=tmp_path)


def test_guard_allow_partial_flag_warns_and_writes(monkeypatch, tmp_path, caplog):
    _patch_sources(monkeypatch, _stoxx(467), "wikipedia")
    with caplog.at_level(logging.WARNING, logger=bu.logger.name):
        bu.main(["--allow-partial-stoxx"], data_dir=tmp_path)
    assert any(
        r.levelno == logging.WARNING and "467" in r.getMessage() for r in caplog.records
    )
    universe = json.loads((tmp_path / "universe.json").read_text(encoding="utf-8"))
    assert len(universe) == 467 + 3
    prov = json.loads(
        (tmp_path / "universe_provenance.json").read_text(encoding="utf-8")
    )
    assert prov["stoxx_tier"] == "wikipedia"
    assert prov["stoxx600_count"] == 467


def test_guard_passes_at_threshold(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, _stoxx(590), "ishares-b")
    bu.main([], data_dir=tmp_path)
    prov = json.loads(
        (tmp_path / "universe_provenance.json").read_text(encoding="utf-8")
    )
    assert prov == {
        "stoxx_tier": "ishares-b",
        "sp500_count": 2,
        "sp400_count": 1,
        "stoxx600_count": 590,
        "total_unique": 593,
    }


def test_guard_boundary_589_raises(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, _stoxx(589), "ishares-b")
    with pytest.raises(RuntimeError, match="ishares-b"):
        bu.main([], data_dir=tmp_path)
