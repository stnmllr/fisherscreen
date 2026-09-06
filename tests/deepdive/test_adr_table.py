import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.deepdive.adr_resolver import NO_SEC_SOURCE_REASONS, ADRResolver
from app.deepdive.adr_table import load_adr_table
from app.errors import DeepDiveError


def test_load_seed_has_novo():
    entries = load_adr_table()
    assert entries["NOVO-B.CO"] == {
        "adr_ticker": "NVO",
        "cik": "0000353278",
        "form_type": "20-F",
    }


def test_missing_file_raises(tmp_path):
    with pytest.raises(DeepDiveError, match="not found"):
        load_adr_table(tmp_path / "nope.json")


def test_invalid_json_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(DeepDiveError, match="not valid JSON"):
        load_adr_table(bad)


def test_missing_entries_key_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(DeepDiveError, match="entries"):
        load_adr_table(bad)


def test_bad_cik_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    "X.CO": {"adr_ticker": "X", "cik": "353278", "form_type": "20-F"}
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="10-digit"):
        load_adr_table(bad)


def test_bad_form_type_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    "X.CO": {"adr_ticker": "X", "cik": "0000000001", "form_type": "8-K"}
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="form_type"):
        load_adr_table(bad)


def test_entry_not_object_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps({"version": 1, "entries": {"X.CO": "nope"}}),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="must be an object"):
        load_adr_table(bad)


def test_entries_not_object_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    with pytest.raises(DeepDiveError, match="'entries' must be an object"):
        load_adr_table(bad)


def test_empty_adr_ticker_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    "X.CO": {"adr_ticker": "", "cik": "0000000001", "form_type": "20-F"}
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="adr_ticker"):
        load_adr_table(bad)


# ---------------------------------------------------------------------------
# The negative arm of the tagged union.
#
# `load_adr_table` is the ONLY thing standing between a typo in a hand-typed row
# and a paid deep dive that acts on it, so the arm is exercised through its
# failure modes rather than only its happy path. Each case below is a row a
# human could plausibly produce, and the assertions pin the DIAGNOSIS as well as
# the raise: a misleading message is what sends the next reader hunting in the
# wrong place, and this file has exactly one reader — a human holding a
# malformed row.
# ---------------------------------------------------------------------------

_NEGATIVE_ENTRY = {
    "no_sec_source_reason": "not_sec_registrant",
    "note": "Nur F-6EF der Depotbank unter CIK 0002139860, keine Jahresformulare.",
    "verified_on": "2026-09-04",
}


def _write_table(tmp_path, entries):
    """Write a table file holding ``entries`` and return its path."""
    path = tmp_path / "adr.json"
    path.write_text(
        json.dumps({"version": 1, "entries": entries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _negative(**over):
    """A valid negative entry with ``over`` applied — one defect per test."""
    return {**_NEGATIVE_ENTRY, **over}


def _load_one(tmp_path, entry, ticker="EDV.L"):
    """Load a one-row table; that row is the whole subject of the test."""
    return load_adr_table(_write_table(tmp_path, {ticker: entry}))


def test_negative_entry_loads(tmp_path):
    """The new shape survives loading VERBATIM — the loader validates, it does
    not normalise. `_from_table_entry` indexes 'note' and 'verified_on'
    directly, so a field the loader silently dropped would become a KeyError
    inside a run rather than a diagnosis at construction time."""
    entry = _negative()
    entries = _load_one(tmp_path, entry)
    assert entries["EDV.L"] == entry


def test_mixed_entry_is_reported_as_a_shape_clash_not_as_an_unknown_field(tmp_path):
    """A row carrying both a CIK and a "no SEC source" verdict is the one
    contradiction the union must never let through: the resolver decides the arm
    by the presence of the tag alone, so it would pick the negative arm and throw
    the CIK away without a word.

    The message matters as much as the raise. "unknown field 'cik'" would be
    true but useless — 'cik' is a perfectly legal field, just not on this arm —
    and would send the reader looking for a spelling mistake that is not there.
    The clash is therefore diagnosed BEFORE the unknown-field sweep, and this
    test pins that ordering, not merely the rejection."""
    with pytest.raises(DeepDiveError) as exc:
        _load_one(tmp_path, _negative(cik="0002139860"))

    msg = str(exc.value)
    assert "either positive" in msg
    assert "or negative" in msg
    assert "remove ['cik']" in msg
    assert "unknown field" not in msg


def test_mixed_entry_names_every_clashing_positive_field(tmp_path):
    """Half a positive mapping is still a mixed entry, and the reader is handed
    the full list to delete instead of bisecting the row one raise at a time."""
    with pytest.raises(DeepDiveError) as exc:
        _load_one(tmp_path, _negative(adr_ticker="EDVMF", form_type="20-F"))

    assert "remove ['adr_ticker', 'form_type']" in str(exc.value)


def test_unknown_reason_code_raises_and_lists_the_derived_codes(tmp_path):
    """The reason vocabulary comes from NoSecSourceReason via get_args, so a code
    this build cannot act on is rejected at load time instead of reaching the
    resolver's `cast` and travelling into a dossier as an unknown label. The
    message listing every current code — including `unverifiable_identity` — is
    the cheap proof that the list is derived rather than a second hand-typed
    copy that can drift from the literal."""
    with pytest.raises(DeepDiveError) as exc:
        _load_one(tmp_path, _negative(no_sec_source_reason="not_sec_registrand"))

    msg = str(exc.value)
    assert "'no_sec_source_reason' must be one of" in msg
    for code in NO_SEC_SOURCE_REASONS:
        assert code in msg


def test_non_string_reason_code_raises(tmp_path):
    """JSON admits any type here, and a bare membership test would pass a list
    straight through to the resolver's cast."""
    with pytest.raises(DeepDiveError, match="must be one of"):
        _load_one(tmp_path, _negative(no_sec_source_reason=["not_sec_registrant"]))


def test_negative_entry_without_verified_on_raises(tmp_path):
    """MANDATORY on this arm, and the whole reason the field exists: "not an SEC
    registrant" is a statement about a point in time. Adyen can register
    tomorrow, and an undated pinned negative would never notice — it would go on
    asserting an absence nobody has re-checked, for as long as the row lives."""
    entry = {k: v for k, v in _NEGATIVE_ENTRY.items() if k != "verified_on"}
    with pytest.raises(DeepDiveError) as exc:
        _load_one(tmp_path, entry)

    msg = str(exc.value)
    assert "'verified_on' is required for a negative entry" in msg
    assert "only true as of a date" in msg


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("04.09.2026", id="german_order"),
        pytest.param("2026-13-04", id="month_13"),
        pytest.param("2026-02-30", id="day_that_does_not_exist"),
        pytest.param("2026-09", id="truncated"),
        pytest.param("", id="empty"),
    ],
)
def test_malformed_verified_on_raises(tmp_path, value):
    """A date that does not parse is worse than a missing one: it looks like
    provenance while carrying none. `2026-02-30` is the case a shape regex would
    wave through, which is why the check is `date.fromisoformat` and why that
    parametrisation must not be dropped."""
    with pytest.raises(DeepDiveError, match="is not an ISO date"):
        _load_one(tmp_path, _negative(verified_on=value))


def test_non_string_verified_on_raises(tmp_path):
    """`20260904` unquoted is a plausible hand-edit. Without the type check it
    reaches `date.fromisoformat` as an int and raises TypeError, which escapes
    the DeepDiveError contract this loader owes its callers."""
    with pytest.raises(DeepDiveError, match="must be an ISO date string"):
        _load_one(tmp_path, _negative(verified_on=20260904))


def test_positive_entry_with_malformed_verified_on_raises(tmp_path):
    """Optional on the positive arm, but not exempt: an unparsable date is a
    defect wherever it appears, and the two positive crosshit rows carry one."""
    entry = {
        "adr_ticker": "ARGX",
        "cik": "0001697862",
        "form_type": "20-F",
        "verified_on": "gestern",
    }
    with pytest.raises(DeepDiveError, match="is not an ISO date"):
        _load_one(tmp_path, entry, ticker="ARGX.BR")


@pytest.mark.parametrize(
    "note",
    [pytest.param("", id="empty_string"), pytest.param(42, id="not_a_string")],
)
def test_negative_entry_needs_a_non_empty_note(tmp_path, note):
    """A hand-maintained verdict has to state its evidence: the note is the only
    thing a later reader can re-check the row against, and it is the text the
    dossier prints. An empty one yields a verdict that cannot explain itself."""
    with pytest.raises(DeepDiveError, match="'note' must be a non-empty string"):
        _load_one(tmp_path, _negative(note=note))


def test_negative_entry_without_a_note_raises(tmp_path):
    entry = {k: v for k, v in _NEGATIVE_ENTRY.items() if k != "note"}
    with pytest.raises(DeepDiveError, match="'note' must be a non-empty string"):
        _load_one(tmp_path, entry)


def test_misspelt_reason_tag_is_caught_as_an_unknown_field(tmp_path):
    """THE failure mode of a hand-maintained file, and the reason unknown fields
    are an error rather than tolerated extra data: a mistyped tag contradicts
    nothing, it simply never fires. `no_sec_source_reasons` routes the row to the
    POSITIVE arm, where without this sweep the reader would be told 'adr_ticker'
    is missing — a true statement about a row nobody meant to write as positive,
    and one that hides the single character actually at fault."""
    entry = _negative()
    entry["no_sec_source_reasons"] = entry.pop("no_sec_source_reason")

    with pytest.raises(DeepDiveError) as exc:
        _load_one(tmp_path, entry)

    msg = str(exc.value)
    assert "unknown field(s) ['no_sec_source_reasons']" in msg
    assert "adr_ticker" in msg  # the allowed set, so the fix is one line away


def test_unknown_field_on_a_negative_entry_raises(tmp_path):
    """The same sweep from the other arm: 'source' is not provenance this schema
    knows, and silently ignored data is data nobody maintains."""
    with pytest.raises(DeepDiveError, match=r"unknown field\(s\) \['source'\]"):
        _load_one(tmp_path, _negative(source="https://www.sec.gov/"))


def test_unknown_field_on_a_positive_entry_raises(tmp_path):
    entry = {
        "adr_ticker": "NVO",
        "cik": "0000353278",
        "form_type": "20-F",
        "from_type": "20-F",
    }
    with pytest.raises(DeepDiveError, match=r"\['from_type'\]"):
        _load_one(tmp_path, entry, ticker="NOVO-B.CO")


# ---------------------------------------------------------------------------
# Backwards compatibility of the schema extension.
# ---------------------------------------------------------------------------

_LEGACY_POSITIVE_ENTRIES = {
    "NOVO-B.CO": {"adr_ticker": "NVO", "cik": "0000353278", "form_type": "20-F"},
    "GOOGL": {"adr_ticker": "GOOGL", "cik": "0001652044", "form_type": "10-K"},
    "ASML": {"adr_ticker": "ASML", "cik": "0000937966", "form_type": "20-F"},
    "KO": {"adr_ticker": "KO", "cik": "0000021344", "form_type": "10-K"},
    "MSFT": {"adr_ticker": "MSFT", "cik": "0000789019", "form_type": "10-K"},
}


def test_the_five_pre_existing_positive_entries_load_unchanged():
    """Read against the real file: the extension was to be additive, and these
    five rows are the measurable meaning of that. Exact dict equality rather
    than a field spot-check — a provenance field appended to one of them changes
    what `_from_table_entry` sees and would slip past a looser assertion."""
    entries = load_adr_table()
    for ticker, expected in _LEGACY_POSITIVE_ENTRIES.items():
        assert entries[ticker] == expected


def test_a_table_of_only_legacy_entries_still_loads(tmp_path):
    """`verified_on` became mandatory on the NEGATIVE arm only. Pinned here on a
    file containing nothing else, so that the day someone promotes the field to
    a global requirement this fails — instead of the five untouched rows."""
    entries = load_adr_table(_write_table(tmp_path, _LEGACY_POSITIVE_ENTRIES))
    assert entries == _LEGACY_POSITIVE_ENTRIES


# ---------------------------------------------------------------------------
# Data probe: the real, hand-maintained data/adr_table.json.
#
# The guard against a wrong row being discovered by a paid run. `load_adr_table`
# is called for the validation, and the shapes are then re-asserted here
# INDEPENDENTLY of it — otherwise the probe would only ever report that the
# validator agrees with itself, and a loosened validator would carry the probe
# green along with it.
# ---------------------------------------------------------------------------

_POSITIVE_KEYS = {"adr_ticker", "cik", "form_type"}
_PROVENANCE_KEYS = {"note", "verified_on"}


def test_real_table_every_entry_satisfies_exactly_one_shape():
    entries = load_adr_table()
    assert entries, "the shipped table must not be empty"

    for ticker, entry in entries.items():
        keys = set(entry)
        if "no_sec_source_reason" in keys:
            assert keys == {"no_sec_source_reason"} | _PROVENANCE_KEYS, ticker
            assert entry["no_sec_source_reason"] in NO_SEC_SOURCE_REASONS, ticker
            assert entry["note"].strip(), ticker
            date.fromisoformat(entry["verified_on"])  # raises -> test fails
        else:
            assert _POSITIVE_KEYS <= keys, ticker
            assert keys <= _POSITIVE_KEYS | _PROVENANCE_KEYS, ticker
            assert entry["adr_ticker"], ticker
            assert len(entry["cik"]) == 10 and entry["cik"].isdigit(), ticker
            assert entry["form_type"] in {"10-K", "20-F"}, ticker
            if "verified_on" in keys:
                date.fromisoformat(entry["verified_on"])


def test_real_table_negative_entries_carry_no_filing_handle():
    """The ResolvedTicker biconditional, checked one layer earlier: a negative
    row that smuggled in a CIK would build an unconstructible verdict and trip
    an assertion mid-run instead of being caught at load time."""
    entries = load_adr_table()
    negatives = {t: e for t, e in entries.items() if "no_sec_source_reason" in e}
    assert negatives, "the negative arm has no row left — is it still exercised?"
    for ticker, entry in negatives.items():
        assert not (_POSITIVE_KEYS & set(entry)), ticker


# The six crosshits of the September run, pinned by VERDICT only — never by note
# prose and never by `verified_on`. Those two are meant to change when a row is
# re-checked, and pinning them would make honest maintenance turn the suite red.
# The verdict is the opposite case: ARGX.BR and WISE.L were measurably
# MISCLASSIFIED before this change (both file a 20-F and were being handed
# quant-only dossiers), so a row silently dropped or flipped back is exactly the
# regression this fence exists for. And if Adyen ever registers with the SEC,
# this failing is the intended, visible consequence — a pinned negative that
# nobody notices is the failure mode `verified_on` was introduced against.
_SEPTEMBER_CROSSHITS: dict[str, object] = {
    "ARGX.BR": {"adr_ticker": "ARGX", "cik": "0001697862", "form_type": "20-F"},
    "WISE.L": {"adr_ticker": "WSE", "cik": "0002099039", "form_type": "20-F"},
    "EDV.L": "not_sec_registrant",
    "ADYEN.AS": "not_sec_registrant",
    "ANTO.L": "not_sec_registrant",
    "G24.DE": "not_sec_registrant",
}


@pytest.mark.parametrize("ticker", sorted(_SEPTEMBER_CROSSHITS))
def test_real_table_pins_the_verdict_of_each_september_crosshit(ticker):
    entries = load_adr_table()
    assert ticker in entries, f"{ticker} lost its override row"
    entry = entries[ticker]
    expected = _SEPTEMBER_CROSSHITS[ticker]

    if isinstance(expected, str):
        assert entry.get("no_sec_source_reason") == expected
    else:
        assert {k: entry[k] for k in expected} == expected


# The two rows the identity-matcher change adds, deliberately kept apart from
# the six above because they are a different KIND of override. Those six correct
# a verdict the resolver reached on good input. These two correct the INPUT:
# yfinance answers for GLB.IR with 'Beacon Hill CBO III Ltd' and OpenFIGI
# answers for BT-A.L with 'BRITANNIA GROUP PLC'. In both cases the name check
# refused correctly — the counter-basket in test_issuer_normalisation.py pins
# that both pairs must stay unmatched — and no normalisation rule can or should
# repair a source that names the wrong company. So they are not matcher debt;
# without the row they would simply sit in the quant-only path forever.
#
# BT-A.L is `no_annual_form` and NOT a positive mapping. Until 2026-09-05 the
# row also had to compensate for a defect — `detect_annual_form` searched the
# whole `recent` window with no date cut and answered '20-F' off a filing from
# 2020. That defect is fixed; the function now returns None for BT. The row
# stays for the OTHER reason it exists: OpenFIGI names the wrong company, so
# without it BT-A.L falls into `unverifiable_identity`, i.e. "unchecked" rather
# than the hand-checked finding that it files nothing current.
_IDENTITY_OVERRIDE_ROWS = {
    "GLB.IR": "not_sec_registrant",
    "BT-A.L": "no_annual_form",
}


@pytest.mark.parametrize("ticker", sorted(_IDENTITY_OVERRIDE_ROWS))
def test_real_table_pins_the_verdict_of_each_identity_override_row(ticker):
    """Loading is asserted through `load_adr_table`, which validates: a row
    misspelt into a shape the loader rejects takes the whole table down, so
    "the row is there" and "the row is well-formed" are one statement."""
    entries = load_adr_table()
    assert ticker in entries, f"{ticker} lost its override row"
    assert entries[ticker]["no_sec_source_reason"] == _IDENTITY_OVERRIDE_ROWS[ticker]


class _ExplodingEUResolver:
    """Fails AT the forbidden call rather than at an `assert_not_called()` after
    it, so a precedence violation names itself instead of surfacing as a bare
    assertion further down."""

    def __call__(self, ticker):
        raise AssertionError(
            f"the EU resolver was consulted for {ticker}, which the override "
            f"table exists to prevent"
        )


@pytest.mark.parametrize("ticker", sorted(_IDENTITY_OVERRIDE_ROWS))
def test_an_identity_override_row_dominates_the_eu_resolver(ticker):
    """ORDERING, on the REAL table — the property that makes the row worth
    having. Both tickers are dotted, so without the override they would be
    routed straight into the OpenFIGI path whose answer is the very thing the
    row overrides. The EDGAR mock is asserted untouched for the same reason: a
    hand decision is a full answer, not a hint to be confirmed against the
    source it short-circuits."""
    edgar = MagicMock()
    resolver = ADRResolver(
        table=load_adr_table(), edgar=edgar, eu_resolver=_ExplodingEUResolver()
    )

    r = resolver.resolve(ticker)

    assert r.no_sec_source_reason == _IDENTITY_OVERRIDE_ROWS[ticker]
    assert r.has_filing_source is False
    assert r.cik is None and r.form_type is None
    assert "Override-Tabelle" in r.no_sec_source_note  # provenance for the reader
    edgar.get_cik.assert_not_called()
    edgar.detect_annual_form.assert_not_called()
