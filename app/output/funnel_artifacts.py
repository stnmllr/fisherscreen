from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from app.screener.funnel import Dropout, FunnelSummary

logger = logging.getLogger(__name__)

_CSV_FIELDS = [
    "ticker", "stage", "reason_code", "severity_bucket",
    "is_large_cap", "sector_wide", "market_cap_eur", "gics_sector",
    "detail",
]


def write_funnel_artifacts(
    summary: FunnelSummary,
    dropouts: list[Dropout],
    output_dir: Path,
    run_month: str,
) -> list[Path]:
    out = output_dir / "Universum"
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / f"{run_month}-funnel_summary.json"
    json_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")

    csv_path = out / f"{run_month}-dropouts.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for d in dropouts:
            writer.writerow({
                "ticker": d.ticker,
                "stage": d.stage.value,
                "reason_code": d.reason_code.value,
                "severity_bucket": d.severity_bucket.value,
                "is_large_cap": d.is_large_cap,
                "sector_wide": d.sector_wide,
                "market_cap_eur": d.market_cap_eur,
                "gics_sector": d.gics_sector,
                "detail": d.detail,
            })

    logger.info("funnel: wrote %s (%d dropouts, %d review-flags)",
                json_path.name, len(dropouts), summary.review_flags)
    return [json_path, csv_path]
