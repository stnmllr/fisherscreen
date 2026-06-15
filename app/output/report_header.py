from __future__ import annotations

from app.screener.funnel import FunnelSummary, Stage

_STAGE_LABEL = {
    Stage.UNIVERSE: "Universum",
    Stage.RESOLUTION: "Resolution",
    Stage.BASIS_GATES: "Basis-Gates",
    Stage.EDGAR_GATES: "EDGAR-Gates",
    Stage.SCORING: "Scoring",
    Stage.CROSSHITS: "Crosshits",
}


def render_header(summary: FunnelSummary, run_month: str) -> str:
    prov = summary.provenance or {}
    stoxx_tier = prov.get("stoxx_tier", "nicht erfasst")
    universe_size = summary.stage(Stage.UNIVERSE).entered

    lines = [
        f"## Lauf-Übersicht {run_month}",
        "",
        f"- **Stichtag:** {run_month} · **Universum:** {universe_size} "
        f"(S&P 500 / S&P 400 / STOXX 600)",
        f"- **STOXX-Quellstufe:** {stoxx_tier}",
        "- **Datenbasis:** yfinance (Kurs/Vol/Fundamentals) · "
        "SEC EDGAR (Filings; DEF-14A/Form-4 nur US-Filer)",
        "",
        "| Stufe | rein | raus | übrig |",
        "|---|---|---|---|",
    ]
    for s in summary.stages:
        raus = str(s.dropped) if s.ran else "—"
        rein = str(s.entered) if s.ran else "—"
        uebrig = str(s.remaining)
        lines.append(f"| {_STAGE_LABEL[s.stage]} | {rein} | {raus} | {uebrig} |")
    lines += [
        "",
        f"**Review-Flags: {summary.review_flags}** (Aufschlüsselung in "
        f"`{run_month}-dropouts.csv`)",
        "",
        "> Tool A ist ein Drei-Achsen-Screen: growth, profitability, resilience "
        "werden datengedeckt 0–5 bewertet. management wird upstream im EDGAR-Gate "
        "geprüft (jeder Survivor hat es passiert), innovation ist auf den Deep Dive "
        "verschoben — beide zählen nicht als Crosshit-Treffer. Crosshit = ≥2 der "
        "drei aktiven Achsen ≥4.0 — über mehrere unabhängige Achsen bestätigte Qualität.",
        "",
    ]
    return "\n".join(lines)
