"""Live probe: the override table's claims about the SEC, checked against the SEC.

`data/adr_table.json` is a hand-maintained set of claims about the outside world
("ARGX is CIK 1697862 and files a 20-F", "Adyen is not an SEC registrant"). The
hermetic tests in `test_adr_table.py` prove those rows are well-formed and that
the resolver obeys them — they cannot prove the rows are still TRUE. Only the
SEC can say that, so this module is network-bound and marked `integration`
wholesale (see `pytestmark`): CI deselects it via -m "not integration", and it
is meant to be run by hand before a deep dive that would otherwise be steered by
a stale row.

The two entry shapes are NOT the same verification problem:

* A POSITIVE row is fully checkable. adr_ticker -> SEC company_tickers.json ->
  the stated cik, then detect_annual_form(cik) -> the stated form_type. Three
  claims, all provable, all checked below.

* A NEGATIVE row is not. "X is not an SEC registrant" cannot be established
  positively — there is no ticker to look up, and that absence IS the claim.
  Two partial checks are available instead. Where the note names the CIK of the
  depositary's F-6 shell, that CIK must still show no annual form (a 20-F
  turning up there is exactly how the claim would die). And for every negative
  row, `verified_on` must not have expired.

Everything is driven off the real `data/adr_table.json`, never off a fixture: a
row added next month is covered the moment it is added. A fixture would freeze
this probe at today's table and rot silently the first time the table grows.
"""

import re
from datetime import date

import pytest

from app.config import settings
from app.deepdive.adr_table import load_adr_table
from app.services.edgar_client import EdgarClientImpl

# Every test in this module talks to the SEC or judges a hand decision by the
# calendar. Neither belongs in a hermetic run, so the marker is module-wide
# rather than per test — a check added here later must not silently slip into CI.
pytestmark = pytest.mark.integration

# A negative verdict is a finding from ONE DAY, not a fact. "Adyen is not an SEC
# registrant" was true when someone checked; a registration can follow at any
# time without anything in this repo changing. So this threshold makes the probe
# go red on the CALENDAR rather than on a defect, which is normally the wrong
# thing to build. It is right here for two reasons: the claim itself has a shelf
# life, and this module never runs in CI — an expired row blocks no build and no
# merge, it only tells the person about to spend a paid deep dive that the hand
# decision steering it is half a year old. 180 days mirrors the horizon the
# codebase already uses for ADR mappings (settings.adr_cache_ttl_days).
_NEGATIVE_VERDICT_MAX_AGE_DAYS = 180

# The depositary's F-6 shell CIK as the notes spell it out: "(CIK 0002139860)",
# "(CIK 1788707)". Digits required, so a note saying "kein CIK in
# company_tickers.json" correctly yields no match and the row is skipped rather
# than checked against a CIK that was never claimed.
_CIK_IN_NOTE_RE = re.compile(r"\bCIK\s*(\d{4,10})\b")

_ENTRIES = load_adr_table()
# Both lists non-empty is a hermetic property and is asserted as such in
# test_adr_table.py; repeating it here would only add a second network-gated
# copy of a check that already runs everywhere.
_POSITIVE_ROWS = sorted(
    t for t, e in _ENTRIES.items() if "no_sec_source_reason" not in e
)
_NEGATIVE_ROWS = sorted(t for t, e in _ENTRIES.items() if "no_sec_source_reason" in e)

_REVERIFY = (
    "Re-verify the row in data/adr_table.json against the SEC and bump its "
    "'verified_on' — do not patch this test."
)


@pytest.fixture(scope="module")
def edgar() -> EdgarClientImpl:
    """One real client for the whole module.

    Module-scoped on purpose: `EdgarClientImpl` caches company_tickers.json per
    instance and paces itself with a per-instance rate limiter, so a client per
    test would refetch ~1 MB each time and defeat the shared pacing the SEC
    fair-access policy expects.
    """
    if not settings.edgar_user_agent:
        pytest.skip(
            "FISHERSCREEN_EDGAR_USER_AGENT is not set — the SEC requires an "
            "identifying User-Agent, so this probe cannot run politely"
        )
    client = EdgarClientImpl(
        settings.edgar_user_agent,
        max_requests_per_second=settings.edgar_max_requests_per_second,
    )
    # Prime the ticker map through the RAISING loader instead of letting
    # `get_cik` populate it: get_cik swallows a fetch failure and returns None,
    # which has the same shape as "this ticker is not registered". Under a
    # network problem every positive row would then report as stale — a failure
    # must stay distinguishable from an empty result.
    client._ticker_map = client._load_ticker_map()
    return client


@pytest.mark.parametrize("ticker", _POSITIVE_ROWS)
def test_positive_row_adr_ticker_still_maps_to_the_stated_cik(ticker, edgar):
    """Claim 1 and 2 of a positive row: the ADR ticker is still in the SEC's own
    ticker->CIK map, and it still points at the CIK the table names.

    A vanished ticker and a changed CIK are different accidents (a delisting vs.
    a re-registration or a plain typo), so they are asserted separately."""
    entry = _ENTRIES[ticker]
    adr = entry["adr_ticker"]

    live = edgar.get_cik(adr)

    assert live is not None, (
        f"{ticker}: adr_ticker '{adr}' is no longer in SEC company_tickers.json "
        f"— the ADR line may have been delisted or renamed. {_REVERIFY}"
    )
    assert live.zfill(10) == entry["cik"], (
        f"{ticker}: adr_ticker '{adr}' now resolves to CIK {live.zfill(10)}, but "
        f"the table claims {entry['cik']}. {_REVERIFY}"
    )


@pytest.mark.parametrize("ticker", _POSITIVE_ROWS)
def test_positive_row_cik_still_files_the_stated_annual_form(ticker, edgar):
    """Claim 3 of a positive row: the filer still uses the annual form the table
    names. A 20-F filer that becomes a US domestic filer switches to 10-K, and a
    dossier built on the wrong form fetches the wrong document — quietly, since
    both are 'an annual filing'.

    `detect_annual_form` raises DataSourceError on a fetch failure and returns
    None only for a filer with genuinely no annual form, so a red here is a
    statement about the row, not about the network."""
    entry = _ENTRIES[ticker]

    live = edgar.detect_annual_form(entry["cik"])

    assert live == entry["form_type"], (
        f"{ticker}: CIK {entry['cik']} now files "
        f"{live if live else 'no annual form at all'}, but the table claims "
        f"{entry['form_type']}. {_REVERIFY}"
    )


@pytest.mark.parametrize("ticker", _NEGATIVE_ROWS)
def test_negative_row_named_cik_still_shows_no_annual_form(ticker, edgar):
    """The one half of a `not_sec_registrant` row that CAN be checked positively.

    "Not an SEC registrant" is unprovable by construction — there is no ticker
    to look up, which is the claim. But where the note names the CIK behind the
    depositary's F-6 shell, the falsifier is checkable: if an annual form ever
    appears under that CIK, the issuer has registered and the row is wrong.

    THE CHECK IS REASON-SPECIFIC, and was not always: it reads a named CIK as an
    F-6 shell and an annual form under it as proof of registration. Both
    readings only hold for `not_sec_registrant`. A `no_annual_form` row makes a
    different claim — the issuer IS registered, it just files nothing current —
    and its note names its OWN CIK, under which `detect_annual_form` legitimately
    finds something. Running the registrant check against it asked a question the
    row never answered and reported a correct row as obsolete (BT-A.L, the first
    negative row of that kind, 2026-09-04). One check under two claims is the
    same conflation the census buckets were split for.

    Two kinds of row are therefore SKIPPED, loudly rather than silently, and
    both keep the staleness check below as their only guarantee:

    * a row whose note names no CIK — nothing to look up;
    * a `no_annual_form` row — the claim is about RECENCY, and
      `detect_annual_form` searches the whole `recent` window without a date
      cut, so it cannot distinguish "filed a 20-F six years ago and stopped"
      from "files a 20-F". Whether that function needs a recency cut is the open
      question the BT-A.L note itself raises; until it has one, no automated
      check here can falsify the claim."""
    entry = _ENTRIES[ticker]
    reason = entry["no_sec_source_reason"]
    if reason != "not_sec_registrant":
        pytest.skip(
            f"{ticker}: a '{reason}' row does not claim the issuer is "
            f"unregistered, so an annual form under its CIK falsifies nothing — "
            f"this row rests on the staleness check alone"
        )
    match = _CIK_IN_NOTE_RE.search(entry["note"])
    if match is None:
        pytest.skip(
            f"{ticker}: the note names no CIK, so there is nothing to look up — "
            f"'is not a registrant' stays unprovable and this row rests on the "
            f"staleness check alone"
        )
    cik = match.group(1).zfill(10)

    live = edgar.detect_annual_form(cik)

    assert live is None, (
        f"{ticker}: CIK {cik} (named in the note as the ADR/F-6 shell) now files "
        f"a {live} — the issuer appears to have become an SEC registrant, so the "
        f"negative verdict is obsolete and the row should become a positive "
        f"mapping. {_REVERIFY}"
    )


@pytest.mark.parametrize("ticker", _NEGATIVE_ROWS)
def test_negative_row_verdict_has_not_expired(ticker):
    """The other half: age. Since the claim cannot be re-proved automatically,
    the only remaining guarantee is that a human looked recently enough. Red
    here means 'nobody has checked this in half a year', not 'this is wrong'."""
    entry = _ENTRIES[ticker]
    verified_on = date.fromisoformat(entry["verified_on"])
    age_days = (date.today() - verified_on).days

    assert age_days <= _NEGATIVE_VERDICT_MAX_AGE_DAYS, (
        f"{ticker}: the '{entry['no_sec_source_reason']}' verdict was last "
        f"verified on {verified_on} — {age_days} days ago, over the "
        f"{_NEGATIVE_VERDICT_MAX_AGE_DAYS}-day shelf life of a hand-checked "
        f"negative. This is not a defect: re-check the issuer at "
        f"https://www.sec.gov/cgi-bin/browse-edgar?company= and bump "
        f"'verified_on', or convert the row to a positive mapping if it has "
        f"registered since."
    )
