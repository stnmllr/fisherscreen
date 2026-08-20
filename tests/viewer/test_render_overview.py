"""Tests for the overview table.

Two invariants run through all of them:

* The displayed text is always the dossier's own string. Sorting gets a
  separate numeric attribute — deriving it is parsing, not computing.
* Everything that comes out of a dossier is untrusted and must be escaped.
"""
from datetime import date, datetime, timezone
from pathlib import Path

from app.viewer.html import TABLE_SCROLL_CLASS
from app.viewer.models import Dossier, ParsedPoint
from app.viewer.render_overview import (
    FRESHNESS_RED_DAYS,
    FRESHNESS_YELLOW_DAYS,
    build_overview_row,
    freshness_flag,
    render_overview,
    sort_key,
)

GENERATED_AT = datetime(2026, 8, 20, 13, 5, tzinfo=timezone.utc)


def row_of(**overrides):
    duplicates = overrides.pop("duplicate_names", set())
    return build_overview_row(make_dossier(**overrides), duplicate_names=duplicates)


def make_dossier(**overrides) -> Dossier:
    """A dossier with the shape the real files have, so tests state only
    what they are actually about."""
    fields = {
        "ticker": "ARGX",
        "form_type": "20-F",
        "generated_at": datetime(2026, 8, 20, 12, 56, tzinfo=timezone.utc),
        "filing_date": date(2026, 3, 19),
        "quant_date": date(2026, 8, 20),
        "days_since_filing": 154,
        "company_name": "argenx SE",
        "headline_metrics": {"Op. Margin": "32.0%", "Gross Margin": "59.1%"},
        "metrics": {"Bewertung": {"P/E fwd": "26.4", "FCF-Yield": "1.2%"}},
        "points": [],
        "source_path": Path("ARGX_2026-08-20.md"),
    }
    fields.update(overrides)
    return Dossier(**fields)


def rated(number: int, rating: int | None, confidence: str | None) -> ParsedPoint:
    return ParsedPoint(number=number, rating=rating, confidence=confidence)


def test_sort_key_parses_thousands_separator():
    assert sort_key("1,254.9") == 1254.9


def test_sort_key_parses_percentage():
    assert sort_key("32.0%") == 32.0


def test_sort_key_parses_value_with_unit_suffix():
    assert sort_key("314.2× (FY)") == 314.2


def test_sort_key_parses_negative_value():
    assert sort_key("-1.4%") == -1.4


def test_sort_key_returns_none_for_non_numeric():
    assert sort_key("n/a") is None
    assert sort_key("") is None


def test_sort_key_ignores_digits_that_follow_a_non_numeric_value():
    """`Total Shareholder Yield n/a (… Ø 5J Buyback n/a)` must not sort as 5:
    the number has to open the string, otherwise any stray digit in a
    footnote becomes the sort value."""
    assert sort_key("n/a (Div n/a aktuell + Ø 5J Buyback n/a)") is None


def test_row_links_to_the_detail_page_by_ticker():
    row = build_overview_row(make_dossier(ticker="ASML.AS"), duplicate_names=set())

    assert row.ticker == "ASML.AS"
    assert row.href == "ticker/ASML.AS.html"


def test_row_percent_encodes_a_ticker_that_is_not_url_safe():
    """Display text stays the original symbol; only the href is encoded."""
    row = build_overview_row(make_dossier(ticker="RDS/A"), duplicate_names=set())

    assert row.href == "ticker/RDS%2FA.html"
    assert row.ticker == "RDS/A"


def test_row_summarises_the_star_distribution():
    points = [
        rated(1, 5, "🟢"),
        rated(2, 5, "🟢"),
        rated(3, 4, "🟡"),
        rated(4, 3, "🔴"),
    ]
    row = build_overview_row(make_dossier(points=points), duplicate_names=set())

    assert row.star_summary == "2×★5 · 1×★4 · 1×★3"


def test_row_ignores_unrated_points_in_the_distribution():
    """Placeholder points carry no rating; counting them as a grade would
    invent 15 assessments out of two."""
    points = [rated(1, 4, "🟢"), rated(2, None, None)]
    row = build_overview_row(make_dossier(points=points), duplicate_names=set())

    assert row.star_summary == "1×★4"


def test_row_marks_an_entirely_unrated_dossier_as_missing():
    row = build_overview_row(make_dossier(points=[]), duplicate_names=set())

    assert row.star_summary is None


def test_row_counts_low_confidence_points():
    points = [rated(1, 5, "🟢"), rated(2, 3, "🔴"), rated(3, 2, "🔴")]
    row = build_overview_row(make_dossier(points=points), duplicate_names=set())

    assert row.red_count == 2


def test_row_takes_metrics_verbatim_from_the_dossier():
    row = build_overview_row(make_dossier(), duplicate_names=set())

    assert row.pe_fwd == "26.4"
    assert row.op_margin == "32.0%"
    assert row.fcf_yield == "1.2%"


def test_row_leaves_missing_metrics_empty():
    row = build_overview_row(
        make_dossier(metrics={}, headline_metrics={}), duplicate_names=set()
    )

    assert row.pe_fwd is None
    assert row.op_margin is None
    assert row.fcf_yield is None


def test_row_flags_a_repeated_company_name():
    """ASML ran once as `ASML` and once as `ASML.AS`. The viewer cannot prove
    the two symbols are one company, so it shows both rows and says so."""
    row = build_overview_row(
        make_dossier(ticker="ASML.AS", company_name="ASML Holding N.V."),
        duplicate_names={"ASML Holding N.V."},
    )

    assert row.is_duplicate_name is True


def test_row_without_a_repeated_name_is_not_flagged():
    row = build_overview_row(
        make_dossier(company_name="argenx SE"),
        duplicate_names={"ASML Holding N.V."},
    )

    assert row.is_duplicate_name is False


def test_row_without_company_name_is_not_flagged():
    """A dossier whose H1 did not parse has no identity to collide with."""
    row = build_overview_row(
        make_dossier(company_name=None), duplicate_names={"ASML Holding N.V."}
    )

    assert row.is_duplicate_name is False


def test_freshness_is_neutral_below_the_first_threshold():
    assert freshness_flag(FRESHNESS_YELLOW_DAYS - 1) == (None, None)


def test_freshness_turns_yellow_at_a_quarter():
    """Annual filings are older than 120 days most of the year, so yellow is
    a prompt to check, not a defect."""
    css_class, title = freshness_flag(FRESHNESS_YELLOW_DAYS)

    assert css_class == "age-yellow"
    assert "Quartal" in title


def test_freshness_turns_red_beyond_a_full_reporting_cycle():
    css_class, title = freshness_flag(FRESHNESS_RED_DAYS + 1)

    assert css_class == "age-red"
    assert "Berichtszyklus" in title


def test_freshness_of_unknown_age_is_neutral():
    assert freshness_flag(None) == (None, None)


def test_page_carries_header_title_and_back_link():
    page = render_overview([row_of()], generated_at=GENERATED_AT)

    assert "https://macro.stnmllr.com/" in page
    assert "Macro Risk Monitor" in page
    assert "Deep Dives" in page


def test_page_stamps_the_injected_time_and_is_byte_stable():
    """`generated_at` is injected, never read from the clock — otherwise two
    builds of the same input produce two different files."""
    first = render_overview([row_of()], generated_at=GENERATED_AT)
    second = render_overview([row_of()], generated_at=GENERATED_AT)

    assert first == second
    assert "2026-08-20 13:05" in first


def test_page_references_the_external_stylesheet_and_script():
    page = render_overview([row_of()], generated_at=GENERATED_AT)

    assert 'href="site.css"' in page
    assert 'src="sort.js"' in page


def test_page_links_each_row_to_its_detail_page():
    page = render_overview([row_of(ticker="ASML.AS")], generated_at=GENERATED_AT)

    assert 'href="ticker/ASML.AS.html"' in page
    assert ">ASML.AS<" in page


def test_page_prints_the_dossier_string_and_a_numeric_sort_value():
    """ARGX's broken EV/EBIT of 1,254.9 must appear exactly as written; the
    sort attribute is the parsed twin, not a replacement."""
    page = render_overview(
        [row_of(metrics={"Bewertung": {"P/E fwd": "1,254.9"}})],
        generated_at=GENERATED_AT,
    )

    assert ">1,254.9<" in page
    assert 'data-sort="1254.9"' in page


def test_page_marks_an_unsortable_cell_with_an_empty_sort_value():
    page = render_overview(
        [row_of(metrics={"Bewertung": {"P/E fwd": "n/a"}})],
        generated_at=GENERATED_AT,
    )

    assert 'data-sort=""' in page
    assert ">n/a<" in page


def test_page_shows_a_missing_metric_as_a_dash():
    page = render_overview(
        [row_of(metrics={}, headline_metrics={})], generated_at=GENERATED_AT
    )

    assert "—" in page


def test_page_flags_a_stale_filing_with_class_and_tooltip():
    page = render_overview([row_of(days_since_filing=154)], generated_at=GENERATED_AT)

    assert "age-yellow" in page
    assert "Quartal" in page


def test_page_does_not_flag_a_fresh_filing():
    page = render_overview([row_of(days_since_filing=30)], generated_at=GENERATED_AT)

    assert "age-yellow" not in page
    assert "age-red" not in page


def test_page_shows_the_duplicate_identity_badge():
    page = render_overview(
        [
            row_of(
                ticker="ASML.AS",
                company_name="ASML Holding N.V.",
                duplicate_names={"ASML Holding N.V."},
            )
        ],
        generated_at=GENERATED_AT,
    )

    assert "weiterer Lauf unter anderem Symbol" in page


def test_page_counts_low_confidence_points_in_its_own_column():
    points = [rated(1, 3, "🔴"), rated(2, 4, "🟢")]
    page = render_overview([row_of(points=points)], generated_at=GENERATED_AT)

    assert "🔴" in page
    assert 'data-sort="1"' in page


def test_page_lists_skipped_files_by_name():
    """Silently swallowing an unreadable file is the real danger here."""
    page = render_overview(
        [row_of()],
        generated_at=GENERATED_AT,
        skipped=["ADYEN_OnePager.md", "broken.md"],
    )

    assert "2 Dateien übersprungen" in page
    assert "ADYEN_OnePager.md" in page
    assert "broken.md" in page


def test_page_renders_a_dossier_without_a_filing_date():
    """Gen-1 dossiers carry no filing_date; the row must still render and
    must not claim a date."""
    page = render_overview([row_of(filing_date=None)], generated_at=GENERATED_AT)

    assert "20-F" in page
    assert "None" not in page


def test_page_renders_a_dossier_without_a_known_age():
    page = render_overview([row_of(days_since_filing=None)], generated_at=GENERATED_AT)

    assert "Tage" not in page
    assert "None" not in page


def test_page_renders_a_dossier_without_a_company_name():
    """The H1 did not parse — the ticker link is all the identity there is."""
    page = render_overview([row_of(company_name=None)], generated_at=GENERATED_AT)

    assert 'href="ticker/ARGX.html"' in page
    assert "None" not in page
    assert '<div class="t-sub">—</div>' not in page


def test_page_uses_singular_for_a_single_skipped_file():
    page = render_overview(
        [row_of()], generated_at=GENERATED_AT, skipped=["broken.md"]
    )

    assert "1 Datei übersprungen" in page


def test_page_says_nothing_about_skipped_files_when_there_are_none():
    page = render_overview([row_of()], generated_at=GENERATED_AT)

    assert "übersprungen" not in page


def test_page_states_an_empty_result_instead_of_showing_a_bare_table():
    page = render_overview([], generated_at=GENERATED_AT)

    assert "Keine Dossiers" in page


def test_page_keeps_the_given_row_order():
    page = render_overview(
        [row_of(ticker="ARGX"), row_of(ticker="MSFT")], generated_at=GENERATED_AT
    )

    assert page.index("ARGX") < page.index("MSFT")


def test_page_escapes_markup_from_dossier_content():
    """Company names and metrics are Gemini output plus hand-written notes —
    nothing between generator and browser validates them."""
    payload = "<script>alert(1)</script>"
    page = render_overview(
        [
            row_of(
                company_name=payload,
                metrics={"Bewertung": {"P/E fwd": payload}},
                headline_metrics={"Op. Margin": payload},
            )
        ],
        generated_at=GENERATED_AT,
    )

    assert "<script>" not in page
    assert "alert(1)" not in page.replace("&lt;script&gt;alert(1)&lt;/script&gt;", "")
    assert page.count("&lt;script&gt;alert(1)&lt;/script&gt;") == 3


def test_overview_table_sits_in_a_scroll_container():
    """Eight columns do not fit a phone viewport. Without the wrapper the
    whole page scrolls sideways instead of the table alone — the spec asks
    for the opposite, and the pages are read on a phone."""
    page = render_overview([row_of()], generated_at=GENERATED_AT)

    assert f'<div class="{TABLE_SCROLL_CLASS}" tabindex="0"><table' in page
