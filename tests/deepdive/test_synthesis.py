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


def _points_with_ratings(ratings):
    """ratings: list of 15 ints. Build a valid 15-point synthesizer return."""
    pts = []
    for i, n in enumerate(range(1, 16)):
        pts.append({"number": n, "title": f"P{n}", "rating": ratings[i],
                    "confidence": "🟢", "reasoning": "Solide Begründung.",
                    "sources": ["20-F §5"]})
    return {"points": pts}


def test_user_prompt_contains_valuation_block_before_filing_sections():
    from app.deepdive.synthesis import _build_user_prompt

    prompt = _build_user_prompt(
        "X", "20-F", {"20-F_item5": "rev"}, _qs())
    heading = ("## Bewertung & Kapitalstruktur "
               "(TTM-Stand, ohne historischen 5J-Vergleich)")
    assert heading in prompt
    assert prompt.index(heading) > prompt.index("Quant-Snapshot (JSON)")
    assert prompt.index(heading) < prompt.index("Filing-Sections:")


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


def test_model_violating_point_maps_to_geminierror():
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["reasoning"] = " ".join(["w"] * 71)  # exceeds 70-word cap
    syn.synthesize.return_value = data
    with pytest.raises(GeminiError, match="violates the contract"):
        run_synthesis(
            ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
            quant=_qs(), synthesizer=syn, max_input_tokens=200000)


def test_star_inflation_logs_warning(caplog):
    import logging
    syn = MagicMock()
    syn.synthesize.return_value = _points_with_ratings([5] * 6 + [4] * 9)
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        run_synthesis(
            ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
            quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert "sterne-inflation" in caplog.text
    assert "6/15" in caplog.text


def test_no_weak_points_logs_warning(caplog):
    import logging
    syn = MagicMock()
    syn.synthesize.return_value = _points_with_ratings([4] * 15)
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        run_synthesis(
            ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
            quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert "keine schwachen punkte" in caplog.text


def test_balanced_distribution_no_distribution_warning(caplog):
    import logging
    syn = MagicMock()
    syn.synthesize.return_value = _points_with_ratings(
        [5] * 4 + [2] * 3 + [4] * 8)
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        run_synthesis(
            ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
            quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert "sterne-inflation" not in caplog.text
    assert "keine schwachen punkte" not in caplog.text


def test_system_prompt_contains_hardening_anchors():
    from app.deepdive.synthesis import _SYSTEM_PROMPT

    for anchor in (
        "STERNE-RUBRIK",
        "VERTEILUNG",
        "ABGRENZUNG",
        "BEAR-CASE-PFLICHT",
        "WETTBEWERB",
        "[Marktkontext]",
        "Erfinde keine Konkurrenznamen",
        "🟢 NUR",
        '"points":[{"number":int',
    ):
        assert anchor in _SYSTEM_PROMPT, f"missing anchor: {anchor!r}"


def test_misformatted_filing_cite_logs_warning(caplog):
    import logging
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["20-F Item 5"]  # no § — un-validatable
    syn.synthesize.return_value = data
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        run_synthesis(
            ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
            quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert "not validatable" in caplog.text
