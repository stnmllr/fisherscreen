import pytest

import app.screener.filters as filters


@pytest.fixture(autouse=True)
def _calibrated_value_floor(monkeypatch):
    """Gate-invoking tests run with a deterministic value floor; the production
    constant stays a fail-loud sentinel until the calibration gate sets it. A test
    that needs the sentinel sets it back to None explicitly."""
    monkeypatch.setattr(filters, "MIN_AVG_DAILY_VALUE_EUR", 1_000_000.0)
