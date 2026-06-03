"""Unit tests for scripts/build_universe.py pure ticker-normalisation helpers.

Fixtures-only: no network, no HTTP. Only the pure string functions are exercised.
"""

from scripts.build_universe import _apply_country_suffix, _normalise_us_ticker


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
