import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.errors import DeepDiveError

# `norm_issuer`, `issuer_name` and `same_issuer_identity` are exercised in
# tests/deepdive/test_issuer_normalisation.py — the counter-basket, the stump
# survey and one case per rule live there, together. What is tested here is the
# RESOLVER: the ladder it walks and the verdicts it produces.


def test_local_symbol_variants_for_dashed_ticker():
    """The full ladder, in order. The trailing-slash form is last and is the
    measured answer to a miss of its own: OpenFIGI carries BP as 'BP/', so
    'BP.L' and 'JD.L' returned nothing under any of the three forms before it."""
    from app.deepdive.eu_adr_resolution import local_symbol_variants

    assert local_symbol_variants("NOVO-B.CO") == [
        "NOVO-B",
        "NOVO B",
        "NOVOB",
        "NOVO-B/",
    ]


def test_local_symbol_variants_for_an_undashed_ticker_is_two_entries():
    """No dash, so the two dash-rewrites collapse into the base form and the
    order-preserving dedup drops them. BP.L is the measured case the slash form
    was added for, and it costs exactly one extra call — not three."""
    from app.deepdive.eu_adr_resolution import local_symbol_variants

    assert local_symbol_variants("BP.L") == ["BP", "BP/"]


def test_home_exch_codes_from_suffix():
    from app.deepdive.eu_adr_resolution import home_exch_codes

    assert home_exch_codes("NOVO-B.CO") == ["DC"]
    assert home_exch_codes("SAP.DE") == ["GY", "GR"]


def test_find_home_identity_accepts_only_name_match():
    """Wrong candidate returns a foreign issuer -> rejected; right one accepted.

    The reference arrives RAW ('Novo Nordisk A/S', as yfinance spells it), not
    as a pre-computed key: both sides are normalised inside the function, which
    is the only arrangement in which the two recipes cannot age apart. A caller
    that normalised its own side would be a second, silently drifting copy."""
    from app.deepdive.eu_adr_resolution import find_home_identity

    openfigi = MagicMock()
    openfigi.map_ticker.side_effect = [
        {"name": "ROCHE BOBOIS SA"},  # NOVO-B  -> foreign, rejected
        {"name": "NOVO NORDISK A/S-B"},  # NOVO B  -> matches, accepted
        None,  # NOVOB   -> never reached
        None,  # NOVO-B/ -> never reached
    ]
    ident = find_home_identity("NOVO-B.CO", "Novo Nordisk A/S", openfigi=openfigi)
    assert ident["name"] == "NOVO NORDISK A/S-B"
    # Accepted on the second rung, so the ladder stopped there.
    assert openfigi.map_ticker.call_count == 2


def test_find_home_identity_returns_none_when_no_candidate_answers():
    """`None`, not a raise. "No candidate matched" is a legitimate RESULT and
    belongs in the return type: it says something about our matcher, not about
    a failed call, and the caller — not the ladder — decides what it means. A
    control-flow exception here would also be the kind a later reader can widen
    until it swallows a genuine DataSourceError from OpenFIGI.

    The third possibility stays forbidden and is pinned by
    `test_find_home_identity_accepts_only_name_match`: returning an unverified
    match. None is honest ignorance, a wrong ident is phantom data."""
    from app.deepdive.eu_adr_resolution import find_home_identity

    openfigi = MagicMock()
    openfigi.map_ticker.return_value = None

    ident = find_home_identity("NOVO-B.CO", "Whatever Inc", openfigi=openfigi)

    assert ident is None
    # The whole ladder was walked before giving up: 1 home exchange (DC) x 4
    # local-symbol variants ('NOVO-B', 'NOVO B', 'NOVOB', 'NOVO-B/'). A
    # short-circuit would make "no match" mean "the first guess missed", which
    # is a different and much weaker statement.
    assert openfigi.map_ticker.call_count == 4


def test_find_home_identity_returns_none_when_every_answer_is_a_foreign_issuer():
    """The other way to reach None, and the one that matters: OpenFIGI ANSWERED
    every time, it just answered with somebody else. Distinguishing this from
    "no answer" is the NAME-SANITY-CHECK's entire job — accepting here is the
    ROCHE -> ROCHE BOBOIS false hit."""
    from app.deepdive.eu_adr_resolution import find_home_identity

    openfigi = MagicMock()
    openfigi.map_ticker.return_value = {"name": "ROCHE BOBOIS SA"}

    ident = find_home_identity("NOVO-B.CO", "Novo Nordisk A/S", openfigi=openfigi)

    assert ident is None
    assert openfigi.map_ticker.call_count == 4


def test_unverifiable_identity_note_says_unchecked_rather_than_disproven():
    """THE load-bearing wording of this change, tested at the factory so it
    cannot drift unnoticed through either call site.

    `not_sec_registrant` means we looked and found no registration.
    `unverifiable_identity` means we never got far enough to look. A dossier
    that blurred the two would assert an absence nobody established — so the
    note must say "ungeprüft, nicht widerlegt" and must NOT contain the claim
    the registrant verdict makes."""
    from app.deepdive.eu_adr_resolution import unverifiable_identity

    r = unverifiable_identity("XX-Y.CO", cause="Testursache")

    assert r.has_filing_source is False
    assert r.no_sec_source_reason == "unverifiable_identity"
    assert r.cik is None
    assert r.form_type is None
    assert r.adr_ticker is None
    assert "ungeprüft, nicht widerlegt" in r.no_sec_source_note
    assert "XX-Y.CO" in r.no_sec_source_note  # which ticker we failed on
    assert "Testursache" in r.no_sec_source_note  # and why, in the reader's words
    assert "Dossier ist quant-only" in r.no_sec_source_note
    # The claim we are NOT entitled to make here.
    assert "kein SEC-Registrant" not in r.no_sec_source_note


def test_pick_us_adr_line_prefers_depositary_receipt():
    """Selection is exchange code + DR preference, nothing else: the home line
    (GY) is excluded, and among the two US lines the Depositary Receipt wins
    over the plain 'F' line even though the latter comes first."""
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
        {
            "ticker": "ASML",
            "exchCode": "GY",
            "securityType2": "Common Stock",
            "name": "ASML HOLDING NV",
        },
    ]
    assert pick_us_adr_line(lines)["ticker"] == "ASML"


def test_pick_us_adr_line_none_when_no_us_line():
    from app.deepdive.eu_adr_resolution import pick_us_adr_line

    lines = [
        {
            "ticker": "RMV",
            "exchCode": "LN",
            "securityType2": "Common Stock",
            "name": "RIGHTMOVE PLC",
        }
    ]
    assert pick_us_adr_line(lines) is None


def test_pick_us_adr_line_accepts_abbreviated_issuer_name():
    """The unit-level half of the fix for
    tickets/2026-09-03-same-issuer-abbreviation-gap.md (the end-to-end half is
    test_share_class_accepts_us_line_whose_name_abbreviates_the_issuer).

    'ENDEAVOUR MNG PLC-UNSPON ADR' normalises to ENDEAVOURMNG-UNSPONADR, which
    is neither a prefix of nor prefixed by ENDEAVOURMINING — so `_same_issuer`
    dropped the DR line before the preference loop could ever see it. On a share
    class every line belongs to the home issuer by construction, so no name is
    compared and the abbreviated line is picked."""
    from app.deepdive.eu_adr_resolution import pick_us_adr_line

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


# Share-class FIGIs as measured on 2026-09-03 (SPEC): the anchor the home line
# itself carries. Rightmove has no measured value here and gets a synthetic one
# — its verdict does not depend on the anchor's content, only on its presence.
_ASML_SHARE_CLASS = "BBG001S7Q066"
_RELX_SHARE_CLASS = "BBG001S6ZD33"
_EDV_SHARE_CLASS = "BBG011DVVG30"
_RMV_SHARE_CLASS = "BBG001SYNTH00"


def _deps(longname="ASML Holding N.V."):
    """Default shape: a home line that CARRIES a `shareClassFIGI`, i.e. the
    anchored path every issuer takes — it is the only path left.

    `search_issuer` still gets a stub that returns an empty page even though the
    production code no longer calls it. That is deliberate: should the paginated
    full-text path ever be reintroduced, an empty page turns the verdict into
    `no_us_line` instead of quietly producing the same answer, so the tests below
    fail loudly rather than pass for the wrong reason."""
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


def _no_anchor_deps(ident):
    """Anchorless shape: a name-verified home line WITHOUT a usable
    `shareClassFIGI`. Everything else is resolvable — `lines_by_share_class`,
    `get_cik` and `detect_annual_form` would all answer — so the only reason
    this shape can produce anything other than a happy path is the missing
    anchor itself."""
    openfigi, edgar, yfinance = _deps()
    openfigi.map_ticker.return_value = ident
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
    from app.deepdive.eu_adr_resolution import pick_us_adr_line

    page = _relx_search_page()
    assert len(page) == 100  # a full page -> a `next` cursor the old path ignored
    assert pick_us_adr_line(page) is None


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
def test_home_line_without_share_class_anchor_fail_louds_and_caches_nothing(
    tmp_path, ident
):
    """A home line without a usable `shareClassFIGI` raises instead of returning
    a verdict. Without the anchor there is nothing to enumerate, so the issuer's
    US lines are not merely unfound but UNDETERMINABLE — `no_us_line` would
    assert an absence that was never established. The predecessor of this test
    pinned a `search_issuer` fallback that a census over all 416 dotted EU
    tickers measured as dead (zero of its WARNINGs against 26 unrelated ones in
    the same log, so the instrument was demonstrably live).

    THE THREE PARAMETRISATIONS ARE THE POINT and must not be collapsed into one:
    they are the only place `(ident.get("shareClassFIGI") or "").strip()` is
    exercised. `key_absent` covers the `.get` default, `none` the `or ""` (a
    present-but-null key, which is what OpenFIGI actually returns), `blank` the
    `.strip()` (whitespace is not an anchor). Drop any one of them and that
    normalisation loses its only coverage silently.

    Nothing may be cached: the raise sits ABOVE `_cache_put`, and that ordering
    is what keeps an unverifiable situation structurally uncacheable — a cached
    non-verdict would outlive the run that could not make it."""
    cache = tmp_path / "adr.json"
    openfigi, edgar, yfinance = _no_anchor_deps(ident)

    with pytest.raises(DeepDiveError, match="carries no shareClassFIGI"):
        _resolve("ASML.AS", cache, (openfigi, edgar, yfinance))

    assert not cache.exists()  # no verdict written for an unverifiable identity
    # The raise precedes every enumeration attempt, so nothing was even asked.
    openfigi.lines_by_share_class.assert_not_called()
    openfigi.search_issuer.assert_not_called()
    edgar.get_cik.assert_not_called()


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


def _no_name_match_deps():
    """Trigger 1: OpenFIGI answers, but no answer matches the reference name."""
    openfigi, edgar, yfinance = _deps()
    openfigi.map_ticker.return_value = None
    return openfigi, edgar, yfinance


def _no_reference_name_deps():
    """Trigger 2: yfinance has no longName/shortName, so there is nothing to
    check an OpenFIGI hit AGAINST. Reached before OpenFIGI is called at all."""
    openfigi, edgar, yfinance = _deps()
    yfinance.get_ticker_info.return_value = {}
    return openfigi, edgar, yfinance


def test_resolve_eu_adr_unverifiable_identity_returns_a_classified_verdict(tmp_path):
    """BEHAVIOUR CHANGE, and the predecessor of this test asserted the opposite.

    It used to raise, which meant CLI exit 1 and no dossier at all. It now
    degrades, and that is safe for one specific reason: the quant half of a
    dossier hangs on the REQUESTED TICKER, not on the OpenFIGI identity. Price,
    valuation and peers are correct whether or not a name match succeeded — only
    the SEC half is missing, and the label says exactly that.

    What must NOT happen is the third option: guessing an identity. That is
    still forbidden, and `find_home_identity` returning None is what enforces
    it."""
    openfigi, edgar, yfinance = _no_name_match_deps()

    r = _resolve("ASML.AS", tmp_path / "adr.json", (openfigi, edgar, yfinance))

    assert r.has_filing_source is False
    assert r.no_sec_source_reason == "unverifiable_identity"
    assert r.cik is None
    assert r.form_type is None
    assert r.adr_ticker is None
    assert "keine OpenFIGI-Heimatlinie" in r.no_sec_source_note
    assert "ungeprüft, nicht widerlegt" in r.no_sec_source_note
    assert "Dossier ist quant-only" in r.no_sec_source_note
    # Nothing downstream was consulted: without an identity there is no share
    # class to enumerate and no US line to look a CIK up for.
    openfigi.lines_by_share_class.assert_not_called()
    edgar.get_cik.assert_not_called()


def test_resolve_eu_adr_without_a_reference_name_returns_a_classified_verdict(tmp_path):
    """Second trigger, same verdict — and it fires one step earlier: with no
    reference name there is nothing to check an OpenFIGI answer against, so
    accepting one would be "first answer wins" by another route."""
    openfigi, edgar, yfinance = _no_reference_name_deps()

    r = _resolve("ASML.AS", tmp_path / "adr.json", (openfigi, edgar, yfinance))

    assert r.has_filing_source is False
    assert r.no_sec_source_reason == "unverifiable_identity"
    assert "kein Referenzname von yfinance" in r.no_sec_source_note
    assert "ungeprüft, nicht widerlegt" in r.no_sec_source_note
    assert "Dossier ist quant-only" in r.no_sec_source_note
    openfigi.map_ticker.assert_not_called()


@pytest.mark.parametrize(
    "make_deps",
    [
        pytest.param(_no_name_match_deps, id="no_name_match"),
        pytest.param(_no_reference_name_deps, id="no_reference_name"),
    ],
)
def test_unverifiable_identity_is_never_written_to_the_cache(tmp_path, make_deps):
    """THE load-bearing property of the whole degrade decision.

    The other three verdicts describe the ISSUER, so caching them for the
    negative TTL is right — an issuer without a US line will still have none
    tomorrow. This one describes OUR MATCHER, which is being repaired in the
    next PR. A cached "could not verify" would therefore outlive its own cause
    for the full TTL and hide the fix from the very tickers it was written for.

    Asserted as file absence rather than as a mocked `_cache_put`: the
    guarantee is about what is on disk, and a structural absence cannot be
    reintroduced by someone adding a second write path."""
    cache = tmp_path / "adr.json"

    r = _resolve("ASML.AS", cache, make_deps())

    assert r.no_sec_source_reason == "unverifiable_identity"
    assert not cache.exists()


def test_unverifiable_identity_leaves_an_existing_cache_byte_identical(tmp_path):
    """The realistic shape of the previous test: in production the cache file
    already exists because other tickers resolved into it. File absence would
    then prove nothing, so this pins the stronger property — no entry appears,
    and no neighbouring entry is disturbed by a rewrite."""
    cache = tmp_path / "adr.json"
    _resolve("RMV.L", cache, _eu_only_deps())  # a real verdict, legitimately cached
    before = cache.read_text(encoding="utf-8")

    r = _resolve("ASML.AS", cache, _no_name_match_deps())

    assert r.no_sec_source_reason == "unverifiable_identity"
    assert cache.read_text(encoding="utf-8") == before
    assert "ASML.AS" not in json.loads(before)


def test_uncached_unverifiable_identity_lets_the_very_next_call_resolve(tmp_path):
    """The consequence that makes the non-caching matter, stated as behaviour
    rather than as file state: once the matcher can identify the ticker, the
    next call resolves for real. Had the verdict been cached, this second call
    would have been served the stale "could not verify" for negative_ttl_days."""
    cache = tmp_path / "adr.json"

    first = _resolve("ASML.AS", cache, _no_name_match_deps())
    assert first.no_sec_source_reason == "unverifiable_identity"

    second = _resolve("ASML.AS", cache, _deps())  # the repaired matcher

    assert second.has_filing_source is True
    assert second.cik == "0000937966"


def test_unverifiable_identity_logs_a_warning_not_an_info(tmp_path, caplog):
    """Level is a claim about expectedness. An issuer without a US line is
    normal and logs INFO; an identity our matcher cannot resolve is a defect on
    our side and must be visible at WARNING, otherwise the five known matcher
    defects degrade silently now that they no longer abort the run."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.deepdive.eu_adr_resolution"):
        _resolve("ASML.AS", tmp_path / "adr.json", _no_name_match_deps())

    assert any(
        "unverifiable identity" in rec.getMessage()
        and "ASML.AS" in rec.getMessage()
        and rec.levelno == logging.WARNING
        for rec in caplog.records
    )


def test_missing_share_class_anchor_still_raises_and_does_not_degrade(tmp_path):
    """CONTRAST FENCE against the new degrade path — a different concern from
    `test_home_line_without_share_class_anchor_fail_louds_and_caches_nothing`
    above, which pins how the anchor value is normalised.

    Here the identity IS verified; only the enumeration handle is missing, so
    the issuer's US lines are undeterminable rather than absent. Degrading it to
    `unverifiable_identity` would be doubly false — the identity is known — and
    degrading it to `no_us_line` would assert an absence from an unexamined
    universe. Measured across all 416 dotted EU tickers it never occurred, so if
    it fires it is new information and must stay loud."""
    cache = tmp_path / "adr.json"
    openfigi, edgar, yfinance = _no_anchor_deps({"name": "ASML HOLDING NV"})

    with pytest.raises(DeepDiveError, match="carries no shareClassFIGI"):
        _resolve("ASML.AS", cache, (openfigi, edgar, yfinance))

    assert not cache.exists()


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


def test_transient_openfigi_error_on_the_identity_lookup_also_propagates(tmp_path):
    """Same guard one call earlier, on the OTHER OpenFIGI surface: the identity
    lookup. `map_ticker` failing is a statement about the API, and the shape it
    must never take is a `None` that reads as 'no verifiable identity' — that
    would raise DeepDiveError instead of DataSourceError and mislabel an outage
    as an unverifiable issuer."""
    from app.errors import DataSourceError

    cache = tmp_path / "adr.json"
    openfigi, edgar, yfinance = _deps()
    openfigi.map_ticker.side_effect = DataSourceError("OpenFIGI 503")

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
