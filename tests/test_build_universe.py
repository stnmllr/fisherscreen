"""Unit tests for scripts/build_universe.py pure ticker-normalisation helpers.

Fixtures-only: no network, no HTTP. Only the pure string functions are exercised.
"""

import pytest

from scripts.build_universe import (
    _apply_country_suffix,
    _normalise_class_suffix,
    _normalise_us_ticker,
)


# --- ITEM 1: trailing-dot fix on LSE tickers --------------------------------


def test_lse_trailing_dot_ba_is_stripped_before_suffix():
    # Wikipedia delivers "BA." for BAE Systems; "BA." + ".L" must not yield "BA..L".
    assert _apply_country_suffix("BA.", "United Kingdom") == "BA.L"


def test_lse_trailing_dot_rr_is_stripped_before_suffix():
    assert _apply_country_suffix("RR.", "United Kingdom") == "RR.L"


def test_lse_trailing_dot_sn_is_stripped_before_suffix():
    assert _apply_country_suffix("SN.", "United Kingdom") == "SN.L"


def test_lse_no_trailing_dot_baseline_unchanged():
    # Plain ticker without trailing dot stays exactly as before the fix.
    assert _apply_country_suffix("AAL", "United Kingdom") == "AAL.L"


# --- ITEM 1: no over-reach (internal dots must survive) ---------------------


def test_us_class_share_internal_dot_not_mangled_by_trailing_strip():
    # A legit class share: BRK.B -> BRK-B (internal dot becomes dash via the US
    # normaliser, untouched by the trailing-dot strip in _apply_country_suffix).
    assert _normalise_us_ticker("BRK.B") == "BRK-B"


def test_internal_dot_base_keeps_internal_dot_only_trailing_stripped():
    # "BT.A" has an INTERNAL dot (not trailing) -> it must survive; only a
    # trailing dot would be stripped. Documents that internal-dot multi-class is
    # a separate, out-of-scope residual; pins current trailing-only behaviour.
    assert _apply_country_suffix("BT.A", "United Kingdom") == "BT.A.L"


# --- Nordic class-share normalisation (trailing lowercase a/b/c) -------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ERICb", "ERIC-B"),
        ("ATCOa", "ATCO-A"),
        ("ELUXb", "ELUX-B"),
        ("SKFb", "SKF-B"),
        ("TEL2b", "TEL2-B"),  # digit in base is allowed
    ],
)
def test_class_suffix_is_normalised(raw, expected):
    assert _normalise_class_suffix(raw) == expected


@pytest.mark.parametrize(
    "ticker",
    [
        "BRK-B",   # already hyphenated -> not [A-Z0-9]{2,}[abc]$
        "AAPL",    # plain US ticker, no trailing lowercase
        "NESN",    # plain EU ticker
        "HMB",     # all-caps concatenated class form -> deliberately NOT split
        "MSFT",
        "NOVO-B",  # already hyphenated
        "A",       # too short
        "Ab",      # base length 1 -> must NOT transform
        "ABCd",    # trailing 'd' not in a/b/c
        "",        # empty -> unchanged
    ],
)
def test_non_class_suffix_unchanged(ticker):
    assert _normalise_class_suffix(ticker) == ticker


def test_apply_country_suffix_normalises_nordic_class_share():
    # ERICb (Sweden) must resolve to the yfinance form ERIC-B.ST.
    assert _apply_country_suffix("ERICb", "Sweden") == "ERIC-B.ST"


def test_apply_country_suffix_leaves_allcaps_form_untouched():
    # HMB is all-caps concatenated: ambiguous, deliberately NOT split here
    # (handled at the data level instead). Documents the limitation.
    assert _apply_country_suffix("HMB", "Sweden") == "HMB.ST"
