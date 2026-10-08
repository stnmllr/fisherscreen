from __future__ import annotations

import logging
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.output.report_header import prepend_prior_run_warning
from app.screener.deterministic_scorer import (
    LEVERAGE_REDFLAG_THRESHOLD,
    leverage_ratio,
)
from app.screener.dimensions import (
    clears_crosshit_bar,
    is_crosshit,
    is_excluded_price_taker,
    qualifying_dimensions,
    steadiness_is_assessable,
)
from app.screener.price_takers import PriceTakerTable, load_price_takers

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)


# Grund-Marker der nicht bewerteten Stetigkeit. Sie stehen NEBEN dem `n/a`,
# nicht neben dem Ticker: die vorhandenen Ticker-Marker (⌖ ⚠ ~) haben eine
# andere Bedeutungsebene und duerfen nicht verwaessert werden (Spec §7).
_STEADINESS_MARKS = {
    "no_sec_registrant": "∅",
    "series_too_short": "↧",
    "no_concept": "⊘",
}


def _steadiness_cell(record) -> str:
    """Bewertet -> der Score. Nicht bewertet -> `n/a` mit Grund, NIE die 3.

    Die 3 anzuzeigen waere die sichtbare Haelfte desselben Fehlers, den das
    Gate vermeidet: sie sieht aus wie ein Messergebnis und ist keins."""
    if steadiness_is_assessable(record):
        return str(record.steadiness)
    mark = _STEADINESS_MARKS.get(record.steadiness_reason or "", "")
    return f"n/a {mark}".strip()


def _flags(record) -> str:
    """Audit markers: ⌖ = a sector-relative axis fell back to the global pool;
    ⚠ = low data confidence (e.g. <4 fiscal years / consistency unprovable);
    ~ = an axis scored on only one of its two inputs (partial evidence)."""
    basis = record.score_basis or {}
    flags = ""
    if any(v == "global_fallback" for v in basis.values()):
        flags += "⌖"
    if getattr(record, "data_confidence", "ok") == "low":
        flags += "⚠"
    if getattr(record, "partial_evidence_axes", None):
        flags += "~"
    return flags


def generate(
    records: list[ScreenerRecord],
    run_record: RunRecord,
    output_dir: Path,
    *,
    score_threshold: float = 4.0,
    min_dimensions: int = 2,
    cap: int = 50,
    header: str | None = None,
    price_takers: PriceTakerTable | None = None,
    prior_run_warning: str | None = None,
) -> Path:
    output_dir = output_dir / "Universum"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_month = run_record.run_id[:7]  # "YYYY-MM"
    out_path = output_dir / f"{run_month}-Crosshits.md"

    scored = [r for r in records if r.gemini_dimensions is not None]
    crosshits = _compute_crosshits(scored, score_threshold, min_dimensions, cap)
    steadiness_failed = _compute_steadiness_failures(
        scored, score_threshold, min_dimensions
    )
    leverage_failed = _compute_leverage_failures(
        scored, score_threshold, min_dimensions
    )
    price_taker_failed = _compute_price_taker_exclusions(
        scored, score_threshold, min_dimensions
    )

    body = _build_body(
        crosshits,
        run_month,
        score_threshold,
        min_dimensions,
        header,
        price_takers,
        steadiness_failed=steadiness_failed,
        leverage_failed=leverage_failed,
        price_taker_failed=price_taker_failed,
    )
    body = prepend_prior_run_warning(body, prior_run_warning)
    out_path.write_text(body, encoding="utf-8")

    logger.info("crosshits: wrote %s (%d crosshits)", out_path.name, len(crosshits))
    return out_path


def _entry(record: ScreenerRecord, qualifying: list[str]) -> dict:
    dims = record.gemini_dimensions or {}
    avg = sum(dims.get(d, 0) for d in qualifying) / len(qualifying)
    # Ranking sharpener: more top scores (5) among the qualifying merit
    # dimensions ranks higher. Monotonic with avg today, but stays correct
    # if the threshold/min_dimensions knobs change later.
    num_fives = sum(1 for d in qualifying if dims.get(d) == 5)
    return {
        "record": record,
        "qualifying_dims": qualifying,
        "avg_score": round(avg, 2),
        "num_fives": num_fives,
    }


def _ranked(entries: list[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda x: (-len(x["qualifying_dims"]), -x["num_fives"], -x["avg_score"]),
    )


def _compute_crosshits(
    scored: list[ScreenerRecord],
    score_threshold: float,
    min_dimensions: int,
    cap: int,
) -> list[dict]:
    """The crosshit list. Membership is decided by `is_crosshit` -- the same rule
    the funnel counts with -- so the table and the funnel's `crosshits` stage can
    never disagree. Before this, the table applied only the three-axis rule and
    listed titles whose measured steadiness had already failed the gate (October
    2026: 25 rows against a funnel count of 17)."""
    result = [
        _entry(record, qualifying_dimensions(record, score_threshold))
        for record in scored
        if is_crosshit(record, score_threshold, min_dimensions)
    ]
    return _ranked(result)[:cap]


def _compute_steadiness_failures(
    scored: list[ScreenerRecord],
    score_threshold: float,
    min_dimensions: int,
) -> list[dict]:
    """Titles that clear the three yfinance axes but fail on a MEASURED steadiness
    below the threshold. Not crosshits; shown separately so the decision stays
    visible instead of the titles silently disappearing. Read against the merit
    bar, not `is_crosshit`: a price taker that clears everything belongs in the
    price-taker section, not here."""
    result = []
    for record in scored:
        qualifying = qualifying_dimensions(record, score_threshold)
        if len(qualifying) >= min_dimensions and not clears_crosshit_bar(
            record, score_threshold, min_dimensions
        ):
            result.append(_entry(record, qualifying))
    return _ranked(result)


def _compute_leverage_failures(
    scored: list[ScreenerRecord],
    score_threshold: float,
    min_dimensions: int,
) -> list[dict]:
    """Titles that are not crosshits ONLY because of the resilience leverage red
    flag: growth and profitability clear the threshold, steadiness clears it or
    was not measured. Membership rules are untouched -- this is visibility. A
    title that clears the merit bar regardless (possible below three dimensions)
    is not kept out by the red flag; if it is a price taker, it is listed there."""
    result = []
    for record in scored:
        if not record.resilience_red_flag:
            continue
        if clears_crosshit_bar(record, score_threshold, min_dimensions):
            continue
        dims = record.gemini_dimensions or {}
        if (
            dims.get("growth", 0) < score_threshold
            or dims.get("profitability", 0) < score_threshold
        ):
            continue
        if (
            steadiness_is_assessable(record)
            and (record.steadiness or 0.0) < score_threshold
        ):
            continue
        result.append(_entry(record, qualifying_dimensions(record, score_threshold)))
    return _ranked(result)


def _compute_price_taker_exclusions(
    scored: list[ScreenerRecord],
    score_threshold: float,
    min_dimensions: int,
) -> list[dict]:
    """Titles that would be crosshits if they were not price takers: every
    merit and steadiness condition met, barred only by the rule in `is_crosshit`.
    A price taker that also misses an axis fails on merit and is not listed."""
    result = [
        _entry(record, qualifying_dimensions(record, score_threshold))
        for record in scored
        if is_excluded_price_taker(record, score_threshold, min_dimensions)
    ]
    return _ranked(result)


def _price_taker_cell(record: ScreenerRecord, table: PriceTakerTable) -> str:
    """Which arm caught the title. The ticker arm wins, as in is_price_taker."""
    if record.ticker in table.tickers:
        return "Override"
    return record.gics_industry or ""


def _leverage_cell(record: ScreenerRecord) -> str:
    """The figure behind the red flag: the ratio, or why there is none."""
    ratio = leverage_ratio(record)
    if ratio is not None:
        return f"{ratio:.1f}x"
    return "Nettoschuld, EBITDA ≤ 0"


def _build_body(
    crosshits: list[dict],
    run_month: str,
    score_threshold: float,
    min_dimensions: int,
    header: str | None = None,
    price_takers: PriceTakerTable | None = None,
    *,
    steadiness_failed: list[dict] | None = None,
    leverage_failed: list[dict] | None = None,
    price_taker_failed: list[dict] | None = None,
) -> str:
    lines = [f"# Universum {run_month} — Crosshits", ""]
    if header:
        lines += [header.rstrip("\n"), ""]
    lines += [
        f"*Schwelle: Score ≥{score_threshold} in ≥{min_dimensions} Dimensionen*",
        "",
    ]
    if not crosshits:
        lines += [
            "> Keine Crosshits in diesem Lauf. Entweder kein Ticker erreichte die Schwelle",
            "> in mindestens zwei Dimensionen, oder das Universum war nach Filtern zu klein.",
        ]
    else:
        lines += _table(crosshits)
        assessed = sum(1 for e in crosshits if steadiness_is_assessable(e["record"]))
        lines += [
            "",
            f"> **Stetigkeit** = vierte Achse ueber bis zu zehn Jahre EDGAR-Jahreszahlen "
            f"(Rueckgangsjahre, Margeneinbruch vom Hoch, schlechteste Nettomarge). "
            f"**{assessed} von {len(crosshits)}** Titeln dieser Liste sind bewertet; "
            f"`n/a` heisst nicht bewertbar und wird weder belohnt noch bestraft: "
            f"`∅` kein SEC-Registrant, `↧` Reihe kuerzer als sieben Jahre, "
            f"`⊘` kein Konzept getroffen. Bei sieben bis neun Jahren ist der "
            f"Hoechstwert 4.",
        ]
    if price_taker_failed:
        lines += [
            "",
            f"> **Preisnehmer** zaehlen nicht als Crosshits. "
            f"**{len(price_taker_failed)}** Titel haetten die Schwelle sonst "
            f"erreicht; sie stehen im Abschnitt *Am Preisnehmer-Ausschluss "
            f"gescheitert*.",
        ]
    if steadiness_failed:
        lines += [
            "",
            "## Am Stetigkeits-Gate gescheitert",
            "",
            f"> Diese Titel erreichen auf den drei Achsen die Schwelle, ihre "
            f"**gemessene** Stetigkeit liegt aber unter {score_threshold}. Sie sind "
            f"**keine** Crosshits und zaehlen im Funnel nicht mit; sie stehen hier, "
            f"damit die Entscheidung sichtbar bleibt.",
            "",
        ]
        lines += _table(steadiness_failed)
    if leverage_failed:
        lines += [
            "",
            "## Am Verschuldungs-Red-Flag gescheitert",
            "",
            f"> Diese Titel erreichen bei growth und profitability die Schwelle und "
            f"scheitern nicht an der Stetigkeit, ihre Verschuldung loest aber das "
            f"Red-Flag aus: Nettoverschuldung/EBITDA ueber "
            f"{LEVERAGE_REDFLAG_THRESHOLD:.1f}x oder Nettoschuld bei EBITDA ≤ 0 "
            f"(resilience = 0). Sie sind **keine** Crosshits und zaehlen im Funnel "
            f"nicht mit; sie stehen hier, damit die Entscheidung sichtbar bleibt. "
            f"Versorger und Immobilien sind vom Red-Flag ausgenommen.",
            "",
        ]
        lines += _table(
            leverage_failed, extra=("Nettoverschuldung/EBITDA", _leverage_cell)
        )
    if price_taker_failed:
        # Membership comes from `record.price_taker` (set by the scorer); the table
        # is read only to name the arm that caught a title. Loaded here, not at
        # import: the loader is fail-loud, and an import-time raise would take
        # down anything that merely imports this module. Injectable for tests.
        table = price_takers if price_takers is not None else load_price_takers()
        lines += [
            "",
            "## Am Preisnehmer-Ausschluss gescheitert",
            "",
            "> Diese Titel erfuellen alle Bedingungen eines Crosshits (Achsen und, "
            "wo gemessen, Stetigkeit), verkaufen aber zu einem Preis, den sie nicht "
            "setzen (Rohstoffe, Speicherchips). In einem Preiszyklus faerben sich "
            "alle drei Achsen gleichzeitig gruen, ohne dass sich am Geschaeft etwas "
            "geaendert haette. Sie sind **keine** Crosshits und zaehlen im Funnel "
            "nicht mit; Scores und Perzentile sind unveraendert. Sie stehen hier, "
            "damit das Urteil sichtbar bleibt. Grundlage ist `data/price_takers.json` "
            "(yfinance-`industry`, bewusst grob; `Override` = per Ticker benannt).",
            "",
        ]
        lines += _table(
            price_taker_failed,
            extra=("Grund", lambda r: _price_taker_cell(r, table)),
        )
    return "\n".join(lines) + "\n"


def _table(
    entries: list[dict],
    *,
    extra: tuple[str, Callable[[ScreenerRecord], str]] | None = None,
) -> list[str]:
    """One table layout for the list and every failure section. `extra` appends
    a section-specific column: (header, cell function)."""
    header = (
        "| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score "
        "| Stetigkeit |"
    )
    rule = "|---|---|---|---|---|---|---|---|"
    if extra is not None:
        header += f" {extra[0]} |"
        rule += "---|"
    lines = [header, rule]
    for i, entry in enumerate(entries, 1):
        r = entry["record"]
        dims_str = ", ".join(entry["qualifying_dims"])
        row = (
            f"| {i} | {r.ticker} {_flags(r)} | {r.name or ''} | {r.gics_sector or ''} "
            f"| {len(entry['qualifying_dims'])} | {dims_str} | {entry['avg_score']} "
            f"| {_steadiness_cell(r)} |"
        )
        if extra is not None:
            row += f" {extra[1](r)} |"
        lines.append(row)
    return lines
