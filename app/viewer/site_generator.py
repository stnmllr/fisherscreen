"""Builds the static site: one overview plus one page per dossier.

The only part of the viewer that touches the filesystem. Two things it
guards: filenames — tickers legitimately carry `.` and `-` and must not be
renamed, because the overview already links to the unchanged symbol — and
visibility: a dossier that cannot become a page is named on the overview
instead of disappearing between input directory and output directory.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Sequence

from app.viewer.assets import CSS_FILENAME, JS_FILENAME, SITE_CSS, SORT_JS
from app.viewer.dossier_parser import parse_dossier
from app.viewer.models import Dossier
from app.viewer.render_detail import render_detail
from app.viewer.render_overview import build_overview_row, render_overview

logger = logging.getLogger(__name__)

INDEX_FILENAME: Final[str] = "index.html"
TICKER_DIRNAME: Final[str] = "ticker"

# A ticker becomes a filename verbatim. `.` and `-` are fine; a path
# separator is not, and neither is its URL-encoded link (`%2F` decodes back
# to a directory boundary). Historically seen: RDS/A.
_PATH_SEPARATORS: Final[tuple[str, ...]] = ("/", "\\")
_UNWRITABLE_NOTICE: Final[str] = (
    "{filename} ({ticker}: Symbol enthält einen Pfadtrenner und ergibt keinen "
    "gültigen Dateinamen)"
)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    logger.debug("viewer: wrote %s", path)


def _is_writable(dossier: Dossier) -> bool:
    return not any(sep in dossier.ticker for sep in _PATH_SEPARATORS)


def _duplicate_names(dossiers: Sequence[Dossier]) -> set[str]:
    """Company names carried by more than one dossier.

    Two runs of one company under different symbols stay separate rows; the
    overview only marks them, because merging them would guess an identity
    no ISIN or CIK confirms.
    """
    counts = Counter(
        dossier.company_name
        for dossier in dossiers
        if dossier.company_name is not None
    )
    return {name for name, count in counts.items() if count > 1}


def generate_site(
    dossiers: Sequence[Dossier],
    output_dir: Path,
    *,
    generated_at: datetime | None = None,
    skipped: Sequence[str] = (),
) -> Path:
    """Write the whole site and return the path of the index page.

    `generated_at` defaults to the clock for the CLI; callers that care
    about byte-identical rebuilds inject it. `skipped` names input files
    that never became a dossier — they are printed on the overview, since a
    dossier that vanishes without a trace looks like one that was never
    written.
    """
    stamp = generated_at or datetime.now(timezone.utc)
    output_dir = Path(output_dir)
    ticker_dir = output_dir / TICKER_DIRNAME
    ticker_dir.mkdir(parents=True, exist_ok=True)

    renderable = [dossier for dossier in dossiers if _is_writable(dossier)]
    notices = list(skipped) + _unwritable_notices(dossiers)
    duplicates = _duplicate_names(renderable)

    _write(output_dir / CSS_FILENAME, SITE_CSS)
    _write(output_dir / JS_FILENAME, SORT_JS)
    for dossier in renderable:
        _write(
            ticker_dir / f"{dossier.ticker}.html",
            render_detail(dossier, generated_at=stamp),
        )

    rows = [
        build_overview_row(dossier, duplicate_names=duplicates)
        for dossier in renderable
    ]
    index_path = output_dir / INDEX_FILENAME
    _write(index_path, render_overview(rows, generated_at=stamp, skipped=notices))
    logger.info(
        "viewer: wrote %s (%d detail pages, %d skipped)",
        index_path,
        len(renderable),
        len(notices),
    )
    return index_path


def _unwritable_notices(dossiers: Sequence[Dossier]) -> list[str]:
    notices = []
    for dossier in dossiers:
        if _is_writable(dossier):
            continue
        logger.warning(
            "viewer: %s has no valid filename — no detail page written",
            dossier.ticker,
        )
        notices.append(
            _UNWRITABLE_NOTICE.format(
                filename=dossier.source_path.name, ticker=dossier.ticker
            )
        )
    return notices


def skipped_filenames(input_dir: Path, dossiers: Sequence[Dossier]) -> list[str]:
    """Input files that produced no dossier at all.

    Files that merely lost the de-duplication (an older run of a ticker that
    also has a newer one) are not reported: they were dropped on purpose,
    and calling them skipped would report a defect where none is. Hence the
    second parse of the leftovers — parseability, not absence, is the
    criterion.
    """
    rendered = {dossier.source_path.name for dossier in dossiers}
    return [
        path.name
        for path in sorted(Path(input_dir).glob("*.md"))
        if path.name not in rendered and parse_dossier(path) is None
    ]
