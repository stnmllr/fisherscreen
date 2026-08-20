"""Tests for the site build.

The generator is the only part of the viewer that touches the filesystem,
so this is where the two file-level risks live: a ticker that is not a
legal filename (`ASML.AS`, `NOVO-B.CO`, historically `RDS/A`), and a
dossier that quietly fails to produce a page.

Everything writes to tmp_path — tests/conftest.py blocks writes below the
repo's output/.
"""
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from app.viewer.assets import CSS_FILENAME, JS_FILENAME
from app.viewer.models import Dossier
from app.viewer.render_overview import DUPLICATE_BADGE
from app.viewer.site_generator import generate_site, skipped_filenames

GENERATED_AT = datetime(2026, 8, 20, 13, 5, tzinfo=timezone.utc)

DOSSIER_TEXT = """---
ticker: {ticker}
form_type: 10-K
generated_at: '{generated_at}'
quant_date: '2026-01-01'
---

# Deep Dive: {ticker} Corp ({ticker})
"""


def make_dossier(ticker: str = "FICO", **overrides) -> Dossier:
    fields = {
        "ticker": ticker,
        "form_type": "10-K",
        "generated_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "quant_date": date(2026, 7, 1),
        "company_name": f"{ticker} Corporation",
        "points": [],
        "source_path": Path(f"{ticker}_2026-07-01.md"),
    }
    fields.update(overrides)
    return Dossier(**fields)


def build(tmp_path: Path, dossiers, **kwargs) -> Path:
    return generate_site(
        dossiers, tmp_path / "site", generated_at=GENERATED_AT, **kwargs
    )


def test_writes_index_and_both_assets(tmp_path):
    index = build(tmp_path, [make_dossier()])

    assert index.name == "index.html"
    assert index.exists()
    assert (index.parent / CSS_FILENAME).exists()
    assert (index.parent / JS_FILENAME).exists()


def test_returns_the_index_path(tmp_path):
    index = build(tmp_path, [make_dossier()])

    assert index == tmp_path / "site" / "index.html"


def test_creates_missing_parent_directories(tmp_path):
    index = generate_site(
        [make_dossier()], tmp_path / "deep" / "nested", generated_at=GENERATED_AT
    )

    assert index.exists()


def test_writes_one_detail_page_per_dossier(tmp_path):
    index = build(tmp_path, [make_dossier("FICO"), make_dossier("MSCI")])

    assert (index.parent / "ticker" / "FICO.html").exists()
    assert (index.parent / "ticker" / "MSCI.html").exists()


def test_keeps_dots_and_hyphens_in_filenames(tmp_path):
    """`ASML.AS` and `NOVO-B.CO` are legal filenames; renaming them would
    break the link the overview already writes."""
    index = build(tmp_path, [make_dossier("ASML.AS"), make_dossier("NOVO-B.CO")])

    assert (index.parent / "ticker" / "ASML.AS.html").exists()
    assert (index.parent / "ticker" / "NOVO-B.CO.html").exists()


def test_overview_links_resolve_to_the_written_files(tmp_path):
    index = build(tmp_path, [make_dossier("NOVO-B.CO")])

    assert 'href="ticker/NOVO-B.CO.html"' in index.read_text(encoding="utf-8")


def test_detail_page_is_the_rendered_dossier(tmp_path):
    index = build(tmp_path, [make_dossier("FICO")])
    page = (index.parent / "ticker" / "FICO.html").read_text(encoding="utf-8")

    assert "FICO Corporation" in page
    assert '<link rel="stylesheet" href="../site.css">' in page


def test_duplicate_company_names_are_flagged_on_the_overview(tmp_path):
    """Two runs of one company under different symbols stay separate rows —
    merging them would guess an identity nobody verified."""
    dossiers = [
        make_dossier("ASML", company_name="ASML Holding N.V."),
        make_dossier("ASML.AS", company_name="ASML Holding N.V."),
    ]
    index = build(tmp_path, dossiers)

    assert DUPLICATE_BADGE in index.read_text(encoding="utf-8")


def test_distinct_company_names_are_not_flagged(tmp_path):
    index = build(tmp_path, [make_dossier("FICO"), make_dossier("MSCI")])

    assert DUPLICATE_BADGE not in index.read_text(encoding="utf-8")


def test_skipped_files_are_named_on_the_overview(tmp_path):
    index = build(tmp_path, [make_dossier()], skipped=["ADYEN_OnePager.md"])

    assert "ADYEN_OnePager.md" in index.read_text(encoding="utf-8")


def test_empty_input_still_produces_a_page(tmp_path):
    """An empty site is a result too; failing to write would leave the last
    build standing and look current."""
    index = build(tmp_path, [])

    assert index.exists()


def test_generated_at_defaults_to_the_clock(tmp_path):
    """The default exists for the CLI; tests always inject."""
    index = generate_site([make_dossier()], tmp_path / "site")

    assert "Stand:" in index.read_text(encoding="utf-8")


def test_ticker_with_path_separator_is_skipped_not_written(tmp_path, caplog):
    """`RDS/A` cannot be a filename and its URL-encoded link would not
    resolve either. It is dropped loudly and named on the page instead of
    producing a dead link."""
    with caplog.at_level(logging.WARNING):
        index = build(tmp_path, [make_dossier("RDS/A"), make_dossier("FICO")])
    text = index.read_text(encoding="utf-8")

    assert not (index.parent / "ticker" / "A.html").exists()
    assert "RDS/A" in text
    assert "übersprungen" in text
    assert "RDS/A" in caplog.text


def test_unrepresentable_ticker_does_not_take_the_build_down(tmp_path):
    index = build(tmp_path, [make_dossier("RDS/A"), make_dossier("FICO")])

    assert (index.parent / "ticker" / "FICO.html").exists()


# --- skipped_filenames ----------------------------------------------------


def write_dossier(directory: Path, ticker: str, day: str, generated_at: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{ticker}_{day}.md").write_text(
        DOSSIER_TEXT.format(ticker=ticker, generated_at=generated_at),
        encoding="utf-8",
    )


def test_skipped_filenames_reports_unreadable_files(tmp_path):
    write_dossier(tmp_path, "FICO", "2026-07-01", "2026-07-01T00:00:00+00:00")
    (tmp_path / "ADYEN_OnePager_Executive_Summary_2026-07-02.md").write_text(
        "just prose", encoding="utf-8"
    )
    dossiers = [make_dossier("FICO", source_path=tmp_path / "FICO_2026-07-01.md")]

    assert skipped_filenames(tmp_path, dossiers) == [
        "ADYEN_OnePager_Executive_Summary_2026-07-02.md"
    ]


def test_skipped_filenames_ignores_superseded_runs(tmp_path):
    """An older run of the same ticker was deliberately dropped by the
    parser's de-duplication; calling it "skipped" would report a defect."""
    write_dossier(tmp_path, "FICO", "2026-06-18", "2026-06-18T00:00:00+00:00")
    write_dossier(tmp_path, "FICO", "2026-07-01", "2026-07-01T00:00:00+00:00")
    dossiers = [make_dossier("FICO", source_path=tmp_path / "FICO_2026-07-01.md")]

    assert skipped_filenames(tmp_path, dossiers) == []
