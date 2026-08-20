"""Reader for Tool-B dossiers written by `app/deepdive/dossier_generator.py`.

The generator is the writer, this is the reader. It must cope with every
generation that ever landed in output/Watchlist/ — the format grew an
insider block and a valuation-range line over time, and old files are never
regenerated. Rule of thumb: parse what is there, return None for what is
not, and never invent a value.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter
import yaml
from pydantic import ValidationError

from app.deepdive.fisher_points import FISHER_POINTS
from app.errors import ViewerError
from app.viewer.models import MAX_RATING, MIN_RATING, Dossier, ParsedPoint

logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"^(?P<ticker>[^_]+)_(?P<date>\d{4}-\d{2}-\d{2})\.md$")

# Greedy on the name: company names may themselves contain parentheses
# ("Coca-Cola Company (The)"), so the LAST group is the ticker.
_H1_RE = re.compile(r"^#\s+Deep Dive:\s*(?P<name>.+)\s+\((?P<ticker>[^()]*)\)\s*$")

_HEADING_BEWERTUNG = "Bewertung"
_HEADING_VALUATION_PREFIX = "Bewertung & Kapitalstruktur"
_HEADING_POINTS = "Fishers 15 Punkte"
_HEADING_SUMMARY = "Executive Summary"
_HEADING_NOTES = "Stef's Notizen"
_HEADING_INSIDER = "Insider-Transaktionen"
_HEADING_COVERAGE = "Source Coverage"
_SEGMENT_SEPARATOR = " · "

_POINT_HEADING_RE = re.compile(
    r"^###\s+Punkt\s+(?P<number>\d+)\s*(?:—|-|–)\s*(?P<title>.*)$"
)
_RATING_LINE_RE = re.compile(r"^\*\*Bewertung:\*\*")
_CONFIDENCE_RE = re.compile(r"\*\*Confidence:\*\*\s*(?P<confidence>\S+)")
_TRAILING_SOURCE_RE = re.compile(r"\[([^\[\]]+)\]\s*$")
# `*[…]*` marks an unfilled generator placeholder, never real content.
_PLACEHOLDER_RE = re.compile(r"\*\[.*\]\*", re.DOTALL)

_STAR = "⭐"
_INSIDER_PREFIX = "**Insider-Transaktionen:**"

_PARENTHETICAL_SUFFIX_RE = re.compile(r"\s*\([^()]*\)\s*$")
_TABLE_SEPARATOR_CELL_RE = re.compile(r":?-{2,}:?")

# Label vocabularies of the valuation block, derived from the rendered
# output of app/deepdive/valuation_block.py. Unknown segments are never
# dropped (see parse_metric_line), so an added metric shows up as an extra
# instead of vanishing.
_VALUATION_LABELS: tuple[str, ...] = (
    "P/E trail.",
    "P/E fwd",
    "EV/EBIT",
    "EV/Sales",
    "FCF-Yield",
    "Div-Yield",
    "Payout",
)
_RANGE_LABELS: tuple[str, ...] = ("P/E", "EV/EBIT", "FCF-Yield")
_CAPITAL_LABELS: tuple[str, ...] = (
    "Total Debt",
    "Cash",
    "D/E",
    "Current Ratio",
    "Interest Coverage",
    "Total Shareholder Yield",
)
_CONSENSUS_LABELS: tuple[str, ...] = ("Target", "Upside")
_FORWARD_LABELS: tuple[str, ...] = ("Revenue", "EPS")

_LABELS_BY_LINE: dict[str, tuple[str, ...]] = {
    "Bewertung": _VALUATION_LABELS,
    "Bewertungs-Range": _RANGE_LABELS,
    "Kapitalstruktur": _CAPITAL_LABELS,
    "Analyst Consensus": _CONSENSUS_LABELS,
    "Forward-Konsens": _FORWARD_LABELS,
}


def _load_post(path: Path) -> frontmatter.Post | None:
    """Read + split frontmatter. Returns None on any per-file defect so a
    single broken dossier can never abort a whole build."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("viewer: cannot read %s: %s", path.name, exc)
        return None
    try:
        return frontmatter.loads(text)
    except yaml.YAMLError as exc:
        logger.warning("viewer: malformed frontmatter in %s: %s", path.name, exc)
        return None


def _split_sections(body: str) -> dict[str, list[str]]:
    """Body -> {level-2 heading text: lines}. Content before the first `##`
    (the H1) lands under the empty key."""
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return sections


def _parse_company_name(lines: list[str]) -> str | None:
    for line in lines:
        match = _H1_RE.match(line.strip())
        if match:
            return match.group("name").strip()
    return None


def _parse_headline_metrics(lines: list[str]) -> dict[str, str]:
    """The italic one-liner under `## Bewertung`: `*Market Cap: … · …*`."""
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("*") or "Market Cap" not in stripped:
            continue
        payload = stripped.strip("*").strip()
        metrics: dict[str, str] = {}
        for segment in payload.split(_SEGMENT_SEPARATOR):
            key, separator, value = segment.partition(":")
            if not separator:
                logger.warning(
                    "viewer: headline segment without label: %r", segment
                )
                continue
            metrics[key.strip()] = value.strip()
        return metrics
    return {}


def parse_metric_line(
    line: str, labels: tuple[str, ...]
) -> tuple[dict[str, str], list[str]]:
    """Split one `Label: seg · seg · seg` line into known metrics + leftovers.

    A segment is matched against the LONGEST known label prefix, so
    `P/E trail. 39.4` binds to `P/E trail.` and not to a shorter `P/E`.
    Segments with no known prefix are returned as-is in the second element:
    dropping them would make a newly added generator metric disappear
    without a trace.
    """
    _, _, payload = line.partition(":")
    ordered = sorted(labels, key=len, reverse=True)
    known: dict[str, str] = {}
    extras: list[str] = []
    for raw_segment in payload.split(_SEGMENT_SEPARATOR):
        segment = raw_segment.strip()
        if not segment:
            continue
        label = _match_label(segment, ordered)
        if label is None:
            extras.append(segment)
            continue
        known[label] = segment[len(label):].lstrip(": ").strip()
    return known, extras


def _match_label(segment: str, ordered_labels: list[str]) -> str | None:
    """Longest label that is a prefix of `segment` on a token boundary."""
    for label in ordered_labels:
        if not segment.startswith(label):
            continue
        rest = segment[len(label):]
        if not rest or rest[0] in " :":
            return label
    return None


def _line_label(line: str) -> str:
    """`Bewertungs-Range (~1J, 66 Wo): …` -> `Bewertungs-Range`.

    The parenthesised span stays available via `raw_metric_lines`; keying on
    it would make the key vary per dossier.
    """
    head, _, _ = line.partition(":")
    return _PARENTHETICAL_SUFFIX_RE.sub("", head).strip()


def _is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(_TABLE_SEPARATOR_CELL_RE.fullmatch(c) for c in cells)


def _parse_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


_ValuationSection = tuple[
    dict[str, dict[str, str]],
    dict[str, str],
    dict[str, list[str]],
    list[list[str]],
]


def _parse_valuation_section(lines: list[str]) -> _ValuationSection:
    """Metric lines + peer table of the `## Bewertung & Kapitalstruktur` block."""
    metrics: dict[str, dict[str, str]] = {}
    raw_lines: dict[str, str] = {}
    extras: dict[str, list[str]] = {}
    table: list[list[str]] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("|"):
            cells = _parse_table_row(line)
            if not _is_table_separator(cells):
                table.append(cells)
            continue
        if ":" not in line:
            continue
        label = _line_label(line)
        if not label:
            continue
        raw_lines[label] = line
        known, unknown = parse_metric_line(line, _LABELS_BY_LINE.get(label, ()))
        if known:
            metrics[label] = known
        if unknown:
            extras[label] = unknown
    return metrics, raw_lines, extras, table


def _parse_prose_section(lines: list[str]) -> str | None:
    """Free-text section content, with the generator's placeholders mapped to
    None (`*[3 Sätze: …]*`, `*[Leer — Stef füllt manuell in Obsidian]*`).

    An unfilled placeholder is an absence of content; rendering it as text
    would present boilerplate as an author's statement.
    """
    text = "\n".join(lines).strip()
    if not text:
        return None
    if _PLACEHOLDER_RE.fullmatch(text):
        return None
    return text


def _parse_insider_section(lines: list[str]) -> tuple[str | None, list[str]]:
    """`(summary line without its bold prefix, raw detail lines)`.

    Detail lines keep their original indentation: the generator nests
    per-owner transactions two spaces deep, and that nesting is meaning.
    Gen-1/Gen-2 dossiers have no insider section at all -> (None, []).
    """
    summary: str | None = None
    details: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        if line.strip().startswith(_INSIDER_PREFIX):
            summary = line.strip()[len(_INSIDER_PREFIX):].strip()
            continue
        details.append(line.rstrip())
    return summary, details


def _parse_source_coverage(lines: list[str]) -> dict[str, str]:
    """`- EDGAR: 20-F via ADR` -> {"EDGAR": "20-F via ADR"}."""
    coverage: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        key, separator, value = stripped[2:].partition(":")
        if not separator:
            continue
        coverage[key.strip()] = value.strip()
    return coverage


def _split_reasoning_and_sources(prose: str) -> tuple[str | None, list[str]]:
    """Peel `[..]` provenance markers off the END of the prose.

    Only trailing markers are provenance — brackets inside a sentence belong
    to the text and stay there.
    """
    text = prose.strip()
    sources: list[str] = []
    while True:
        match = _TRAILING_SOURCE_RE.search(text)
        if match is None:
            break
        sources.insert(0, match.group(1).strip())
        text = text[: match.start()].rstrip()
    return (text or None), sources


def _parse_rating_line(line: str) -> tuple[int | None, str | None]:
    """`**Bewertung:** ⭐⭐⭐ · **Confidence:** 🟡` -> (3, "🟡").

    The generator writes `?` when it has no rating; counting stars then
    yields 0, which stays None instead of becoming a fabricated grade.
    """
    stars = line.count(_STAR)
    rating = stars if MIN_RATING <= stars <= MAX_RATING else None
    match = _CONFIDENCE_RE.search(line)
    confidence = match.group("confidence") if match else None
    return rating, confidence


def _parse_point_block(number: int, title: str | None, block: list[str]) -> ParsedPoint:
    rating: int | None = None
    confidence: str | None = None
    prose_lines = list(block)
    for index, line in enumerate(prose_lines):
        if _RATING_LINE_RE.match(line.strip()):
            rating, confidence = _parse_rating_line(line)
            prose_lines = prose_lines[index + 1:]
            break
    reasoning, sources = _split_reasoning_and_sources("\n".join(prose_lines))
    return ParsedPoint(
        number=number,
        title=title,
        rating=rating,
        confidence=confidence,
        reasoning=reasoning,
        sources=sources,
    )


def _parse_points(lines: list[str]) -> list[ParsedPoint]:
    """Parse the `### Punkt N — …` blocks and pad the result to 1..15.

    The dossier's own title always wins: Gen-2 dossiers carry long,
    Gemini-authored titles. FISHER_POINTS only supplies titles for numbers
    the dossier does not contain at all.
    """
    parsed: dict[int, ParsedPoint] = {}
    number: int | None = None
    title: str | None = None
    block: list[str] = []

    def flush() -> None:
        if number is not None:
            parsed[number] = _parse_point_block(number, title, block)

    for line in lines:
        match = _POINT_HEADING_RE.match(line.strip())
        if match:
            flush()
            number = int(match.group("number"))
            title = match.group("title").strip() or None
            block = []
            continue
        if number is not None:
            block.append(line)
    flush()

    points: list[ParsedPoint] = []
    for canonical_number, canonical_title in FISHER_POINTS:
        point = parsed.pop(canonical_number, None)
        if point is None:
            point = ParsedPoint(
                number=canonical_number,
                title=canonical_title,
                is_placeholder=True,
            )
        points.append(point)
    for leftover in sorted(parsed):
        logger.warning(
            "viewer: point number %s outside 1..15 — not rendered", leftover
        )
    return points


def _valuation_lines(sections: dict[str, list[str]]) -> list[str]:
    """The valuation heading carries a variable suffix — Gen 1 wrote
    "(TTM-Stand, ohne historischen 5J-Vergleich)", Gen 2+ writes
    "(TTM-Stand + Mehrjahres-Median/Perzentil-Vergleich)"."""
    for heading, lines in sections.items():
        if heading.startswith(_HEADING_VALUATION_PREFIX):
            return lines
    return []


def _build_dossier(path: Path, meta: dict[str, Any], body: str) -> Dossier:
    sections = _split_sections(body)
    metrics, raw_metric_lines, metric_extras, peer_table = _parse_valuation_section(
        _valuation_lines(sections)
    )
    insider_summary_line, insider_detail_lines = _parse_insider_section(
        sections.get(_HEADING_INSIDER, [])
    )
    return Dossier(
        **meta,
        source_path=path,
        insider_summary_line=insider_summary_line,
        insider_detail_lines=insider_detail_lines,
        source_coverage=_parse_source_coverage(sections.get(_HEADING_COVERAGE, [])),
        company_name=_parse_company_name(sections.get("", [])),
        headline_metrics=_parse_headline_metrics(
            sections.get(_HEADING_BEWERTUNG, [])
        ),
        executive_summary=_parse_prose_section(
            sections.get(_HEADING_SUMMARY, [])
        ),
        metrics=metrics,
        raw_metric_lines=raw_metric_lines,
        metric_extras=metric_extras,
        peer_table=peer_table,
        points=_parse_points(sections.get(_HEADING_POINTS, [])),
        notes=_parse_prose_section(sections.get(_HEADING_NOTES, [])),
    )


def parse_dossier(path: Path) -> Dossier | None:
    """Parse one dossier file. Returns None when `path` is not a Tool-B
    dossier (foreign file, one-pager, placeholder) or is unparseable."""
    path = Path(path)
    if not _FILENAME_RE.match(path.name):
        logger.info("viewer: skipping non-dossier filename %s", path.name)
        return None

    post = _load_post(path)
    if post is None:
        return None

    meta = dict(post.metadata)
    if not meta.get("ticker") or not meta.get("form_type"):
        logger.info("viewer: skipping %s (no dossier frontmatter)", path.name)
        return None

    try:
        return _build_dossier(path, meta, post.content)
    except ValidationError as exc:
        logger.warning("viewer: unusable frontmatter in %s: %s", path.name, exc)
        return None


def _run_key(dossier: Dossier) -> datetime:
    """Sort key for "newest run". A hand-edited unquoted `generated_at`
    parses as naive; read it as UTC rather than crashing the comparison."""
    generated_at = dossier.generated_at
    if generated_at.tzinfo is None:
        return generated_at.replace(tzinfo=timezone.utc)
    return generated_at


def iter_dossiers(input_dir: Path) -> list[Dossier]:
    """All parseable dossiers of `input_dir`, newest run per ticker, by ticker.

    Deep dives are re-run over time and every run stays on disk; the viewer
    shows the current state, so older runs of the same ticker are dropped.
    A single unparseable file is skipped with a warning — only a missing
    input directory is fatal.
    """
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise ViewerError(f"dossier input directory not found: {input_dir}")

    newest: dict[str, Dossier] = {}
    for path in sorted(input_dir.glob("*.md")):
        dossier = parse_dossier(path)
        if dossier is None:
            continue
        previous = newest.get(dossier.ticker)
        if previous is None or _run_key(dossier) > _run_key(previous):
            newest[dossier.ticker] = dossier

    logger.info("viewer: %d dossiers after de-duplication", len(newest))
    return [newest[ticker] for ticker in sorted(newest)]
