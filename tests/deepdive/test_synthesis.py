from unittest.mock import MagicMock

import pytest

from app.deepdive.synthesis import run_synthesis
from app.errors import GeminiError
from app.models.deep_dive_record import PointInTimeQuant, QuantSnapshot


def _qs():
    return QuantSnapshot(point_in_time=PointInTimeQuant(ticker="NOVO-B.CO"))


def _good_points():
    pts = []
    for n in range(1, 16):
        pts.append({"number": n, "title": f"P{n}", "rating": 4,
                    "confidence": "🟢", "reasoning": "Solide Begründung.",
                    "sources": ["20-F §5"]})
    return {"points": pts}


def test_returns_15_fisher_points():
    syn = MagicMock()
    syn.synthesize.return_value = _good_points()
    pts = run_synthesis(
        ticker="NOVO-B.CO", form_type="20-F",
        sections={"20-F_item5": "rev"}, quant=_qs(),
        synthesizer=syn, max_input_tokens=200000)
    assert len(pts) == 15
    assert pts[0].number == 1


def test_hallucinated_section_downgraded_to_inference():
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["20-F §99"]  # section never sent
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["Inferenz"]
    assert pts[0].confidence == "🟡"  # capped by model validator


def test_inference_only_caps_confidence():
    syn = MagicMock()
    data = _good_points()
    data["points"][1]["sources"] = ["Inferenz"]
    data["points"][1]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[1].confidence == "🟡"


def test_wrong_point_count_raises():
    syn = MagicMock()
    bad = {"points": _good_points()["points"][:14]}
    syn.synthesize.return_value = bad
    with pytest.raises(GeminiError, match="expected 15"):
        run_synthesis(ticker="X", form_type="20-F",
                      sections={"20-F_item5": "x"}, quant=_qs(),
                      synthesizer=syn, max_input_tokens=200000)


def test_gemini_error_propagates():
    syn = MagicMock()
    syn.synthesize.side_effect = GeminiError("prompt too large")
    with pytest.raises(GeminiError, match="too large"):
        run_synthesis(ticker="X", form_type="20-F",
                      sections={"20-F_item5": "x"}, quant=_qs(),
                      synthesizer=syn, max_input_tokens=10)


def test_mixed_sources_with_one_hallucination_collapses_all():
    syn = MagicMock()
    data = _good_points()
    data["points"][2]["sources"] = ["20-F §5", "20-F §99", "yfinance, 5J"]
    data["points"][2]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[2].sources == ["Inferenz"]
    assert pts[2].confidence == "🟡"


def test_points_14_15_confidence_code_enforced_red():
    syn = MagicMock()
    data = _good_points()  # all confidence "🟢", sources ["20-F §5"]
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    by_num = {p.number: p for p in pts}
    assert by_num[14].confidence == "🔴"
    assert by_num[15].confidence == "🔴"
    assert by_num[1].confidence == "🟢"  # others untouched
