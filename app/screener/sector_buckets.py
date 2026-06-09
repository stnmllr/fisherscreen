"""Sector bucket resolution: pick the finest GICS node that clears a population
threshold n_min, rolling up finest->coarsest. Returns None when no node clears
n_min — the dual-arm gate then simply does not fire its relative arm (fail-safe
by construction, spec §4)."""
from __future__ import annotations


def resolve_bucket(
    node_chain: list[str],
    counts: dict[str, int],
    n_min: int,
) -> str | None:
    """node_chain is finest->coarsest (e.g. [sub_industry, industry, group, sector]).
    Returns the finest node with counts[node] >= n_min, else None."""
    for node in node_chain:
        if counts.get(node, 0) >= n_min:
            return node
    return None
