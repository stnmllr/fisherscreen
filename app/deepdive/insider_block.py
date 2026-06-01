from __future__ import annotations

from app.models.deep_dive_record import InsiderSummary, InsiderTransaction

_HEAD = "**Insider-Transaktionen:**"


def _money(v: float | None) -> str:
    return f"{v:,.0f}" if v is not None else "n/a"


def _pct_suffix(t: InsiderTransaction) -> str:
    """Sign coupled to acquired/disposed; only for direct holdings with a valid
    denominator. Omitted otherwise (no misleading number)."""
    if t.shares is None or t.shares_after is None or t.direct_or_indirect != "D":
        return ""
    if t.acquired_disposed == "D":
        pre = t.shares_after + t.shares
        if pre <= 0:
            return ""
        return f" — hält nun {_money(t.shares_after)} = −{t.shares / pre:.0%} der direkten Holdings"
    if t.acquired_disposed == "A":
        pre = t.shares_after - t.shares
        if pre <= 0:
            return ""
        return f" — hält nun {_money(t.shares_after)} = +{t.shares / pre:.0%} der direkten Holdings"
    return ""


def _b5_suffix(t: InsiderTransaction) -> str:
    if t.is_10b5_1 is True:
        return " (10b5-1-geplant)"
    if t.is_10b5_1 is False:
        return " (ungeplant)"
    return ""


def _tx_line(t: InsiderTransaction) -> str:
    base = (
        f"{t.owner_name} ({t.role}) {t.date or '?'}: {t.code} "
        f"{_money(t.shares)} @ {t.price if t.price is not None else 'n/a'} "
        f"= {_money(t.value)}"
    )
    return f"- {base}{_pct_suffix(t)}{_b5_suffix(t)}"


def render_insider_block(summary: InsiderSummary | None, form_type: str) -> str:
    if summary is None or summary.coverage_state == "fpi_exempt":
        return (
            f"{_HEAD} nicht anwendbar (Foreign Private Issuer, "
            f"Section-16-exempt — kein Form-4)."
        )
    cs = summary.coverage_state
    win = summary.window_label
    if cs == "skipped":
        return f"{_HEAD} übersprungen (`--no-insider`)."
    if cs == "fetch_failed":
        return (
            f"{_HEAD} Fetch fehlgeschlagen "
            f"({summary.n_parsed}/{summary.n_filings_total} XMLs) — "
            f"kein Urteil möglich (nicht „kein Signal“)."
        )
    if cs == "empty":
        return (
            f"{_HEAD} 0 Form-4 in {win} (für einen US-Filer auffällig — "
            f"ggf. Datenlücke)."
        )
    n_sig = len(summary.significant_buys) + len(summary.significant_sells)
    parsed_note = (
        f" · {summary.n_parsed} von {summary.n_filings_total} geparst"
        if cs == "partial" else ""
    )
    header = (
        f"{_HEAD} {summary.n_filings_total} Form-4-Filings · darin "
        f"{summary.n_transactions_total} Transaktionen → {n_sig} signifikant "
        f"({len(summary.significant_buys)} Käufe, "
        f"{len(summary.significant_sells)} Verkäufe) · "
        f"{summary.immaterial_sell_count} immateriell · "
        f"{summary.routine_count} Routine (A/M/F/G){parsed_note}"
    )
    lines = [header]
    for t in summary.significant_buys + summary.significant_sells:
        lines.append(_tx_line(t))
    return "\n".join(lines)


def insider_coverage_label(summary: InsiderSummary | None) -> str:
    """One-line SourceCoverage.insider value."""
    if summary is None or summary.coverage_state == "fpi_exempt":
        return "nicht anwendbar (FPI, Section-16-exempt)"
    cs = summary.coverage_state
    if cs == "skipped":
        return "übersprungen (--no-insider)"
    if cs == "fetch_failed":
        return f"Fetch fehlgeschlagen ({summary.n_parsed}/{summary.n_filings_total})"
    if cs == "empty":
        return "0 Form-4 in 12M (auffällig für US-Filer)"
    n_sig = len(summary.significant_buys) + len(summary.significant_sells)
    return (
        f"12M Form-4: {summary.n_parsed}/{summary.n_filings_total} geparst, "
        f"{n_sig} signifikant ({len(summary.significant_buys)} Käufe, "
        f"{len(summary.significant_sells)} Verkäufe)"
    )
