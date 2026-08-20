"""Tests for the per-ticker detail page.

Same two invariants as the overview, plus a third one that is specific to
this page: an absent section is stated as absent. The detail page is the
place where a missing insider block, an unfilled summary or a metric from a
known-buggy run would otherwise look like a value that simply does not
exist.
"""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.viewer.html import TABLE_SCROLL_CLASS, esc
from app.viewer.models import Dossier, ParsedPoint
from app.viewer.render_detail import (
    BACK_HREF,
    BACK_LABEL,
    DEFECT_FOOTNOTE_CLASS,
    DEFECT_MARKER,
    DEFECT_METRIC_LABELS,
    INSIDER_MISSING_NOTE,
    LOW_CONFIDENCE_NOTE,
    NOTES_EMPTY_NOTE,
    PEER_CAPTION_CLASS,
    PENDING_SECTIONS,
    PLACEHOLDER_POINT_NOTE,
    SUMMARY_PENDING_NOTE,
    has_display_value,
    render_detail,
)
from app.viewer.render_overview import (
    FRESHNESS_RED_TITLE,
    build_overview_row,
    render_overview,
)

GENERATED_AT = datetime(2026, 8, 20, 13, 5, tzinfo=timezone.utc)


def make_dossier(**overrides) -> Dossier:
    """A dossier shaped like the real files, so each test states only what
    it is actually about."""
    fields = {
        "ticker": "FICO",
        "form_type": "10-K",
        "generated_at": datetime(2026, 7, 1, 21, 11, tzinfo=timezone.utc),
        "filing_date": date(2025, 11, 7),
        "quant_date": date(2026, 7, 1),
        "days_since_filing": 236,
        "company_name": "Fair Isaac Corporation",
        "headline_metrics": {
            "Market Cap": "27,708,030,976 USD",
            "Gross Margin": "84.2%",
            "Op. Margin": "58.2%",
        },
        "metrics": {
            "Bewertung": {"P/E fwd": "22.0", "EV/EBIT": "33.3"},
            "Kapitalstruktur": {"D/E": "n/a", "Current Ratio": "2.2"},
            "Analyst Consensus": {"Target": "1528.55 (Median 1521.5)"},
            "Forward-Konsens": {"Revenue": "28.0% (lfd. GJ)"},
        },
        "metric_extras": {"Analyst Consensus": ["buy", "20 Analysten"]},
        "raw_metric_lines": {},
        "points": [],
        "source_path": Path("FICO_2026-07-01.md"),
    }
    fields.update(overrides)
    return Dossier(**fields)


def render(**overrides) -> str:
    return render_detail(make_dossier(**overrides), generated_at=GENERATED_AT)


# --- header ---------------------------------------------------------------


def test_header_names_company_and_ticker():
    page = render()

    assert "Fair Isaac Corporation" in page
    assert "FICO" in page


def test_header_falls_back_to_ticker_without_company_name():
    """The H1 of a Gen-1 dossier may be unparseable; the page must still
    identify itself rather than print an em dash as a headline."""
    page = render(company_name=None)

    assert "FICO" in page
    assert "<h1>—" not in page


def test_header_shows_filing_and_quant_state():
    page = render()

    assert "10-K" in page
    assert "2025-11-07" in page
    assert "2026-07-01" in page


def test_header_links_back_to_the_overview():
    page = render()

    assert BACK_HREF in page
    assert BACK_LABEL in page


def test_header_marks_a_stale_filing():
    page = render(days_since_filing=400)

    assert "age-red" in page
    assert FRESHNESS_RED_TITLE in page


def test_header_leaves_a_fresh_filing_unmarked():
    page = render(days_since_filing=10)

    assert "age-red" not in page
    assert "age-yellow" not in page


def test_header_omits_the_age_badge_when_age_is_unknown():
    """No age is not "0 days" — an unknown age gets no badge at all."""
    page = render(days_since_filing=None)

    assert "Tage" not in page


def test_generated_at_is_injected_not_read_from_the_clock():
    """Byte-identical output for identical input; otherwise every rebuild is
    a diff."""
    dossier = make_dossier()

    assert render_detail(dossier, generated_at=GENERATED_AT) == render_detail(
        dossier, generated_at=GENERATED_AT
    )


def test_generated_at_is_shown():
    assert "2026-08-20 13:05" in render()


# --- executive summary ----------------------------------------------------


def test_summary_is_marked_as_pending_when_unfilled():
    """All 23 dossiers carry only the generator's prompt placeholder, which
    the parser resolves to None. Printing boilerplate as a summary would
    present a prompt as an author's statement."""
    page = render(executive_summary=None)

    assert SUMMARY_PENDING_NOTE in page


def test_summary_is_rendered_when_present():
    page = render(executive_summary="Kern-These.\n\nHauptrisiko.")

    assert "<p>Kern-These.</p>" in page
    assert SUMMARY_PENDING_NOTE not in page


# --- quant tiles ----------------------------------------------------------


def test_headline_metrics_are_rendered_prominently():
    page = render()

    assert "Market Cap" in page
    assert "27,708,030,976 USD" in page


def test_every_metric_block_is_rendered():
    page = render()

    for label in ("Bewertung", "Kapitalstruktur", "Analyst Consensus"):
        assert label in page
    assert "22.0" in page
    assert "2.2" in page


def test_metric_extras_stay_visible():
    """`strong_buy` and `20 Analysten` carry no label and would be dropped by
    a label-driven renderer — they belong to the consensus block."""
    page = render()

    assert "20 Analysten" in page
    assert "buy" in page


def test_block_with_only_extras_is_still_rendered():
    """A newly added, still unlabelled generator segment must show up rather
    than take its whole block down with it."""
    page = render(metrics={}, metric_extras={"Forward-Konsens": ["ein neues Segment"]})

    assert "ein neues Segment" in page


def test_empty_metric_block_is_omitted():
    """No values means no empty frame claiming there were some."""
    page = render(metrics={"Bewertung": {"P/E fwd": "22.0"}}, metric_extras={})

    assert "Forward-Konsens" not in page


def test_valuation_range_line_is_rendered_verbatim():
    """The range line keeps its own span annotation ("~3J, 181 Wo"); a
    re-composed version would be the viewer computing."""
    raw = "Bewertungs-Range (~3J, 181 Wo): P/E TTM 37.9 vs Median 74.9"
    page = render(raw_metric_lines={"Bewertungs-Range": raw})

    assert "~3J, 181 Wo" in page


def test_missing_valuation_range_line_is_omitted():
    """Gen-1 dossiers have no range line at all."""
    page = render(raw_metric_lines={})

    assert "Bewertungs-Range" not in page


# --- "is there a value at all" --------------------------------------------


@pytest.mark.parametrize(
    "display",
    [
        None,
        "",
        "   ",
        "—",
        "n/a",
        "n/a (Div n/a aktuell + Ø 5J Buyback n/a)",
        "n/a (Interest Expense fehlt)",
    ],
)
def test_absent_display_values_are_recognised(display):
    """`n/a` as a prefix counts too: ARGX writes `n/a (Div n/a aktuell + …)`
    — the metric is missing, the parenthesis only spells out why."""
    assert has_display_value(display) is False


@pytest.mark.parametrize(
    "display",
    [
        "0",
        "0.0%",
        "24.2% (Div 23.0% aktuell + Ø 4J Buyback 1.2%)",
        "1528.55 (Median 1521.5)",
    ],
)
def test_present_display_values_are_recognised(display):
    """Presence, not plausibility: `0` is a value and stays one. The check
    never looks at how big the number is — the viewer still computes
    nothing."""
    assert has_display_value(display) is True


# --- defect markers -------------------------------------------------------


def test_defect_marks_the_metric_but_keeps_the_value():
    """A defect qualifies a number, it never removes it — omitting it would
    claim the dossier has no such value."""
    page = render(ticker="ARGX", metrics={"Bewertung": {"EV/EBIT": "1254.9"}})

    assert DEFECT_MARKER in page
    assert "1254.9" in page


def test_defect_footnote_writes_each_note_once():
    """EV/EBIT and EV/Sales share one defect note. Both tiles carry the
    tooltip, but the footnote states the reason once and names both
    metrics — the same paragraph twice reads like two findings."""
    page = render(
        ticker="ARGX", metrics={"Bewertung": {"EV/EBIT": "1254.9", "EV/Sales": "14.3"}}
    )
    footnote = page.split(DEFECT_FOOTNOTE_CLASS)[-1]

    assert page.count(DEFECT_MARKER) == 3  # two tiles + the footnote entry
    assert footnote.count("floatShares") == 1
    assert "EV/EBIT, EV/Sales" in footnote


def test_defect_note_is_attached_as_a_tooltip():
    page = render(ticker="ARGX", metrics={"Bewertung": {"EV/EBIT": "1254.9"}})

    assert 'title="Für ARGX rechnet Yahoo' in page


def test_unaffected_ticker_gets_no_marker():
    """The ARGX enterprise-value defect is ticker-scoped."""
    page = render(ticker="FICO", metrics={"Bewertung": {"EV/EBIT": "33.3"}})

    assert DEFECT_MARKER not in page


def test_defect_of_a_metric_the_dossier_lacks_is_not_footnoted():
    """The range defect applies to every run, but a Gen-1 dossier has no
    range line — a footnote there would qualify a number nobody can see."""
    page = render(raw_metric_lines={}, metrics={"Bewertung": {"P/E fwd": "22.0"}})

    assert "EV-Definitionen" not in page


def test_range_line_carries_its_own_defect():
    raw = "Bewertungs-Range (~3J): P/E TTM 37.9 vs Median 74.9"
    page = render(raw_metric_lines={"Bewertungs-Range": raw})

    assert DEFECT_MARKER in page
    assert "EV-Definitionen" in page


def test_dossier_without_quant_date_keeps_the_undated_markers():
    """Corrected expectation: this used to assert that no marker at all
    appears without a quant date.

    Only the *dated* defect windows are uncheckable without the field. The
    EV rules carry no date, so suspending them too would have hidden a known
    defect the moment a dossier generation stops writing `quant_date`.
    """
    page = render(
        quant_date=None,
        ticker="ARGX",
        metrics={"Bewertung": {"EV/EBIT": "1254.9", "Div-Yield": "23.0%"}},
    )

    assert DEFECT_MARKER in page
    assert "floatShares" in page
    assert "Div-Yield-Bug" not in page


def test_metric_without_a_value_gets_no_marker():
    """FICO's dossier says `D/E n/a`. A unit warning on a value that is not
    there qualifies nothing — it is noise, and `⚠ n/a` reads as if the
    absence itself were suspect."""
    page = render(ticker="FICO", metrics={"Kapitalstruktur": {"D/E": "n/a"}})

    assert "n/a" in page
    assert DEFECT_MARKER not in page
    assert "Einheiten-Mismatch" not in page


def test_metric_whose_value_is_only_an_explanation_gets_no_marker():
    """ARGX: `Total Shareholder Yield: n/a (Div n/a aktuell + Ø 5J Buyback
    n/a)` — inside the div-yield window, but there is no yield to qualify."""
    page = render(
        ticker="ARGX",
        quant_date=date(2026, 6, 1),
        metrics={
            "Kapitalstruktur": {
                "Total Shareholder Yield": "n/a (Div n/a aktuell + Ø 5J Buyback n/a)"
            }
        },
    )

    assert DEFECT_MARKER not in page
    assert "Div-Yield-Bug" not in page


def test_metric_with_a_real_value_stays_marked():
    """Counter-check to the two above: GOOGL's `24.2% (Div 23.0% aktuell +
    Ø 4J Buyback 1.2%)` is a value from the buggy window and must keep both
    marker and footnote."""
    page = render(
        ticker="GOOGL",
        quant_date=date(2026, 6, 1),
        metrics={
            "Kapitalstruktur": {
                "Total Shareholder Yield": "24.2% (Div 23.0% aktuell + Ø 4J Buyback 1.2%)"
            }
        },
    )

    assert DEFECT_MARKER in page
    assert "Div-Yield-Bug" in page


def test_valueless_metric_does_not_suppress_its_neighbour():
    """One missing metric must not clear the block: D/E has no value, the
    range line does."""
    page = render(
        metrics={"Kapitalstruktur": {"D/E": "n/a"}},
        raw_metric_lines={"Bewertungs-Range": "Bewertungs-Range (~3J): P/E TTM 37.9"},
    )

    assert "EV-Definitionen" in page
    assert "Einheiten-Mismatch" not in page


@pytest.mark.parametrize("metric_key", sorted(DEFECT_METRIC_LABELS))
def test_every_known_defect_key_maps_to_a_rendered_label(metric_key):
    """The mapping is explicit rather than derived from the label string; a
    new defect key without a mapping would silently never show."""
    block, label = DEFECT_METRIC_LABELS[metric_key]

    assert block
    assert label


# --- peer table -----------------------------------------------------------

PEER_TABLE = [
    ["Ticker", "P/E fwd"],
    ["FICO", "22.0"],
    ["EFX", "15.8"],
]


def test_peer_table_is_rendered():
    page = render(peer_table=PEER_TABLE)

    assert "<th>Ticker</th>" in page
    assert "<td>EFX</td>" in page


def test_peer_rationale_is_shown_as_caption():
    page = render(peer_table=PEER_TABLE, peer_rationale="Big-Tech-Wettbewerber")

    assert "Big-Tech-Wettbewerber" in page


def test_peer_caption_is_absent_without_a_rationale():
    """Most dossiers carry no rationale; a caption reading "—" would look
    like an empty statement rather than none."""
    page = render(peer_table=PEER_TABLE, peer_rationale=None)

    assert PEER_CAPTION_CLASS not in page


def test_peer_section_is_omitted_without_a_table():
    """No peer rows means no comparison was made — an empty table would
    imply one."""
    page = render(peer_table=[])

    assert "Peer" not in page


# --- Fisher points --------------------------------------------------------


def point(**overrides) -> ParsedPoint:
    fields = {
        "number": 1,
        "title": "Marktpotential",
        "rating": 4,
        "confidence": "🟢",
        "reasoning": "Starkes Wachstum.",
        "sources": ["10-K §1", "yfinance, 5J"],
    }
    fields.update(overrides)
    return ParsedPoint(**fields)


def test_point_card_shows_number_title_and_reasoning():
    page = render(points=[point()])

    assert "Punkt 1" in page
    assert "Marktpotential" in page
    assert "Starkes Wachstum." in page


def test_point_card_shows_sources_as_badges():
    page = render(points=[point()])

    assert 'class="tag">10-K §1<' in page


def test_point_card_renders_rating_as_stars():
    page = render(points=[point(rating=4)])

    assert "★★★★☆" in page


def test_point_without_rating_shows_no_stars():
    """The generator writes `?` when it has no rating; zero stars is not a
    grade of zero."""
    page = render(points=[point(rating=None)])

    assert "★" not in page


def test_confidence_colours_the_dot():
    assert "dot green" in render(points=[point(confidence="🟢")])
    assert "dot yellow" in render(points=[point(confidence="🟡")])
    assert "dot red" in render(points=[point(confidence="🔴")])


def test_unknown_confidence_stays_neutral():
    """An unparsed confidence is not a green light."""
    page = render(points=[point(confidence=None)])

    assert "dot na" in page


def test_low_confidence_card_is_muted_and_explained():
    """🔴 means thin evidence, not a verdict on the company — the card is
    toned down and says why."""
    page = render(points=[point(confidence="🔴")])

    assert "point muted" in page
    assert LOW_CONFIDENCE_NOTE in page


def test_low_confidence_note_reads_as_evidence_gap_not_as_a_grade():
    """Wording guard: the note must not sound like a bad mark."""
    assert "schlecht" not in LOW_CONFIDENCE_NOTE
    assert "mangelhaft" not in LOW_CONFIDENCE_NOTE


def test_full_confidence_card_is_not_muted():
    page = render(points=[point(confidence="🟢")])

    assert "point muted" not in page
    assert LOW_CONFIDENCE_NOTE not in page


def test_placeholder_point_is_marked_as_absent():
    """A point the dossier never contained is a different thing from a point
    with thin evidence."""
    page = render(
        points=[ParsedPoint(number=14, title="Offenheit", is_placeholder=True)]
    )

    assert PLACEHOLDER_POINT_NOTE in page
    assert LOW_CONFIDENCE_NOTE not in page
    assert "point absent" in page


def test_points_section_is_omitted_without_points():
    page = render(points=[])

    assert "Fishers 15 Punkte" not in page


# --- insider --------------------------------------------------------------

INSIDER_DETAILS = [
    "- LANSING WILLIAM J (CEO) — 124 signifikante Transaktionen:",
    "  - 2025-11-10: S 160 @ 1725.46 = 276,074 (ungeplant)",
]


def test_insider_summary_is_shown():
    page = render(insider_summary_line="48 Form-4-Filings · 127 signifikant")

    assert "48 Form-4-Filings" in page


def test_insider_details_are_collapsed():
    """FICO alone has 130+ detail lines; expanded they push every other
    section off the screen."""
    page = render(
        insider_summary_line="48 Form-4-Filings", insider_detail_lines=INSIDER_DETAILS
    )

    assert "<details>" in page
    assert "<details open" not in page


def test_insider_details_keep_their_nesting():
    page = render(
        insider_summary_line="48 Form-4-Filings", insider_detail_lines=INSIDER_DETAILS
    )

    assert "<li>LANSING WILLIAM J (CEO) — 124 signifikante Transaktionen:\n<ul>" in page


def test_insider_section_states_a_missing_block_honestly():
    """13 of 23 dossiers predate the insider stage; an empty frame would
    look like "no transactions"."""
    page = render(insider_summary_line=None, insider_detail_lines=[])

    assert INSIDER_MISSING_NOTE in page
    assert "<details>" not in page


def test_insider_summary_without_details_renders_no_disclosure():
    page = render(insider_summary_line="nicht anwendbar (FPI)", insider_detail_lines=[])

    assert "nicht anwendbar (FPI)" in page
    assert "<details>" not in page


# --- source coverage ------------------------------------------------------


def test_section_flags_are_rendered_as_pills():
    page = render(section_flags={"10-K_item1": "ok"})

    assert "pill green" in page
    assert "10-K_item1" in page


def test_missing_flag_is_red():
    page = render(section_flags={"10-K_item8": "missing"})

    assert "pill red" in page


def test_degraded_flags_are_yellow():
    for state in ("ambiguous", "fallback_used", "truncated"):
        page = render(section_flags={"10-K_item1": state})

        assert "pill yellow" in page, state


def test_unknown_flag_state_is_not_painted_green():
    """The flag vocabulary is closed; an unknown word is not a clean bill."""
    page = render(section_flags={"10-K_item1": "weird_new_state"})

    assert "pill green" not in page
    assert "pill na" in page


def test_source_coverage_is_listed():
    page = render(source_coverage={"EDGAR": "10-K (US direct)"})

    assert "EDGAR" in page
    assert "10-K (US direct)" in page


def test_coverage_section_is_omitted_when_empty():
    page = render(section_flags={}, source_coverage={})

    assert "Source Coverage" not in page


# --- notes ----------------------------------------------------------------


def test_notes_are_rendered_as_markdown():
    page = render(notes="- erster Punkt\n  - Unterpunkt")

    expected = "<ul>\n<li>erster Punkt\n<ul>\n<li>Unterpunkt</li>\n</ul>\n</li>\n</ul>"

    assert expected in page


def test_empty_notes_say_where_they_are_maintained():
    page = render(notes=None)

    assert NOTES_EMPTY_NOTE in page


# --- pending sections -----------------------------------------------------


def test_pending_sections_are_present_and_marked_as_pending():
    """They exist in the template now so B.3/B.4 appear later without a
    template change."""
    page = render()

    for section_id, heading in PENDING_SECTIONS:
        assert f'id="{section_id}"' in page
        assert esc(heading) in page  # "Stef's" arrives HTML-escaped


# --- structure ------------------------------------------------------------


def test_sections_appear_in_reading_order():
    page = render(
        peer_table=PEER_TABLE,
        points=[point()],
        insider_summary_line="48 Form-4-Filings",
        section_flags={"10-K_item1": "ok"},
        notes="hi",
    )
    order = [
        'id="summary"',
        'id="quant"',
        'id="peers"',
        'id="points"',
        'id="insider"',
        'id="coverage"',
        'id="notes"',
        f'id="{PENDING_SECTIONS[0][0]}"',
    ]
    positions = [page.index(anchor) for anchor in order]

    assert positions == sorted(positions)


HOSTILE = "<script>alert(1)</script>"


def test_detail_page_escapes_injection_from_every_field():
    """Dossier content is model output plus hand-written notes — nothing
    validates it between generator and browser."""
    page = render(
        company_name=HOSTILE,
        points=[point(title=HOSTILE, reasoning=HOSTILE, sources=[HOSTILE])],
        insider_summary_line=HOSTILE,
        insider_detail_lines=[f"- {HOSTILE}"],
        notes=HOSTILE,
        peer_table=[[HOSTILE], [HOSTILE]],
        source_coverage={HOSTILE: HOSTILE},
        section_flags={HOSTILE: HOSTILE},
        metric_extras={"Bewertung": [HOSTILE]},
    )

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_overview_page_escapes_injection_from_every_field():
    dossier = make_dossier(
        company_name=HOSTILE, points=[point(title=HOSTILE, reasoning=HOSTILE)]
    )
    row = build_overview_row(dossier, duplicate_names={HOSTILE})
    page = render_overview([row], generated_at=GENERATED_AT)

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_peer_table_sits_in_a_scroll_container():
    """Seven columns need ~532px even at the 12px mobile size; on a 375px
    screen that is 125px of overflow. The wrapper keeps it off the page."""
    page = render(peer_table=PEER_TABLE)

    assert f'<div class="{TABLE_SCROLL_CLASS}" tabindex="0"><table' in page
