# app/output/changes_generator.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    universum_dir = output_dir / "Universum"
    universum_dir.mkdir(parents=True, exist_ok=True)

    run_month = run_record.run_id[:7]  # "YYYY-MM"
    out_path = universum_dir / f"{run_month}-Changes.md"

    current_dim_tickers = _compute_current_dim_tickers(records, score_threshold, cap)
    prior_result = _load_prior_frontmatter(universum_dir, run_month)
    body = _build_body(run_month, current_dim_tickers, prior_result)
    out_path.write_text(body, encoding="utf-8")

    logger.info("changes: wrote %s", out_path.name)
    return out_path


def _compute_current_dim_tickers(
    records: list[ScreenerRecord],
    score_threshold: float,
    cap: int,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {dim: set() for dim in DIMENSIONS}
    for record in records:
        if record.gemini_dimensions is None:
            continue
        for dim in DIMENSIONS:
            if record.gemini_dimensions.get(dim, 0) >= score_threshold:
                result[dim].add(record.ticker)
    for dim in DIMENSIONS:
        if len(result[dim]) > cap:
            result[dim] = set(list(result[dim])[:cap])
    return result


def _load_prior_frontmatter(universum_dir: Path, current_month: str) -> dict[str, Any] | None:
    candidates = sorted(universum_dir.glob("????-??-Dimensions.md"))
    candidates = [p for p in candidates if p.stem[:7] < current_month]
    if not candidates:
        return None
    prior_path = candidates[-1]
    try:
        post = frontmatter.load(str(prior_path))
        dims = post.metadata.get("dimensions", {})
        if not dims:
            return None
        return {"path": prior_path, "dimensions": dims}
    except Exception as exc:
        logger.warning("changes: failed to parse %s — treating as no prior: %s", prior_path.name, exc)
        return None


def _build_body(
    run_month: str,
    current: dict[str, set[str]],
    prior_result: dict[str, Any] | None,
) -> str:
    lines = [f"# Universum {run_month} — Changes", ""]

    if prior_result is None:
        lines += [
            "> Erster verfügbarer Run. Keine Vergleichsbasis vorhanden.",
            "> Alle Ticker in diesem Run sind neu im Universum.",
        ]
        return "\n".join(lines) + "\n"

    prior_path: Path = prior_result["path"]
    prior_dims: dict[str, Any] = prior_result["dimensions"]
    prior_month = prior_path.stem[:7]

    lines.append(f"*Vergleichsbasis: {prior_path.name} | Aktuell: {run_month}*")
    if prior_month != _month_minus_one(run_month):
        lines.append(
            f"*Hinweis: {_month_minus_one(run_month)}-Run nicht verfügbar — Diff gegen {prior_month}.*"
        )
    lines.append("")

    any_change = False
    for dim in DIMENSIONS:
        prior_tickers: set[str] = set(prior_dims.get(dim, {}).get("tickers", []))
        current_tickers: set[str] = current.get(dim, set())
        new_in = current_tickers - prior_tickers
        removed = prior_tickers - current_tickers

        if new_in or removed:
            any_change = True
            lines.append(f"## {dim.capitalize()}")
            if new_in:
                lines.append(f"**Neu:** {', '.join(sorted(new_in))}")
            if removed:
                lines.append(f"**Raus:** {', '.join(sorted(removed))}")
            lines.append("")

    if not any_change:
        lines.append("*Keine Änderungen gegenüber dem Vormonat.*")

    return "\n".join(lines) + "\n"


def _month_minus_one(ym: str) -> str:
    year, month = int(ym[:4]), int(ym[5:7])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"
