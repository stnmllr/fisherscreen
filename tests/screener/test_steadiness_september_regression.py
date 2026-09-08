"""Acceptance case for the steadiness axis: the 24 crosshits of September 2026.

This is the measure of record for the dimension (spec 10.2). The universe-wide
share of titles scoring >= 4.0 was considered as a criterion and rejected — the
median title is a 3/3/3, and that is correct; forcing a share would have pushed
the S3 edge negative and handed a 4 for "steadiness" to a title with a loss year.

The fixture holds the real annual series as extracted from EDGAR on 2026-09-08,
so the test exercises the actual bands, the mean and the window cap against real
data without touching the network. Regenerate it only when the extraction
changes — and then re-read the numbers rather than pasting them.
"""

import json
from pathlib import Path

from app.screener.steadiness import (
    NO_CONCEPT,
    SERIES_TOO_SHORT,
    compute_steadiness,
)

_FIXTURE = Path(__file__).parent / "september_2026_annual_series.json"

# Spec 10.2. Scores are pinned; the lists are what the test iterates, so naming
# a ninth title later does not turn this red on its own.
EXPECTED_SCORES = {
    "NEM": 1.33,
    "MU": 1.33,
    "ABNB": 2.0,
    "HL": 2.33,
    "TER": 2.67,
    "PLTR": 2.67,
    "TPL": 3.67,
    "META": 3.67,
    "NVDA": 4.0,
    "TDG": 4.0,
    "GOOG": 4.67,
    "GOOGL": 4.67,
    "MEDP": 4.67,
    "MNST": 4.67,
    "FAST": 5.0,
    "FICO": 5.0,
}
MUST_FALL = ("HL", "NEM", "MU", "TER", "META", "TPL", "PLTR", "ABNB")
MUST_STAY = ("FICO", "FAST", "MEDP", "GOOG", "GOOGL", "MNST", "TDG", "NVDA")
NO_SEC = ("EDV.L", "ANTO.L", "ARGX.BR", "ADYEN.AS", "G24.DE", "WISE.L")
TOO_SHORT = ("RGLD", "SNDK")

THRESHOLD = 4.0


def _fixture():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _steadiness(entry):
    series = {
        key: dict(zip(payload["years"], payload["values"]))
        for key, payload in entry["series"].items()
    }
    return compute_steadiness(
        series["revenue"], series["operating_income"], series["net_income"]
    )


def _assessed(data):
    """Having series is not the same as being assessable: RGLD and SNDK carry all
    three concepts and still fall to the seven-year window rule. The client says
    "concepts found", the window rule decides."""
    out = {}
    for ticker, entry in data.items():
        if "series" not in entry:
            continue
        result = _steadiness(entry)
        if result.assessable:
            out[ticker] = result
    return out


def test_every_assessed_title_scores_what_the_spec_says():
    actual = {t: r.score for t, r in _assessed(_fixture()).items()}
    assert actual == EXPECTED_SCORES


def test_the_cyclicals_fall():
    """Not narrowly and not on one sub-score: NEM and MU land at 1.33 with
    2/1/1. Their operating margin runs from -17.2% to 50.0% and -37.0% to
    49.3% respectively."""
    data = _fixture()
    for ticker in MUST_FALL:
        result = _steadiness(data[ticker])
        assert result.assessable, ticker
        assert result.score < THRESHOLD, f"{ticker} scored {result.score}"


def test_the_keepers_stay():
    data = _fixture()
    for ticker in MUST_STAY:
        result = _steadiness(data[ticker])
        assert result.assessable, ticker
        assert result.score >= THRESHOLD, f"{ticker} scored {result.score}"


def test_nvda_and_tdg_sit_exactly_on_the_edge():
    """Decided, not accidental: one more weak margin year tips either of them.
    For a semiconductor title that is the expected behaviour, not a defect."""
    data = _fixture()
    assert _steadiness(data["NVDA"]).score == THRESHOLD
    assert _steadiness(data["TDG"]).score == THRESHOLD


def test_meta_falls_on_the_margin_break_not_on_revenue():
    """Operating margin 39.6% -> 24.8% across 2021-22. At a 15pp S2 edge META
    would have stayed; 12 is the chosen edge, and this is what it buys."""
    result = _steadiness(_fixture()["META"])

    assert result.down_years == 1
    assert result.margin_drawdown_pp == 24.9
    assert result.score == 3.67


def test_tpl_falls_although_its_margin_never_leaves_the_seventies():
    """The eight-year window caps it at 4 anyway, and two down years plus a
    15.1pp fall put it below. Its margin runs 86.9% -> 71.8%, which is the case
    the relative-drawdown ticket is about."""
    result = _steadiness(_fixture()["TPL"])

    assert len(result.years) == 8
    assert result.score == 3.67


def test_the_non_sec_registrants_have_no_series_at_all():
    data = _fixture()
    for ticker in NO_SEC:
        assert data[ticker]["cik"] is None, ticker


def test_the_short_histories_are_not_assessable():
    data = _fixture()
    for ticker in TOO_SHORT:
        entry = data[ticker]
        if "series" not in entry:
            assert entry["reason"] in (NO_CONCEPT, "missing"), ticker
            continue
        # concepts present, window too short — the layering, not a data gap
        assert _steadiness(entry).reason == SERIES_TOO_SHORT, ticker


def test_sixteen_of_the_twentyfour_are_assessed():
    """PLTR (8y) and ABNB (7y) are assessed, not neutral — the graded rule sets
    the bar at seven years. Only RGLD (5y) and SNDK (4y) are too short."""
    assessed = _assessed(_fixture())
    assert len(assessed) == 16
    assert "PLTR" in assessed and "ABNB" in assessed
    assert "RGLD" not in assessed and "SNDK" not in assessed
