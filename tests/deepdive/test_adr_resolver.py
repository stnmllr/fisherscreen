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
    """Hand-listing these would let the cache validator drift from the type."""
    assert NO_SEC_SOURCE_REASONS == frozenset(
        {"no_us_line", "not_sec_registrant", "no_annual_form"}
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
