import frontmatter

from app.deepdive.dossier_generator import _flag_str, generate_dossier
from app.deepdive.filing_parser import SectionFlag
from app.models.deep_dive_record import (
    DeepDiveRecord,
    FisherPoint,
    PointInTimeQuant,
    QuantSnapshot,
    SourceCoverage,
)


def _record(**over):
    pts = [
        FisherPoint(
            number=n,
            title=f"Punkt {n}",
            rating=4,
            confidence="🟢",
            reasoning="Begründung.",
            sources=["20-F §5"],
        )
        for n in range(1, 16)
    ]
    base = dict(
        ticker="NOVO-B.CO",
        adr_ticker="NVO",
        cik="0000353278",
        form_type="20-F",
        filing_sections={"20-F_item5": "x"},
        section_flags={},
        synthesis=pts,
        quant_snapshot=QuantSnapshot(
            point_in_time=PointInTimeQuant(ticker="NOVO-B.CO", name="Novo Nordisk")
        ),
        source_coverage=SourceCoverage(edgar="20-F via ADR"),
    )
    base.update(over)
    return DeepDiveRecord(**base)


def test_dossier_frontmatter_renders_composite_flag_string():
    flag = SectionFlag(extraction="ok", missing=False, truncated=True, anchor_id="x")
    assert _flag_str(flag) == "ok+truncated"
    flag2 = SectionFlag(
        extraction="fallback_used", missing=False, truncated=False, anchor_id=None
    )
    assert _flag_str(flag2) == "fallback_used"
    flag3 = SectionFlag(
        extraction="fallback_used", missing=True, truncated=False, anchor_id=None
    )
    assert _flag_str(flag3) == "fallback_used+missing"


def test_frontmatter_renders_section_flags_from_dataclass(tmp_path):
    rec = _record(
        section_flags={
            "20-F_item4": SectionFlag(
                extraction="ok", missing=False, truncated=False, anchor_id="a4"
            ),
            "20-F_item18": SectionFlag(
                extraction="fallback_used",
                missing=True,
                truncated=False,
                anchor_id=None,
            ),
        }
    )
    post = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    )
    assert post["section_flags"] == {
        "20-F_item4": "ok",
        "20-F_item18": "fallback_used+missing",
    }


def test_writes_file_with_date_name(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    assert p.parent.name == "Watchlist"
    assert p.name.startswith("NOVO-B.CO_")
    assert p.name.endswith(".md")


def test_frontmatter_and_15_miniblocks(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    post = frontmatter.loads(p.read_text(encoding="utf-8"))
    assert post["ticker"] == "NOVO-B.CO"
    assert post["form_type"] == "20-F"
    body = post.content
    for n in range(1, 16):
        assert f"### Punkt {n} —" in body
    assert "| # | Punkt |" not in body  # NOT a table
    assert "## Source Coverage" in body
    assert "20-F via ADR" in body
    assert "Stef's Notizen" in body


def test_each_point_renders_a_source_marker(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    body = frontmatter.loads(p.read_text(encoding="utf-8")).content
    assert body.count("[20-F §5]") == 15


def test_bewertung_formats_money_and_percent(tmp_path):
    rec = _record()
    rec.quant_snapshot.point_in_time.market_cap = 234567890000.0
    rec.quant_snapshot.point_in_time.currency = "DKK"
    rec.quant_snapshot.point_in_time.gross_margin = 0.836
    rec.quant_snapshot.point_in_time.operating_margin = 0.41
    body = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    ).content
    assert "234,567,890,000 DKK" in body
    assert "83.6%" in body
    assert "41.0%" in body


def test_frontmatter_has_vintage_fields(tmp_path):
    from datetime import datetime, timezone

    rec = _record(
        filing_date="2025-02-05",
        generated_at=datetime(2025, 5, 19, 12, 0, tzinfo=timezone.utc),
    )
    post = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    )
    assert post["filing_date"] == "2025-02-05"
    assert post["quant_date"] == "2025-05-19"
    assert post["days_since_filing"] == 103


def test_frontmatter_vintage_fields_none_when_no_filing_date(tmp_path):
    post = frontmatter.loads(
        generate_dossier(_record(), tmp_path).read_text(encoding="utf-8")
    )
    assert post["filing_date"] is None
    assert post["days_since_filing"] is None
    assert post["quant_date"]  # quant_date always present


def test_body_has_filing_stand_line(tmp_path):
    from datetime import datetime, timezone

    rec = _record(
        filing_date="2025-02-05",
        generated_at=datetime(2025, 5, 19, 12, 0, tzinfo=timezone.utc),
    )
    body = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    ).content
    assert (
        "*Filing-Stand: 2025-02-05 · Quant-Stand: 2025-05-19 · "
        "103 Tage Differenz — zwischenzeitliche Entwicklungen siehe "
        "Tool-B Scuttlebutt (B.3)*"
    ) in body
    # placed inside ## Bewertung, before the valuation block heading
    lines = body.splitlines()
    fs_idx = next(i for i, ln in enumerate(lines) if ln.startswith("*Filing-Stand:"))
    mc_idx = next(i for i, ln in enumerate(lines) if ln.startswith("*Market Cap:"))
    vb_idx = next(
        i
        for i, ln in enumerate(lines)
        if ln.startswith("## Bewertung & Kapitalstruktur")
    )
    assert mc_idx < fs_idx < vb_idx


def test_body_filing_stand_unknown_when_no_filing_date(tmp_path):
    body = frontmatter.loads(
        generate_dossier(_record(), tmp_path).read_text(encoding="utf-8")
    ).content
    quant_date = next(ln for ln in body.splitlines() if ln.startswith("*Filing-Stand:"))
    assert "Filing-Stand: unbekannt" in quant_date
    assert "Quant-Stand:" in quant_date


def test_valuation_gap_marked_honest(tmp_path):
    body = frontmatter.loads(
        generate_dossier(_record(), tmp_path).read_text(encoding="utf-8")
    ).content
    # Old roadmap valuation line + jargon must be gone entirely.
    assert "*KGV / EV-EBIT / FCF-Yield (aktuell vs. 5J):" not in body
    assert "folgt B.2 (KGV/EV-EBIT/FCF-Yield vs. 5J)" not in body
    # The valuation-coverage line itself no longer says "folgt B.2".
    bewertung_cov_line = next(
        ln for ln in body.splitlines() if ln.startswith("- Bewertungs-Kennzahlen:")
    )
    assert "folgt B.2" not in bewertung_cov_line
    # New SourceCoverage default text + new valuation block heading present.
    assert (
        "TTM + Mehrjahres-Median/Perzentil (KGV/EV-EBIT/FCF-Yield; "
        "Wochen-Preis × GJ-Fundamental, split-normalisiert; reale Tiefe "
        "~3J, da freie yfinance nur 4 GJ liefert — 5J+ via SEC-XBRL ist "
        "Phase-2); cross-currency Honest-Label-Skip; restated-Fassung"
    ) in body
    assert "Bewertungs-Kennzahlen" in body
    assert (
        "## Bewertung & Kapitalstruktur "
        "(TTM-Stand + Mehrjahres-Median/Perzentil-Vergleich)"
    ) in body


def test_valuation_block_derived_na_reason_in_dossier(tmp_path):
    rec = _record()  # pit has no enterprise_value
    body = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    ).content
    assert "EV/EBIT n/a (EV fehlt)" in body


def test_valuation_block_interest_coverage_fy_suffix(tmp_path):
    rec = _record()
    rec.quant_snapshot.point_in_time.ebit = 2.0e9
    rec.quant_snapshot.point_in_time.interest_expense = -1.0e8
    body = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    ).content
    assert "Interest Coverage 20.0× (FY)" in body


def test_valuation_block_tsy_formula_text(tmp_path):
    rec = _record()
    rec.quant_snapshot.point_in_time.dividend_yield = 0.024
    body = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    ).content
    assert "Total Shareholder Yield" in body
    assert "(Div 2.4% aktuell + Ø" in body
    assert "J Buyback" in body


from app.models.deep_dive_record import InsiderSummary, InsiderTransaction


def test_dossier_renders_insider_section_and_frontmatter(tmp_path):
    rec = _record(
        insider_summary=InsiderSummary(
            coverage_state="ok",
            n_filings_total=10,
            n_parsed=10,
            n_transactions_total=12,
            routine_count=11,
            significant_buys=[
                InsiderTransaction(
                    owner_name="Roe Sam",
                    role="CEO",
                    code="P",
                    bucket="buy",
                    value=200_000,
                    acquired_disposed="A",
                    significant=True,
                )
            ],
            net_buy_value=200_000.0,
            net_sell_value=0.0,
        )
    )
    post = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    )
    assert "## Insider-Transaktionen" in post.content
    assert "Form-4-Filings" in post.content
    assert post["insider_coverage_state"] == "ok"
    assert post["insider_n_filings"] == 10
    assert post["insider_significant_count"] == 1
    assert post["insider_net_buy"] == 200_000


def test_dossier_insider_frontmatter_none_when_absent(tmp_path):
    post = frontmatter.loads(
        generate_dossier(_record(), tmp_path).read_text(encoding="utf-8")
    )
    assert post["insider_coverage_state"] is None
    # default _record() has insider_summary=None -> section still present (FPI text)
    assert "## Insider-Transaktionen" in post.content


# --------------------------------------------------------------------------
# Quant-only dossier (no SEC filing source at all).
# --------------------------------------------------------------------------

import re

from app.deepdive.dossier_generator import FORM_TYPE_NO_SEC_SOURCE

_NO_SEC_NOTE = (
    "Kein SEC-Hard-Scuttlebutt: ENDEAVOUR MINING PLC ist kein SEC-Registrant. "
    "Dossier ist quant-only (Quant + Bewertung + Peers)."
)

# The viewer's own placeholder regex, duplicated on purpose: this file must fail
# when the generator's replacement drifts back into placeholder shape, without
# importing the viewer.
_VIEWER_PLACEHOLDER_RE = re.compile(r"\*\[.*\]\*", re.DOTALL)


def _quant_only_record(**over):
    base = dict(
        ticker="EDV.L",
        adr_ticker=None,
        cik=None,
        form_type=None,
        no_sec_source_reason="not_sec_registrant",
        no_sec_source_note=_NO_SEC_NOTE,
        filing_sections={},
        synthesis=[],
        insider_summary=InsiderSummary(coverage_state="no_sec_source"),
        source_coverage=SourceCoverage(edgar=_NO_SEC_NOTE),
        quant_snapshot=QuantSnapshot(
            point_in_time=PointInTimeQuant(ticker="EDV.L", name="Endeavour Mining")
        ),
    )
    base.update(over)
    return _record(**base)


def _body_and_meta(rec, tmp_path):
    post = frontmatter.loads(
        generate_dossier(rec, tmp_path).read_text(encoding="utf-8")
    )
    return post.content, post.metadata


def test_quant_only_dossier_frontmatter_is_valid_and_labelled(tmp_path):
    body, meta = _body_and_meta(_quant_only_record(), tmp_path)

    assert meta["ticker"] == "EDV.L"
    assert meta["form_type"] == FORM_TYPE_NO_SEC_SOURCE == "kein SEC-Filing"
    assert meta["cik"] is None
    assert meta["no_sec_source_reason"] == "not_sec_registrant"
    assert meta["no_sec_source_note"] == _NO_SEC_NOTE
    assert body  # front matter parsed cleanly, body is not empty


def test_quant_only_executive_summary_replaces_the_gemini_promise(tmp_path):
    """The normal placeholder promises Gemini will fill this in. Here Gemini
    structurally never runs, so the promise would be false — and the text must
    not match the viewer's placeholder regex, which would null it silently."""
    body, _ = _body_and_meta(_quant_only_record(), tmp_path)
    summary = body.split("## Executive Summary")[1].split("##")[0].strip()

    assert "Quant-only-Dossier" in summary
    assert _NO_SEC_NOTE in summary
    assert "bewusst kein Gemini-Lauf" in summary
    assert "[" not in summary  # the single load-bearing character
    assert _VIEWER_PLACEHOLDER_RE.fullmatch(summary) is None


def test_quant_only_vintage_line_says_kein_sec_filing_not_unbekannt(tmp_path):
    """ "unbekannt" would imply a filing whose date we merely lost."""
    body, _ = _body_and_meta(_quant_only_record(), tmp_path)
    vintage = next(ln for ln in body.splitlines() if ln.startswith("*Filing-Stand:"))

    assert "Filing-Stand: kein SEC-Filing" in vintage
    assert "unbekannt" not in vintage
    assert "Quant-Stand:" in vintage


def test_quant_only_points_section_states_the_skip(tmp_path):
    body, _ = _body_and_meta(_quant_only_record(), tmp_path)

    assert "## Fishers 15 Punkte" in body
    assert "### Punkt" not in body
    assert "Keine Punkte — die Synthese wurde übersprungen" in body


def test_quant_only_insider_and_edgar_coverage_carry_the_reason(tmp_path):
    body, _ = _body_and_meta(_quant_only_record(), tmp_path)

    assert f"- EDGAR: {_NO_SEC_NOTE}" in body
    assert "kein SEC-Registrant" in body.split("## Insider-Transaktionen")[1]


def test_normal_dossier_has_no_sec_source_fields_as_none(tmp_path):
    """Regression fence: the two new keys are additive and stay null for every
    dossier that does have a filing source."""
    _, meta = _body_and_meta(_record(), tmp_path)

    assert meta["form_type"] == "20-F"
    assert meta["no_sec_source_reason"] is None
    assert meta["no_sec_source_note"] is None
