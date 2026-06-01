from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import frontmatter

from app.deepdive.filing_parser import SectionFlag
from app.deepdive.insider_block import render_insider_block
from app.deepdive.valuation_block import render_valuation_block
from app.models.deep_dive_record import DeepDiveRecord

logger = logging.getLogger(__name__)

_STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


def _flag_str(flag: SectionFlag) -> str:
    parts = [flag.extraction]
    if flag.missing:
        parts.append("missing")
    if flag.truncated:
        parts.append("truncated")
    return "+".join(parts)


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

    quant_date = record.generated_at.date().isoformat()
    if record.filing_date is not None:
        vintage_line = (
            f"*Filing-Stand: {record.filing_date} · "
            f"Quant-Stand: {quant_date} · "
            f"{record.days_since_filing} Tage Differenz — zwischenzeitliche "
            f"Entwicklungen siehe Tool-B Scuttlebutt (B.3)*"
        )
    else:
        vintage_line = (
            f"*Filing-Stand: unbekannt · Quant-Stand: {quant_date}*"
        )

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
        vintage_line,
        "",
        render_valuation_block(record.quant_snapshot),
        "",
        "## Insider-Transaktionen",
        render_insider_block(record.insider_summary, record.form_type),
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

    pc = record.quant_snapshot.peer_comparison
    peer_tickers = [p.ticker for p in pc.peers] if pc else []
    peer_rationale = pc.rationale if pc else None

    post = frontmatter.Post("\n".join(lines))
    post.metadata.update({
        "ticker": record.ticker,
        "adr_ticker": record.adr_ticker,
        "cik": record.cik,
        "form_type": record.form_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filing_date": record.filing_date,
        "quant_date": record.generated_at.date().isoformat(),
        "days_since_filing": record.days_since_filing,
        "section_flags": {
            key: _flag_str(flag) for key, flag in record.section_flags.items()
        },
        "peer_tickers": peer_tickers,
        "peer_rationale": peer_rationale,
        "insider_coverage_state": (
            record.insider_summary.coverage_state
            if record.insider_summary else None
        ),
        "insider_n_filings": (
            record.insider_summary.n_filings_total
            if record.insider_summary else None
        ),
        "insider_significant_count": (
            len(record.insider_summary.significant_buys)
            + len(record.insider_summary.significant_sells)
            if record.insider_summary else None
        ),
        "insider_net_buy": (
            record.insider_summary.net_buy_value if record.insider_summary else None
        ),
        "insider_net_sell": (
            record.insider_summary.net_sell_value if record.insider_summary else None
        ),
    })
    out.write_text(frontmatter.dumps(post), encoding="utf-8")
    logger.info("dossier: wrote %s", out.name)
    return out
