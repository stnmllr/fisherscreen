import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.errors import DeepDiveError


def test_norm_issuer_folds_legal_forms_and_spaces():
    from app.deepdive.eu_adr_resolution import norm_issuer

    assert norm_issuer("ASML Holding N.V.") == norm_issuer("ASML HOLDING NV")
    assert norm_issuer("ROCHE HOLDING AG") != norm_issuer("ROCHE BOBOIS SA")


def test_issuer_name_strips_class_token():
    from app.deepdive.eu_adr_resolution import issuer_name

    assert issuer_name("ROCHE HOLDING AG-BR") == "ROCHE HOLDING AG"
    assert issuer_name("COCA-COLA CO") == "COCA-COLA CO"  # hyphen with space kept


def test_local_symbol_variants_for_dashed_ticker():
    from app.deepdive.eu_adr_resolution import local_symbol_variants

    assert local_symbol_variants("NOVO-B.CO") == ["NOVO-B", "NOVO B", "NOVOB"]


def test_home_exch_codes_from_suffix():
    from app.deepdive.eu_adr_resolution import home_exch_codes

    assert home_exch_codes("NOVO-B.CO") == ["DC"]
    assert home_exch_codes("SAP.DE") == ["GY", "GR"]


def test_find_home_identity_accepts_only_name_match():
    # Wrong candidate returns a foreign issuer -> rejected; right one accepted.
    from app.deepdive.eu_adr_resolution import find_home_identity, norm_issuer

    openfigi = MagicMock()
    openfigi.map_ticker.side_effect = [
        {"name": "ROCHE BOBOIS SA"},  # NOVO-B  -> foreign, rejected
        {"name": "NOVO NORDISK A/S-B"},  # NOVO B  -> matches, accepted
    ]
    ref = norm_issuer("Novo Nordisk A/S")
    ident = find_home_identity("NOVO-B.CO", ref, openfigi=openfigi)
    assert ident["name"] == "NOVO NORDISK A/S-B"


def test_find_home_identity_fail_loud_when_no_match():
    from app.deepdive.eu_adr_resolution import find_home_identity, norm_issuer

    openfigi = MagicMock()
    openfigi.map_ticker.return_value = None
    with pytest.raises(DeepDiveError, match="no verifiable OpenFIGI"):
        find_home_identity("XX-Y.CO", norm_issuer("Whatever Inc"), openfigi=openfigi)


def test_pick_us_adr_line_prefers_depositary_receipt():
    from app.deepdive.eu_adr_resolution import (
        pick_us_adr_line,
        norm_issuer,
        issuer_name,
    )

    ident_norm = norm_issuer(issuer_name("ASML HOLDING NV"))
    lines = [
        {
            "ticker": "ASMLF",
            "exchCode": "US",
            "securityType2": "Common Stock",
            "name": "ASML HOLDING NV",
        },
        {
            "ticker": "ASML",
            "exchCode": "US",
            "securityType2": "Depositary Receipt",
            "name": "ASML HOLDING NV-NY REG SHS",
        },
        {
            "ticker": "ASML",
            "exchCode": "GY",
            "securityType2": "Common Stock",
            "name": "ASML HOLDING NV",
        },
    ]
    assert pick_us_adr_line(lines, ident_norm)["ticker"] == "ASML"


def test_pick_us_adr_line_none_when_no_us_line():
    from app.deepdive.eu_adr_resolution import pick_us_adr_line, norm_issuer

    lines = [
        {
            "ticker": "RMV",
            "exchCode": "LN",
            "securityType2": "Common Stock",
            "name": "RIGHTMOVE PLC",
        }
    ]
    assert pick_us_adr_line(lines, norm_issuer("RIGHTMOVE PLC")) is None


def test_pick_us_adr_line_without_name_filter_prefers_depositary_receipt():
    """The anchored call form (no `ident_norm`). The DR preference is the part
    that must NOT drift between the two call forms — it is policy, not filter."""
    from app.deepdive.eu_adr_resolution import pick_us_adr_line

    lines = [
        {
            "ticker": "ASMLF",
            "exchCode": "US",
            "securityType2": "Common Stock",
            "name": "ASML HOLDING NV",
        },
        {
            "ticker": "ASML",
            "exchCode": "US",
            "securityType2": "Depositary Receipt",
            "name": "ASML HOLDING NV-NY REG SHS",
        },
    ]
    assert pick_us_adr_line(lines)["ticker"] == "ASML"


def test_pick_us_adr_line_without_name_filter_accepts_abbreviated_issuer_name():
    """The anchor argument in isolation, and the direct fix for
    tickets/2026-09-03-same-issuer-abbreviation-gap.md.

    'ENDEAVOUR MNG PLC-UNSPON ADR' normalises to ENDEAVOURMNG-UNSPONADR, which
    is neither a prefix of nor prefixed by ENDEAVOURMINING — so `_same_issuer`
    dropped the DR line before the preference loop could ever see it. On a share
    class every line belongs to the home issuer by construction, so no name is
    compared and the abbreviated line is picked."""
    from app.deepdive.eu_adr_resolution import (
        issuer_name,
        norm_issuer,
        pick_us_adr_line,
    )

    lines = [
        {
            "ticker": "EDVMF",
            "exchCode": "PQ",
            "securityType2": "Common Stock",
            "name": "ENDEAVOUR MINING PLC",
        },
        {
            "ticker": "ENVMY",
            "exchCode": "PQ",
            "securityType2": "Depositary Receipt",
            "name": "ENDEAVOUR MNG PLC-UNSPON ADR",
        },
    ]
    assert pick_us_adr_line(lines)["ticker"] == "ENVMY"
    # Same input through the fallback call form still has the documented hole —
    # pinned here so the gap disappears only when the fallback itself does.
    ident_norm = norm_issuer(issuer_name("ENDEAVOUR MINING PLC"))
    assert pick_us_adr_line(lines, ident_norm)["ticker"] == "EDVMF"


def test_pick_us_adr_line_with_name_filter_still_drops_a_foreign_issuer():
    """FENCE for the fallback arm: making `ident_norm` optional must not turn
    the filter off where it IS passed. Full-text search returns other issuers'
    lines, so on that path the name check is the only thing between the DR
    preference and a foreign line."""
    from app.deepdive.eu_adr_resolution import norm_issuer, pick_us_adr_line

    lines = [
        {
            "ticker": "RBSA",
            "exchCode": "US",
            "securityType2": "Depositary Receipt",
            "name": "ROCHE BOBOIS SA-UNSPON ADR",
        },
    ]
    assert pick_us_adr_line(lines, norm_issuer("ASML HOLDING NV")) is None
    assert pick_us_adr_line(lines) is not None  # unfiltered: exchange code only


def test_fallback_name_filter_is_prefix_tolerant_by_design_not_exact():
    """CHARACTERISATION of the fallback filter as it stands today — pre-existing
    behaviour, untouched by the share-class change, pinned so the difference
    between the two guards stays visible.

    `norm_issuer` strips ' HOLDING', so 'ROCHE HOLDING AG' normalises to plain
    'ROCHE' — which IS a prefix of 'ROCHEBOBOIS-UNSPONADR'. `_same_issuer` is
    prefix-tolerant on purpose (it has to accept 'ASML HOLDING NV-NY REG SHS'),
    so it accepts the Bobois line here. The ROCHE/Bobois guard that actually
    holds lives one level up in `find_home_identity`, which compares for strict
    equality; this test documents that `_same_issuer` is the weaker check and is
    not that guard. The anchored path sidesteps the question entirely."""
    from app.deepdive.eu_adr_resolution import _same_issuer, norm_issuer

    assert norm_issuer("ROCHE HOLDING AG") == "ROCHE"
    assert _same_issuer("ROCHE BOBOIS SA-UNSPON ADR", norm_issuer("ROCHE HOLDING AG"))
    # find_home_identity's strict equality is what rejects it:
    assert norm_issuer("ROCHE HOLDING AG") != norm_issuer("ROCHE BOBOIS SA")


# Share-class FIGIs as measured on 2026-09-03 (SPEC): the anchor the home line
# itself carries. Rightmove has no measured value here and gets a synthetic one
# — its verdict does not depend on the anchor's content, only on its presence.
_ASML_SHARE_CLASS = "BBG001S7Q066"
_RELX_SHARE_CLASS = "BBG001S6ZD33"
_EDV_SHARE_CLASS = "BBG011DVVG30"
_RMV_SHARE_CLASS = "BBG001SYNTH00"


def _deps(longname="ASML Holding N.V."):
    """Default shape: a home line that CARRIES a `shareClassFIGI`, i.e. the
    anchored path every normal issuer takes.

    `search_issuer` deliberately returns an empty page. It must not be called on
    this path at all, and an empty page makes an accidental fall back to it
    change the verdict to `no_us_line` rather than quietly produce the same
    answer — so every test below that claims to exercise the resolution path
    fails if the anchored branch stops being taken."""
    openfigi = MagicMock()
    openfigi.map_ticker.return_value = {
        "name": "ASML HOLDING NV",
        "shareClassFIGI": _ASML_SHARE_CLASS,
    }
    openfigi.lines_by_share_class.return_value = [
        {
            "ticker": "ASML",
            "exchCode": "NA",
            "securityType2": "Common Stock",
            "name": "ASML HOLDING NV",
        },
        {
            "ticker": "ASMLF",
            "exchCode": "US",
            "securityType2": "Common Stock",
            "name": "ASML HOLDING NV",
        },
        {
            "ticker": "ASML",
            "exchCode": "US",
            "securityType2": "Depositary Receipt",
            "name": "ASML HOLDING NV-NY REG SHS",
        },
    ]
    openfigi.search_issuer.return_value = []
    edgar = MagicMock()
    edgar.get_cik.return_value = "937966"
    edgar.detect_annual_form.return_value = "20-F"
    yfinance = MagicMock()
    yfinance.get_ticker_info.return_value = {"longName": longname}
    return openfigi, edgar, yfinance


def _eu_only_deps():
    """Rightmove shape: a verifiable home identity with no US line at all."""
    openfigi, edgar, yfinance = _deps(longname="Rightmove plc")
    openfigi.map_ticker.return_value = {
        "name": "RIGHTMOVE PLC",
        "shareClassFIGI": _RMV_SHARE_CLASS,
    }
    openfigi.lines_by_share_class.return_value = [
        {
            "ticker": "RMV",
            "exchCode": "LN",
            "securityType2": "Common Stock",
            "name": "RIGHTMOVE PLC",
        },
    ]
    return openfigi, edgar, yfinance


def _edv_deps():
    """EDV.L shape: a US line exists, but it is an unsponsored OTC line whose
    issuer has no CIK in company_tickers.json -> not an SEC registrant."""
    openfigi, edgar, yfinance = _deps(longname="Endeavour Mining plc")
    openfigi.map_ticker.return_value = {
        "name": "ENDEAVOUR MINING PLC",
        "shareClassFIGI": _EDV_SHARE_CLASS,
    }
    openfigi.lines_by_share_class.return_value = [
        {
            "ticker": "EDVMF",
            "exchCode": "US",
            "securityType2": "Common Stock",
            "name": "ENDEAVOUR MINING PLC",
        },
    ]
    edgar.get_cik.return_value = None
    return openfigi, edgar, yfinance


def _relx_search_page():
    """The measured first page of /search for RELX: 100 hits (a full page, so a
    `next` cursor exists) and ZERO US lines. Standard Chartered and Enel
    measured the same shape on 2026-09-03."""
    venues = ["LN", "NA", "GY", "SW", "IM"]
    return [
        {
            "ticker": f"REL{i}",
            "exchCode": venues[i % len(venues)],
            "securityType2": "Common Stock",
            "name": "RELX PLC",
        }
        for i in range(100)
    ]


def _relx_deps():
    """RELX: 20-F filer with a NYSE listing that the old path booked as
    `no_us_line`. The share class holds the US lines the first search page does
    not; the OTC foreign-ordinary 'F' line comes first, which is the documented
    best-effort-display caveat (same CIK, same 20-F)."""
    openfigi, edgar, yfinance = _deps(longname="RELX PLC")
    openfigi.map_ticker.return_value = {
        "name": "RELX PLC",
        "shareClassFIGI": _RELX_SHARE_CLASS,
    }
    openfigi.search_issuer.return_value = _relx_search_page()
    openfigi.lines_by_share_class.return_value = [
        {
            "ticker": "REL",
            "exchCode": "LN",
            "securityType2": "Common Stock",
            "name": "RELX PLC",
        },
        {
            "ticker": "RLXXF",
            "exchCode": "US",
            "securityType2": "Common Stock",
            "name": "RELX PLC",
        },
        {
            "ticker": "RELXY",
            "exchCode": "US",
            "securityType2": "Common Stock",
            "name": "RELX PLC-SPONSORED ADR",
        },
    ]
    edgar.get_cik.return_value = "929869"
    return openfigi, edgar, yfinance


def _no_share_class_deps(ident):
    """Fallback shape: a home line WITHOUT a usable `shareClassFIGI`. The search
    page carries a foreign issuer's DR line first, so the name filter is the
    only thing standing between the fallback and a ROCHE-BOBOIS-class false
    hit — if it were dropped, the DR preference would pick the wrong issuer."""
    openfigi, edgar, yfinance = _deps()
    openfigi.map_ticker.return_value = ident
    openfigi.search_issuer.return_value = [
        {
            "ticker": "RBSA",
            "exchCode": "US",
            "securityType2": "Depositary Receipt",
            "name": "ROCHE BOBOIS SA-UNSPON ADR",
        },
        {
            "ticker": "ASMLF",
            "exchCode": "US",
            "securityType2": "Common Stock",
            "name": "ASML HOLDING NV",
        },
    ]
    return openfigi, edgar, yfinance


def _resolve(ticker, cache_path, deps, *, ttl_days=180, negative_ttl_days=30):
    from app.deepdive.eu_adr_resolution import resolve_eu_adr

    openfigi, edgar, yfinance = deps
    return resolve_eu_adr(
        ticker,
        openfigi=openfigi,
        edgar=edgar,
        yfinance=yfinance,
        cache_path=cache_path,
        ttl_days=ttl_days,
        negative_ttl_days=negative_ttl_days,
    )


def test_resolve_eu_adr_happy_path(tmp_path):
    from app.deepdive.eu_adr_resolution import resolve_eu_adr

    openfigi, edgar, yfinance = _deps()
    r = resolve_eu_adr(
        "ASML.AS",
        openfigi=openfigi,
        edgar=edgar,
        yfinance=yfinance,
        cache_path=tmp_path / "adr.json",
        ttl_days=180,
        negative_ttl_days=30,
    )
    assert r.adr_ticker == "ASML"
    assert r.cik == "0000937966"
    assert r.form_type == "20-F"
    assert r.has_filing_source is True


def test_resolve_eu_adr_anchors_on_share_class_and_never_searches(tmp_path):
    """Main path: the home line's own `shareClassFIGI` is the anchor. One
    mapping call on that canonical identifier returns every sibling line of the
    share class, and the paginated full-text `search_issuer` is not called.

    `search_issuer.assert_not_called()` is the load-bearing assertion: both
    paths would resolve this fixture to the same CIK, so only the absence of the
    call distinguishes the new implementation from the old one."""
    openfigi, edgar, yfinance = _deps()

    r = _resolve("ASML.AS", tmp_path / "adr.json", (openfigi, edgar, yfinance))

    openfigi.lines_by_share_class.assert_called_once_with(_ASML_SHARE_CLASS)
    openfigi.search_issuer.assert_not_called()
    assert r.adr_ticker == "ASML"  # DR line, picked out of three share-class lines
    assert r.cik == "0000937966"
    assert r.form_type == "20-F"
    assert r.has_filing_source is True


def test_relx_search_page_fixture_really_holds_no_us_line():
    """Fixture integrity for the regression below: if that 100-hit page ever
    grew a US line, the regression test would pass for the wrong reason and
    stop proving anything about the anchor."""
    from app.deepdive.eu_adr_resolution import (
        issuer_name,
        norm_issuer,
        pick_us_adr_line,
    )

    page = _relx_search_page()
    assert len(page) == 100  # a full page -> a `next` cursor the old path ignored
    assert pick_us_adr_line(page, norm_issuer(issuer_name("RELX PLC"))) is None


def test_share_class_finds_the_us_line_search_issuer_misses(tmp_path):
    """THE regression this change exists for (RELX, measured 2026-09-03).

    `search_issuer` reads only the first page of a paginated result and returned
    100 hits with zero US lines, so RELX — a 20-F filer with a NYSE listing —
    was booked `no_us_line`. That is a wrong VERDICT, not a wrong display
    symbol: it decides whether the dossier gets hard scuttlebutt at all. The
    share class contains the US line (RLXXF, CIK 929869), so the verdict is a
    resolved filing source."""
    openfigi, edgar, yfinance = _relx_deps()

    r = _resolve("REL.L", tmp_path / "adr.json", (openfigi, edgar, yfinance))

    assert r.has_filing_source is True
    assert r.no_sec_source_reason is None
    assert r.adr_ticker == "RLXXF"
    assert r.cik == "0000929869"
    assert r.form_type == "20-F"
    openfigi.search_issuer.assert_not_called()


def test_share_class_accepts_us_line_whose_name_abbreviates_the_issuer(tmp_path):
    """No name comparison on the anchored path — end to end, and the closing
    argument for tickets/2026-09-03-same-issuer-abbreviation-gap.md.

    An issuer whose ONLY US line is the abbreviated DR line
    ('ENDEAVOUR MNG PLC-UNSPON ADR' vs 'ENDEAVOUR MINING PLC') used to fall out
    of `_same_issuer` and produce a `no_us_line` verdict — quiet and wrong, a
    plausible-looking quant-only dossier claiming there is no US listing. On the
    share class the name is never consulted, so the line is accepted and its CIK
    resolved."""
    openfigi, edgar, yfinance = _deps(longname="Endeavour Mining plc")
    openfigi.map_ticker.return_value = {
        "name": "ENDEAVOUR MINING PLC",
        "shareClassFIGI": _EDV_SHARE_CLASS,
    }
    openfigi.lines_by_share_class.return_value = [
        {
            "ticker": "ENVMY",
            "exchCode": "PQ",
            "securityType2": "Depositary Receipt",
            "name": "ENDEAVOUR MNG PLC-UNSPON ADR",
        },
    ]
    edgar.get_cik.return_value = "1854270"

    r = _resolve("EDV.L", tmp_path / "adr.json", (openfigi, edgar, yfinance))

    assert r.has_filing_source is True
    assert r.adr_ticker == "ENVMY"
    assert r.cik == "0001854270"


@pytest.mark.parametrize(
    "ident",
    [
        pytest.param({"name": "ASML HOLDING NV"}, id="key_absent"),
        pytest.param({"name": "ASML HOLDING NV", "shareClassFIGI": None}, id="none"),
        pytest.param({"name": "ASML HOLDING NV", "shareClassFIGI": "  "}, id="blank"),
    ],
)
def test_home_line_without_share_class_falls_back_to_search_with_name_filter(
    tmp_path, caplog, ident
):
    """The temporary fallback. A home line without a usable `shareClassFIGI`
    must not regress from 'searched badly' to 'not searched at all', so it takes
    the old path — WITH the name filter, which is what keeps the foreign DR line
    (ROCHE BOBOIS) from winning the preference loop.

    The WARNING is asserted because it is the measuring instrument: a census run
    that never emits it is the evidence for deleting this branch, so a silently
    dropped log line would remove the only reason the branch could ever go."""
    openfigi, edgar, yfinance = _no_share_class_deps(ident)

    with caplog.at_level(logging.WARNING, logger="app.deepdive.eu_adr_resolution"):
        r = _resolve("ASML.AS", tmp_path / "adr.json", (openfigi, edgar, yfinance))

    openfigi.search_issuer.assert_called_once_with("ASML HOLDING NV")
    openfigi.lines_by_share_class.assert_not_called()
    assert r.adr_ticker == "ASMLF"  # name filter dropped the ROCHE BOBOIS DR line
    assert r.cik == "0000937966"

    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ASML.AS" in warnings[0].getMessage()
    assert "shareClassFIGI" in warnings[0].getMessage()


def test_anchored_path_logs_no_fallback_warning(tmp_path, caplog):
    """Counterpart to the test above: the instrument must be silent when the
    anchor is used, otherwise a census run cannot tell the two apart and the
    WARNING measures nothing."""
    openfigi, edgar, yfinance = _deps()

    with caplog.at_level(logging.WARNING, logger="app.deepdive.eu_adr_resolution"):
        _resolve("ASML.AS", tmp_path / "adr.json", (openfigi, edgar, yfinance))

    assert [rec for rec in caplog.records if rec.levelno == logging.WARNING] == []


def test_resolve_eu_adr_persists_and_reads_cache(tmp_path):
    from app.deepdive.eu_adr_resolution import resolve_eu_adr

    cache = tmp_path / "adr.json"
    openfigi, edgar, yfinance = _deps()
    resolve_eu_adr(
        "ASML.AS",
        openfigi=openfigi,
        edgar=edgar,
        yfinance=yfinance,
        cache_path=cache,
        ttl_days=180,
        negative_ttl_days=30,
    )
    # second call: OpenFIGI must NOT be hit again (served from cache).
    openfigi2 = MagicMock()
    r = resolve_eu_adr(
        "ASML.AS",
        openfigi=openfigi2,
        edgar=edgar,
        yfinance=yfinance,
        cache_path=cache,
        ttl_days=180,
        negative_ttl_days=30,
    )
    assert r.cik == "0000937966"
    openfigi2.map_ticker.assert_not_called()


def test_resolve_eu_adr_no_us_line_returns_no_sec_source_verdict(tmp_path):
    """Behaviour change: a pure-EU listing no longer aborts the deep dive. The
    issuer is verifiably not an SEC registrant, which is a fact about the
    company, not a failure — it degrades to a quant-only dossier."""
    r = _resolve("RMV.L", tmp_path / "adr.json", _eu_only_deps())

    assert r.has_filing_source is False
    assert r.no_sec_source_reason == "no_us_line"
    assert r.cik is None
    assert r.form_type is None
    assert r.adr_ticker is None
    assert "hat keine US-Notierung" in r.no_sec_source_note
    assert "quant-only" in r.no_sec_source_note


def test_resolve_eu_adr_us_line_without_cik_returns_not_sec_registrant(tmp_path):
    """The EDV.L case. The old message called this a symbol error; it is not —
    an unsponsored OTC line exists without the issuer's involvement."""
    r = _resolve("EDV.L", tmp_path / "adr.json", _edv_deps())

    assert r.has_filing_source is False
    assert r.no_sec_source_reason == "not_sec_registrant"
    assert r.cik is None
    assert r.form_type is None
    assert "Die einzige US-Linie (EDVMF)" in r.no_sec_source_note
    assert "Kein Symbol-Fehler." in r.no_sec_source_note


def test_resolve_eu_adr_without_annual_form_returns_no_annual_form(tmp_path):
    openfigi, edgar, yfinance = _edv_deps()
    edgar.get_cik.return_value = "1854270"
    edgar.detect_annual_form.return_value = None

    r = _resolve("EDV.L", tmp_path / "adr.json", (openfigi, edgar, yfinance))

    assert r.has_filing_source is False
    assert r.no_sec_source_reason == "no_annual_form"
    assert r.cik is None  # the discovered CIK lives in the note prose only
    assert "reicht weder 10-K noch 20-F ein" in r.no_sec_source_note
    assert "CIK 1854270" in r.no_sec_source_note


def test_resolve_eu_adr_unverifiable_identity_still_fail_louds(tmp_path):
    """REGRESSION FENCE for "only structural causes degrade": an unverifiable
    OpenFIGI identity is not a statement about SEC registration — we do not know
    which company we are looking at, so a dossier would be phantom data."""
    openfigi, edgar, yfinance = _deps()
    openfigi.map_ticker.return_value = None
    with pytest.raises(DeepDiveError, match="no verifiable OpenFIGI"):
        _resolve("ASML.AS", tmp_path / "adr.json", (openfigi, edgar, yfinance))


def test_resolve_eu_adr_no_reference_name_fail_loud(tmp_path):
    from app.deepdive.eu_adr_resolution import resolve_eu_adr

    openfigi, edgar, yfinance = _deps()
    yfinance.get_ticker_info.return_value = {}  # no longName/shortName
    with pytest.raises(DeepDiveError, match="no reference name"):
        resolve_eu_adr(
            "ASML.AS",
            openfigi=openfigi,
            edgar=edgar,
            yfinance=yfinance,
            cache_path=tmp_path / "adr.json",
            ttl_days=180,
            negative_ttl_days=30,
        )


def test_transient_openfigi_error_propagates_and_writes_no_cache(tmp_path):
    """THE central guard of this change: failure != empty. A DataSourceError is
    a statement about the API, never about the issuer — it must abort (CLI exit
    2) and must NOT leave a cached verdict that would poison later runs.

    Raised from `lines_by_share_class`, i.e. the live path: the new call is a
    new failure surface, and the one shape it must never take is an empty line
    list that reads as `no_us_line`."""
    from app.errors import DataSourceError

    cache = tmp_path / "adr.json"
    openfigi, edgar, yfinance = _deps()
    openfigi.lines_by_share_class.side_effect = DataSourceError("OpenFIGI 503")

    with pytest.raises(DataSourceError, match="OpenFIGI 503"):
        _resolve("ASML.AS", cache, (openfigi, edgar, yfinance))
    assert not cache.exists()


def test_transient_openfigi_error_on_the_fallback_path_also_propagates(tmp_path):
    """Same guard for the fallback arm — it is temporary, not exempt."""
    from app.errors import DataSourceError

    cache = tmp_path / "adr.json"
    openfigi, edgar, yfinance = _no_share_class_deps({"name": "ASML HOLDING NV"})
    openfigi.search_issuer.side_effect = DataSourceError("OpenFIGI 503")

    with pytest.raises(DataSourceError, match="OpenFIGI 503"):
        _resolve("ASML.AS", cache, (openfigi, edgar, yfinance))
    assert not cache.exists()


def test_transient_edgar_error_propagates_and_writes_no_cache(tmp_path):
    from app.errors import DataSourceError

    cache = tmp_path / "adr.json"
    openfigi, edgar, yfinance = _deps()
    edgar.get_cik.side_effect = DataSourceError("EDGAR 429")

    with pytest.raises(DataSourceError, match="EDGAR 429"):
        _resolve("ASML.AS", cache, (openfigi, edgar, yfinance))
    assert not cache.exists()


def test_negative_verdict_is_cached_and_served(tmp_path):
    cache = tmp_path / "adr.json"
    _resolve("RMV.L", cache, _eu_only_deps())

    openfigi2, edgar2, yfinance2 = _deps()
    r = _resolve("RMV.L", cache, (openfigi2, edgar2, yfinance2))

    assert r.no_sec_source_reason == "no_us_line"
    assert "hat keine US-Notierung" in r.no_sec_source_note
    openfigi2.map_ticker.assert_not_called()
    openfigi2.search_issuer.assert_not_called()
    openfigi2.lines_by_share_class.assert_not_called()


def test_negative_and_positive_ttls_are_independent(tmp_path):
    """A no-SEC-source verdict is a statement about today (an ADR facility can
    be registered later); a positive ADR mapping is not. Under
    negative_ttl_days=0 the verdict expires while the mapping survives."""
    cache = tmp_path / "adr.json"
    _resolve("ASML.AS", cache, _deps())
    _resolve("RMV.L", cache, _eu_only_deps())

    positive_deps = _deps()
    positive = _resolve("ASML.AS", cache, positive_deps, negative_ttl_days=0)
    assert positive.cik == "0000937966"
    positive_deps[0].map_ticker.assert_not_called()  # still cached

    negative_deps = _eu_only_deps()
    negative = _resolve("RMV.L", cache, negative_deps, negative_ttl_days=0)
    assert negative.no_sec_source_reason == "no_us_line"
    negative_deps[0].map_ticker.assert_called()  # expired -> re-resolved


def test_positive_entry_expires_under_its_own_ttl(tmp_path):
    """Counterpart to the test above: the positive TTL is live, not decorative
    — the asymmetry only means something if BOTH arms can expire."""
    cache = tmp_path / "adr.json"
    _resolve("ASML.AS", cache, _deps())

    deps = _deps()
    r = _resolve("ASML.AS", cache, deps, ttl_days=0)

    assert r.cik == "0000937966"
    deps[0].map_ticker.assert_called()  # expired -> re-resolved


def _write_cache(tmp_path, payload):
    cache = tmp_path / "adr.json"
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return cache


def test_legacy_four_key_cache_entry_is_still_served(tmp_path):
    """FENCE for the live cache/adr_resolved.json. Its four entries predate the
    no_sec_source keys; re-resolving them would be a needless OpenFIGI round
    trip and, worse, would mean the new writer silently invalidated the old
    reader. Hand-written on purpose: _cache_put must not define the fixture."""
    cache = _write_cache(
        tmp_path,
        {
            "ASML.AS": {
                "adr_ticker": "ASML",
                "cik": "0000937966",
                "form_type": "20-F",
                "_cached_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    deps = _deps()
    r = _resolve("ASML.AS", cache, deps)

    assert r.adr_ticker == "ASML"
    assert r.cik == "0000937966"
    assert r.form_type == "20-F"
    assert r.has_filing_source is True
    deps[0].map_ticker.assert_not_called()


class _Omit:
    """Marker for a key that must be absent, not present-and-None."""


_OMIT = _Omit()
_FRESH = "__now__"  # replaced with a fresh timestamp at fixture-build time


def _entry(**over):
    base = {
        "adr_ticker": "ASML",
        "cik": "0000937966",
        "form_type": "20-F",
        "_cached_at": _FRESH,
    }
    base.update(over)
    if base.get("_cached_at") == _FRESH:
        base["_cached_at"] = datetime.now(timezone.utc).isoformat()
    return {k: v for k, v in base.items() if v is not _OMIT}


@pytest.mark.parametrize(
    "entry_kwargs",
    [
        pytest.param({"_cached_at": _OMIT}, id="missing_cached_at"),
        pytest.param({"_cached_at": "gestern"}, id="unparsable_cached_at"),
        pytest.param({"form_type": None}, id="half_positive_entry"),
        pytest.param(
            {
                "adr_ticker": None,
                "cik": None,
                "form_type": None,
                "no_sec_source_reason": "delisted_in_2027",
                "no_sec_source_note": "note",
            },
            id="unknown_reason_code",
        ),
        pytest.param(
            {
                "adr_ticker": None,
                "cik": None,
                "form_type": None,
                "no_sec_source_reason": "no_us_line",
                "no_sec_source_note": None,
            },
            id="verdict_without_note",
        ),
    ],
)
def test_malformed_cache_entry_is_a_miss_never_a_crash(tmp_path, entry_kwargs):
    """Every read goes through .get(): a KeyError here would escape the CLI as
    an unhandled exception rather than a clean exit code. A miss re-resolves."""
    cache = _write_cache(tmp_path, {"ASML.AS": _entry(**entry_kwargs)})
    deps = _deps()
    r = _resolve("ASML.AS", cache, deps)

    assert r.cik == "0000937966"  # re-resolved live, not read from the entry
    deps[0].map_ticker.assert_called()


def test_cache_entry_that_is_not_an_object_is_a_miss(tmp_path):
    cache = _write_cache(tmp_path, {"ASML.AS": "not-a-dict"})
    deps = _deps()
    r = _resolve("ASML.AS", cache, deps)

    assert r.cik == "0000937966"
    deps[0].map_ticker.assert_called()


def test_unparsable_cache_file_self_heals_end_to_end(tmp_path):
    """Same self-healing as the top-level-list case, different entrance: the
    bytes are not JSON at all. Both unusable shapes must leave a well-formed
    object behind, never an exception and never a half-written file."""
    cache = tmp_path / "adr.json"
    cache.write_text("{ this is not json", encoding="utf-8")

    deps = _deps()
    r = _resolve("ASML.AS", cache, deps)

    assert r.cik == "0000937966"
    deps[0].map_ticker.assert_called()

    healed = json.loads(cache.read_text(encoding="utf-8"))
    assert isinstance(healed, dict)
    assert healed["ASML.AS"]["cik"] == "0000937966"


def test_naive_cached_at_is_read_as_utc_not_a_crash(tmp_path):
    """A hand-edited cache entry loses its offset. Comparing naive and aware
    datetimes would raise TypeError; the reader assumes UTC instead."""
    naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    cache = _write_cache(tmp_path, {"ASML.AS": _entry(_cached_at=naive)})

    deps = _deps()
    r = _resolve("ASML.AS", cache, deps)

    assert r.cik == "0000937966"
    deps[0].map_ticker.assert_not_called()  # fresh -> served from cache


def test_cache_top_level_list_is_a_miss(tmp_path):
    """A JSON top level that is a list, not an object, must read as a miss.

    Deliberately narrow: this pins the READ side in isolation, so a future
    change that makes _cache_get tolerate the wrong top-level type fails here
    even if the end-to-end path still looks fine thanks to the write-side
    repair. The full self-healing round trip is asserted separately below.
    """
    from app.deepdive.eu_adr_resolution import _cache_get

    cache = _write_cache(tmp_path, ["ASML.AS"])
    assert _cache_get(cache, "ASML.AS", 180, 30) is None


@pytest.mark.parametrize(
    "top_level",
    [pytest.param(["ASML.AS"], id="list"), pytest.param("ASML.AS", id="string")],
)
def test_cache_with_wrong_top_level_type_self_heals_end_to_end(tmp_path, top_level):
    """Stronger than a miss: a cache file that is valid JSON of the wrong
    top-level type is REPAIRED, not merely ignored.

    _cache_get reads it as a miss, so the ticker is re-resolved live, and
    _cache_put overwrites the unusable content with a well-formed object
    instead of raising TypeError on the index assignment. A deep dive must
    never die on its own cache file.
    """
    cache = _write_cache(tmp_path, top_level)
    deps = _deps()

    r = _resolve("ASML.AS", cache, deps)

    assert r.cik == "0000937966"  # live result, no exception
    deps[0].map_ticker.assert_called()

    healed = json.loads(cache.read_text(encoding="utf-8"))
    assert isinstance(healed, dict)
    assert healed["ASML.AS"]["cik"] == "0000937966"
    assert healed["ASML.AS"]["form_type"] == "20-F"


def test_healthy_cache_keeps_foreign_entries_on_write(tmp_path):
    """FENCE against a "simplifying" refactoring that sets data = {}
    unconditionally: the write side merges into a healthy cache. Wiping it on
    every write would cost an OpenFIGI round trip per ticker per run and would
    not fail a single test without this one.
    """
    sap_entry = {
        "adr_ticker": "SAP",
        "cik": "0001000184",
        "form_type": "20-F",
        "_cached_at": datetime.now(timezone.utc).isoformat(),
    }
    cache = _write_cache(tmp_path, {"SAP.DE": sap_entry})

    _resolve("ASML.AS", cache, _deps())

    merged = json.loads(cache.read_text(encoding="utf-8"))
    assert merged["SAP.DE"] == sap_entry  # untouched, byte for byte
    assert merged["ASML.AS"]["cik"] == "0000937966"
