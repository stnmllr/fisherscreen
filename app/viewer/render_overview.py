"""Overview page: one row per dossier.

The page is a table of dossiers, not an analysis of them. Every number is
printed exactly as the dossier wrote it — the viewer parses, it never
computes, so a rounding or unit decision always stays with the generator.
Sorting needs a comparable value, which is why each numeric cell carries a
separate `data-sort` attribute derived from the same string.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from string import Template
from typing import AbstractSet, Final, Sequence
from urllib.parse import quote

from app.viewer.assets import CSS_FILENAME, JS_FILENAME
from app.viewer.html import esc, scrollable_table, tag
from app.viewer.models import Dossier

logger = logging.getLogger(__name__)

_LOW_CONFIDENCE: Final[str] = "🔴"
_STAR: Final[str] = "★"
_SEGMENT_SEPARATOR: Final[str] = " · "

# Three stages instead of the usual two: for annual filings, "older than a
# quarter" is the normal state for most of the year (6 of 10 current
# dossiers sit between 134 and 306 days), so a two-stage scheme would paint
# the majority red and stop meaning anything. Red is precaution, not an
# active signal — no dossier in the current stock reaches it.
FRESHNESS_YELLOW_DAYS: Final[int] = 120
FRESHNESS_RED_DAYS: Final[int] = 365
FRESHNESS_YELLOW_TITLE: Final[str] = (
    "Filing älter als ein Quartal — zwischenzeitliche Entwicklungen prüfen"
)
FRESHNESS_RED_TITLE: Final[str] = (
    "Filing älter als ein voller Berichtszyklus — Stand vor dem letzten "
    "Jahresabschluss"
)

_VALUATION_BLOCK: Final[str] = "Bewertung"
_PE_FORWARD_KEY: Final[str] = "P/E fwd"
_FCF_YIELD_KEY: Final[str] = "FCF-Yield"
_OP_MARGIN_KEY: Final[str] = "Op. Margin"

# Anchored: the number must open the string. A stray digit in a trailing
# comment ("n/a (… Ø 5J Buyback n/a)") would otherwise become the sort key
# of a cell that has no value at all.
_LEADING_NUMBER_RE: Final[re.Pattern[str]] = re.compile(r"^[-+]?\d[\d,]*(?:\.\d+)?")


def sort_key(display: str) -> float | None:
    """Numeric sort value of a rendered metric string, or None.

    None means "not comparable" and is rendered as an empty `data-sort`, on
    which the sort script pushes the row to the end in either direction.

    No try/except around the conversion: the pattern only admits shapes
    that `float` accepts once the thousands separators are gone, so a
    handler here would be untestable dead code.
    """
    match = _LEADING_NUMBER_RE.match(display.strip())
    if match is None:
        return None
    return float(match.group().replace(",", ""))


@dataclass(frozen=True)
class OverviewRow:
    """One rendered line of the overview.

    Metric fields hold the dossier's own display strings; None means the
    dossier has no such value, which the renderer shows as a dash.
    """

    ticker: str
    href: str
    company_name: str | None
    form_type: str
    filing_date: date | None
    star_summary: str | None
    red_count: int
    pe_fwd: str | None
    op_margin: str | None
    fcf_yield: str | None
    days_since_filing: int | None
    is_duplicate_name: bool


def _detail_href(ticker: str) -> str:
    """Tickers carry `.`, `-` and historically `/` (`RDS/A`); the path has to
    survive that, while the displayed symbol stays untouched."""
    return f"ticker/{quote(ticker, safe='')}.html"


def _star_summary(dossier: Dossier) -> str | None:
    """`2×★5 · 1×★4`, highest grade first. None when nothing is rated."""
    counts = Counter(
        point.rating for point in dossier.points if point.rating is not None
    )
    if not counts:
        return None
    return _SEGMENT_SEPARATOR.join(
        f"{counts[rating]}×{_STAR}{rating}" for rating in sorted(counts, reverse=True)
    )


def freshness_flag(days_since_filing: int | None) -> tuple[str | None, str | None]:
    """`(css class, tooltip)` for the age column; `(None, None)` = unremarkable.

    An unknown age stays neutral: colouring it would assert a staleness the
    dossier does not state.
    """
    if days_since_filing is None:
        return None, None
    if days_since_filing > FRESHNESS_RED_DAYS:
        return "age-red", FRESHNESS_RED_TITLE
    if days_since_filing >= FRESHNESS_YELLOW_DAYS:
        return "age-yellow", FRESHNESS_YELLOW_TITLE
    return None, None


def build_overview_row(
    dossier: Dossier, *, duplicate_names: AbstractSet[str]
) -> OverviewRow:
    """Project one dossier onto its overview line. No value is recomputed."""
    valuation = dossier.metrics.get(_VALUATION_BLOCK, {})
    return OverviewRow(
        ticker=dossier.ticker,
        href=_detail_href(dossier.ticker),
        company_name=dossier.company_name,
        form_type=dossier.form_type,
        filing_date=dossier.filing_date,
        star_summary=_star_summary(dossier),
        red_count=sum(
            1 for point in dossier.points if point.confidence == _LOW_CONFIDENCE
        ),
        pe_fwd=valuation.get(_PE_FORWARD_KEY),
        op_margin=dossier.headline_metrics.get(_OP_MARGIN_KEY),
        fcf_yield=valuation.get(_FCF_YIELD_KEY),
        days_since_filing=dossier.days_since_filing,
        is_duplicate_name=dossier.company_name is not None
        and dossier.company_name in duplicate_names,
    )


PAGE_TITLE: Final[str] = "FisherScreen — Deep Dives"
BACK_LINK_URL: Final[str] = "https://macro.stnmllr.com/"
BACK_LINK_LABEL: Final[str] = "← Macro Risk Monitor"
DUPLICATE_BADGE: Final[str] = "weiterer Lauf unter anderem Symbol"
DUPLICATE_BADGE_TITLE: Final[str] = (
    "Gleicher Firmenname, anderes Symbol — die beiden Läufe werden bewusst "
    "nicht zusammengeführt: ohne ISIN/CIK-Anker wäre die Identität geraten."
)
EMPTY_NOTICE: Final[str] = "Keine Dossiers gefunden."
_TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%d %H:%M %Z"

_COLUMNS: Final[tuple[tuple[str, bool], ...]] = (
    ("Ticker / Firma", True),
    ("Filing", True),
    ("Fisher-Kompakt", False),
    ("🔴", True),
    ("P/E fwd", True),
    ("Op-Marge", True),
    ("FCF-Yield", True),
    ("Frische", True),
)

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
<a class="hd-back" href="$back_url">$back_label</a>
<div class="hd-top">
<h1>FisherScreen — <span>Deep Dives</span></h1>
<div class="hd-meta">Stand: $generated_at</div>
</div>
</header>
<main>
$body
</main>
<script src="$js" defer></script>
</body>
</html>
"""
)


def _sort_attribute(display: str | None) -> str:
    """`data-sort` twin of a display string; empty when not comparable."""
    if display is None:
        return ""
    value = sort_key(display)
    return "" if value is None else str(value)


def _metric_cell(display: str | None) -> str:
    return tag("td", esc(display), class_="num", data_sort=_sort_attribute(display))


def _identity_cell(row: OverviewRow) -> str:
    link = tag("a", esc(row.ticker), href=row.href)
    parts = [tag("div", link, class_="t-name")]
    if row.company_name is not None:
        parts.append(tag("div", esc(row.company_name), class_="t-sub"))
    if row.is_duplicate_name:
        parts.append(
            tag("span", esc(DUPLICATE_BADGE), class_="tag", title=DUPLICATE_BADGE_TITLE)
        )
    return tag("td", "".join(parts), data_sort=row.ticker)


def _filing_cell(row: OverviewRow) -> str:
    date_text = esc(row.filing_date.isoformat() if row.filing_date else None)
    inner = tag("div", esc(row.form_type)) + tag("div", date_text, class_="t-sub")
    return tag(
        "td",
        inner,
        class_="mono",
        data_sort=row.filing_date.isoformat() if row.filing_date else "",
    )


def _red_cell(row: OverviewRow) -> str:
    if row.red_count == 0:
        inner = esc("—")
    else:
        inner = tag("span", f"🔴 {row.red_count}", class_="pill red")
    return tag("td", inner, class_="num", data_sort=str(row.red_count))


def _freshness_cell(row: OverviewRow) -> str:
    css_class, title = freshness_flag(row.days_since_filing)
    if row.days_since_filing is None:
        inner = esc(None)
    else:
        inner = tag(
            "span", f"{row.days_since_filing} Tage", class_=css_class, title=title
        )
    return tag(
        "td",
        inner,
        class_="num",
        data_sort="" if row.days_since_filing is None else str(row.days_since_filing),
    )


def _row_html(row: OverviewRow) -> str:
    cells = (
        _identity_cell(row),
        _filing_cell(row),
        tag("td", esc(row.star_summary), class_="stars"),
        _red_cell(row),
        _metric_cell(row.pe_fwd),
        _metric_cell(row.op_margin),
        _metric_cell(row.fcf_yield),
        _freshness_cell(row),
    )
    return tag("tr", "".join(cells))


def _table_html(rows: Sequence[OverviewRow]) -> str:
    header = tag(
        "tr",
        "".join(
            tag("th", esc(label), data_sortable="1" if sortable else None)
            for label, sortable in _COLUMNS
        ),
    )
    body = "".join(_row_html(row) for row in rows)
    # Same scroll container as the peer table, from the same function: eight
    # columns do not fit a phone, and a table that overflows on its own
    # takes the whole page sideways with it.
    return scrollable_table(
        tag(
            "table",
            tag("thead", header) + tag("tbody", body),
            data_sortable_table="1",
        )
    )


def _skipped_html(skipped: Sequence[str]) -> str:
    """Name every file that did not make it onto the page.

    A dossier that vanishes without a trace looks exactly like a dossier
    that was never written.
    """
    if not skipped:
        return ""
    noun = "Datei" if len(skipped) == 1 else "Dateien"
    names = ", ".join(esc(name) for name in skipped)
    return tag("div", f"{len(skipped)} {noun} übersprungen: {names}", class_="foot")


def render_overview(
    rows: Sequence[OverviewRow],
    *,
    generated_at: datetime,
    skipped: Sequence[str] = (),
) -> str:
    """Render the overview page.

    `generated_at` is injected rather than read from the clock so that two
    builds of the same input produce byte-identical output — otherwise
    every build shows up as a diff.
    """
    if rows:
        body = _table_html(rows)
    else:
        body = tag("div", esc(EMPTY_NOTICE), class_="banner")
        logger.warning("viewer: overview rendered without any dossier")
    return _PAGE.substitute(
        title=esc(PAGE_TITLE),
        css=CSS_FILENAME,
        js=JS_FILENAME,
        back_url=BACK_LINK_URL,
        back_label=esc(BACK_LINK_LABEL),
        generated_at=esc(generated_at.strftime(_TIMESTAMP_FORMAT).strip()),
        body=body + _skipped_html(skipped),
    )
