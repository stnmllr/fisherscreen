# app/output/dimensions_generator.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import frontmatter

from app.screener.dimensions import DIMENSIONS

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)


def generate(
    records: list[ScreenerRecord],
    run_record: RunRecord,
    output_dir: Path,
    *,
    score_threshold: float = 4.0,
    cap: int = 50,
) -> Path:
    """Generate the monthly Dimensions markdown file for the Universum output.

    Writes YAML frontmatter (structured data for tooling) plus a human-readable
    markdown body with one section per Fisher dimension.

    Args:
        records: All ScreenerRecords for this run (scored and unscored).
        run_record: Metadata for the current run (provides run_id for filename).
        output_dir: Root output directory; file is written to output_dir/Universum/.
        score_threshold: Minimum dimension score for a ticker to qualify (inclusive).
        cap: Maximum number of tickers to include per dimension.

    Returns:
        Path to the written file.
    """
    universum_dir = output_dir / "Universum"
    universum_dir.mkdir(parents=True, exist_ok=True)

    run_month = run_record.run_id[:7]  # "YYYY-MM"
    out_path = universum_dir / f"{run_month}-Dimensions.md"

    scored = [r for r in records if r.gemini_dimensions is not None]
    dim_data = _compute_dimension_data(scored, score_threshold, cap)
    crosshits = _compute_crosshits_for_frontmatter(scored, score_threshold, cap)

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
    """Build per-dimension qualifying ticker lists, sorted by score descending, capped."""
    result: dict = {}
    for dim in DIMENSIONS:
        all_qualifying = sorted(
            [r for r in scored if (r.gemini_dimensions or {}).get(dim, 0) >= score_threshold],
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
    cap: int,
) -> list[dict]:
    """Find tickers that qualify in two or more dimensions (cross-dimension strength)."""
    crosshits: list[dict] = []
    for record in scored:
        dims = record.gemini_dimensions or {}
        qualifying_dims = [d for d in DIMENSIONS if dims.get(d, 0) >= score_threshold]
        if len(qualifying_dims) >= 2:
            avg = sum(dims.get(d, 0) for d in qualifying_dims) / len(qualifying_dims)
            crosshits.append(
                {
                    "ticker": record.ticker,
                    "dimensions": qualifying_dims,
                    "avg_score": round(avg, 2),
                }
            )
    crosshits.sort(key=lambda x: (-len(x["dimensions"]), -x["avg_score"]))
    return crosshits[:cap]


def _build_markdown_body(
    dim_data: dict,
    scored: list[ScreenerRecord],
    run_month: str,
    score_threshold: float,
    cap: int,
) -> str:
    """Render the human-readable markdown body with one section per dimension."""
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
                lines.append(f"| {i} | {ticker} | {name} | {sector} | {score} |")
        lines.append("")
    return "\n".join(lines)
