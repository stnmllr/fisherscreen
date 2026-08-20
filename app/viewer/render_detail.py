"""Detail page: one dossier, rendered in full.

Same rule as the overview — the viewer parses, it never computes. Every
number on this page is the dossier's own string. What this page adds is
absence: an unfilled summary, a missing insider block or a metric from a
known-buggy run is stated as such instead of being left to look like a
value that simply does not exist.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from string import Template
from typing import Final

from app.viewer.assets import CSS_FILENAME
from app.viewer.defects import DataDefect, defects_for
from app.viewer.html import esc, md_to_html, table_html, tag
from app.viewer.models import MAX_RATING, Dossier, ParsedPoint
from app.viewer.render_overview import freshness_flag

logger = logging.getLogger(__name__)

BACK_HREF: Final[str] = "../index.html"
BACK_LABEL: Final[str] = "← Übersicht"
DEFECT_MARKER: Final[str] = "⚠"
DEFECT_FOOTNOTE_CLASS: Final[str] = "foot defects"
SUMMARY_PENDING_NOTE: Final[str] = (
    "folgt B.1 — der Generator hat hier bisher nur seinen Prompt-Platzhalter "
    "geschrieben; ihn als Text zu zeigen hieße, einen Prompt als Aussage "
    "auszugeben."
)

# 🔴 is a statement about the sources, not about the company. The wording
# says so explicitly, because a dimmed card next to two stars invites
# exactly the opposite reading.
LOW_CONFIDENCE_NOTE: Final[str] = (
    "Geringe Belegdichte: zu diesem Punkt stand in den ausgewerteten Quellen "
    "kaum Substanz. Die Aussage betrifft die Quellenlage, nicht das "
    "Unternehmen — hier gehört ein Scuttlebutt-Blick hin."
)
PLACEHOLDER_POINT_NOTE: Final[str] = "— nicht im Dossier enthalten"
INSIDER_MISSING_NOTE: Final[str] = (
    "Dieser Dossier-Jahrgang hat noch keine Insider-Sektion — es liegen also "
    "keine Form-4-Daten vor, nicht etwa keine Transaktionen."
)
NOTES_EMPTY_NOTE: Final[str] = "leer — wird in Obsidian gepflegt"
PENDING_NOTE: Final[str] = "folgt"

# Rendered empty on purpose: the sections exist in the template now so B.3
# and B.4 appear in place once they are built, without a template change.
PENDING_SECTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("b3-scuttlebutt", "B.3 Soft Scuttlebutt"),
    ("b4-tonality", "B.4 Sprach-/Tonalitätsanalyse"),
    ("stef-scuttlebutt", "Stef's Scuttlebutt"),
)

# Blocks of the valuation section, in the order the dossier writes them.
METRIC_BLOCKS: Final[tuple[str, ...]] = (
    "Bewertung",
    "Kapitalstruktur",
    "Analyst Consensus",
    "Forward-Konsens",
)
RANGE_BLOCK: Final[str] = "Bewertungs-Range"

# Defect key (defects.py) -> the block and display label it belongs to.
# Explicit rather than derived from the key spelling: `ev_ebit` and the
# label `EV/EBIT` only look related, and `EV/EBIT` occurs in two blocks.
DEFECT_METRIC_LABELS: Final[dict[str, tuple[str, str]]] = {
    "ev_ebit": ("Bewertung", "EV/EBIT"),
    "ev_sales": ("Bewertung", "EV/Sales"),
    "dividend_yield": ("Bewertung", "Div-Yield"),
    "debt_to_equity": ("Kapitalstruktur", "D/E"),
    "total_shareholder_yield": ("Kapitalstruktur", "Total Shareholder Yield"),
    "valuation_range": (RANGE_BLOCK, RANGE_BLOCK),
}
_DEFECT_KEY_BY_LABEL: Final[dict[tuple[str, str], str]] = {
    target: key for key, target in DEFECT_METRIC_LABELS.items()
}

_TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%d %H:%M %Z"
_AGE_SUFFIX: Final[str] = "Tage seit Filing"
_SEGMENT_SEPARATOR: Final[str] = " · "

PEERS_HEADING: Final[str] = "Peer-Vergleich"
POINTS_HEADING: Final[str] = "Fishers 15 Punkte"
INSIDER_HEADING: Final[str] = "Insider-Transaktionen"
COVERAGE_HEADING: Final[str] = "Source Coverage"
NOTES_HEADING: Final[str] = "Stef's Notizen"
PEER_CAPTION_CLASS: Final[str] = "peer-note"

_STAR_FULL: Final[str] = "★"
_STAR_EMPTY: Final[str] = "☆"
_LOW_CONFIDENCE: Final[str] = "🔴"
_CONFIDENCE_CLASSES: Final[dict[str, str]] = {
    "🟢": "green",
    "🟡": "yellow",
    _LOW_CONFIDENCE: "red",
}

# Flag vocabulary of the dossier generator. `ok` is the only state that
# means "intact"; everything unknown is neutral rather than green.
_FLAG_RED: Final[str] = "missing"
_FLAG_YELLOW: Final[tuple[str, ...]] = ("ambiguous", "fallback_used", "truncated")
_FLAG_GREEN: Final[frozenset[str]] = frozenset({"ok"})

_PAGE = Template(
    """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<link rel="stylesheet" href="$css">
</head>
<body>
<header>
<a class="hd-back" href="$back_href">$back_label</a>
<div class="hd-top">
<h1>$heading</h1>
<div class="hd-meta">$meta</div>
</div>
$badges
</header>
<main>
$body
</main>
</body>
</html>
"""
)


class _DefectCollector:
    """Collects the defects that actually reached a rendered cell.

    A defect of a metric the dossier does not carry is not footnoted: the
    note qualifies a number, and there is no number to qualify.
    """

    def __init__(self, ticker: str, quant_date: date | None) -> None:
        self._defects = defects_for(ticker, quant_date)
        self._applied: list[tuple[str, DataDefect]] = []

    def take(self, block: str, label: str) -> DataDefect | None:
        """Defect for one cell, remembered for the footnote. None = clean."""
        key = _DEFECT_KEY_BY_LABEL.get((block, label))
        if key is None:
            return None
        defect = self._defects.get(key)
        if defect is None:
            return None
        self._applied.append((label, defect))
        return defect

    def footnote(self) -> str:
        """One entry per distinct note, naming every metric it covers."""
        if not self._applied:
            return ""
        by_note: dict[str, list[str]] = {}
        for label, defect in self._applied:
            by_note.setdefault(defect.note, []).append(label)
        entries = "".join(
            tag("li", f"{DEFECT_MARKER} {esc(', '.join(labels))}: {esc(note)}")
            for note, labels in by_note.items()
        )
        return tag("div", tag("ul", entries), class_=DEFECT_FOOTNOTE_CLASS)


def _defect_marker(defect: DataDefect | None) -> str:
    if defect is None:
        return ""
    return " " + tag("span", DEFECT_MARKER, class_="defect", title=defect.note)


def _kpi_tile(label: str, value: str, defect: DataDefect | None, css: str) -> str:
    """One KPI tile. A defect adds a marker, it never hides the value."""
    inner = tag("div", esc(label) + _defect_marker(defect), class_="k-name")
    inner += tag("div", esc(value), class_="k-val")
    return tag("div", inner, class_=css)


def _grid(tiles: list[str]) -> str:
    return tag("div", "".join(tiles), class_="kpi-grid") if tiles else ""


def _headline_grid(dossier: Dossier) -> str:
    """Market Cap / margins — the three numbers the dossier itself leads with."""
    return _grid(
        [
            _kpi_tile(label, value, None, "kpi hero")
            for label, value in dossier.headline_metrics.items()
        ]
    )


def _metric_block(dossier: Dossier, block: str, defects: _DefectCollector) -> str:
    """One labelled block of tiles, or "" when the dossier has no such block."""
    values = dossier.metrics.get(block, {})
    extras = dossier.metric_extras.get(block, [])
    if not values and not extras:
        return ""
    tiles = [
        _kpi_tile(label, value, defects.take(block, label), "kpi")
        for label, value in values.items()
    ]
    unlabelled = "".join(tag("span", esc(extra), class_="tag") for extra in extras)
    return (
        tag("h3", esc(block))
        + _grid(tiles)
        + (tag("div", unlabelled, class_="extras") if unlabelled else "")
    )


def _range_line(dossier: Dossier, defects: _DefectCollector) -> str:
    """The multi-year range line, verbatim. Gen-1 dossiers have none."""
    raw = dossier.raw_metric_lines.get(RANGE_BLOCK)
    if raw is None:
        return ""
    marker = _defect_marker(defects.take(RANGE_BLOCK, RANGE_BLOCK))
    return tag("div", esc(raw) + marker, class_="range-line")


def _quant_section(dossier: Dossier) -> str:
    defects = _DefectCollector(dossier.ticker, dossier.quant_date)
    blocks = "".join(
        _metric_block(dossier, block, defects) for block in METRIC_BLOCKS
    )
    body = (
        _headline_grid(dossier)
        + blocks
        + _range_line(dossier, defects)
        + defects.footnote()
    )
    return _section("quant", "Kennzahlen", body)


def _summary_section(dossier: Dossier) -> str:
    if dossier.executive_summary is None:
        body = tag("div", esc(SUMMARY_PENDING_NOTE), class_="banner")
    else:
        body = tag("div", md_to_html(dossier.executive_summary), class_="card")
    return _section("summary", "Executive Summary", body)


def _section(section_id: str, heading: str, inner: str) -> str:
    return tag("section", tag("h2", esc(heading)) + inner, id=section_id)


def _peers_section(dossier: Dossier) -> str:
    """Peer table plus the user's own rationale. No table means no section:
    an empty one would imply a comparison that was never made."""
    if not dossier.peer_table:
        return ""
    body = table_html(dossier.peer_table)
    if dossier.peer_rationale is not None:
        body += tag("div", esc(dossier.peer_rationale), class_=PEER_CAPTION_CLASS)
    return _section("peers", PEERS_HEADING, body)


def _stars(rating: int | None) -> str:
    """`★★★★☆` for 4. No rating stays a dash — zero stars would read as a
    grade of zero, and the generator writes `?` when it has none."""
    if rating is None:
        return esc(None)
    return _STAR_FULL * rating + _STAR_EMPTY * (MAX_RATING - rating)


def _confidence_dot(confidence: str | None) -> str:
    """Colour of the confidence dot. An unparsed confidence is neutral, not
    a green light."""
    css = _CONFIDENCE_CLASSES.get(confidence or "", "na")
    return tag("span", "", class_=f"dot {css}", title=f"Confidence: {esc(confidence)}")


def _point_card(point: ParsedPoint) -> str:
    head = tag("span", esc(f"Punkt {point.number}"), class_="p-num")
    title = tag("div", esc(point.title), class_="p-title")
    if point.is_placeholder:
        body = tag("div", esc(PLACEHOLDER_POINT_NOTE), class_="p-absent")
        return tag("div", head + title + body, class_="card point absent")

    is_low = point.confidence == _LOW_CONFIDENCE
    sources = "".join(tag("span", esc(source), class_="tag") for source in point.sources)
    body = (
        head
        + _confidence_dot(point.confidence)
        + title
        + tag("div", _stars(point.rating), class_="stars")
        + tag("div", md_to_html(point.reasoning), class_="p-text")
        + tag("div", sources, class_="p-sources")
    )
    if is_low:
        body += tag("div", esc(LOW_CONFIDENCE_NOTE), class_="p-note")
    return tag("div", body, class_="card point muted" if is_low else "card point")


def _points_section(dossier: Dossier) -> str:
    if not dossier.points:
        logger.warning("viewer: %s has no Fisher points", dossier.ticker)
        return ""
    cards = "".join(_point_card(point) for point in dossier.points)
    return _section("points", POINTS_HEADING, tag("div", cards, class_="point-grid"))


def _insider_section(dossier: Dossier) -> str:
    """Summary in the open, the per-transaction lines folded away.

    FICO alone contributes 130+ detail lines; expanded they bury every other
    section. A dossier generation without the block at all says so — an
    empty frame would read as "no transactions".
    """
    details = dossier.insider_detail_lines
    if dossier.insider_summary_line is None and not details:
        body = tag("div", esc(INSIDER_MISSING_NOTE), class_="banner")
        return _section("insider", INSIDER_HEADING, body)

    body = tag("div", esc(dossier.insider_summary_line), class_="card")
    if details:
        label = tag("summary", esc(f"{len(details)} Detailzeilen anzeigen"))
        body += tag("details", label + md_to_html("\n".join(details)))
    return _section("insider", INSIDER_HEADING, body)


def _flag_class(state: str) -> str:
    """Ampel colour of one section flag.

    Green is a whitelist, not the fallback: an unknown state is exactly the
    case where the viewer does not know whether the section is intact, and
    painting it green would be a claim.
    """
    if _FLAG_RED in state:
        return "red"
    if any(word in state for word in _FLAG_YELLOW):
        return "yellow"
    if state in _FLAG_GREEN:
        return "green"
    logger.warning("viewer: unknown section flag state %r", state)
    return "na"


def _coverage_section(dossier: Dossier) -> str:
    if not dossier.section_flags and not dossier.source_coverage:
        return ""
    pills = "".join(
        tag("span", esc(f"{name}: {state}"), class_=f"pill {_flag_class(state)}")
        for name, state in dossier.section_flags.items()
    )
    items = "".join(
        tag("dt", esc(name)) + tag("dd", esc(value))
        for name, value in dossier.source_coverage.items()
    )
    body = tag("div", pills, class_="pills") + tag("dl", items, class_="kv")
    return _section("coverage", COVERAGE_HEADING, body)


def _notes_section(dossier: Dossier) -> str:
    if dossier.notes is None:
        body = tag("div", esc(NOTES_EMPTY_NOTE), class_="banner")
    else:
        body = tag("div", md_to_html(dossier.notes), class_="card")
    return _section("notes", NOTES_HEADING, body)


def _pending_sections() -> str:
    return "".join(
        _section(section_id, heading, tag("div", esc(PENDING_NOTE), class_="banner"))
        for section_id, heading in PENDING_SECTIONS
    )


def _heading(dossier: Dossier) -> str:
    """Company name plus symbol; the symbol alone when the H1 was unparseable."""
    symbol = tag("span", esc(dossier.ticker))
    if dossier.company_name is None:
        return symbol
    return f"{esc(dossier.company_name)} {symbol}"


def _meta_line(dossier: Dossier, generated_at: datetime) -> str:
    filing = dossier.filing_date.isoformat() if dossier.filing_date else None
    quant = dossier.quant_date.isoformat() if dossier.quant_date else None
    stand = generated_at.strftime(_TIMESTAMP_FORMAT).strip()
    parts = (
        esc(dossier.form_type),
        f"Filing {esc(filing)}",
        f"Quant {esc(quant)}",
        f"Stand: {esc(stand)}",
    )
    return _SEGMENT_SEPARATOR.join(parts)


def _age_badge(dossier: Dossier) -> str:
    """Freshness badge, shared with the overview column. Unknown age gets no
    badge — colouring it would assert a staleness the dossier never states."""
    days = dossier.days_since_filing
    if days is None:
        return ""
    css_class, title = freshness_flag(days)
    badge = tag(
        "span",
        esc(f"{days} {_AGE_SUFFIX}"),
        class_=" ".join(filter(None, ("tag", css_class))),
        title=title,
    )
    return tag("div", badge, class_="hd-badges")


def render_detail(dossier: Dossier, *, generated_at: datetime) -> str:
    """Render the detail page of one dossier.

    `generated_at` is injected rather than read from the clock so that two
    builds of the same input are byte-identical — otherwise every build
    shows up as a diff.
    """
    body = (
        _summary_section(dossier)
        + _quant_section(dossier)
        + _peers_section(dossier)
        + _points_section(dossier)
        + _insider_section(dossier)
        + _coverage_section(dossier)
        + _notes_section(dossier)
        + _pending_sections()
    )
    return _PAGE.substitute(
        title=esc(f"{dossier.ticker} — FisherScreen Deep Dive"),
        css=f"../{CSS_FILENAME}",
        back_href=BACK_HREF,
        back_label=esc(BACK_LABEL),
        heading=_heading(dossier),
        meta=_meta_line(dossier, generated_at),
        badges=_age_badge(dossier),
        body=body,
    )
