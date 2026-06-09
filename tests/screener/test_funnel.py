from app.models.screener_record import ScreenerRecord
from app.screener.funnel import (
    LARGE_CAP_GROWTH_EUR,
    LARGE_CAP_VOLUME_EUR,
    ReasonCode,
    SeverityBucket,
    Stage,
    _severity,
    build_funnel,
)
from app.screener.runner import BasisFilterResult


def test_resolution_data_quality_codes_always_review():
    # mc=None must not trip is_large_cap/tripwire — severity path is None-safe.
    for rc in (ReasonCode.RESOLUTION_NO_SYMBOL_DATA, ReasonCode.RESOLUTION_FX_UNAVAILABLE):
        assert _severity(rc, market_cap_eur=None, sector_wide=False) == SeverityBucket.REVIEW


def _dq_record(ticker, detail):
    r = ScreenerRecord(ticker=ticker, gics_sector="Technology", market_cap_eur=None)
    r.resolution_detail = detail
    return r


def test_funnel_diverts_count_as_resolution_review_and_reconcile():
    vol = _resolved("VOL", basis_reason="avg_volume")
    ok = _resolved("OK")
    nsd = _dq_record("NSD", "NO_RAW_MC")
    fxu = _dq_record("FXU", "NO_FX")
    basis = BasisFilterResult(passed=[ok], unresolved=[], resolved=[vol, ok],
                              degraded=[], no_symbol_data=[nsd], fx_unavailable=[fxu])
    summary, dropouts = build_funnel(universe=["VOL", "OK", "NSD", "FXU"], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    by = {d.ticker: d for d in dropouts}
    assert by["NSD"].reason_code == ReasonCode.RESOLUTION_NO_SYMBOL_DATA
    assert by["NSD"].severity_bucket == SeverityBucket.REVIEW
    assert by["NSD"].detail == "NO_RAW_MC"
    assert by["FXU"].reason_code == ReasonCode.RESOLUTION_FX_UNAVAILABLE
    # Guardrail 1: basis_gates.entered derived from resolution.remaining (not independent)
    assert summary.stage(Stage.BASIS_GATES).entered == summary.stage(Stage.RESOLUTION).remaining
    assert summary.stage(Stage.RESOLUTION).dropped == 2  # NSD + FXU (unresolved empty)
    assert len(dropouts) + summary.stage(Stage.EDGAR_GATES).remaining == 4


def test_diverts_do_not_shift_sector_wide():
    ind = [_resolved(f"I{i}", sector="Industrials", basis_reason="gross_margin") for i in range(6)]
    nsd = _dq_record("NSD", "NO_RAW_MC")
    nsd.gics_sector = "Industrials"
    basis = BasisFilterResult(passed=[], unresolved=[], resolved=ind, degraded=[],
                              no_symbol_data=[nsd], fx_unavailable=[])
    summary, dropouts = build_funnel(universe=[r.ticker for r in ind] + ["NSD"], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    margin = [d for d in dropouts if d.reason_code == ReasonCode.GATE_GROSS_MARGIN]
    assert len(margin) == 6 and all(d.sector_wide is True for d in margin)
    nsd_drop = next(d for d in dropouts if d.ticker == "NSD")
    assert nsd_drop.sector_wide is False


def test_volume_threshold_decoupled_from_growth():
    # market cap between the two thresholds (3B..10B): REVIEW for volume, BENIGN for growth.
    mc = 5_000_000_000
    assert LARGE_CAP_VOLUME_EUR < mc < LARGE_CAP_GROWTH_EUR
    assert _severity(ReasonCode.GATE_VOLUME, market_cap_eur=mc, sector_wide=False) == SeverityBucket.REVIEW
    assert _severity(ReasonCode.GATE_REVENUE_GROWTH, market_cap_eur=mc, sector_wide=False) == SeverityBucket.BENIGN


def test_large_cap_volume_drop_is_review_regardless_of_metric():
    from app.screener.funnel import _severity, ReasonCode, SeverityBucket, LARGE_CAP_VOLUME_EUR
    assert _severity(ReasonCode.GATE_VOLUME, market_cap_eur=LARGE_CAP_VOLUME_EUR + 1,
                     sector_wide=False) == SeverityBucket.REVIEW


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


def _resolved(ticker, sector="Technology", mc=5e9, *, basis_reason=None,
              edgar_reason=None, edgar_skipped=None, dims=None):
    r = ScreenerRecord(ticker=ticker, gics_sector=sector, market_cap_eur=mc)
    if basis_reason:
        r.filter_passed_basis = False
        r.filter_failed_reason = basis_reason
        return r
    r.filter_passed_basis = True
    if edgar_skipped:
        r.edgar_skipped = True
        r.edgar_skipped_reason = edgar_skipped
        r.filter_passed_edgar = None
    elif edgar_reason:
        r.filter_passed_edgar = False
        r.filter_failed_reason = edgar_reason
    else:
        r.filter_passed_edgar = True
    r.gemini_dimensions = dims
    return r


def test_reconciliation_invariant_full_run():
    skipped = _resolved("SKIP", edgar_skipped="no_cik", dims={"growth": 4, "profitability": 4})
    below = _resolved("LOW", dims={"growth": 4})
    hit = _resolved("HIT", dims={"growth": 4, "profitability": 4})
    vol = _resolved("VOL", basis_reason="avg_volume")
    gc = _resolved("GC", edgar_reason="going_concern")
    resolved = [vol, skipped, gc, below, hit]
    passed = [skipped, gc, below, hit]
    scored = [skipped, below, hit]
    basis = BasisFilterResult(passed=passed, unresolved=["DEGR", "GONE"],
                              resolved=resolved, degraded=["DEGR"])
    summary, dropouts = build_funnel(
        universe=["VOL", "SKIP", "GC", "LOW", "HIT", "DEGR", "GONE"],
        basis=basis, scored=scored,
        score_threshold=4.0, crosshits_min_dimensions=2,
    )
    crosshit_uebrig = summary.stage(Stage.CROSSHITS).remaining
    assert len(dropouts) + crosshit_uebrig == 7
    drop_tickers = [d.ticker for d in dropouts]
    assert len(drop_tickers) == len(set(drop_tickers))
    assert set(drop_tickers) <= {"VOL", "SKIP", "GC", "LOW", "HIT", "DEGR", "GONE"}
    assert "HIT" not in drop_tickers
    assert "SKIP" not in drop_tickers
    assert summary.pass_through_count == 1


def test_dry_run_omits_scoring_stages():
    vol = _resolved("VOL", basis_reason="avg_volume")
    ok = _resolved("OK")
    basis = BasisFilterResult(passed=[ok], unresolved=[], resolved=[vol, ok], degraded=[])
    summary, dropouts = build_funnel(universe=["VOL", "OK"], basis=basis, scored=None,
                                     score_threshold=4.0, crosshits_min_dimensions=2)
    assert summary.stage(Stage.SCORING).ran is False
    assert summary.stage(Stage.CROSSHITS).ran is False
    assert summary.stage(Stage.EDGAR_GATES).remaining == 1


def test_sector_wide_excludes_margin_free_sectors():
    fin = [_resolved(f"F{i}", sector="Financial Services", basis_reason="gross_margin")
           for i in range(6)]
    basis = BasisFilterResult(passed=[], unresolved=[], resolved=fin, degraded=[])
    summary, dropouts = build_funnel(universe=[r.ticker for r in fin], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    assert all(d.severity_bucket == SeverityBucket.BENIGN for d in dropouts)
    assert all(d.sector_wide is False for d in dropouts)


def test_sector_wide_fires_for_normal_sector():
    ind = [_resolved(f"I{i}", sector="Industrials", basis_reason="gross_margin")
           for i in range(6)]
    basis = BasisFilterResult(passed=[], unresolved=[], resolved=ind, degraded=[])
    summary, dropouts = build_funnel(universe=[r.ticker for r in ind], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    assert all(d.sector_wide is True for d in dropouts)
    assert all(d.severity_bucket == SeverityBucket.REVIEW for d in dropouts)


def test_sector_wide_denominator_excludes_pre_margin_drops():
    recs = [_resolved(f"V{i}", sector="Industrials", basis_reason="avg_volume")
            for i in range(4)]
    recs.append(_resolved("M0", sector="Industrials", basis_reason="gross_margin"))
    basis = BasisFilterResult(passed=[], unresolved=[], resolved=recs, degraded=[])
    summary, dropouts = build_funnel(universe=[r.ticker for r in recs], basis=basis,
                                     scored=None, score_threshold=4.0, crosshits_min_dimensions=2)
    margin_drop = next(d for d in dropouts if d.ticker == "M0")
    assert margin_drop.sector_wide is False


def test_metrik_na_maps_to_framework_bucket():
    from app.screener.funnel import _BASIS_REASON, ReasonCode
    assert _BASIS_REASON["metric_na"] is ReasonCode.FRAMEWORK_METRIK_NA


def test_statement_unavailable_maps_to_framework_statement_unavailable():
    from app.screener.funnel import _BASIS_REASON, ReasonCode
    assert _BASIS_REASON["statement_unavailable"] is ReasonCode.FRAMEWORK_STATEMENT_UNAVAILABLE


def test_statement_unavailable_dropout_is_review_and_reconciles():
    """FRAMEWORK_STATEMENT_UNAVAILABLE is REVIEW (transient) and reconciliation holds."""
    unavail = _resolved("FETCH_ERR", sector="Financial Services", basis_reason="statement_unavailable")
    hit = _resolved("HIT", dims={"growth": 4, "profitability": 4})
    basis = BasisFilterResult(
        passed=[hit],
        unresolved=[],
        resolved=[unavail, hit],
        degraded=[],
    )
    summary, dropouts = build_funnel(
        universe=["FETCH_ERR", "HIT"],
        basis=basis,
        scored=[hit],
        score_threshold=4.0,
        crosshits_min_dimensions=2,
    )
    codes = [d.reason_code for d in dropouts]
    assert ReasonCode.FRAMEWORK_STATEMENT_UNAVAILABLE in codes
    unavail_drop = next(d for d in dropouts if d.ticker == "FETCH_ERR")
    assert unavail_drop.stage == Stage.BASIS_GATES
    assert unavail_drop.severity_bucket == SeverityBucket.REVIEW
    # Reconciliation: every universe ticker is a dropout or in the final stage
    assert len(dropouts) + summary.stage(Stage.CROSSHITS).remaining == 2


def test_metrik_na_dropout_is_own_bucket_and_reconciles():
    """FRAMEWORK_METRIK_NA surfaces as a distinct basis-gates dropout and reconciliation holds."""
    bank = _resolved("BANK", sector="Financials", basis_reason="metric_na")
    hit = _resolved("HIT", dims={"growth": 4, "profitability": 4})
    basis = BasisFilterResult(
        passed=[hit],
        unresolved=[],
        resolved=[bank, hit],
        degraded=[],
    )
    summary, dropouts = build_funnel(
        universe=["BANK", "HIT"],
        basis=basis,
        scored=[hit],
        score_threshold=4.0,
        crosshits_min_dimensions=2,
    )
    codes = [d.reason_code for d in dropouts]
    assert ReasonCode.FRAMEWORK_METRIK_NA in codes
    bank_drop = next(d for d in dropouts if d.ticker == "BANK")
    assert bank_drop.stage == Stage.BASIS_GATES
    assert bank_drop.reason_code == ReasonCode.FRAMEWORK_METRIK_NA
    # Reconciliation: every universe ticker is either a dropout or in the final stage
    assert len(dropouts) + summary.stage(Stage.CROSSHITS).remaining == 2
