# app/output/dimensions_generator.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import frontmatter

from app.output.crosshits_generator import _flags
from app.screener.dimensions import DIMENSIONS, is_crosshit, qualifying_dimensions

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

# Top Gemini score; counted as a ranking tiebreaker like in crosshits_generator.
_MAX_SCORE = 5

# management/innovation are sentinel-3 (not merit). Render an explicit n/a note
# instead of a "no ticker reached the threshold" list, since the threshold is N/A.
_NON_MERIT_BODY: dict[str, str] = {
    "management": "*n/a — Governance wird upstream im EDGAR-Gate geprüft (kein Merit-Score).*",
    "innovation": "*n/a — keine R&D-Daten; verschoben auf Deep Dive (kein Merit-Score).*",
}


def generate(
    records: list[ScreenerRecord],
    run_record: RunRecord,
    output_dir: Path,
    *,
    score_threshold: float = 4.0,
    min_dimensions: int = 2,
    cap: int = 50,
) -> Path:
    universum_dir = output_dir / "Universum"
    universum_dir.mkdir(parents=True, exist_ok=True)

    run_month = run_record.run_id[:7]  # "YYYY-MM"
    out_path = universum_dir / f"{run_month}-Dimensions.md"

    scored = [r for r in records if r.gemini_dimensions is not None]
    dim_data = _compute_dimension_data(scored, score_threshold, cap)
    crosshits = _compute_crosshits_for_frontmatter(
        scored, score_threshold, min_dimensions, cap
    )

    metadata: dict = {
        "run_id": run_record.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universum_size": len(records),
        "score_threshold": score_threshold,
        "cap_per_dimension": cap,
        "dimensions": dim_data,
        "crosshits": crosshits,
    }
    body = _build_markdown_body(dim_data, scored, run_month, score_threshold, cap)

    post = frontmatter.Post(body)
    post.metadata.update(metadata)
    out_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    logger.info(
        "dimensions: wrote %s (%d records, %d scored)",
        out_path.name,
        len(records),
        len(scored),
    )
    return out_path


def _compute_dimension_data(
    scored: list[ScreenerRecord],
    score_threshold: float,
    cap: int,
) -> dict:
    result: dict = {}
    for dim in DIMENSIONS:
        all_qualifying = sorted(
            [
                r
                for r in scored
                if (r.gemini_dimensions or {}).get(dim, 0) >= score_threshold
            ],
            key=lambda r, d=dim: (r.gemini_dimensions or {}).get(d, 0),
            reverse=True,
        )
        result[dim] = {
            "qualifying_count": len(all_qualifying),
            "tickers": [r.ticker for r in all_qualifying[:cap]],
        }
    return result


def _compute_crosshits_for_frontmatter(
    scored: list[ScreenerRecord],
    score_threshold: float,
    min_dimensions: int,
    cap: int,
) -> list[dict]:
    """Frontmatter crosshit list, decided by `is_crosshit` — the same rule the
    funnel counts with — so frontmatter, Crosshits.md table and funnel count
    cannot disagree. Only merit axes are listed; ranked by (#axes, #fives, avg).
    """
    ranked: list[tuple[tuple[int, int, float], dict]] = []
    for record in scored:
        if not is_crosshit(record, score_threshold, min_dimensions):
            continue
        dims = record.gemini_dimensions or {}
        qualifying = qualifying_dimensions(record, score_threshold)
        scores = [dims.get(d, 0) for d in qualifying]
        avg = round(sum(scores) / len(scores), 2)
        num_fives = sum(1 for s in scores if s == _MAX_SCORE)
        entry = {"ticker": record.ticker, "dimensions": qualifying, "avg_score": avg}
        ranked.append(((-len(qualifying), -num_fives, -avg), entry))
    ranked.sort(key=lambda item: item[0])
    return [entry for _, entry in ranked[:cap]]


def _build_markdown_body(
    dim_data: dict,
    scored: list[ScreenerRecord],
    run_month: str,
    score_threshold: float,
    cap: int,
) -> str:
    ticker_lookup = {r.ticker: r for r in scored}
    lines: list[str] = [
        f"# Universum {run_month} — Dimensions",
        "",
        f"*Score-Schwelle: ≥{score_threshold} | Cap pro Dimension: {cap}*",
        "",
        "---",
        "",
    ]
    for dim in DIMENSIONS:
        tickers = dim_data[dim]["tickers"]
        count = dim_data[dim]["qualifying_count"]
        if dim in _NON_MERIT_BODY:
            lines.append(f"## {dim.capitalize()}")
            lines.append("")
            lines.append(_NON_MERIT_BODY[dim])
            lines.append("")
            continue
        lines.append(f"## {dim.capitalize()} (n={count})")
        lines.append("")
        if not tickers:
            lines.append("*Kein Ticker erreichte die Score-Schwelle.*")
        else:
            lines.append("| # | Ticker | Name | Sektor | Score |")
            lines.append("|---|---|---|---|---|")
            for i, ticker in enumerate(tickers, 1):
                r = ticker_lookup.get(ticker)
                name = (r.name or "") if r else ""
                sector = (r.gics_sector or "") if r else ""
                score = (r.gemini_dimensions or {}).get(dim, "") if r else ""
                lines.append(
                    f"| {i} | {ticker} {_flags(r) if r else ''} | {name} | {sector} | {score} |"
                )
        lines.append("")
    return "\n".join(lines)
