"""Provenance/instrumentation tests for scripts/build_universe.py.

Verifies that fetch_stoxx600() reports which source tier actually fired.
Fixtures-only: sub-fetchers are mocked so no network is hit.
"""

from unittest.mock import patch

import scripts.build_universe as bu


def test_fetch_stoxx600_reports_wikipedia_tier():
    with patch.object(bu, "_fetch_stoxx600_wikipedia", return_value=["ASML.AS", "SAP.DE"]):
        tickers, tier = bu.fetch_stoxx600()
    assert tier == "wikipedia"
    assert tickers == ["ASML.AS", "SAP.DE"]


def test_fetch_stoxx600_reports_ishares_b_tier():
    with patch.object(bu, "_fetch_stoxx600_wikipedia", return_value=[]), \
         patch.object(bu, "_fetch_stoxx600_ishares", return_value=(["A.DE", "B.PA"], "ishares-b")):
        tickers, tier = bu.fetch_stoxx600()
    assert tier == "ishares-b"
    assert tickers == ["A.DE", "B.PA"]


def test_fetch_stoxx600_reports_ishares_c_tier():
    with patch.object(bu, "_fetch_stoxx600_wikipedia", return_value=[]), \
         patch.object(bu, "_fetch_stoxx600_ishares", return_value=(["A.DE"], "ishares-c")):
        tickers, tier = bu.fetch_stoxx600()
    assert tier == "ishares-c"
    assert tickers == ["A.DE"]


def test_fetch_stoxx600_falls_back_to_hardcoded_tier():
    with patch.object(bu, "_fetch_stoxx600_wikipedia", return_value=[]), \
         patch.object(bu, "_fetch_stoxx600_ishares", return_value=None):
        tickers, tier = bu.fetch_stoxx600()
    assert tier == "hardcoded-fallback"
    assert tickers == list(bu.STOXX_FALLBACK)
