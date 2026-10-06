from app.models.screener_record import ScreenerRecord
from app.screener.sector_percentiles import annotate_percentiles, MIN_SECTOR_N


def _rec(
    ticker, sector, op=None, roic=None, gm=None, de=None, rg=None, roe=None, rgm=None
):
    return ScreenerRecord(
        ticker=ticker,
        gics_sector=sector,
        operating_margin=op,
        return_on_invested_capital=roic,
        return_on_equity=roe,
        gross_margin=gm,
        debt_to_equity=de,
        revenue_growth_yoy=rg,
        revenue_growth_median=rgm,
    )


def test_small_sector_falls_back_to_global():
    # One Tech record, but a 30+ member global pool via other sectors.
    recs = [
        _rec(f"P{i}", "Industrials", op=0.10 + i * 0.001, rg=0.05)
        for i in range(MIN_SECTOR_N)
    ]
    tech = _rec("TECH", "Technology", op=0.40, rg=0.05)
    recs.append(tech)
    annotate_percentiles(recs)
    assert (
        tech.score_basis["profitability"] == "global_fallback"
    )  # Technology has 1 < 30
    assert (
        recs[0].score_basis["profitability"] == "sector_relative"
    )  # Industrials has 30
    assert tech.score_basis["growth"] == "global"


def test_debt_to_equity_is_no_longer_a_percentile_input():
    """Resilience leverage is net debt/EBITDA on absolute bands (scorer), not a
    percentile: debt/equity measured buyback cosmetics (MA 0, TDG 5)."""
    recs = [
        _rec(f"I{i}", "Industrials", gm=0.30 + i * 0.01, de=50.0 + i)
        for i in range(MIN_SECTOR_N)
    ]
    recs.append(_rec("SBUX", "Industrials", gm=0.30, de=-150.0))
    annotate_percentiles(recs)
    for r in recs:
        assert "debt_to_equity" not in r.input_percentiles
        assert "gross_margin" in r.input_percentiles
    assert recs[0].score_basis["resilience"] == "sector_relative"


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
    assert (
        hi.input_percentiles["revenue_growth_yoy"]
        > lo.input_percentiles["revenue_growth_yoy"]
    )


def test_profitability_ranks_roic_not_roe():
    """ROE measured buyback cosmetics (book equity ~0 or negative); the
    profitability axis ranks ROIC sector-relatively instead."""
    recs = [
        _rec(f"I{i}", "Industrials", op=0.10, roic=0.05 + i * 0.01, roe=0.2)
        for i in range(MIN_SECTOR_N)
    ]
    annotate_percentiles(recs)
    for r in recs:
        assert "return_on_equity" not in r.input_percentiles
        assert "return_on_invested_capital" in r.input_percentiles
    assert (
        recs[-1].input_percentiles["return_on_invested_capital"]
        > recs[0].input_percentiles["return_on_invested_capital"]
    )


def test_roic_is_sector_relative():
    ind = [
        _rec(f"I{i}", "Industrials", roic=0.05 + i * 0.001) for i in range(MIN_SECTOR_N)
    ]
    tech = [
        _rec(f"T{i}", "Technology", roic=0.50 + i * 0.001) for i in range(MIN_SECTOR_N)
    ]
    annotate_percentiles(ind + tech)
    # top of each sector ranks top, although Industrials' best < Technology's worst
    assert ind[-1].input_percentiles["return_on_invested_capital"] > 90
    assert tech[0].input_percentiles["return_on_invested_capital"] < 10


def test_missing_roic_not_annotated():
    recs = [_rec(f"I{i}", "Industrials", roic=0.1) for i in range(MIN_SECTOR_N)]
    recs.append(_rec("NA", "Industrials", roic=None))
    annotate_percentiles(recs)
    assert "return_on_invested_capital" not in recs[-1].input_percentiles


def test_both_growth_inputs_are_global_across_sectors():
    """The median annual growth drives the axis; the quarterly YoY stays as its
    fallback. Both rank against the whole cohort, never per sector."""
    recs = [_rec(f"A{i}", "Industrials", rg=0.01, rgm=0.02) for i in range(20)]
    recs += [_rec(f"B{i}", "Technology", rg=0.50, rgm=0.30) for i in range(20)]
    annotate_percentiles(recs)
    hi = next(r for r in recs if r.ticker == "B0")
    lo = next(r for r in recs if r.ticker == "A0")
    for f in ("revenue_growth_yoy", "revenue_growth_median"):
        assert hi.input_percentiles[f] > lo.input_percentiles[f]


def test_missing_median_not_annotated_and_excluded_from_distribution():
    recs = [_rec(f"I{i}", "Industrials", rg=0.05, rgm=0.01 * i) for i in range(10)]
    short = _rec("SHORT", "Industrials", rg=0.05, rgm=None)
    recs.append(short)
    annotate_percentiles(recs)
    assert "revenue_growth_median" not in short.input_percentiles
    assert "revenue_growth_yoy" in short.input_percentiles
    # the top median ranks against the 10 present values only: (9 + 0.5) / 10
    assert recs[9].input_percentiles["revenue_growth_median"] == 95.0
