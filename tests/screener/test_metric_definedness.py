# tests/screener/test_metric_definedness.py
from app.models.screener_record import ScreenerRecord
from app.screener.metric_definedness import is_gross_margin_undefined_info_only


def _rec(gm):
    return ScreenerRecord(ticker="T", gross_margin=gm)


def test_none_margin_is_undefined():
    assert is_gross_margin_undefined_info_only(_rec(None)) is True


def test_zero_margin_is_undefined():
    assert is_gross_margin_undefined_info_only(_rec(0.0)) is True


def test_negative_margin_is_undefined_info_only():
    # .info-only default cannot distinguish structural-undefined from real-negative;
    # Gate-A A1 verifies the gm<=0 basket holds no real industrial negative-marger.
    assert is_gross_margin_undefined_info_only(_rec(-0.05)) is True


def test_positive_margin_is_defined():
    assert is_gross_margin_undefined_info_only(_rec(0.20)) is False
