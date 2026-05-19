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


def test_user_prompt_renders_citeable_section_headers():
    import re

    from app.deepdive.synthesis import _build_user_prompt

    prompt = _build_user_prompt(
        "X", "20-F", {"20-F_item5": "rev", "20-F_item4": "biz"}, _qs())
    assert re.search(r"### 20-F §5", prompt)
    assert re.search(r"### 20-F §4", prompt)
    assert not re.search(r"### 20-F_item", prompt)


def test_section_label_handles_10k():
    from app.deepdive.synthesis import _section_label

    assert _section_label("10-K_item7") == "10-K §7"
    assert _section_label("no_item_marker") == "no §_marker"
    assert _section_label("plainkey") == "plainkey"


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


# --- 1.5.x: no-space sub-item cite parsing (`20-F §4B`) -------------------
# Root cause: _SECTION_CITE_RE captured (\w+) so the no-space sub-item form
# "20-F §4B" yielded item "4B" -> key "20-F_item4B", never matching the
# numeric sent keys -> every such point falsely collapsed to ["Inferenz"].
# These assert the REAL _validate_sources behaviour directly.

_SENT = {"20-F_item4", "20-F_item5", "20-F_item18"}


def test_no_space_subitem_cite_not_collapsed_red_driver():
    """RED-driver: '20-F §4B' (item 4 IS sent) must NOT collapse; the exact
    cite string is preserved. FAILS on \\w+ (captures '4B'), PASSES on \\d+."""
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §4B"], "20-F", _SENT)
    assert out == ["20-F §4B"]


def test_multiple_no_space_subitems_not_collapsed():
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §5C", "20-F §4B"], "20-F", _SENT)
    assert out == ["20-F §5C", "20-F §4B"]


def test_space_subitem_cite_not_collapsed_regression_guard():
    """Already worked with \\w+; must keep working with \\d+ ('§<num> <letter>')."""
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §5 D"], "20-F", _SENT)
    assert out == ["20-F §5 D"]


def test_plain_sent_cite_not_collapsed_regression_guard():
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §4"], "20-F", _SENT)
    assert out == ["20-F §4"]


def test_subitem_cite_of_unsent_item_still_collapses():
    """The fix must not weaken real hallucination catching: item 6 NOT sent."""
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §6A"], "20-F", _SENT)
    assert out == ["Inferenz"]


def test_plain_unsent_cite_still_collapses():
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §15"], "20-F", _SENT)
    assert out == ["Inferenz"]


def test_mixed_sent_and_unsent_subitems_collapses():
    """Item 4 sent, item 7 not -> any not-sent cite collapses (unchanged rule)."""
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §4B", "20-F §7B"], "20-F", _SENT)
    assert out == ["Inferenz"]


def test_non_section_filing_string_still_hits_not_validatable(caplog):
    """A filing-ish string without § still has no regex match -> warning path
    unchanged with \\d+ (returned sources unchanged, no collapse)."""
    import logging

    from app.deepdive.synthesis import _validate_sources

    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        out = _validate_sources(["20-F item5"], "20-F", _SENT)
    assert out == ["20-F item5"]
    assert "not validatable" in caplog.text
