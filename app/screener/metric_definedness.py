# app/screener/metric_definedness.py
"""Metric-definedness predicate + waterfall-shape discriminator for the
gross_margin gate (Punkt 2). The .info-only predicate is the runtime DEFAULT;
the waterfall classifier is used by the Gate-A calibration probe and becomes the
runtime predicate only if Gate-A finds a non-empty edge (spec §6 Property A)."""
from __future__ import annotations

from app.models.screener_record import ScreenerRecord


def is_gross_margin_undefined_info_only(record: ScreenerRecord) -> bool:
    """Runtime DEFAULT definedness predicate (.info-only, no fetch).
    gm is None or <= 0 => treat as structurally undefined => METRIK_NA."""
    gm = record.gross_margin
    return gm is None or gm <= 0.0
