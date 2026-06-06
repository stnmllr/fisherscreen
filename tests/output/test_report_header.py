from app.output.report_header import render_header
from app.screener.funnel import FunnelStage, FunnelSummary, Stage


def _summary():
    stages = [
        FunnelStage(Stage.UNIVERSE, 2100, 0, 2100),
        FunnelStage(Stage.RESOLUTION, 2100, 100, 2000),
        FunnelStage(Stage.BASIS_GATES, 2000, 1500, 500),
        FunnelStage(Stage.EDGAR_GATES, 500, 10, 490),
        FunnelStage(Stage.SCORING, 490, 5, 485),
        FunnelStage(Stage.CROSSHITS, 485, 400, 85),
    ]
    return FunnelSummary(stages=stages, review_flags=3, pass_through_count=12,
                         provenance={"stoxx_tier": "ishares-b", "sp500_count": 503,
                                     "sp400_count": 400, "stoxx600_count": 600})


def test_header_contains_key_facts():
    out = render_header(_summary(), run_month="2026-06")
    assert "2026-06" in out
    assert "Review-Flags: 3" in out
    assert "ishares-b" in out
    assert "Crosshit" in out             # threshold plaintext
    assert "| Stufe |" in out            # funnel table header
    assert "yfinance" in out and "SEC EDGAR" in out


def test_header_graceful_without_provenance():
    s = _summary()
    s.provenance = None
    out = render_header(s, run_month="2026-06")
    assert "nicht erfasst" in out        # graceful fallback


def test_stage_label_map_covers_all_stages():
    from app.output.report_header import _STAGE_LABEL
    from app.screener.funnel import Stage
    assert set(_STAGE_LABEL.keys()) == set(Stage), \
        "_STAGE_LABEL must have an entry for every Stage enum member"
