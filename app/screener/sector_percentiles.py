"""percentile_prep: annotate the pre-scoring cohort with within-run percentile ranks.

growth (revenue_growth_yoy) is ALWAYS cohort-global. profitability/resilience inputs
are sector-relative iff the record's sector has >= MIN_SECTOR_N members, else they fall
back to the global pool (score_basis records which). None values are excluded from
distributions.

Profitability ranks operating_margin and return_on_invested_capital. ROIC is not a
yfinance field: app.screener.roic computes it before this module runs. It replaced
return_on_equity, which measured buyback cosmetics (book equity ~0 or negative).

Resilience has a single percentile input, gross_margin. Its leverage half is net
debt / EBITDA on FIXED ABSOLUTE bands in the scorer, not a percentile: debt/equity
used to sit here and measured buyback cosmetics (tiny or negative book equity)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.screener.percentiles import percentile_rank

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

MIN_SECTOR_N = 30
_GLOBAL_INPUT = "revenue_growth_yoy"
_SECTOR_RELATIVE_INPUTS = (
    "operating_margin",
    "return_on_invested_capital",
    "gross_margin",
)
_AXIS_INPUTS = {
    "profitability": ("operating_margin", "return_on_invested_capital"),
    "resilience": ("gross_margin",),
}


def _distribution(records: list["ScreenerRecord"], field: str) -> list[float]:
    return [getattr(r, field) for r in records if getattr(r, field) is not None]


def annotate_percentiles(records: list["ScreenerRecord"]) -> None:
    """Set `input_percentiles` and `score_basis` on each record in place."""
    global_dist = {
        f: _distribution(records, f) for f in (_GLOBAL_INPUT, *_SECTOR_RELATIVE_INPUTS)
    }

    sector_members: dict[str | None, list["ScreenerRecord"]] = {}
    for r in records:
        sector_members.setdefault(r.gics_sector, []).append(r)
    sector_dist: dict[tuple[str | None, str], list[float]] = {}
    for sector, members in sector_members.items():
        for f in _SECTOR_RELATIVE_INPUTS:
            sector_dist[(sector, f)] = _distribution(members, f)

    for r in records:
        pcts: dict[str, float] = {}
        basis: dict[str, str] = {"growth": "global"}

        gv = getattr(r, _GLOBAL_INPUT)
        if gv is not None and global_dist[_GLOBAL_INPUT]:
            pcts[_GLOBAL_INPUT] = percentile_rank(gv, global_dist[_GLOBAL_INPUT])

        sector = r.gics_sector
        use_sector = (
            sector is not None and len(sector_members.get(sector, [])) >= MIN_SECTOR_N
        )
        for axis, fields in _AXIS_INPUTS.items():
            basis[axis] = "sector_relative" if use_sector else "global_fallback"
            for f in fields:
                v = getattr(r, f)
                if v is None:
                    continue
                dist = sector_dist[(sector, f)] if use_sector else global_dist[f]
                if dist:
                    pcts[f] = percentile_rank(v, dist)

        r.input_percentiles = pcts
        r.score_basis = basis
