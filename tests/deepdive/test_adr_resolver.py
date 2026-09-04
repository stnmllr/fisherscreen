import pytest
from unittest.mock import MagicMock

from app.deepdive.adr_resolver import (
    NO_SEC_SOURCE_REASONS,
    ADRResolver,
    ResolvedTicker,
    no_sec_source,
)
from app.errors import DeepDiveError


def _resolver(table=None, edgar=None, eu_resolver=None):
    if table is None:
        table = {
            "NOVO-B.CO": {"adr_ticker": "NVO", "cik": "0000353278", "form_type": "20-F"}
        }
    if edgar is None:
        edgar = MagicMock()
    if eu_resolver is None:
        eu_resolver = MagicMock()
    return ADRResolver(table=table, edgar=edgar, eu_resolver=eu_resolver)


def test_resolves_eu_adr_entry():
    r = _resolver().resolve("NOVO-B.CO")
    assert r == ResolvedTicker(
        ticker="NOVO-B.CO", adr_ticker="NVO", cik="0000353278", form_type="20-F"
    )


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
    """DELIBERATE ASYMMETRY — do not "harmonise" this with the EU path, and do
    not harmonise it with its own sibling below either.

    Two things differ from `test_us_filer_without_annual_form_degrades_to_...`,
    which degrades the very next line of the same function. Here nothing has
    verified the input: an undotted US symbol reaches EDGAR unchecked, so "no
    CIK" is indistinguishable from a typo, and degrading would emit a
    plausible-looking dossier for a ticker that does not exist. One step later
    the CIK out of the SEC ticker map has proven the issuer exists, so the
    finding there is about the issuer and may degrade. Against the EU path the
    same argument runs the other way: a dotted ticker has its home identity
    verified via OpenFIGI before the CIK lookup, so "no CIK" there provably
    means "not an SEC registrant". Fatal here, degraded there — on purpose.
    """
    edgar = MagicMock()
    edgar.get_cik.return_value = None
    with pytest.raises(DeepDiveError, match="not found in the SEC company_tickers"):
        _resolver(edgar=edgar).resolve("NOTAREAL")
    # The abort precedes the form lookup: an unverified symbol must not reach
    # EDGAR a second time, and no verdict may be narrated from a phantom CIK.
    edgar.detect_annual_form.assert_not_called()


def test_us_filer_without_annual_form_degrades_to_quant_only():
    """Sibling of the fatal branch above — and deliberately NOT fatal.

    Past the CIK lookup the identity is proven, because the CIK came out of the
    SEC ticker map, so "no annual form" is a statement about the issuer rather
    than about the input. A registrant filing only 40-F, 10-Q or F-6 is the
    Phase-2 "other forms" gap, not a typo, and the identical finding must not
    mean exit 1 for a US symbol and exit 0 for a dotted EU ticker. It therefore
    degrades to the same quant-only verdict the EU path already produces.
    """
    edgar = MagicMock()
    edgar.get_cik.return_value = "111"
    edgar.detect_annual_form.return_value = None

    r = _resolver(edgar=edgar).resolve("WEIRD")

    assert r.ticker == "WEIRD"
    assert r.has_filing_source is False
    assert r.no_sec_source_reason == "no_annual_form"
    # No filing handles survive the verdict: the CIK is real but leads nowhere,
    # so it lives in the note prose only, never in a followable field.
    assert r.cik is None
    assert r.form_type is None
    assert r.adr_ticker is None
    assert "reicht weder 10-K noch 20-F ein" in r.no_sec_source_note
    assert "CIK 111" in r.no_sec_source_note  # evidence kept, but as prose
    assert "quant-only" in r.no_sec_source_note  # honestly labelled downgrade
    edgar.detect_annual_form.assert_called_once_with("111")


def test_resolved_ticker_rejects_form_type_without_cik():
    """Biconditional, direction A: a filing source is cik AND form_type. A
    form_type without a cik is half-resolved and must be unconstructible."""
    with pytest.raises(AssertionError, match="no_sec_source_reason excludes"):
        ResolvedTicker(ticker="X.L", adr_ticker=None, cik=None, form_type="20-F")


def test_resolved_ticker_rejects_reason_together_with_cik():
    """Biconditional, direction B: direction A alone still admits cik set /
    form_type None with a reason. A no-source verdict must carry no filing
    handles at all — otherwise a caller could follow a phantom filing path."""
    with pytest.raises(AssertionError, match="needs a note and no cik/form_type"):
        ResolvedTicker(
            ticker="X.L",
            adr_ticker=None,
            cik="0000000001",
            form_type=None,
            no_sec_source_reason="no_us_line",
            no_sec_source_note="note",
        )


def test_resolved_ticker_rejects_verdict_without_note():
    """A verdict that cannot explain itself is phantom data in the dossier."""
    with pytest.raises(AssertionError, match="needs a note and no cik/form_type"):
        ResolvedTicker(
            ticker="X.L",
            adr_ticker=None,
            cik=None,
            form_type=None,
            no_sec_source_reason="no_us_line",
            no_sec_source_note=None,
        )


def test_no_sec_source_factory_yields_a_pure_verdict():
    r = no_sec_source("EDV.L", reason="not_sec_registrant", note="Kein SEC-Filing.")
    assert r.has_filing_source is False
    assert r.cik is None
    assert r.form_type is None
    assert r.adr_ticker is None  # discovered symbols live in the note prose only
    assert r.no_sec_source_reason == "not_sec_registrant"
    assert r.no_sec_source_note == "Kein SEC-Filing."


def test_positive_resolved_ticker_has_filing_source():
    r = ResolvedTicker("ASML.AS", "ASML", "0000937966", "20-F")
    assert r.has_filing_source is True
    assert r.no_sec_source_reason is None
    assert r.no_sec_source_note is None


def test_reason_set_is_derived_from_the_literal_type():
    """Hand-listing these would let the cache validator drift from the type.

    Four codes, and the fourth is of a different KIND: `no_us_line`,
    `not_sec_registrant` and `no_annual_form` are statements about the issuer's
    registration status, while `unverifiable_identity` is a statement about our
    matcher — we never got far enough to look. Folding it into
    `not_sec_registrant` would make a dossier assert an absence it never
    established, which is why it is its own member and not a note variant."""
    assert NO_SEC_SOURCE_REASONS == frozenset(
        {
            "no_us_line",
            "not_sec_registrant",
            "no_annual_form",
            "unverifiable_identity",
        }
    )


def test_eu_ticker_delegates_to_eu_resolver():
    eu = MagicMock(return_value=ResolvedTicker("ASML.AS", "ASML", "0000937966", "20-F"))
    r = _resolver(table={}, eu_resolver=eu).resolve("ASML.AS")
    assert r.adr_ticker == "ASML"
    eu.assert_called_once_with("ASML.AS")


def test_di_mockable_via_injected_table():
    r = ADRResolver(
        table={"X.CO": {"adr_ticker": "X", "cik": "0000000001", "form_type": "20-F"}},
        edgar=MagicMock(),
        eu_resolver=MagicMock(),
    )
    assert r.resolve("X.CO").adr_ticker == "X"


# ---------------------------------------------------------------------------
# The override table's negative arm, and its precedence over the EU resolver.
#
# This is what the change is for: Tool B runs on a handful of crosshits, so a
# hand-verified row that is CERTAIN beats a matcher that is merely usually
# right. ARGX.BR and WISE.L were measurably misclassified before the table
# gained these rows.
# ---------------------------------------------------------------------------

_ADYEN_NOTE = (
    "Kein SEC-Hard-Scuttlebutt: Adyen N.V. ist kein SEC-Registrant. Bei der SEC "
    "existiert nur 'Adyen N.V./ADR' (CIK 1788707) mit F-6EF, kein Jahresformular."
)
_ADYEN_ROW = {
    "no_sec_source_reason": "not_sec_registrant",
    "note": _ADYEN_NOTE,
    "verified_on": "2026-09-04",
}
_ARGX_ROW = {
    "adr_ticker": "ARGX",
    "cik": "0001697862",
    "form_type": "20-F",
    "note": "SEC company_tickers.json: ARGX -> ARGENX SE, CIK 1697862.",
    "verified_on": "2026-09-04",
}


class _ExplodingEUResolver:
    """Hand-written rather than a MagicMock, on purpose: a mock would record the
    call and let the test reach an `assert_not_called()` afterwards, so a
    precedence violation would be reported as a bare assertion at the end of the
    test. A raise fails AT the forbidden call, names it, and cannot be defeated
    by someone later reordering the assertions."""

    def __call__(self, ticker):
        raise AssertionError(
            f"the override table must decide {ticker} before the EU resolver runs"
        )


def test_negative_table_entry_yields_a_no_sec_source_verdict():
    """The table could previously only say "here is the CIK". Now it can also
    say "this issuer provably files nothing", and that verdict must arrive in
    exactly the shape the EU resolver produces — same reason vocabulary, same
    absence of filing handles — so the quant-only path downstream cannot tell
    where the verdict was decided."""
    r = _resolver(table={"ADYEN.AS": _ADYEN_ROW}).resolve("ADYEN.AS")

    assert r.ticker == "ADYEN.AS"
    assert r.has_filing_source is False
    assert r.no_sec_source_reason == "not_sec_registrant"
    assert r.cik is None
    assert r.form_type is None
    assert r.adr_ticker is None


def test_negative_table_note_carries_the_tables_prose_and_its_provenance():
    """A dossier reader has to be able to tell a HAND decision from a resolved
    one, and to see how old it is: a negative verdict is only true as of the day
    someone checked. So the note is the row's own evidence plus its origin and
    date — the evidence alone would read like a machine finding."""
    r = _resolver(table={"ADYEN.AS": _ADYEN_ROW}).resolve("ADYEN.AS")

    assert r.no_sec_source_note.startswith(_ADYEN_NOTE)
    assert "Override-Tabelle" in r.no_sec_source_note
    assert "2026-09-04" in r.no_sec_source_note


def test_negative_table_entry_is_case_insensitive_like_the_positive_one():
    """The lookup is upper-cased for both arms; a yfinance-style lower-case
    ticker must not fall through to the EU resolver."""
    resolver = _resolver(
        table={"ADYEN.AS": _ADYEN_ROW}, eu_resolver=_ExplodingEUResolver()
    )
    assert resolver.resolve("adyen.as").no_sec_source_reason == "not_sec_registrant"


def test_positive_table_entry_is_unchanged_by_the_negative_arm():
    r = _resolver().resolve("NOVO-B.CO")
    assert r == ResolvedTicker(
        ticker="NOVO-B.CO", adr_ticker="NVO", cik="0000353278", form_type="20-F"
    )


def test_positive_table_entry_ignores_its_optional_provenance_fields():
    """`note` and `verified_on` are documentation for the human maintainer, not
    payload. Full equality against the four-field ResolvedTicker is the check:
    were the note to leak into `no_sec_source_note`, the biconditional would
    make the object unconstructible — and this pins that it never gets there."""
    r = _resolver(table={"ARGX.BR": _ARGX_ROW}).resolve("ARGX.BR")

    assert r == ResolvedTicker(
        ticker="ARGX.BR", adr_ticker="ARGX", cik="0001697862", form_type="20-F"
    )
    assert r.has_filing_source is True
    assert r.no_sec_source_note is None


def test_negative_table_entry_wins_before_the_eu_resolver():
    """ORDERING IS THE POINT, not merely the verdict. A dotted EU ticker would
    otherwise be routed to the dynamic OpenFIGI path, whose answer for these
    exact tickers is the thing the table exists to override."""
    resolver = _resolver(
        table={"ADYEN.AS": _ADYEN_ROW}, eu_resolver=_ExplodingEUResolver()
    )
    assert resolver.resolve("ADYEN.AS").no_sec_source_reason == "not_sec_registrant"


def test_positive_table_entry_wins_before_the_eu_resolver():
    """The measured defect this change repairs: ARGX.BR files a 20-F, the EU
    resolver did not find it, and the deep dive got a quant-only dossier. With
    the row in place the resolver is never consulted at all."""
    resolver = _resolver(
        table={"ARGX.BR": _ARGX_ROW}, eu_resolver=_ExplodingEUResolver()
    )
    assert resolver.resolve("ARGX.BR").cik == "0001697862"


def test_table_hit_never_touches_edgar():
    """The override is a full answer, not a hint to be confirmed: neither arm
    may spend an EDGAR call, and a negative row in particular must not be
    'verified' against the very source it exists to short-circuit."""
    edgar = MagicMock()
    for table, ticker in ((_ADYEN_ROW, "ADYEN.AS"), (_ARGX_ROW, "ARGX.BR")):
        _resolver(
            table={ticker: table}, edgar=edgar, eu_resolver=_ExplodingEUResolver()
        ).resolve(ticker)
    edgar.get_cik.assert_not_called()
    edgar.detect_annual_form.assert_not_called()


def test_negative_table_entry_accepts_the_unverifiable_identity_code():
    """The table's vocabulary is the resolver's vocabulary, imported not copied.
    Nothing in the shipped file uses this code today — a hand row would be a
    statement about our matcher, which is not something a human verifies — but
    the arm must not silently narrow to a subset of NO_SEC_SOURCE_REASONS."""
    row = {
        "no_sec_source_reason": "unverifiable_identity",
        "note": "Testzeile.",
        "verified_on": "2026-09-04",
    }
    r = _resolver(table={"XX.L": row}).resolve("XX.L")
    assert r.no_sec_source_reason == "unverifiable_identity"
