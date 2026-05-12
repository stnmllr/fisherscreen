import logging

from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

MIN_MARKET_CAP_USD: float = 300_000_000
MIN_AVG_DAILY_VOLUME: float = 100_000
MIN_PRICE_USD: float = 1.0
MAX_BID_ASK_SPREAD_PCT: float = 0.05


def passes_market_cap_filter(record: ScreenerRecord) -> bool:
    if record.market_cap is None:
        logger.warning("ticker=%s market_cap missing", record.ticker)
        return False
    return record.market_cap >= MIN_MARKET_CAP_USD


def passes_volume_filter(record: ScreenerRecord) -> bool:
    if record.avg_daily_volume is None:
        logger.warning("ticker=%s avg_daily_volume missing", record.ticker)
        return False
    return record.avg_daily_volume >= MIN_AVG_DAILY_VOLUME


def passes_penny_stock_filter(record: ScreenerRecord) -> bool:
    if record.price is None:
        logger.warning("ticker=%s price missing", record.ticker)
        return False
    return record.price >= MIN_PRICE_USD


def passes_liquidity_filter(record: ScreenerRecord) -> bool:
    if not record.bid or not record.ask:
        logger.warning("ticker=%s bid/ask missing or zero", record.ticker)
        return False
    mid = (record.bid + record.ask) / 2
    spread_pct = (record.ask - record.bid) / mid
    return spread_pct <= MAX_BID_ASK_SPREAD_PCT


def _get_fail_reason(record: ScreenerRecord) -> str | None:
    if not passes_market_cap_filter(record):
        return "market_cap"
    if not passes_volume_filter(record):
        return "avg_volume"
    if not passes_penny_stock_filter(record):
        return "penny_stock"
    if not passes_liquidity_filter(record):
        return "liquidity"
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
    logger.info("basis_filter: %d/%d records passed", len(passed), len(records))
    return passed
