"""Parser tests against inline fixtures — one per dossier generation.

Why inline instead of the real files: the newer dossiers under output/ are
gitignored, so CI has nothing to read. The real-file tests below are marked
`integration` and excluded in CI (-m "not integration").

Generations (verified against output/Watchlist/):
  Gen 1 (2026-05-20)  no insider frontmatter, no insider section, no
                      Bewertungs-Range line, valuation heading variant
                      "(TTM-Stand, ohne historischen 5J-Vergleich)"
  Gen 2 (2026-06-01)  Bewertungs-Range line present, still no insider
  Gen 3 (2026-07+)    insider frontmatter + "## Insider-Transaktionen"
"""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.viewer.dossier_parser import parse_dossier

GEN3_MARKDOWN = """---
adr_ticker: null
cik: 0001697862
days_since_filing: 154
filing_date: '2026-03-19'
form_type: 20-F
generated_at: '2026-08-20T12:56:48.951855+00:00'
insider_coverage_state: fpi_exempt
insider_n_filings: 0
insider_net_buy: 0.0
insider_net_sell: 0.0
insider_significant_count: 0
peer_rationale: null
peer_tickers:
- ALNY
- NBIX
quant_date: '2026-08-20'
section_flags:
  20-F_item5: ok
ticker: ARGX
---

# Deep Dive: argenx SE (ARGX)

## Executive Summary
*[3 Sätze: Kern-These + Hauptrisiko + Empfehlung — von Gemini in B.1+ befüllt; \
B.1 Durchstich nutzt die 15 Mini-Blöcke als Substanz.]*

## Bewertung
*Market Cap: 64,616,747,008 USD · Gross Margin: 59.1% · Op. Margin: 32.0%*

*Filing-Stand: 2026-03-19 · Quant-Stand: 2026-08-20 · 154 Tage Differenz — \
zwischenzeitliche Entwicklungen siehe Tool-B Scuttlebutt (B.3)*

## Bewertung & Kapitalstruktur (TTM-Stand + Mehrjahres-Median/Perzentil-Vergleich)

Bewertung: P/E trail. 39.4 · P/E fwd 26.4 · EV/EBIT 1254.9 · EV/Sales 387.6 · \
FCF-Yield 1.2% · Div-Yield n/a · Payout 0.0%
Bewertungs-Range (~1J, 66 Wo): P/E TTM 39.4 vs Median 51.9 (25-Perz. 44.9) · \
EV/EBIT TTM 1254.9 vs Median 476.3 (25-Perz. 397.1) · FCF-Yield TTM 1.2% vs \
Median -1.4% (25-Perz. -3.6%)
Kapitalstruktur: Total Debt 47,000,000 USD · Cash 5,184,000,000 USD · D/E 0.6 · \
Current Ratio 5.1 · Interest Coverage 314.2× (FY) · Total Shareholder Yield n/a \
(Div n/a aktuell + Ø 5J Buyback n/a)
Analyst Consensus: strong_buy · Target: 1098.32 (Median 1100.0) · 22 Analysten · \
Upside 6.3%
Forward-Konsens: Revenue 46.4% (lfd. GJ), 22.9% (Folge-GJ) · EPS 47.9% (lfd. GJ)
Peer-Vergleich (Nutzer-Auswahl):
| Ticker | P/E tr. | P/E fwd | Op-Margin | Gross-M. | Rev-Growth (yoy) | FCF-Yield |
|--------|--------:|--------:|----------:|---------:|-----------------:|----------:|
| ARGX | 39.4 | 26.4 | 32.0% | 59.1% | 59.3% | 1.2% |
| ALNY | 42.2 | 19.3 | 17.9% | 79.7% | 66.9% | 0.8% |

## Insider-Transaktionen
**Insider-Transaktionen:** nicht anwendbar (Foreign Private Issuer, \
Section-16-exempt — kein Form-4).

## Fishers 15 Punkte

### Punkt 1 — Marktpotential für mehrjährige Umsatzzuwächse
**Bewertung:** ⭐⭐⭐⭐⭐ · **Confidence:** 🟢

ARGX zeigt enormes Wachstumspotenzial [nicht am Ende zählt nicht] und eine \
tiefe Pipeline. [20-F §5] [yfinance, 5J]

### Punkt 2 — Management-Determination für neue Produkte/Services
**Bewertung:** ⭐⭐⭐ · **Confidence:** 🟡

Die Entschlossenheit des Managements wird explizit untermauert. [20-F §5]

## Source Coverage

- EDGAR: 20-F (US direct)
- Quant (Punkt-in-Zeit): live-yfinance
- Währung: konsistent

## Stef's Notizen

*[Leer — Stef füllt manuell in Obsidian]*
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_parses_frontmatter_core_fields(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.ticker == "ARGX"
    assert dossier.form_type == "20-F"
    assert dossier.generated_at == datetime(
        2026, 8, 20, 12, 56, 48, 951855, tzinfo=timezone.utc
    )
    assert dossier.filing_date == date(2026, 3, 19)
    assert dossier.quant_date == date(2026, 8, 20)
    assert dossier.days_since_filing == 154
    assert dossier.adr_ticker is None
    assert dossier.peer_tickers == ["ALNY", "NBIX"]
    assert dossier.section_flags == {"20-F_item5": "ok"}
    assert dossier.insider_coverage_state == "fpi_exempt"
    assert dossier.insider_n_filings == 0
    assert dossier.source_path.name == "ARGX_2026-08-20.md"


def test_parses_company_name_from_h1(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.company_name == "argenx SE"


def test_parses_headline_metrics_from_bewertung_section(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.headline_metrics == {
        "Market Cap": "64,616,747,008 USD",
        "Gross Margin": "59.1%",
        "Op. Margin": "32.0%",
    }


ONE_PAGER_MARKDOWN = """# Adyen N.V. (ADYEN.AS) — Executive Summary
*One-Pager · Stand 2026-07-02 · Quelle: Q1-2026-Update*

## Kern-These (3 Sätze)

Adyen ist eine selbstgebaute Single-Platform für den globalen Zahlungsverkehr.
"""


def test_one_pager_is_filtered_out(tmp_path):
    """Same directory, no frontmatter, different structure — must not be
    mistaken for a dossier."""
    path = _write(
        tmp_path,
        "ADYEN_OnePager_Executive_Summary_2026-07-02.md",
        ONE_PAGER_MARKDOWN,
    )

    assert parse_dossier(path) is None


def test_gitkeep_is_filtered_out(tmp_path):
    assert parse_dossier(_write(tmp_path, ".gitkeep", "")) is None


def test_file_without_dossier_frontmatter_is_filtered_out(tmp_path):
    """Correct filename shape, but frontmatter lacks ticker/form_type."""
    text = "---\ntitle: Notizen\n---\n\n# Irgendwas\n"

    assert parse_dossier(_write(tmp_path, "XYZ_2026-07-01.md", text)) is None


KO_H1_MARKDOWN = """---
form_type: 10-K
generated_at: '2026-05-26T08:00:00+00:00'
ticker: KO
---

# Deep Dive: Coca-Cola Company (The) (KO)

## Executive Summary
Kurz.
"""


def test_company_name_keeps_inner_parentheses(tmp_path):
    """Real case KO_2026-05-26.md: the company name itself carries a
    parenthesised suffix. The LAST group is the ticker, everything before
    it is the name."""
    dossier = parse_dossier(_write(tmp_path, "KO_2026-05-26.md", KO_H1_MARKDOWN))

    assert dossier is not None
    assert dossier.company_name == "Coca-Cola Company (The)"


LONG_TITLE_MARKDOWN = """---
form_type: 10-K
generated_at: '2026-06-01T08:46:07.627842+00:00'
ticker: GOOGL
---

# Deep Dive: Alphabet Inc. (GOOGL)

## Fishers 15 Punkte

### Punkt 1 — Verfügt das Unternehmen über Produkte oder Dienstleistungen mit \
ausreichendem Marktpotenzial für mehrjährige Umsatzzuwächse?
**Bewertung:** ⭐⭐⭐⭐ · **Confidence:** 🔴

Alphabet hat Runway. [10-K Item 1]
"""


def test_parses_point_rating_from_stars(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.points[0].rating == 5
    assert dossier.points[1].rating == 3


def test_parses_point_confidence(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.points[0].confidence == "🟢"
    assert dossier.points[1].confidence == "🟡"


def test_sources_split_from_reasoning_only_at_the_end(tmp_path):
    """Trailing [..] markers are provenance; a bracket inside the prose is
    prose and must stay in the reasoning."""
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    point = dossier.points[0]
    assert point.sources == ["20-F §5", "yfinance, 5J"]
    assert point.reasoning == (
        "ARGX zeigt enormes Wachstumspotenzial [nicht am Ende zählt nicht] "
        "und eine tiefe Pipeline."
    )


def test_points_are_padded_to_fifteen(tmp_path):
    """A dossier with only 2 points must not crash and must not shrink the
    list — missing numbers become flagged placeholders."""
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert [p.number for p in dossier.points] == list(range(1, 16))
    assert [p.is_placeholder for p in dossier.points[:2]] == [False, False]

    filler = dossier.points[4]
    assert filler.is_placeholder is True
    assert filler.title == "Lohnende Gewinnmargen"
    assert filler.rating is None
    assert filler.confidence is None
    assert filler.reasoning is None
    assert filler.sources == []


def test_present_point_keeps_its_own_title(tmp_path):
    """FISHER_POINTS is a fallback for missing numbers only. Gemini-authored
    long titles (Gen 2) must survive verbatim."""
    dossier = parse_dossier(
        _write(tmp_path, "GOOGL_2026-06-01.md", LONG_TITLE_MARKDOWN)
    )

    assert dossier is not None
    assert dossier.points[0].title == (
        "Verfügt das Unternehmen über Produkte oder Dienstleistungen mit "
        "ausreichendem Marktpotenzial für mehrjährige Umsatzzuwächse?"
    )
    assert dossier.points[0].is_placeholder is False


FILLED_PROSE_MARKDOWN = """---
form_type: 10-K
generated_at: '2026-07-01T21:11:46.023247+00:00'
ticker: MSCI
---

# Deep Dive: MSCI Inc. (MSCI)

## Executive Summary
MSCI verdient an Index-Lizenzen. Hauptrisiko ist ETF-Gebührendruck.
Empfehlung: beobachten.

## Stef's Notizen

Erste Tranche bei 480 USD gekauft.
"""


def test_placeholder_executive_summary_is_none(tmp_path):
    """`*[3 Sätze: …]*` is the generator's unfilled placeholder, not content."""
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.executive_summary is None


def test_placeholder_notes_is_none(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.notes is None


def test_filled_executive_summary_and_notes_are_kept(tmp_path):
    dossier = parse_dossier(
        _write(tmp_path, "MSCI_2026-07-01.md", FILLED_PROSE_MARKDOWN)
    )

    assert dossier is not None
    assert dossier.executive_summary == (
        "MSCI verdient an Index-Lizenzen. Hauptrisiko ist ETF-Gebührendruck.\n"
        "Empfehlung: beobachten."
    )
    assert dossier.notes == "Erste Tranche bei 480 USD gekauft."


def test_parse_metric_line_longest_known_prefix_wins():
    from app.viewer.dossier_parser import _VALUATION_LABELS, parse_metric_line

    known, extras = parse_metric_line(
        "Bewertung: P/E trail. 39.4 · P/E fwd 26.4 · Payout 0.0%",
        _VALUATION_LABELS,
    )

    assert known == {"P/E trail.": "39.4", "P/E fwd": "26.4", "Payout": "0.0%"}
    assert extras == []


def test_parse_metric_line_keeps_unknown_segments():
    """A metric the vocabulary does not know must stay retrievable —
    otherwise a new generator field vanishes silently."""
    from app.viewer.dossier_parser import _VALUATION_LABELS, parse_metric_line

    known, extras = parse_metric_line(
        "Bewertung: P/E trail. 39.4 · PEG 1.8 · Rule of 40 62%",
        _VALUATION_LABELS,
    )

    assert known == {"P/E trail.": "39.4"}
    assert extras == ["PEG 1.8", "Rule of 40 62%"]


def test_parse_metric_line_strips_colon_after_label():
    from app.viewer.dossier_parser import _CONSENSUS_LABELS, parse_metric_line

    known, extras = parse_metric_line(
        "Analyst Consensus: strong_buy · Target: 1098.32 (Median 1100.0) · "
        "22 Analysten · Upside 6.3%",
        _CONSENSUS_LABELS,
    )

    assert known == {"Target": "1098.32 (Median 1100.0)", "Upside": "6.3%"}
    assert extras == ["strong_buy", "22 Analysten"]


def test_metrics_are_keyed_by_line_label(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.metrics["Bewertung"]["EV/Sales"] == "387.6"
    assert dossier.metrics["Bewertung"]["Div-Yield"] == "n/a"
    assert dossier.metrics["Kapitalstruktur"]["Cash"] == "5,184,000,000 USD"
    assert dossier.metrics["Kapitalstruktur"]["Interest Coverage"] == "314.2× (FY)"
    assert dossier.metrics["Bewertungs-Range"]["EV/EBIT"] == (
        "TTM 1254.9 vs Median 476.3 (25-Perz. 397.1)"
    )
    assert dossier.metrics["Forward-Konsens"]["EPS"] == "47.9% (lfd. GJ)"


def test_raw_metric_lines_keep_the_full_original_line(tmp_path):
    """The parenthesised span ("~1J, 66 Wo") is part of the honest label and
    must not be lost by keying on the bare label."""
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.raw_metric_lines["Bewertungs-Range"].startswith(
        "Bewertungs-Range (~1J, 66 Wo): P/E TTM 39.4"
    )
    assert "Peer-Vergleich" in dossier.raw_metric_lines


def test_unknown_metric_segment_reaches_metric_extras(tmp_path):
    text = GEN3_MARKDOWN.replace(
        "Bewertung: P/E trail. 39.4 ·", "Bewertung: PEG 1.8 · P/E trail. 39.4 ·"
    )
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", text))

    assert dossier is not None
    assert dossier.metric_extras["Bewertung"] == ["PEG 1.8"]
    assert dossier.metrics["Bewertung"]["P/E trail."] == "39.4"


def test_implausible_metric_value_is_passed_through_unchanged(tmp_path):
    """Pre-2026-06-01 dossiers carry the yfinance dividend-yield percent
    glitch (23.0% instead of ~0.2%). Correcting it here would rewrite
    history; the parser passes it through verbatim."""
    text = GEN3_MARKDOWN.replace("Div-Yield n/a", "Div-Yield 23.0%")
    dossier = parse_dossier(_write(tmp_path, "GOOGL_2026-06-01.md", text))

    assert dossier is not None
    assert dossier.metrics["Bewertung"]["Div-Yield"] == "23.0%"


def test_peer_table_rows_without_separator_row(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.peer_table[0] == [
        "Ticker",
        "P/E tr.",
        "P/E fwd",
        "Op-Margin",
        "Gross-M.",
        "Rev-Growth (yoy)",
        "FCF-Yield",
    ]
    assert dossier.peer_table[1] == [
        "ARGX", "39.4", "26.4", "32.0%", "59.1%", "59.3%", "1.2%",
    ]
    assert len(dossier.peer_table) == 3


GEN1_MARKDOWN = """---
adr_ticker: ASML
cik: 0000937966
days_since_filing: 84
filing_date: '2026-02-25'
form_type: 20-F
generated_at: '2026-05-20T10:57:11.139433+00:00'
peer_rationale: Semi-Equipment-Direktwettbewerber
peer_tickers:
- AMAT
quant_date: '2026-05-20'
section_flags:
  20-F_item4: missing
ticker: ASML
---

# Deep Dive: ASML Holding N.V. - New York Re (ASML)

## Executive Summary
*[3 Sätze: Kern-These + Hauptrisiko + Empfehlung — von Gemini in B.1+ befüllt.]*

## Bewertung
*Market Cap: 578,824,110,080 USD · Gross Margin: 52.6% · Op. Margin: 36.0%*

*Filing-Stand: 2026-02-25 · Quant-Stand: 2026-05-20 · 84 Tage Differenz*

## Bewertung & Kapitalstruktur (TTM-Stand, ohne historischen 5J-Vergleich)

Bewertung: P/E trail. 49.5 · P/E fwd 31.5 · EV/EBIT 49.7 · EV/Sales 17.5 · \
FCF-Yield 1.4% · Div-Yield 59.0% · Payout 25.8%
Kapitalstruktur: Total Debt 2,705,600,000 USD · Cash 8,376,300,032 USD · \
D/E 13.0 · Current Ratio 1.4 · Interest Coverage 97.4× (FY) · \
Total Shareholder Yield n/a (Div 59.0% aktuell + Ø 5J Buyback n/a)
Peer-Begründung (Nutzer): "Semi-Equipment-Direktwettbewerber"

## Fishers 15 Punkte

### Punkt 1 — Marktpotential für mehrjährige Umsatzzuwächse
**Bewertung:** ⭐⭐⭐⭐⭐ · **Confidence:** 🟡

ASML ist durch seine EUV-Monopolstellung zentral. [Inferenz]

## Source Coverage

- EDGAR: 20-F via ADR
- Quant (Punkt-in-Zeit): tool-a-cache
- Währung: financialCurrency EUR != Listing-Währung USD

## Stef's Notizen

*[Leer — Stef füllt manuell in Obsidian]*
"""

INSIDER_MARKDOWN = """---
form_type: 10-K
generated_at: '2026-06-01T09:00:00+00:00'
insider_coverage_state: ok
insider_n_filings: 122
insider_significant_count: 19
ticker: MSFT
---

# Deep Dive: Microsoft Corporation (MSFT)

## Insider-Transaktionen
**Insider-Transaktionen:** 122 Form-4-Filings · darin 149 Transaktionen → \
19 signifikant (2 Käufe, 17 Verkäufe) · 1 immateriell · 129 Routine (A/M/F/G)
- STANTON JOHN W (Director) 2026-02-18: P 5,000 @ 397.35 = 1,986,750 (ungeplant)
- SMITH BRADFORD L (Officer) — 2 signifikante Transaktionen:
  - 2025-04-23: P 3,842 @ 377.465 = 1,450,221 (ungeplant)
  - 2025-04-30: S 30 @ 390.5729 = 11,717 (ungeplant)

## Fishers 15 Punkte
"""


def test_gen1_dossier_without_insider_section_parses(tmp_path):
    """Gen 1 has neither insider frontmatter nor an insider section, and a
    different valuation heading suffix — it must still parse."""
    dossier = parse_dossier(_write(tmp_path, "ASML_2026-05-20.md", GEN1_MARKDOWN))

    assert dossier is not None
    assert dossier.insider_summary_line is None
    assert dossier.insider_detail_lines == []
    assert dossier.insider_coverage_state is None
    assert dossier.company_name == "ASML Holding N.V. - New York Re"
    assert dossier.metrics["Bewertung"]["P/E trail."] == "49.5"
    assert "Bewertungs-Range" not in dossier.metrics
    assert dossier.peer_rationale == "Semi-Equipment-Direktwettbewerber"
    assert len(dossier.points) == 15


def test_insider_summary_line_split_from_detail_lines(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "MSFT_2026-06-01.md", INSIDER_MARKDOWN))

    assert dossier is not None
    assert dossier.insider_summary_line == (
        "122 Form-4-Filings · darin 149 Transaktionen → 19 signifikant "
        "(2 Käufe, 17 Verkäufe) · 1 immateriell · 129 Routine (A/M/F/G)"
    )
    assert len(dossier.insider_detail_lines) == 4
    assert dossier.insider_detail_lines[0].startswith("- STANTON JOHN W (Director)")
    assert dossier.insider_detail_lines[3].startswith("  - 2025-04-30:")


def test_fpi_insider_line_has_no_detail_lines(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", GEN3_MARKDOWN))

    assert dossier is not None
    assert dossier.insider_summary_line is not None
    assert dossier.insider_summary_line.startswith("nicht anwendbar (Foreign Private")
    assert dossier.insider_detail_lines == []


def test_source_coverage_is_parsed_into_a_mapping(tmp_path):
    dossier = parse_dossier(_write(tmp_path, "ASML_2026-05-20.md", GEN1_MARKDOWN))

    assert dossier is not None
    assert dossier.source_coverage == {
        "EDGAR": "20-F via ADR",
        "Quant (Punkt-in-Zeit)": "tool-a-cache",
        "Währung": "financialCurrency EUR != Listing-Währung USD",
    }


BROKEN_FRONTMATTER_MARKDOWN = """---
ticker: [ARGX
form_type: 10-K
---

# Deep Dive: Kaputt AG (KPT)
"""


def _write_run(tmp_path: Path, ticker: str, day: str) -> Path:
    """Minimal dossier for one run of `ticker` on `day`."""
    text = (
        "---\n"
        "form_type: 10-K\n"
        f"generated_at: '{day}T08:00:00+00:00'\n"
        f"ticker: {ticker}\n"
        "---\n\n"
        f"# Deep Dive: {ticker} Inc. ({ticker})\n"
    )
    return _write(tmp_path, f"{ticker}_{day}.md", text)


def test_iter_dossiers_keeps_only_the_newest_run_per_ticker(tmp_path):
    from app.viewer.dossier_parser import iter_dossiers

    _write_run(tmp_path, "MSFT", "2026-05-27")
    _write_run(tmp_path, "MSFT", "2026-06-01")
    _write_run(tmp_path, "MSFT", "2026-05-28")

    dossiers = iter_dossiers(tmp_path)

    assert [d.source_path.name for d in dossiers] == ["MSFT_2026-06-01.md"]


def test_iter_dossiers_sorted_by_ticker(tmp_path):
    from app.viewer.dossier_parser import iter_dossiers

    _write_run(tmp_path, "MSFT", "2026-06-01")
    _write_run(tmp_path, "ARGX", "2026-08-20")
    _write_run(tmp_path, "FICO", "2026-07-01")

    assert [d.ticker for d in iter_dossiers(tmp_path)] == ["ARGX", "FICO", "MSFT"]


def test_iter_dossiers_skips_only_the_broken_file(tmp_path):
    """One unparseable dossier must not take the whole build down."""
    from app.viewer.dossier_parser import iter_dossiers

    _write(tmp_path, "KPT_2026-07-01.md", BROKEN_FRONTMATTER_MARKDOWN)
    _write_run(tmp_path, "MSFT", "2026-06-01")

    assert [d.ticker for d in iter_dossiers(tmp_path)] == ["MSFT"]


def test_iter_dossiers_ignores_foreign_files(tmp_path):
    from app.viewer.dossier_parser import iter_dossiers

    _write(
        tmp_path,
        "ADYEN_OnePager_Executive_Summary_2026-07-02.md",
        ONE_PAGER_MARKDOWN,
    )
    _write(tmp_path, ".gitkeep", "")
    _write_run(tmp_path, "MSFT", "2026-06-01")

    assert [d.ticker for d in iter_dossiers(tmp_path)] == ["MSFT"]


def test_iter_dossiers_tolerates_naive_generated_at(tmp_path):
    """A hand-edited, unquoted `generated_at` parses as a naive datetime.
    Comparing it with an aware one must not raise — it is read as UTC."""
    from app.viewer.dossier_parser import iter_dossiers

    _write_run(tmp_path, "MSFT", "2026-06-01")
    _write(
        tmp_path,
        "MSFT_2026-06-02.md",
        "---\nform_type: 10-K\ngenerated_at: 2026-06-02 08:00:00\nticker: MSFT\n---\n\n"
        "# Deep Dive: Microsoft Corporation (MSFT)\n",
    )

    dossiers = iter_dossiers(tmp_path)

    assert [d.source_path.name for d in dossiers] == ["MSFT_2026-06-02.md"]


def test_iter_dossiers_raises_on_missing_directory(tmp_path):
    """A missing input directory is a build-level defect, not a per-file one
    — fail loud instead of silently producing an empty site."""
    from app.errors import ViewerError
    from app.viewer.dossier_parser import iter_dossiers

    with pytest.raises(ViewerError):
        iter_dossiers(tmp_path / "does-not-exist")


# --- integration: the real, partly gitignored dossiers under output/ ---

_WATCHLIST_DIR = Path(__file__).resolve().parents[2] / "output" / "Watchlist"

_real_dossiers_present = pytest.mark.skipif(
    not _WATCHLIST_DIR.is_dir(),
    reason="output/Watchlist/ not present (dossiers are gitignored)",
)


@pytest.mark.integration
@_real_dossiers_present
def test_real_watchlist_parses_every_dossier():
    """23 of the 25 .md files are dossiers; the 2 one-pagers are not."""
    from app.viewer.dossier_parser import iter_dossiers

    parsed = [parse_dossier(p) for p in sorted(_WATCHLIST_DIR.glob("*.md"))]
    dossiers = [d for d in parsed if d is not None]

    assert len(dossiers) == 23
    assert all(len(d.points) == 15 for d in dossiers)
    assert all(d.company_name for d in dossiers)

    newest = iter_dossiers(_WATCHLIST_DIR)
    assert [d.ticker for d in newest] == [
        "ARGX",
        "ASML",
        "ASML.AS",
        "FICO",
        "GOOGL",
        "KO",
        "MEDP",
        "MSCI",
        "MSFT",
        "NOVO-B.CO",
    ]


@pytest.mark.integration
@_real_dossiers_present
def test_real_ko_company_name_keeps_parenthesised_suffix():
    dossier = parse_dossier(_WATCHLIST_DIR / "KO_2026-05-26.md")

    assert dossier is not None
    assert dossier.company_name == "Coca-Cola Company (The)"


@pytest.mark.integration
@_real_dossiers_present
def test_real_gen3_argx():
    dossier = parse_dossier(_WATCHLIST_DIR / "ARGX_2026-08-20.md")

    assert dossier is not None
    assert dossier.company_name == "argenx SE"
    assert dossier.insider_coverage_state == "fpi_exempt"
    assert dossier.insider_detail_lines == []
    assert dossier.headline_metrics["Market Cap"] == "64,616,747,008 USD"
    assert dossier.metrics["Bewertung"]["P/E trail."] == "39.4"
    assert dossier.peer_table[0][0] == "Ticker"
    assert dossier.points[0].rating == 5
    assert dossier.points[0].sources == ["20-F §5", "yfinance, 5J"]


@pytest.mark.integration
@_real_dossiers_present
def test_real_gen3_fico_large_insider_block():
    dossier = parse_dossier(_WATCHLIST_DIR / "FICO_2026-07-01.md")

    assert dossier is not None
    assert dossier.insider_summary_line is not None
    assert dossier.insider_summary_line.startswith("48 Form-4-Filings")
    assert len(dossier.insider_detail_lines) > 100
    assert dossier.insider_significant_count == 127


@pytest.mark.integration
@_real_dossiers_present
def test_real_gen1_asml_without_insider_section():
    dossier = parse_dossier(_WATCHLIST_DIR / "ASML_2026-05-20.md")

    assert dossier is not None
    assert dossier.insider_summary_line is None
    assert dossier.insider_detail_lines == []
    assert dossier.insider_coverage_state is None
    assert "Bewertungs-Range" not in dossier.metrics
    assert dossier.metrics["Bewertung"]["Div-Yield"] == "59.0%"
    assert dossier.metrics["Kapitalstruktur"]["Current Ratio"] == "1.4"


@pytest.mark.integration
@_real_dossiers_present
def test_real_gen2_googl_keeps_long_point_titles():
    dossier = parse_dossier(_WATCHLIST_DIR / "GOOGL_2026-06-01.md")

    assert dossier is not None
    assert all(not p.is_placeholder for p in dossier.points)
    assert len(dossier.points[0].title or "") > 40
    assert dossier.metrics["Bewertungs-Range"]["P/E"].startswith("TTM 29.0")


@pytest.mark.integration
@_real_dossiers_present
def test_real_dossiers_have_no_unknown_valuation_or_capital_segments():
    """Guard against a new metric being added to the generator without the
    viewer's vocabulary noticing."""
    unknown: dict[str, list[str]] = {}
    for path in sorted(_WATCHLIST_DIR.glob("*.md")):
        dossier = parse_dossier(path)
        if dossier is None:
            continue
        for line_label in ("Bewertung", "Kapitalstruktur", "Bewertungs-Range"):
            extras = dossier.metric_extras.get(line_label)
            if extras:
                unknown[f"{path.name}:{line_label}"] = extras

    assert unknown == {}


# --- robustness: defensive branches of the parser ---


def test_undecodable_file_is_skipped(tmp_path):
    path = tmp_path / "BIN_2026-07-01.md"
    path.write_bytes(b"\xff\xfe\x00 not utf-8 \xff")

    assert parse_dossier(path) is None


def test_dossier_without_h1_has_no_company_name(tmp_path):
    text = "---\nform_type: 10-K\ngenerated_at: '2026-07-01T08:00:00+00:00'\n"
    text += "ticker: XYZ\n---\n\n## Executive Summary\nKurz.\n"

    dossier = parse_dossier(_write(tmp_path, "XYZ_2026-07-01.md", text))

    assert dossier is not None
    assert dossier.company_name is None


def test_bewertung_section_without_headline_line(tmp_path):
    """Only the vintage line, no `*Market Cap: …*` — no fabricated metrics."""
    text = GEN3_MARKDOWN.replace(
        "*Market Cap: 64,616,747,008 USD · Gross Margin: 59.1% · "
        "Op. Margin: 32.0%*",
        "",
    )

    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", text))

    assert dossier is not None
    assert dossier.headline_metrics == {}


def test_valuation_lines_without_label_are_ignored(tmp_path):
    """Prose or a colon-less line inside the valuation block must not
    produce a bogus metric key."""
    text = GEN3_MARKDOWN.replace(
        "Analyst Consensus: strong_buy",
        "Hinweis ohne Doppelpunkt\n: fuehrender Doppelpunkt\n"
        "Analyst Consensus: strong_buy",
    )

    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", text))

    assert dossier is not None
    assert "Hinweis ohne Doppelpunkt" not in dossier.raw_metric_lines
    assert "" not in dossier.raw_metric_lines
    assert dossier.metrics["Analyst Consensus"]["Upside"] == "6.3%"


def test_source_coverage_bullet_without_colon_is_ignored(tmp_path):
    text = GEN3_MARKDOWN.replace(
        "- EDGAR: 20-F (US direct)", "- freie Notiz ohne Trenner\n- EDGAR: 20-F"
    )

    dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", text))

    assert dossier is not None
    assert dossier.source_coverage["EDGAR"] == "20-F"
    assert "freie Notiz ohne Trenner" not in dossier.source_coverage


def test_point_number_outside_one_to_fifteen_is_dropped_with_warning(
    tmp_path, caplog
):
    text = GEN3_MARKDOWN.replace(
        "### Punkt 2 — Management-Determination",
        "### Punkt 16 — Erfundener Punkt\n**Bewertung:** ⭐ · **Confidence:** 🔴\n\n"
        "Text. [Inferenz]\n\n### Punkt 2 — Management-Determination",
    )

    with caplog.at_level("WARNING"):
        dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", text))

    assert dossier is not None
    assert [p.number for p in dossier.points] == list(range(1, 16))
    assert "16" in caplog.text


def test_frontmatter_with_wrong_field_type_skips_only_that_file(tmp_path):
    """`days_since_filing: viele` cannot be an int — skip the file instead of
    guessing a number."""
    text = GEN3_MARKDOWN.replace("days_since_filing: 154", "days_since_filing: viele")

    assert parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", text)) is None


def test_headline_segment_without_label_is_logged_not_dropped_silently(
    tmp_path, caplog
):
    """A colon-less segment has no key to store it under — it must at least
    show up in the log instead of vanishing without a trace."""
    text = GEN3_MARKDOWN.replace(
        "Op. Margin: 32.0%*", "Op. Margin: 32.0% · Sonderlage*"
    )

    with caplog.at_level("WARNING"):
        dossier = parse_dossier(_write(tmp_path, "ARGX_2026-08-20.md", text))

    assert dossier is not None
    assert dossier.headline_metrics["Op. Margin"] == "32.0%"
    assert "Sonderlage" in caplog.text
