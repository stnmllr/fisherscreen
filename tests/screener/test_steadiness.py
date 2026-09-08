"""Tests for the steadiness axis.

Band edges are checked from both sides, because a threshold that is off by one
step moves titles across the crosshit gate silently.
"""

from app.screener.steadiness import (
    NEUTRAL_SCORE,
    NO_CONCEPT,
    SERIES_TOO_SHORT,
    Steadiness,
    compute_steadiness,
    down_years,
    margin_drawdown_pp,
    steadiness_from_record,
    window_years,
)
from app.services.edgar_annual_series_client import (
    AnnualSeriesRecord,
    ConceptCoverage,
)


def _series(years, values):
    return dict(zip(years, values))


def _flat(years, revenue=100.0, margin_pct=20.0, net_pct=10.0):
    """A perfectly steady issuer: constant revenue, constant margins."""
    rev = {y: revenue for y in years}
    return (
        rev,
        {y: revenue * margin_pct / 100 for y in years},
        {y: revenue * net_pct / 100 for y in years},
    )


# --- window ----------------------------------------------------------------


def test_the_window_takes_the_youngest_ten_of_a_longer_history():
    years = range(2010, 2026)  # 16 years
    rev, opi, ni = _flat(years)
    assert window_years(rev, opi, ni) == list(range(2016, 2026))


def test_a_gap_shortens_the_window_to_the_run_ending_at_the_newest_year():
    years = [2016, 2017, 2020, 2021, 2022, 2023, 2024, 2025]
    rev, opi, ni = _flat(years)
    assert window_years(rev, opi, ni) == [2020, 2021, 2022, 2023, 2024, 2025]


def test_only_years_present_in_all_three_series_count():
    rev, opi, ni = _flat(range(2016, 2026))
    del ni[2019]  # net income missing for one year
    assert window_years(rev, opi, ni) == [2020, 2021, 2022, 2023, 2024, 2025]


def test_a_year_without_revenue_truncates_rather_than_leaving_a_hole():
    """Margin and net margin are undefined at zero revenue. Skipping the year in
    place would splice two periods into one series."""
    rev, opi, ni = _flat(range(2016, 2026))
    rev[2020] = 0.0
    assert window_years(rev, opi, ni) == [2021, 2022, 2023, 2024, 2025]


# --- the sub-scores --------------------------------------------------------


def test_down_years_counts_falls_not_rises():
    assert down_years([1, 2, 3, 4]) == 0
    assert down_years([4, 3, 4, 3]) == 2


def test_a_margin_that_only_rises_has_no_drawdown():
    """The reason S2 is not a dispersion measure: this series has a high
    standard deviation and is the opposite of cyclical."""
    assert margin_drawdown_pp([5.0, 15.0, 25.0, 40.0]) == 0.0


def test_the_drawdown_is_measured_from_the_running_peak():
    assert margin_drawdown_pp([10.0, 40.0, 15.0, 35.0]) == 25.0


# --- band edges ------------------------------------------------------------


def _score_with(down=0, drawdown=0.0, worst_net=50.0, n_years=10):
    """Build a synthetic issuer hitting exactly the requested sub-values."""
    years = list(range(2026 - n_years, 2026))
    revenue = {}
    value = 100.0
    for i, y in enumerate(years):
        # place the requested number of falls at the front
        if 0 < i <= down:
            value -= 1.0
        else:
            value += 1.0
        revenue[y] = value
    # margin: start at the peak, drop once by `drawdown`, then hold
    margins = [40.0] + [40.0 - drawdown] * (len(years) - 1)
    operating = {y: revenue[y] * m / 100 for y, m in zip(years, margins)}
    # net margin: worst in the final year
    nets = [50.0] * (len(years) - 1) + [worst_net]
    net = {y: revenue[y] * n / 100 for y, n in zip(years, nets)}
    return compute_steadiness(revenue, operating, net)


def test_s1_band_edges():
    assert _score_with(down=0, drawdown=0.0).score == 5  # 5/5/5
    assert _score_with(down=1, drawdown=0.0).score == 4.67  # 4/5/5
    assert _score_with(down=2, drawdown=0.0).score == 4.33  # 3/5/5
    assert _score_with(down=3, drawdown=0.0).score == 4.0  # 2/5/5
    assert _score_with(down=4, drawdown=0.0).score == 3.67  # 1/5/5


def test_s2_band_edges_are_inclusive_on_the_better_side():
    assert _score_with(drawdown=5.0).score == 5  # <= 5 -> 5
    assert _score_with(drawdown=5.1).score == 4.67  # -> 4
    assert _score_with(drawdown=12.0).score == 4.67  # <= 12 -> 4
    assert _score_with(drawdown=12.1).score == 4.33  # -> 3
    assert _score_with(drawdown=24.0).score == 4.33
    assert _score_with(drawdown=48.1).score == 3.67  # -> 1


def test_s3_band_edges_put_a_loss_year_below_the_four():
    """S3 at zero is the definition, not a calibration: a loss year in the
    window rules out the 4."""
    assert _score_with(worst_net=0.0).score == 4.67  # 5/5/4
    assert _score_with(worst_net=-0.1).score == 4.33  # 5/5/3
    assert _score_with(worst_net=5.0).score == 5  # 5/5/5


# --- the window cap --------------------------------------------------------


def test_a_short_window_is_capped_at_four_even_when_perfect():
    """Seven good years do not equal two cleanly survived cycles."""
    perfect_long = _score_with(n_years=10)
    perfect_short = _score_with(n_years=8)

    assert perfect_long.score == 5
    assert perfect_short.score == 4
    assert perfect_short.assessable


def test_six_years_is_not_assessable():
    result = _score_with(n_years=6)
    assert result.reason == SERIES_TOO_SHORT
    assert result.score == NEUTRAL_SCORE


def test_seven_years_is_the_first_assessable_window():
    assert _score_with(n_years=7).assessable


# --- the two threes --------------------------------------------------------


def test_a_real_three_is_assessable_and_must_not_look_neutral():
    """The whole point of the reason field. This title measured a 3.0; it has to
    fail the gate. A title that could not be measured carries the same number and
    has to be skipped."""
    measured = _score_with(down=2, drawdown=24.0, worst_net=-4.0)  # 3/3/3

    assert measured.score == 3.0
    assert measured.assessable
    assert measured.reason is None


def test_an_unassessable_title_carries_the_same_number_and_a_reason():
    neutral = steadiness_from_record(None)

    assert neutral.score == NEUTRAL_SCORE
    assert neutral.score == 3.0  # identical to the measured three above
    assert not neutral.assessable
    assert neutral.reason == NO_CONCEPT


# --- the record adapter ----------------------------------------------------


def _coverage(years, values):
    return ConceptCoverage(
        concept="Revenues",
        unit="USD",
        years=tuple(years),
        values=tuple(values),
        contiguous=len(years),
        restatements=0,
        naive_fy_count=1,
    )


def test_a_record_without_usable_concepts_stays_neutral():
    record = AnnualSeriesRecord(
        cik="1", entity="Bank", concepts={}, reason="no_concept"
    )
    assert steadiness_from_record(record).reason == NO_CONCEPT


def test_a_usable_record_is_scored_from_its_three_series():
    years = list(range(2016, 2026))
    rev = [100.0 + i for i in range(10)]
    record = AnnualSeriesRecord(
        cik="1",
        entity="Steady Corp",
        concepts={
            "revenue": _coverage(years, rev),
            "operating_income": _coverage(years, [r * 0.2 for r in rev]),
            "net_income": _coverage(years, [r * 0.1 for r in rev]),
        },
        reason=None,
    )
    result = steadiness_from_record(record)

    assert result.assessable
    assert result.score == 5
    assert result.years == tuple(years)
    assert result.down_years == 0


def test_the_reported_sub_values_are_the_ones_the_score_used():
    """The acceptance in spec 10.3 reads these in plain text. If they were
    recomputed or rounded differently they would stop being evidence."""
    result = _score_with(down=2, drawdown=24.0, worst_net=-4.0)

    assert result.down_years == 2
    assert result.margin_drawdown_pp == 24.0
    assert result.worst_net_margin == -4.0


def test_steadiness_is_a_frozen_value():
    assert isinstance(_score_with(), Steadiness)


def test_the_banded_value_is_the_reported_value_not_a_noisier_one():
    """Found by the band-edge test: 40.0 - 35.000000000000004 is
    5.0000000000000036, which falls out of the "<= 5" band while still printing
    as 5.0. Rounding happens before banding, so the acceptance evidence in spec
    10.3 shows the number the score actually used."""
    result = _score_with(drawdown=5.0)

    assert result.margin_drawdown_pp == 5.0
    assert result.score == 5  # 5.0 pp is inside the top band, as printed
