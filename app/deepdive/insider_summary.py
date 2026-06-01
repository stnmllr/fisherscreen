from __future__ import annotations

from app.models.deep_dive_record import (
    InsiderCoverage,
    InsiderSummary,
    InsiderTransaction,
)

# Single source of truth for the absolute significance floor. Tunable; the
# pre-netting cache lets a re-net pick up a changed value without refetching.
INSIDER_SIGNIFICANCE_USD = 1_000_000.0


def compute_insider_summary(
    transactions: list[InsiderTransaction],
    *,
    coverage_state: InsiderCoverage,
    n_filings_total: int,
    n_parsed: int,
    window_label: str = "letzte 12 Monate",
) -> InsiderSummary:
    owner_sell_total: dict[str, float] = {}
    for t in transactions:
        if t.bucket == "sell" and t.value is not None:
            owner_sell_total[t.owner_name] = (
                owner_sell_total.get(t.owner_name, 0.0) + abs(t.value)
            )

    sig_buys: list[InsiderTransaction] = []
    sig_sells: list[InsiderTransaction] = []
    immaterial = 0
    routine = 0
    for t in transactions:
        if t.bucket == "buy":
            t.significant = True
            sig_buys.append(t)
        elif t.bucket == "sell":
            sig = (
                (t.value is not None and abs(t.value) > INSIDER_SIGNIFICANCE_USD)
                or t.role in ("CEO", "CFO")
                or owner_sell_total.get(t.owner_name, 0.0) > INSIDER_SIGNIFICANCE_USD
            )
            t.significant = sig
            if sig:
                sig_sells.append(t)
            else:
                immaterial += 1
        else:
            routine += 1

    net_buy = sum(
        t.value for t in sig_buys
        if t.value is not None and t.acquired_disposed == "A"
    )
    net_sell = sum(
        t.value for t in sig_sells
        if t.value is not None and t.acquired_disposed == "D"
    )
    by_role: dict[str, dict[str, float]] = {}
    for t in sig_buys:
        if t.value is not None and t.acquired_disposed == "A":
            by_role.setdefault(t.role, {"buy": 0.0, "sell": 0.0})["buy"] += t.value
    for t in sig_sells:
        if t.value is not None and t.acquired_disposed == "D":
            by_role.setdefault(t.role, {"buy": 0.0, "sell": 0.0})["sell"] += t.value

    return InsiderSummary(
        coverage_state=coverage_state,
        window_label=window_label,
        n_filings_total=n_filings_total,
        n_parsed=n_parsed,
        n_transactions_total=len(transactions),
        significant_buys=sig_buys,
        significant_sells=sig_sells,
        immaterial_sell_count=immaterial,
        routine_count=routine,
        net_buy_value=float(net_buy),
        net_sell_value=float(net_sell),
        by_role=by_role,
    )
