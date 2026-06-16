from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.screener.dimensions import qualifying_dimensions

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)


def _flags(record) -> str:
    """Audit markers: ⌖ = a sector-relative axis fell back to the global pool;
    ⚠ = low data confidence (e.g. <4 fiscal years / consistency unprovable)."""
    basis = record.score_basis or {}
    flags = ""
    if any(v == "global_fallback" for v in basis.values()):
        flags += "⌖"
    if getattr(record, "data_confidence", "ok") == "low":
        flags += "⚠"
    return flags


def generate(
    records: list[ScreenerRecord],
    run_record: RunRecord,
    output_dir: Path,
    *,
    score_threshold: float = 4.0,
    min_dimensions: int = 2,
    cap: int = 50,
    header: str | None = None,
) -> Path:
    output_dir = output_dir / "Universum"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_month = run_record.run_id[:7]  # "YYYY-MM"
    out_path = output_dir / f"{run_month}-Crosshits.md"

    scored = [r for r in records if r.gemini_dimensions is not None]
    crosshits = _compute_crosshits(scored, score_threshold, min_dimensions, cap)

    body = _build_body(crosshits, run_month, score_threshold, min_dimensions, header)
    out_path.write_text(body, encoding="utf-8")

    logger.info("crosshits: wrote %s (%d crosshits)", out_path.name, len(crosshits))
    return out_path


def _compute_crosshits(
    scored: list[ScreenerRecord],
    score_threshold: float,
    min_dimensions: int,
    cap: int,
) -> list[dict]:
    result = []
    for record in scored:
        qualifying = qualifying_dimensions(record, score_threshold)
        if len(qualifying) >= min_dimensions:
            dims = record.gemini_dimensions or {}
            avg = sum(dims.get(d, 0) for d in qualifying) / len(qualifying)
            # Ranking sharpener: more top scores (5) among the qualifying merit
            # dimensions ranks higher. Monotonic with avg today, but stays correct
            # if the threshold/min_dimensions knobs change later.
            num_fives = sum(1 for d in qualifying if dims.get(d) == 5)
            result.append({
                "record": record,
                "qualifying_dims": qualifying,
                "avg_score": round(avg, 2),
                "num_fives": num_fives,
            })
    result.sort(key=lambda x: (-len(x["qualifying_dims"]), -x["num_fives"], -x["avg_score"]))
    return result[:cap]


def _build_body(
    crosshits: list[dict],
    run_month: str,
    score_threshold: float,
    min_dimensions: int,
    header: str | None = None,
) -> str:
    lines = [f"# Universum {run_month} — Crosshits", ""]
    if header:
        lines += [header.rstrip("\n"), ""]
    lines += [
        f"*Schwelle: Score ≥{score_threshold} in ≥{min_dimensions} Dimensionen*",
        "",
    ]
    if not crosshits:
        lines += [
            "> Keine Crosshits in diesem Lauf. Entweder kein Ticker erreichte die Schwelle",
            "> in mindestens zwei Dimensionen, oder das Universum war nach Filtern zu klein.",
        ]
    else:
        lines += [
            "| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score |",
            "|---|---|---|---|---|---|---|",
        ]
        for i, entry in enumerate(crosshits, 1):
            r = entry["record"]
            dims_str = ", ".join(entry["qualifying_dims"])
            lines.append(
                f"| {i} | {r.ticker} {_flags(r)} | {r.name or ''} | {r.gics_sector or ''} "
                f"| {len(entry['qualifying_dims'])} | {dims_str} | {entry['avg_score']} |"
            )
    return "\n".join(lines) + "\n"
