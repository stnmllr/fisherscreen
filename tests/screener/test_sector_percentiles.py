from app.models.screener_record import ScreenerRecord
from app.screener.sector_percentiles import annotate_percentiles, MIN_SECTOR_N


def _rec(ticker, sector, op=None, roe=None, gm=None, de=None, rg=None):
    return ScreenerRecord(ticker=ticker, gics_sector=sector,
                          operating_margin=op, return_on_equity=roe,
                          gross_margin=gm, debt_to_equity=de, revenue_growth_yoy=rg)


def test_small_sector_falls_back_to_global():
    # One Tech record, but a 30+ member global pool via other sectors.
    recs = [_rec(f"P{i}", "Industrials", op=0.10 + i * 0.001, rg=0.05) for i in range(MIN_SECTOR_N)]
    tech = _rec("TECH", "Technology", op=0.40, rg=0.05)
    recs.append(tech)
    annotate_percentiles(recs)
    assert tech.score_basis["profitability"] == "global_fallback"  # Technology has 1 < 30
    assert recs[0].score_basis["profitability"] == "sector_relative"  # Industrials has 30
    assert tech.score_basis["growth"] == "global"


def test_negative_debt_to_equity_excluded():
    recs = [_rec(f"I{i}", "Industrials", gm=0.30, de=50.0) for i in range(MIN_SECTOR_N)]
    buyback = _rec("SBUX", "Industrials", gm=0.30, de=-150.0)
    recs.append(buyback)
    annotate_percentiles(recs)
    assert "debt_to_equity" not in buyback.input_percentiles  # excluded from its own annotation
    # and excluded from the distribution: a normal d/e still ranks against positives only
    assert "debt_to_equity" in recs[0].input_percentiles


def test_none_metric_not_annotated():
    recs = [_rec(f"I{i}", "Industrials", op=0.10, rg=0.05) for i in range(MIN_SECTOR_N)]
    recs.append(_rec("NA", "Industrials", op=None, rg=0.05))
    annotate_percentiles(recs)
    assert "operating_margin" not in recs[-1].input_percentiles


def test_growth_is_global_across_sectors():
    recs = [_rec(f"A{i}", "Industrials", rg=0.01) for i in range(20)]
    recs += [_rec(f"B{i}", "Technology", rg=0.50) for i in range(20)]
    annotate_percentiles(recs)
    hi = next(r for r in recs if r.ticker == "B0")
    lo = next(r for r in recs if r.ticker == "A0")
    assert hi.input_percentiles["revenue_growth_yoy"] > lo.input_percentiles["revenue_growth_yoy"]
