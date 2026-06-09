from app.models.screener_record import ScreenerRecord
from app.screener.dimensions import DIMENSIONS, is_crosshit, qualifying_dimensions
from app.services import gemini_client


def test_dimensions_constant_has_five_elements():
    assert len(DIMENSIONS) == 5


def test_dimensions_are_the_expected_names():
    assert set(DIMENSIONS) == {"growth", "profitability", "management", "innovation", "resilience"}


def test_gemini_client_uses_same_dimensions_as_central_constant():
    assert list(gemini_client.DIMENSIONS) == list(DIMENSIONS)


def _rec(**dims):
    return ScreenerRecord(ticker="X", gemini_dimensions=dims or None)


def test_qualifying_dimensions_filters_by_threshold():
    rec = _rec(growth=4, profitability=5, management=3)
    assert set(qualifying_dimensions(rec, 4.0)) == {"growth", "profitability"}


def test_is_crosshit_needs_min_dimensions():
    assert is_crosshit(_rec(growth=4, profitability=4), 4.0, 2) is True
    assert is_crosshit(_rec(growth=4, management=3), 4.0, 2) is False


def test_is_crosshit_false_when_no_dimensions():
    assert is_crosshit(_rec(), 4.0, 2) is False
