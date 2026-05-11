from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_yfinance():
    return MagicMock()


@pytest.fixture
def mock_edgar():
    return MagicMock()


@pytest.fixture
def mock_gemini():
    return MagicMock()


@pytest.fixture
def mock_firestore():
    return MagicMock()
