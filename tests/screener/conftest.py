import pytest

import app.screener.compose as compose
import app.screener.filters as filters


@pytest.fixture(autouse=True)
def _calibrated_value_floor(monkeypatch):
    """Gate-invoking tests run with a deterministic value floor; the production
    constant stays a fail-loud sentinel until the calibration gate sets it. A test
    that needs the sentinel sets it back to None explicitly."""
    monkeypatch.setattr(filters, "MIN_AVG_DAILY_VALUE_EUR", 1_000_000.0)


@pytest.fixture(autouse=True)
def _dormant_gross_margin_relative_arm(monkeypatch):
    """Keep the Punkt-2 relative rescue arm dormant in tests unless a test sets it
    explicitly. Mirrors _calibrated_value_floor: production stays sentinel until
    Phase E commits the calibrated table. A test exercising rescue passes
    sector_table/relative_k directly to apply_basis_filters or
    passes_gross_margin_filter — the runner path is also guarded via compose."""
    monkeypatch.setattr(filters, "GROSS_MARGIN_RELATIVE_K", None)
    monkeypatch.setattr(compose, "build_sector_median_table", lambda: None)
    monkeypatch.setattr("app.screener.runner.build_sector_median_table", lambda: None)
