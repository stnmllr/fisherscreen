import logging

from app.errors import FilterConfigError
from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

MIN_MARKET_CAP_EUR: float = 2_000_000_000
# Fail-loud sentinel: None until the calibration gate sets the approved EUR value floor.
# A real run with the sentinel RAISES (impossible to ship an uncalibrated guess).
MIN_AVG_DAILY_VALUE_EUR: float | None = None
MIN_GROSS_MARGIN: float = 0.30
MIN_REVENUE_GROWTH: float = 0.0


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


def passes_gross_margin_filter(record: ScreenerRecord) -> bool:
    if record.gross_margin is None:
        logger.warning("ticker=%s gross_margin missing", record.ticker)
        return False
    return record.gross_margin >= MIN_GROSS_MARGIN


def passes_revenue_growth_filter(record: ScreenerRecord) -> bool:
    if record.revenue_growth_yoy is None:
        logger.warning("ticker=%s revenue_growth_yoy missing", record.ticker)
        return False
    return record.revenue_growth_yoy >= MIN_REVENUE_GROWTH


def _get_fail_reason(record: ScreenerRecord) -> str | None:
    if not passes_volume_filter(record):
        return "avg_volume"
    if not passes_market_cap_filter(record):
        return "market_cap"
    if not passes_gross_margin_filter(record):
        return "gross_margin"
    if not passes_revenue_growth_filter(record):
        return "revenue_growth"
    return None


def apply_basis_filters(records: list[ScreenerRecord]) -> list[ScreenerRecord]:
    passed = []
    for record in records:
        reason = _get_fail_reason(record)
        if reason:
            record.filter_failed_reason = reason
            record.filter_passed_basis = False
        else:
            record.filter_passed_basis = True
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
