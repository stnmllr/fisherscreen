from app.screener.dimensions import DIMENSIONS
from app.services import gemini_client


def test_dimensions_constant_has_five_elements():
    assert len(DIMENSIONS) == 5


def test_dimensions_are_the_expected_names():
    assert set(DIMENSIONS) == {"growth", "profitability", "management", "innovation", "resilience"}


def test_gemini_client_uses_same_dimensions_as_central_constant():
    assert list(gemini_client.DIMENSIONS) == list(DIMENSIONS)
