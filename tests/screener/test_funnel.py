from app.screener.funnel import (
    LARGE_CAP_GROWTH_EUR,
    LARGE_CAP_VOLUME_EUR,
    ReasonCode,
    SeverityBucket,
    _severity,
)


def test_volume_threshold_decoupled_from_growth():
    # market cap between the two thresholds (3B..10B): REVIEW for volume, BENIGN for growth.
    mc = 5_000_000_000
    assert LARGE_CAP_VOLUME_EUR < mc < LARGE_CAP_GROWTH_EUR
    assert _severity(ReasonCode.GATE_VOLUME, market_cap_eur=mc, sector_wide=False) == SeverityBucket.REVIEW
    assert _severity(ReasonCode.GATE_REVENUE_GROWTH, market_cap_eur=mc, sector_wide=False) == SeverityBucket.BENIGN


def test_growth_review_above_growth_threshold():
    assert _severity(ReasonCode.GATE_REVENUE_GROWTH, market_cap_eur=20_000_000_000, sector_wide=False) == SeverityBucket.REVIEW


def test_market_cap_none_is_benign_never_crashes():
    assert _severity(ReasonCode.GATE_VOLUME, market_cap_eur=None, sector_wide=False) == SeverityBucket.BENIGN


def test_gross_margin_review_only_when_sector_wide():
    assert _severity(ReasonCode.GATE_GROSS_MARGIN, market_cap_eur=None, sector_wide=True) == SeverityBucket.REVIEW
    assert _severity(ReasonCode.GATE_GROSS_MARGIN, market_cap_eur=None, sector_wide=False) == SeverityBucket.BENIGN


def test_always_review_codes():
    for rc in (ReasonCode.RESOLUTION_DEGRADED_DICT, ReasonCode.SCORE_NOT_SCORED):
        assert _severity(rc, market_cap_eur=None, sector_wide=False) == SeverityBucket.REVIEW


def test_always_benign_codes():
    for rc in (ReasonCode.GATE_MARKET_CAP, ReasonCode.GATE_GOING_CONCERN,
               ReasonCode.GATE_ENFORCEMENT, ReasonCode.GATE_RESTATEMENT,
               ReasonCode.RESOLUTION_UNRESOLVED, ReasonCode.SCORE_BELOW_THRESHOLD):
        assert _severity(rc, market_cap_eur=None, sector_wide=False) == SeverityBucket.BENIGN
