import logging

from app.errors import FilterConfigError
from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord
from app.screener.industry_group_map import INDUSTRY_GROUP_MAP
from app.screener.sector_buckets import SectorMedianTable, bucket_median

logger = logging.getLogger(__name__)

MIN_MARKET_CAP_EUR: float = 2_000_000_000
# GATE-A-approved EUR daily-trading-value floor (2026-06-08). Structural anchor: the empty
# 0.89M-2.45M band between broken/micro and the survivor population; absolute trading minimum,
# not a relative gap. See docs/superpowers/audits/2026-06-08-1-value-floor/calibration.md.
MIN_AVG_DAILY_VALUE_EUR: float | None = 1_000_000.0
MIN_GROSS_MARGIN: float = 0.30
MIN_REVENUE_GROWTH: float = 0.0
# Phase E (2026-06): relative-arm factor calibrated against the v4-clean pinned table.
# k=0.5 is the maximal-clean ceiling (the first healthy name, AES, falls at k>0.514);
# the sub-k band below it is broken-dominated. See calibration.md (Punkt 2 Phase E).
GROSS_MARGIN_RELATIVE_K: float | None = 0.5


def passes_market_cap_filter(record: ScreenerRecord) -> bool:
    if record.market_cap_eur is None:
        logger.warning("ticker=%s market_cap_eur missing", record.ticker)
        return False
    return record.market_cap_eur >= MIN_MARKET_CAP_EUR


def _avg_daily_value_eur(record: ScreenerRecord) -> float | None:
    """Average daily traded value in EUR = shares/day x price x fx. None if any input
    is missing (an invariant violation at the gate — resolution diverts these)."""
    if record.avg_daily_volume is None or record.price is None or record.fx_rate is None:
        return None
    return record.avg_daily_volume * record.price * record.fx_rate


def passes_volume_filter(record: ScreenerRecord) -> bool:
    if MIN_AVG_DAILY_VALUE_EUR is None:
        raise FilterConfigError(
            "MIN_AVG_DAILY_VALUE_EUR not calibrated (sentinel) — run the calibration gate"
        )
    value = _avg_daily_value_eur(record)
    if value is None:
        raise FilterConfigError(
            f"ticker={record.ticker} value uncomputable at volume gate "
            "(invariant violation: vol/price/fx_rate missing — resolution should have diverted)"
        )
    return value >= MIN_AVG_DAILY_VALUE_EUR


def _node_chain(record: ScreenerRecord) -> list[str]:
    # CT-B (Punkt 2): roll industry up to its GICS *industry group*, NOT the sector.
    # The GICS sector is multimodal — the catch-all contamination CT-B exists to kill;
    # the group is the exogenous, margin-blind intermediate node. A thin industry with
    # no map entry yields chain == [industry]; if that does not clear n_min, resolve_bucket
    # returns None and the relative arm stays dormant (fail-safe: no rescue beats a
    # wrong-bucket rescue). The sector is never consulted.
    industry = record.gics_industry
    group = INDUSTRY_GROUP_MAP.get(industry) if industry else None
    return [n for n in (industry, group) if n]


ABSOLUTE_PASS = "ABSOLUTE_PASS"
RELATIVE_RESCUE = "RELATIVE_RESCUE"


def gross_margin_pass_reason(
    record: ScreenerRecord,
    table: SectorMedianTable | None = None,
    k: float | None = None,
) -> str | None:
    """Why a record clears (or fails) the gross-margin gate — the audit primitive.

    Returns ABSOLUTE_PASS (gm >= MIN_GROSS_MARGIN), RELATIVE_RESCUE (sub-floor name
    rescued by the relative arm: gm < MIN_GROSS_MARGIN AND gm >= k*bucket_median), or
    None (fails the gate / relative arm dormant / no valid bucket reference).

    RELATIVE_RESCUE is reserved for SUB-FLOOR names only: a gm >= MIN_GROSS_MARGIN name
    clears k*median trivially but is ABSOLUTE_PASS — tagging it RELATIVE_RESCUE would
    inflate the rescue count and break the Gate-B additivity identity. Branch structure
    mirrors passes_gross_margin_filter exactly (single source of truth)."""
    gm = record.gross_margin
    if gm is None:
        logger.warning("ticker=%s gross_margin missing", record.ticker)
        return None
    if gm >= MIN_GROSS_MARGIN:          # absolute arm
        return ABSOLUTE_PASS
    if table is None or k is None:      # relative arm fail-safe: dormant
        return None
    median = bucket_median(_node_chain(record), table)
    if median is None:                  # thin sector / no valid reference -> no rescue
        return None
    return RELATIVE_RESCUE if gm >= k * median else None


def passes_gross_margin_filter(
    record: ScreenerRecord,
    table: SectorMedianTable | None = None,
    k: float | None = None,
) -> bool:
    return gross_margin_pass_reason(record, table, k) is not None


def passes_revenue_growth_filter(record: ScreenerRecord) -> bool:
    if record.revenue_growth_yoy is None:
        logger.warning("ticker=%s revenue_growth_yoy missing", record.ticker)
        return False
    return record.revenue_growth_yoy >= MIN_REVENUE_GROWTH


def _get_fail_reason(
    record: ScreenerRecord,
    table: SectorMedianTable | None = None,
    k: float | None = None,
) -> str | None:
    if not passes_volume_filter(record):
        return "avg_volume"
    if not passes_market_cap_filter(record):
        return "market_cap"
    # CT-A: read the pre-computed definedness verdict from the runner pre-pass.
    # UNASSESSABLE = transient fetch failure (retryable); METRIK_NA = structurally undefined.
    # DEFINED or None (non-suspect / not assessed) -> continue to the gross_margin gate.
    if record.definedness is DefinednessOutcome.UNASSESSABLE:
        return "statement_unavailable"
    if record.definedness is DefinednessOutcome.METRIK_NA:
        return "metric_na"
    if not passes_gross_margin_filter(record, table, k):
        return "gross_margin"
    if not passes_revenue_growth_filter(record):
        return "revenue_growth"
    return None


def apply_basis_filters(
    records: list[ScreenerRecord],
    sector_table: SectorMedianTable | None = None,
    relative_k: float | None = None,
) -> list[ScreenerRecord]:
    passed = []
    for record in records:
        reason = _get_fail_reason(record, sector_table, relative_k)
        if reason:
            record.filter_failed_reason = reason
            record.filter_passed_basis = False
        else:
            record.filter_passed_basis = True
            # Tag HOW this record cleared the gross-margin gate (prod audit primitive):
            # ABSOLUTE_PASS (>= floor) or RELATIVE_RESCUE (sub-floor, rescued by the
            # relative arm). Only set on basis-passers — a record that failed an earlier
            # gate never reached/cleared the gross-margin gate.
            record.gross_margin_pass_reason = gross_margin_pass_reason(
                record, sector_table, relative_k
            )
            passed.append(record)

    us_passed = sum(1 for r in passed if "." not in r.ticker)
    eu_passed = len(passed) - us_passed
    us_total = sum(1 for r in records if "." not in r.ticker)
    eu_total = len(records) - us_total
    logger.info(
        "basis_filter: %d/%d records passed (US %d/%d, EU %d/%d)",
        len(passed), len(records),
        us_passed, us_total,
        eu_passed, eu_total,
    )
    return passed


def apply_edgar_filters(records: list[ScreenerRecord]) -> list[ScreenerRecord]:
    passed = []
    for record in records:
        if record.edgar_skipped:
            record.filter_passed_edgar = None
            passed.append(record)
            continue
        if record.has_restatement:
            record.filter_passed_edgar = False
            record.filter_failed_reason = "restatement"
            continue
        if record.has_going_concern:
            record.filter_passed_edgar = False
            record.filter_failed_reason = "going_concern"
            continue
        if record.has_active_enforcement:
            record.filter_passed_edgar = False
            record.filter_failed_reason = "enforcement"
            continue
        record.filter_passed_edgar = True
        passed.append(record)
    logger.info("edgar_filter: %d/%d records passed", len(passed), len(records))
    return passed
