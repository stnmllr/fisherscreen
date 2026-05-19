from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import frontmatter

from app.deepdive.valuation_block import render_valuation_block
from app.models.deep_dive_record import DeepDiveRecord

logger = logging.getLogger(__name__)

_STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


def _fmt_money(v: float | None) -> str:
    return f"{v:,.0f}" if v is not None else "n/a"


def _fmt_pct(v: float | None) -> str:
    return f"{v:.1%}" if v is not None else "n/a"


def generate_dossier(record: DeepDiveRecord, output_dir: Path) -> Path:
    watch_dir = Path(output_dir) / "Watchlist"
    watch_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    out = watch_dir / f"{record.ticker}_{today}.md"

    pit = record.quant_snapshot.point_in_time
    name = pit.name or record.ticker
    cov = record.source_coverage

    lines: list[str] = [
        f"# Deep Dive: {name} ({record.ticker})",
        "",
        "## Executive Summary",
        "*[3 Sätze: Kern-These + Hauptrisiko + Empfehlung — von Gemini in B.1+ "
        "befüllt; B.1 Durchstich nutzt die 15 Mini-Blöcke als Substanz.]*",
        "",
        "## Bewertung",
        f"*Market Cap: {_fmt_money(pit.market_cap)} {pit.currency or ''} · "
        f"Gross Margin: {_fmt_pct(pit.gross_margin)} · "
        f"Op. Margin: {_fmt_pct(pit.operating_margin)}*",
        "",
        render_valuation_block(record.quant_snapshot),
        "",
        "## Fishers 15 Punkte",
        "",
    ]
    for p in record.synthesis:
        marker = " ".join(f"[{s}]" for s in p.sources)
        lines += [
            f"### Punkt {p.number} — {p.title}",
            f"**Bewertung:** {_STARS.get(p.rating, '?')} · "
            f"**Confidence:** {p.confidence}",
            "",
            f"{p.reasoning} {marker}",
            "",
        ]

    lines += [
        "## Source Coverage",
        "",
        f"- EDGAR: {cov.edgar}",
        f"- Quant (Punkt-in-Zeit): {cov.quant_pit_source}",
        f"- Quant (Mehrjahres): {cov.historical}",
        f"- Tool-A-Dimensionen: {cov.gemini_dims}",
        f"- Währung: {cov.currency_note or 'konsistent'}",
        f"- Soft Scuttlebutt: {cov.soft}",
        f"- Sprach-/Tonalitätsanalyse: {cov.sprache}",
        f"- Insider-Transaktionen: {cov.insider}",
        f"- Bewertungs-Kennzahlen: {cov.valuation}",
        "",
        "## Stef's Notizen",
        "",
        "*[Leer — Stef füllt manuell in Obsidian]*",
        "",
    ]

    post = frontmatter.Post("\n".join(lines))
    post.metadata.update({
        "ticker": record.ticker,
        "adr_ticker": record.adr_ticker,
        "cik": record.cik,
        "form_type": record.form_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "section_flags": record.section_flags,
    })
    out.write_text(frontmatter.dumps(post), encoding="utf-8")
    logger.info("dossier: wrote %s", out.name)
    return out
