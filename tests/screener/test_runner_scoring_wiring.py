import inspect
from app.screener.runner import run_screener


def test_run_screener_takes_revenue_cache_not_gemini():
    params = inspect.signature(run_screener).parameters
    assert "revenue_cache" in params
    assert "gemini" not in params
