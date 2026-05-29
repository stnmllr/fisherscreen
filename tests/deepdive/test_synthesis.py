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
    # Real ITEM-5 body so the §5 cites pass the Stage-3 body-heading check and
    # point 1 keeps its model confidence (the focus is the 14/15 code-cap).
    pts = run_synthesis(
        ticker="X", form_type="20-F",
        sections={"20-F_item5": "ITEM 5 OPERATING AND FINANCIAL REVIEW. We review results."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    by_num = {p.number: p for p in pts}
    assert by_num[14].confidence == "🔴"
    assert by_num[15].confidence == "🔴"
    assert by_num[1].confidence == "🟢"  # others untouched


def test_model_violating_point_maps_to_geminierror():
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["rating"] = 6  # out of range (1..5) -> hard contract violation
    syn.synthesize.return_value = data
    with pytest.raises(GeminiError, match="violates the contract"):
        run_synthesis(
            ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
            quant=_qs(), synthesizer=syn, max_input_tokens=200000)


def test_run_synthesis_no_exception_on_long_reasoning():
    """Integration-level bug repro for Punkt 2b: when one of the 15 points has
    a reasoning longer than 70 words, run_synthesis must NOT raise GeminiError
    (previous behavior killed the whole dossier). Instead, the overshooting
    reasoning is truncated by the FisherPoint validator and the run delivers
    all 15 points."""
    syn = MagicMock()
    data = _good_points()
    # One point with 100-word reasoning, no sentence boundary
    data["points"][0]["reasoning"] = " ".join(["w"] * 100)
    syn.synthesize.return_value = data

    pts = run_synthesis(
        ticker="X", form_type="20-F", sections={"20-F_item5": "x"},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)

    assert len(pts) == 15
    content = pts[0].reasoning.replace(" […]", "")
    assert len(content.split()) <= 70


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
        "markiere Marktkontext",
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


# --- Stage 3: 4-arg body-aware _validate_sources --------------------------
# Root-cause history: _SECTION_CITE_RE once captured (\w+), so "20-F §4B"
# keyed "20-F_item4B" and never matched the numeric sent keys -> every such
# cite falsely collapsed to ["Inferenz"] (1.5.2 root-fix). Stage 3 captures
# (\d+[A-Z]?) so 10-K §1A/§7A stay distinct, but adds a numeric-fallback: a
# 20-F sub-paragraph cite (§4B/§5C) falls back to the parent item4/item5.
# Stage 3 also adds a body-heading check, so accept-cases need a section body
# that starts with the expected "ITEM N" heading. These assert the REAL
# _validate_sources behaviour directly.

_SENT = {"20-F_item4", "20-F_item5", "20-F_item18"}
_SECTIONS = {
    "20-F_item4": "ITEM 4 INFORMATION ON THE COMPANY\n\nA. History and development.",
    "20-F_item5": "ITEM 5 OPERATING AND FINANCIAL REVIEW\n\nA. Operating results.",
    "20-F_item18": "ITEM 18 FINANCIAL STATEMENTS\n\nConsolidated statements.",
}


def test_no_space_subitem_cite_not_collapsed_red_driver():
    """'20-F §4B' (item 4 IS sent) must NOT collapse; the exact cite string is
    preserved. §4B keys item4B (not sent) -> numeric-fallback to item4 (sent),
    whose body starts with 'ITEM 4'. No regress on the 1.5.2 root-fix."""
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §4B"], "20-F", _SENT, _SECTIONS)
    assert out == ["20-F §4B"]


def test_multiple_no_space_subitems_not_collapsed():
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §5C", "20-F §4B"], "20-F", _SENT, _SECTIONS)
    assert out == ["20-F §5C", "20-F §4B"]


def test_space_subitem_cite_not_collapsed_regression_guard():
    """'§<num> <letter>': the space ends the suffix, so (\\d+[A-Z]?) captures
    just '5' -> item5 (sent)."""
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §5 D"], "20-F", _SENT, _SECTIONS)
    assert out == ["20-F §5 D"]


def test_plain_sent_cite_not_collapsed_regression_guard():
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §4"], "20-F", _SENT, _SECTIONS)
    assert out == ["20-F §4"]


def test_subitem_cite_of_unsent_item_still_collapses():
    """The fix must not weaken real hallucination catching: item 6 NOT sent
    (neither item6A nor the numeric-fallback item6)."""
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §6A"], "20-F", _SENT, _SECTIONS)
    assert out == ["Inferenz"]


def test_plain_unsent_cite_still_collapses():
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §15"], "20-F", _SENT, _SECTIONS)
    assert out == ["Inferenz"]


def test_mixed_sent_and_unsent_subitems_collapses():
    """Item 4 sent (passes body check), item 7 not -> any not-sent cite
    collapses the whole list (unchanged rule)."""
    from app.deepdive.synthesis import _validate_sources

    out = _validate_sources(["20-F §4B", "20-F §7B"], "20-F", _SENT, _SECTIONS)
    assert out == ["Inferenz"]


def test_non_section_filing_string_still_hits_not_validatable(caplog):
    """A filing-ish string without § still has no regex match -> warning path
    unchanged (returned sources unchanged, no collapse)."""
    import logging

    from app.deepdive.synthesis import _validate_sources

    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        out = _validate_sources(["20-F item5"], "20-F", _SENT, _SECTIONS)
    assert out == ["20-F item5"]
    assert "not validatable" in caplog.text


# --- Stage 3: body-heading check (F4 defense-in-depth) --------------------
# A cited section is only accepted if its body starts (within a 300-char
# page-header tolerance) with the expected "ITEM N" heading.


def test_validate_sources_rejects_cite_when_body_lacks_item_heading():
    from app.deepdive.synthesis import _validate_sources

    sources = ["[10-K §1]"]
    sent_keys = {"10-K_item1"}
    sections = {"10-K_item1": "some random text without item heading"}
    result = _validate_sources(sources, "10-K", sent_keys, sections)
    assert result == ["Inferenz"]


def test_validate_sources_accepts_cite_when_body_has_item_heading():
    from app.deepdive.synthesis import _validate_sources

    sources = ["[10-K §1]"]
    sent_keys = {"10-K_item1"}
    sections = {"10-K_item1": "ITEM 1. BUSINESS\n\nWe build search engines..."}
    result = _validate_sources(sources, "10-K", sent_keys, sections)
    assert result == ["[10-K §1]"]


def test_validate_sources_accepts_cite_with_page_header_prefix():
    from app.deepdive.synthesis import _validate_sources

    sources = ["[10-K §1A]"]
    sent_keys = {"10-K_item1A"}
    sections = {"10-K_item1A": (
        "* * *\n\n| | | | |   \n---|---|---|---|---|---  \n"
        "Table of Contents| Alphabet Inc.  \n  \n"
        "ITEM 1A.RISK FACTORS\n\nOur operations..."
    )}
    result = _validate_sources(sources, "10-K", sent_keys, sections)
    assert result == ["[10-K §1A]"]


def test_validate_sources_accepts_novo_bare_number_style():
    from app.deepdive.synthesis import _validate_sources

    sources = ["[20-F §4]"]
    sent_keys = {"20-F_item4"}
    sections = {"20-F_item4": "ITEM 4 INFORMATION ON THE COMPANY\n\nA. History..."}
    result = _validate_sources(sources, "20-F", sent_keys, sections)
    assert result == ["[20-F §4]"]


def test_validate_sources_letter_suffix_item_not_truncated():
    # Anti-regress for the cite-regex fix: §7A must be captured as "7A", not
    # truncated to "7" (which would key the wrong section). Guards the
    # _SECTION_CITE_RE (\d+[A-Z]?) change. Same risk class for §1A.
    from app.deepdive.synthesis import _validate_sources

    sources = ["[10-K §7A]"]
    sent_keys = {"10-K_item7A"}
    sections = {"10-K_item7A": (
        "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES\n\nWe are exposed..."
    )}
    result = _validate_sources(sources, "10-K", sent_keys, sections)
    assert result == ["[10-K §7A]"]


def test_system_prompt_documents_source_format_without_brackets():
    """Source-Marker im Prompt-Beispiel dürfen keine eckigen Klammern enthalten.
    Sonst landet ein bracketsiertes Source-Token in `sources`, das der
    dossier-generator nochmal mit `[...]` wrappt -> `[[...]]`-Drift im Output.
    Anti-Regression auf Punkt 4 (Marker-Drift)."""
    from app.deepdive.synthesis import _SYSTEM_PROMPT

    assert "'[yfinance" not in _SYSTEM_PROMPT
    assert "'[Marktkontext" not in _SYSTEM_PROMPT


def test_system_prompt_contains_p13_fcf_yield_nudge():
    """P13 (Wachstum ohne Verwässerung) muss FCF-Yield und Shares-Outstanding
    explizit als Schlüssel-Indikatoren nennen, und n/a-Werte verlangen eine
    aktive Begründung statt einer Floskel."""
    from app.deepdive.synthesis import _SYSTEM_PROMPT

    assert "FCF-Yield" in _SYSTEM_PROMPT
    assert "Shares-Outstanding" in _SYSTEM_PROMPT
    assert "n/a" in _SYSTEM_PROMPT


def test_system_prompt_documents_hard_cap_five_stars():
    """VERTEILUNG-Block muss einen nicht-verhandelbaren Hard-Cap auf
    5 von 15 Punkten mit ⭐⭐⭐⭐⭐ benennen. Begründung: 2a.1-Verifikation
    zeigte 6/15 in GOOGL und ASML trotz "höchstens 4"-Heuristik im Prompt."""
    from app.deepdive.synthesis import _SYSTEM_PROMPT

    assert "HARTER CAP" in _SYSTEM_PROMPT
    assert "MAXIMAL 5" in _SYSTEM_PROMPT


def test_system_prompt_top_note_requires_relative_superiority():
    """Jeder ⭐⭐⭐⭐⭐-Punkt muss im reasoning konkret nennen, gegenüber
    welchem Konkurrenten oder Branchen-Standard die Überlegenheit belegt
    ist — Anti-Inflations-Reibung. Reichweite/absolute Zahl reicht nicht."""
    from app.deepdive.synthesis import _SYSTEM_PROMPT

    assert "gegenüber welchem Konkurrenten" in _SYSTEM_PROMPT


# --- Task 2a.2: Filing-Vintage line in user prompt --------------------------


def test_user_prompt_includes_filing_vintage_line():
    """_build_user_prompt with a valid filing_date must include the date."""
    from app.deepdive.synthesis import _build_user_prompt

    prompt = _build_user_prompt(
        "X", "20-F", {"20-F_item5": "rev"}, _qs(), filing_date="2026-02-04"
    )
    assert "Filing-Stand: 2026-02-04" in prompt


def test_user_prompt_vintage_includes_days_since_filing():
    """Days-since must be computed from today (patchable via _today)."""
    from datetime import date
    from unittest.mock import patch

    from app.deepdive.synthesis import _build_user_prompt

    fixed_today = date(2026, 5, 26)
    filing_date = date(2026, 2, 4)
    expected_days = (fixed_today - filing_date).days

    with patch("app.deepdive.synthesis._today", return_value=fixed_today):
        prompt = _build_user_prompt(
            "X", "20-F", {"20-F_item5": "rev"}, _qs(), filing_date="2026-02-04"
        )
    assert f"vor {expected_days} Tagen" in prompt


def test_user_prompt_vintage_omits_when_filing_date_missing():
    """filing_date=None must render 'Filing-Stand: unbekannt', not 'vor ... Tagen'."""
    from app.deepdive.synthesis import _build_user_prompt

    prompt = _build_user_prompt(
        "X", "20-F", {"20-F_item5": "rev"}, _qs(), filing_date=None
    )
    assert "Filing-Stand: unbekannt" in prompt
    assert "vor " not in prompt
    assert "Tagen" not in prompt


def test_user_prompt_vintage_position_before_filing_sections():
    """Vintage line must appear between the valuation block and 'Filing-Sections:'."""
    from app.deepdive.synthesis import _build_user_prompt

    prompt = _build_user_prompt(
        "X", "20-F", {"20-F_item5": "rev"}, _qs(), filing_date="2026-02-04"
    )
    assert prompt.index("Filing-Stand") < prompt.index("Filing-Sections:")


def test_user_prompt_vintage_does_not_affect_existing_blocks():
    """valuation block content must appear byte-identical inside the prompt."""
    from app.deepdive.synthesis import _build_user_prompt
    from app.deepdive.valuation_block import render_valuation_block

    qs = _qs()
    expected_block = render_valuation_block(qs)
    prompt = _build_user_prompt(
        "X", "20-F", {"20-F_item5": "rev"}, qs, filing_date="2026-02-04"
    )
    assert expected_block in prompt


def test_user_prompt_vintage_handles_unparseable_filing_date():
    """An unparseable filing_date must render 'Filing-Stand: unbekannt', never 'None'."""
    from app.deepdive.synthesis import _build_user_prompt

    prompt = _build_user_prompt(
        "X", "20-F", {"20-F_item5": "rev"}, _qs(), filing_date="not-a-date"
    )
    assert "Filing-Stand: unbekannt" in prompt
    assert "None" not in prompt
    # must not raise


# --- Task 1.1b (candidate 3): code-emitted staleness hint -------------------
# The objective trigger that carries the whole fix: _build_user_prompt emits an
# 'Aktualitäts-Hinweis' iff days_since_filing > VINTAGE_THRESHOLD_DAYS. The model
# then only reacts to the hint's presence — it no longer judges staleness itself.
# A pure system-prompt substring test would not cover this trigger mechanism.


def test_user_prompt_emits_staleness_hint_when_stale():
    """days > threshold -> the hint is emitted, carries the concrete day count,
    and scopes to the vintage-sensitive points (single-sourced from the code)."""
    from datetime import date
    from unittest.mock import patch

    from app.deepdive.synthesis import _build_user_prompt

    fixed_today = date(2026, 5, 28)
    expected_days = (fixed_today - date(2025, 1, 1)).days  # 512 -> stale
    with patch("app.deepdive.synthesis._today", return_value=fixed_today):
        prompt = _build_user_prompt(
            "X", "20-F", {"20-F_item5": "rev"}, _qs(), filing_date="2025-01-01"
        )
    assert "Aktualitäts-Hinweis" in prompt
    assert f"{expected_days} Tage" in prompt  # concrete, threshold-robust age
    assert "Punkte 5, 6, 12" in prompt        # scoped to VINTAGE_SENSITIVE_POINTS


def test_user_prompt_no_staleness_hint_when_fresh():
    """days <= threshold -> NO hint. Anti-over-mention is structural: a fresh
    filing's prompt never carries the hint, so the model cannot pick it up."""
    from datetime import date
    from unittest.mock import patch

    from app.deepdive.synthesis import _build_user_prompt

    fixed_today = date(2026, 5, 26)  # filing 2026-02-04 -> 111 days, not stale
    with patch("app.deepdive.synthesis._today", return_value=fixed_today):
        prompt = _build_user_prompt(
            "X", "20-F", {"20-F_item5": "rev"}, _qs(), filing_date="2026-02-04"
        )
    assert "Aktualitäts-Hinweis" not in prompt


def test_user_prompt_no_staleness_hint_when_filing_date_none():
    """filing_date None -> days None -> no hint (consistent with the fail-soft
    None path: missing vintage info is never penalised)."""
    from app.deepdive.synthesis import _build_user_prompt

    prompt = _build_user_prompt(
        "X", "20-F", {"20-F_item5": "rev"}, _qs(), filing_date=None
    )
    assert "Aktualitäts-Hinweis" not in prompt


# --- Vintage confidence cap (RED phase) -------------------------------------
# A post-process step in run_synthesis caps confidence to 🟡 for the vintage-
# sensitive Fisher points {5, 6, 12} when the cited filing is stale
# (days_since_filing > 180, computed from filing_date + the patchable _today()).
# Cap only LOWERS: 🟢 -> 🟡; 🟡 and 🔴 stay. None/unparseable filing_date -> no cap.
# Sections carry a real "ITEM 5" body so the §5 cite stays VALID and is NOT
# collapsed to ["Inferenz"] — that way the only thing that can change 🟢 here is
# the vintage cap, giving a clean assertion failure in RED.

_VINTAGE_SECTIONS = {
    "20-F_item5": "ITEM 5 OPERATING AND FINANCIAL REVIEW. We review results."
}


def test_vintage_cap_lowers_sensitive_points_when_stale():
    """Stale filing (>180 days): points 5, 6, 12 each start 🟢 with a valid §5
    source and must be capped to 🟡 by the vintage post-process."""
    from datetime import date
    from unittest.mock import patch

    syn = MagicMock()
    syn.synthesize.return_value = _good_points()  # all 🟢, sources ["20-F §5"]
    with patch("app.deepdive.synthesis._today", return_value=date(2026, 5, 26)):
        pts = run_synthesis(
            ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
            quant=_qs(), synthesizer=syn, max_input_tokens=200000,
            filing_date="2025-01-01")  # ~510 days -> stale
    by_num = {p.number: p for p in pts}
    assert by_num[5].confidence == "🟡"
    assert by_num[6].confidence == "🟡"
    assert by_num[12].confidence == "🟡"


def test_vintage_cap_not_applied_below_threshold():
    """Non-stale filing (<180 days): point 5 starts 🟢 and must stay 🟢.

    A parallel STALE run is the positive control: under the same data, point 5
    MUST be capped to 🟡 when stale. Asserting the control proves the threshold
    actually gates the cap and makes this test RED until the feature lands."""
    from datetime import date
    from unittest.mock import patch

    syn = MagicMock()
    syn.synthesize.return_value = _good_points()
    with patch("app.deepdive.synthesis._today", return_value=date(2026, 5, 26)):
        pts = run_synthesis(
            ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
            quant=_qs(), synthesizer=syn, max_input_tokens=200000,
            filing_date="2026-03-01")  # ~86 days -> not stale
    by_num = {p.number: p for p in pts}
    assert by_num[5].confidence == "🟢"

    # Positive control: same data, STALE -> P5 must be capped.
    syn_stale = MagicMock()
    syn_stale.synthesize.return_value = _good_points()
    with patch("app.deepdive.synthesis._today", return_value=date(2026, 5, 26)):
        pts_stale = run_synthesis(
            ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
            quant=_qs(), synthesizer=syn_stale, max_input_tokens=200000,
            filing_date="2025-01-01")  # ~510 days -> stale
    assert {p.number: p for p in pts_stale}[5].confidence == "🟡"


def test_vintage_cap_skips_insensitive_points():
    """Stale filing: a point outside {5,6,12} keeps its 🟢. Guards that the HARD
    cap set is exactly {5,6,12} — point 8 (clearly out) AND point 13 (the
    deliberately-excluded borderline point) both stay 🟢. Point 5 (in the set)
    is the positive control proving the cap actually fired on this run."""
    from datetime import date
    from unittest.mock import patch

    syn = MagicMock()
    syn.synthesize.return_value = _good_points()
    with patch("app.deepdive.synthesis._today", return_value=date(2026, 5, 26)):
        pts = run_synthesis(
            ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
            quant=_qs(), synthesizer=syn, max_input_tokens=200000,
            filing_date="2025-01-01")  # stale
    by_num = {p.number: p for p in pts}
    assert by_num[5].confidence == "🟡"   # positive control: cap fired
    assert by_num[8].confidence == "🟢"   # not in set -> untouched
    assert by_num[13].confidence == "🟢"  # excluded borderline -> untouched


def test_vintage_cap_skipped_when_filing_date_none():
    """filing_date=None -> days_since_filing is None -> NO cap. Point 5 must
    keep 🟢 explicitly (deliberate: no penalty for missing vintage info).

    A parallel run WITH a stale date is the positive control: under the same
    data, point 5 must be capped to 🟡. This proves the None-branch is a real
    skip (not just absence of the feature) and keeps the test RED until the
    cap exists."""
    from datetime import date
    from unittest.mock import patch

    syn = MagicMock()
    syn.synthesize.return_value = _good_points()
    pts = run_synthesis(
        ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
        quant=_qs(), synthesizer=syn, max_input_tokens=200000,
        filing_date=None)
    by_num = {p.number: p for p in pts}
    assert by_num[5].confidence == "🟢"

    # Positive control: same data, stale date -> P5 must be capped.
    syn_stale = MagicMock()
    syn_stale.synthesize.return_value = _good_points()
    with patch("app.deepdive.synthesis._today", return_value=date(2026, 5, 26)):
        pts_stale = run_synthesis(
            ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
            quant=_qs(), synthesizer=syn_stale, max_input_tokens=200000,
            filing_date="2025-01-01")
    assert {p.number: p for p in pts_stale}[5].confidence == "🟡"


def test_vintage_cap_only_lowers_never_raises():
    """Stale filing: a sensitive point already at 🔴 must NOT be raised to 🟡
    by the cap (cap only lowers). A point at 🟡 stays 🟡. Point 12 (🟢, in the
    set) is the positive control proving the cap fired on this stale run."""
    from datetime import date
    from unittest.mock import patch

    syn = MagicMock()
    data = _good_points()
    by_idx = {p["number"]: p for p in data["points"]}
    by_idx[5]["confidence"] = "🔴"
    by_idx[6]["confidence"] = "🟡"
    # point 12 left at 🟢 as the positive control
    syn.synthesize.return_value = data
    with patch("app.deepdive.synthesis._today", return_value=date(2026, 5, 26)):
        pts = run_synthesis(
            ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
            quant=_qs(), synthesizer=syn, max_input_tokens=200000,
            filing_date="2025-01-01")  # stale
    by_num = {p.number: p for p in pts}
    assert by_num[5].confidence == "🔴"   # cap must NOT raise 🔴
    assert by_num[6].confidence == "🟡"   # already ≤🟡, unchanged
    assert by_num[12].confidence == "🟡"  # positive control: 🟢 -> 🟡


def test_vintage_cap_coexists_with_points_14_15_red():
    """Stale filing, all 🟢: the new vintage cap (P5 -> 🟡) must compose with the
    existing 14/15 -> 🔴 enforcement. Anti-regress."""
    from datetime import date
    from unittest.mock import patch

    syn = MagicMock()
    syn.synthesize.return_value = _good_points()
    with patch("app.deepdive.synthesis._today", return_value=date(2026, 5, 26)):
        pts = run_synthesis(
            ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
            quant=_qs(), synthesizer=syn, max_input_tokens=200000,
            filing_date="2025-01-01")  # stale
    by_num = {p.number: p for p in pts}
    assert by_num[5].confidence == "🟡"   # vintage cap
    assert by_num[14].confidence == "🔴"  # existing enforcement
    assert by_num[15].confidence == "🔴"  # existing enforcement


def test_system_prompt_contains_vintage_rule():
    """The system prompt must carry a SEMANTIC vintage instruction. The numeric
    threshold lives only in a code constant, so we assert the German anchor
    'Filing-Alter', not the number 180."""
    from app.deepdive.synthesis import _SYSTEM_PROMPT

    assert "Filing-Alter" in _SYSTEM_PROMPT


def test_system_prompt_vintage_reacts_to_staleness_hint():
    """1.1b (candidate 3): the MSFT acceptance run showed the model never judges
    a ~10-month-old 10-K as 'stale' (the latest annual filing is not 'veraltet'
    in its ordinary sense), so a subjective gate never fires. The VINTAGE rule
    therefore no longer asks the model to judge staleness. It reacts
    UNCONDITIONALLY to the code-emitted 'Aktualitäts-Hinweis' signal — naming the
    filing age in the reasoning of the points the hint lists — and stays silent
    when no hint is present. Semantic substrings; the threshold stays in code."""
    from app.deepdive.synthesis import _SYSTEM_PROMPT

    # reacts to the objective, code-emitted signal (not a subjective judgment)
    assert "Aktualitäts-Hinweis" in _SYSTEM_PROMPT
    # unconditional reasoning-naming instruction
    assert "benenne das Filing-Alter" in _SYSTEM_PROMPT
    assert "im reasoning" in _SYSTEM_PROMPT
    # silence when no hint is present (anti-over-mention is also structural:
    # _build_user_prompt simply omits the hint for fresh filings)
    assert "erwähne das Filing-Alter NICHT" in _SYSTEM_PROMPT


def test_vintage_cap_unparseable_filing_date_no_cap():
    """Characterization: an UNPARSEABLE filing_date is fail-soft — treated like
    missing vintage info, so _days_since_filing's `except ValueError` branch
    returns None and NO cap is applied. Point 5 (a vintage-sensitive point that
    starts 🟢 with a valid §5 source) must keep 🟢, and run_synthesis must not
    raise. Locks the contract and covers synthesis.py lines 138-139."""
    syn = MagicMock()
    syn.synthesize.return_value = _good_points()  # all 🟢, sources ["20-F §5"]
    pts = run_synthesis(
        ticker="X", form_type="20-F", sections=_VINTAGE_SECTIONS,
        quant=_qs(), synthesizer=syn, max_input_tokens=200000,
        filing_date="not-a-date")  # unparseable -> no cap
    by_num = {p.number: p for p in pts}
    assert by_num[5].confidence == "🟢"


# --- 2a.1c marker vocabulary -----------------------------------------------

def test_norm_marker_roundtrip_canonical_in_vocab():
    """Completeness: every canonical vocabulary string is reachable as a key in
    the canon map (no canonical entry is unmapped). The comma-fold / Bug-1
    behaviour is guarded separately by
    test_norm_marker_folds_all_separators_including_comma — this test holds by
    construction and does NOT prove the fold."""
    from app.deepdive.synthesis import (
        _MARKER_CANON, _norm_marker, _QUANT_MARKER_VOCAB, _SOFT_MARKER_VOCAB,
    )
    for c in (*_QUANT_MARKER_VOCAB, *_SOFT_MARKER_VOCAB):
        assert _norm_marker(c) in _MARKER_CANON, f"{c!r} not roundtrip-stable"
    # the comma case explicitly
    assert _norm_marker("yfinance, 5J") in _MARKER_CANON


def test_norm_marker_folds_all_separators_including_comma():
    """Direct, non-tautological guard for Bug 1 and the capture-class edges:
    the fold must collapse whitespace, comma, hyphen, underscore and '&'. The
    comma assertion goes RED if the comma is dropped from the fold class
    (-> 'yfinance,5j'), which is the exact Bug-1 regression."""
    from app.deepdive.synthesis import _norm_marker
    assert _norm_marker("yfinance, 5J") == "yfinance5j"      # comma + space
    assert _norm_marker("Peer-Comparison") == "peercomparison"   # hyphen + case
    assert _norm_marker("forward_estimates") == "forwardestimates"  # underscore
    assert _norm_marker("Bewertung & Kapitalstruktur") == "bewertungkapitalstruktur"  # '&'
    # a comma-free variant must fold to the SAME key as the canonical (the
    # property the lookup map relies on; fails if comma is not in the class)
    assert _norm_marker("yfinance 5J") == _norm_marker("yfinance, 5J")


import logging  # module-scope; pytest is already imported at the top of the file


@pytest.mark.parametrize("variant", [
    "Quant-Snapshot", "quant_snapshot", "quant snapshot",
    "forward_estimates", "Forward-Estimates", "forward estimates",
    "peer_comparison", "Peer-Comparison",
    "historical_series", "trend_metrics",
    "Bewertung", "Bewertung & Kapitalstruktur",  # '&' fold-class edge (byte-belegt)
])
def test_normalize_known_quant_variants_to_canonical(variant):
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources([variant]) == ["yfinance, 5J"]


def test_normalize_dedups_multiple_quant_markers():
    from app.deepdive.synthesis import _normalize_sources
    out = _normalize_sources(["Quant-Snapshot", "historical_series", "trend_metrics"])
    assert out == ["yfinance, 5J"]


def test_normalize_keeps_plain_section_cite_with_quant():
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources(["10-K §7", "Quant-Snapshot"]) == ["10-K §7", "yfinance, 5J"]


def test_normalize_section_guard_subparagraph_4b_passes_through():
    """Load-bearing (Lesson w / 1.5.2): the section guard must run via
    _SECTION_CITE_RE.search BEFORE _norm_marker, else '20-F §4B' folds the
    hyphen to '20f§4b', misses the vocab, and collapses to Inferenz — destroying
    grounding. Goes RED if the guard is missing (the §4B cite would fold to
    '20f§4b' and collapse)."""
    from app.deepdive.synthesis import _normalize_sources
    out = _normalize_sources(["20-F §4B"])
    assert out == ["20-F §4B"]


def test_normalize_section_guard_subparagraph_4b_no_warning(caplog):
    from app.deepdive.synthesis import _normalize_sources
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        _normalize_sources(["20-F §4B"])
    assert "controlled vocabulary" not in caplog.text


def test_normalize_unknown_marker_collapses_to_inference_with_warning(caplog):
    from app.deepdive.synthesis import _normalize_sources
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        out = _normalize_sources(["made_up_marker"])
    assert out == ["Inferenz"]
    assert "controlled vocabulary" in caplog.text
    assert "made_up_marker" in caplog.text


def test_normalize_passes_through_soft_markers():
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources(["Marktkontext"]) == ["Marktkontext"]
    assert _normalize_sources(["Inferenz"]) == ["Inferenz"]
    assert _normalize_sources(["yfinance, 5J"]) == ["yfinance, 5J"]


def test_normalize_no_warning_on_canonicalization(caplog):
    from app.deepdive.synthesis import _normalize_sources
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        _normalize_sources(["Quant-Snapshot", "Marktkontext", "yfinance, 5J"])
    assert "controlled vocabulary" not in caplog.text


def test_normalize_embedded_section_cite_passes_through():
    """Discriminates .search from .fullmatch: an embedded cite (cite as a
    substring of a longer string) must be recognized and passed through. Goes
    RED if the guard uses _SECTION_CITE_RE.fullmatch instead of .search."""
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources(["10-K §7 (S. 12)"]) == ["10-K §7 (S. 12)"]


def test_normalize_section_cite_with_unknown_marker_keeps_cite():
    """Pure-function B-dual: a real cite alongside an invented marker keeps the
    cite and collapses only the unknown -> result is NOT ['Inferenz'] (so the
    downstream confidence cap will not fire for a grounded point)."""
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources(["10-K §7", "made_up_marker"]) == ["10-K §7", "Inferenz"]


def test_normalize_empty_list_returns_empty():
    """Empty input stays empty — NOT collapsed to ['Inferenz']. Inventing an
    Inferenz source would mask a model contract violation; instead the empty
    list flows to FisherPoint(sources=[]) whose min_length=1 raises (fail-loud,
    surfaced as GeminiError in run_synthesis)."""
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources([]) == []


def test_quant_marker_canonicalized_and_keeps_green():
    """Load-bearing for A-ordering: pure canonicalization (Quant-Snapshot ->
    yfinance, 5J) must NOT trigger the section-collapse downgrade. Goes RED if
    the downgrade compares against the raw (pre-normalization) source list."""
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["Quant-Snapshot"]
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="10-K",
        sections={"10-K_item7": "ITEM 7 MANAGEMENT DISCUSSION. We discuss."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["yfinance, 5J"]
    assert pts[0].confidence == "🟢"


def test_two_unknown_markers_dedup_then_cap_to_yellow():
    """B: two distinct unknowns -> ['Inferenz', 'Inferenz'] -> dedup ->
    ['Inferenz'] -> FisherPoint validator caps 🟢 to 🟡."""
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["made_up_one", "made_up_two"]
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="10-K",
        sections={"10-K_item7": "ITEM 7 MANAGEMENT DISCUSSION. We discuss."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["Inferenz"]
    assert pts[0].confidence == "🟡"


def test_unknown_marker_does_not_sink_grounded_point():
    """B-dual: a grounded point ([10-K §7, <unknown>]) keeps its section cite,
    is NOT capped (sources != ['Inferenz']), and stays 🟢."""
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["10-K §7", "made_up_marker"]
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="10-K",
        sections={"10-K_item7": "ITEM 7 MANAGEMENT DISCUSSION. We discuss."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["10-K §7", "Inferenz"]
    assert pts[0].confidence == "🟢"


def test_anti_regress_hallucinated_section_still_collapses_and_downgrades():
    """Anti-regress: a never-sent section cite still collapses to ['Inferenz']
    and downgrades 🟢 -> 🟡 after the normalize-before-validate refactor."""
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["20-F §99"]  # never sent
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="20-F",
        sections={"20-F_item5": "ITEM 5 OPERATING REVIEW. We review."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["Inferenz"]
    assert pts[0].confidence == "🟡"


def test_normalize_misformatted_filing_cite_collapses_to_inference(caplog):
    """2a.1c no-leak guard for the format-drift edge: a §-less filing-form cite
    ('20-F Item 5') must NOT leak raw into the dossier — it collapses to
    ['Inferenz'] — while keeping the SPECIFIC 'not validatable' diagnostic
    (distinct from the generic 'not in controlled vocabulary' for invented
    markers)."""
    from app.deepdive.synthesis import _normalize_sources
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        out = _normalize_sources(["20-F Item 5"])
    assert out == ["Inferenz"]
    assert "not validatable" in caplog.text
    assert "not in controlled vocabulary" not in caplog.text
