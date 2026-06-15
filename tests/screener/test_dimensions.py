from app.models.screener_record import ScreenerRecord
from app.screener.dimensions import (
    DIMENSIONS,
    MERIT_DIMENSIONS,
    is_crosshit,
    qualifying_dimensions,
)
from app.services import gemini_client


def test_dimensions_constant_has_five_elements():
    assert len(DIMENSIONS) == 5


def test_dimensions_are_the_expected_names():
    assert set(DIMENSIONS) == {"growth", "profitability", "management", "innovation", "resilience"}


def test_merit_dimensions_are_the_three_active_axes():
    assert MERIT_DIMENSIONS == ("growth", "profitability", "resilience")


def test_management_and_innovation_excluded_from_merit():
    assert "management" not in MERIT_DIMENSIONS
    assert "innovation" not in MERIT_DIMENSIONS


def test_gemini_client_uses_same_dimensions_as_central_constant():
    assert list(gemini_client.DIMENSIONS) == list(DIMENSIONS)


def _rec(**dims):
    return ScreenerRecord(ticker="X", gemini_dimensions=dims or None)


def test_qualifying_dimensions_filters_by_threshold():
    rec = _rec(growth=4, profitability=5, resilience=3)
    assert set(qualifying_dimensions(rec, 4.0)) == {"growth", "profitability"}


def test_qualifying_dimensions_ignores_management_and_innovation():
    # Both sentinel axes are maxed, but neither counts as merit.
    rec = _rec(growth=4, profitability=3, management=5, innovation=5, resilience=3)
    assert set(qualifying_dimensions(rec, 4.0)) == {"growth"}


def test_is_crosshit_needs_min_dimensions():
    assert is_crosshit(_rec(growth=4, profitability=4), 4.0, 2) is True
    assert is_crosshit(_rec(growth=4, resilience=3), 4.0, 2) is False


def test_management_innovation_high_does_not_make_crosshit():
    # growth=4 is the only merit hit; management/innovation=5 must not inflate it.
    rec = _rec(growth=4, profitability=3, management=5, innovation=5, resilience=3)
    assert is_crosshit(rec, 4.0, 2) is False


def test_is_crosshit_false_when_no_dimensions():
    assert is_crosshit(_rec(), 4.0, 2) is False
