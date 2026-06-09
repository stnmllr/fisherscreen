"""Sector bucket resolution: pick the finest GICS node that clears a population
threshold n_min, rolling up finest->coarsest. Returns None when no node clears
n_min — the dual-arm gate then simply does not fire its relative arm (fail-safe
by construction, spec §4)."""
from __future__ import annotations

from dataclasses import dataclass


def resolve_bucket(
    node_chain: list[str],
    counts: dict[str, int],
    *,
    n_min: int,
) -> str | None:
    """node_chain is finest->coarsest (e.g. [sub_industry, industry, group, sector]).
    Returns the finest node with counts[node] >= n_min, else None."""
    for node in node_chain:
        if counts.get(node, 0) >= n_min:
            return node
    return None


@dataclass(frozen=True)
class SectorMedianTable:
    """Pinned per-bucket gross-margin medians together with the population counts
    and n_min used to resolve the finest qualifying bucket.

    Immutable value object: construct once from a JSON snapshot (C2), reuse
    across all tickers in a screener run."""

    entries: dict[str, float]  # bucket node -> median gross margin (0–1 scale)
    n_min: int  # minimum peer count for a bucket to qualify
    counts: dict[str, int]  # bucket node -> population count (mirrors universe snapshot)


def bucket_median(
    node_chain: list[str],
    table: SectorMedianTable,
) -> float | None:
    """Resolve the finest qualifying bucket for node_chain, then return its
    pinned median from table.entries.

    Returns None when no bucket clears n_min (relative arm should not fire)."""
    bucket = resolve_bucket(node_chain, table.counts, n_min=table.n_min)
    if bucket is None:
        return None
    return table.entries.get(bucket)
