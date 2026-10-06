r"""Offline-Neubewertung eines fertigen Monatslaufs auf den gecachten Daten.

Zweck: eine Scoring-Aenderung gegen einen echten Monat pruefen, BEVOR sie in
einen Monatslauf geht -- wie viele Crosshits, welche rein/raus, wie viele
Referenz-Titel (mit scripts/reference_check.py --dropouts/--out).

NUR LESEN, $0:
  data/universe.json, output/Universum/<Monat>-dropouts.csv   Kohorte
  output/Universum/<Monat>-Crosshits.md                       Vergleichsliste
  Firestore settings.ticker_collection                        yfinance-.info
  Firestore settings.revenue_series_collection                Umsatzreihen
  Firestore settings.edgar_annual_series_collection           Stetigkeit
  <cik-map>                                                   Ticker -> CIK

Kein Firestore-Schreiben, kein yfinance, kein EDGAR. Die Caches werden VORAB per
Batch-`get_all` gelesen und dann ueber einen Nur-Lesen-Adapter gereicht, dessen
`set`/`delete` hart scheitern. Ein Cache-Fehltreffer wird als leer/fehlend
behandelt und gezaehlt -- nie nachgeladen.

CIK: Der Monatslauf bezieht die CIK aus SEC `company_tickers.json` (eine
statische Datei). Lokal gibt es keine vollstaendige Kopie; deshalb liest das
Skript eine Ticker->CIK-Datei (`--cik-map`, Default
cache/sec_ticker_cik_map.json). Fehlt sie, bricht es ab. `--refresh-cik-map`
holt die Datei EINMAL (ein einziger GET auf sec.gov, $0) und schreibt sie fuer
die Universum-Ticker -- das ist der einzige Netzzugriff und er ist opt-in.

Crosshits: `is_crosshit` mit Schwelle 4.0 und min_dimensions 3 -- bewusst
EXPLIZIT, nicht aus settings: das lokale .env traegt eine veraltete 2.

HISTORISCH (Analyse 2026-10-06, Commit 5e63b53): Seit ROIC im Scorer steckt
(app/screener/roic.py), bildet der Default den Produktivcode ab -- trotz des
Namens `roe` also schon ROIC. Die `roic*`-Varianten schrieben in das ROE-Feld,
das der Scorer nicht mehr liest; sie sind deshalb gesperrt. Zum Nachvollziehen
der Analyse Commit 5e63b53 auschecken. Ihre damalige Beschreibung:

`--profitability roic|roic-de|roic-de-icfree[-fin]` (Default `roe` = Produktivcode bitgleich): ersetzt den
ROE-Eingang der profitability-Achse durch ROIC = EBIT / (Schulden + Eigenkapital
- Cash), EBIT = operatingMargins * totalRevenue, Eigenkapital = bookValue *
sharesOutstanding (`roic`) bzw. totalDebt / debtToEquity (`roic-de`, siehe
equity_from_info). Nur hier nachgebildet, nicht im Scorer: ROIC wird vor dem
Perzentil in das ROE-Feld geschrieben (gleiche Sektor-Logik, ROIC < 0 -> 0); ein
fehlender ROIC (auch investiertes Kapital <= 0) deckelt die Achse auf 3 --
ausser bei `roic-de-icfree`: dort laeuft sie bei Kapital <= 0 nur auf der op. Marge;
`roic-de-icfree-fin` deckelt Kapital <= 0 nur in Financial Services (Kundengeld).

HISTORISCH (Commit 8831c13): seit dem Median-Scorer rechnet der Default `yoy` --
trotz des Namens -- schon das Median-Jahreswachstum; die Varianten sind gesperrt.
Damalige Beschreibung:
`--growth cagr|blend[-median]` (Default `yoy` = Produktivcode bitgleich), Analyse 2026-10-06:
ersetzt das Quartals-YoY-Perzentil der growth-Achse durch das globale Perzentil der
Umsatz-CAGR aus der gecachten Jahresreihe (`cagr`, ohne CAGR <4 GJ steht YoY ein)
bzw. mittelt beide (`blend`). Der Stetigkeits-Deckel bleibt. `--growth-missing cap3`
deckelt bei fehlender CAGR auf 3 statt der heutigen 4. Nach dem Scorer nachgerechnet
(apply_growth_variant), nicht im Scorer.

Aufruf:
    uv run python scripts\simulate_month_scoring.py --month 2026-10 --out-dir <dir>
    uv run python scripts\simulate_month_scoring.py --month 2026-10 --out-dir <dir> --refresh-cik-map
    uv run python scripts\simulate_month_scoring.py --month 2026-10 --out-dir <dir> --profitability roic
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from google.cloud import firestore

from app.config import settings
from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord
from app.output.crosshits_generator import _compute_steadiness_failures
from app.screener.deterministic_scorer import run_deterministic_scoring
from app.screener.dimensions import is_crosshit, steadiness_is_assessable
from app.screener.funnel import _score_detail
from app.screener.growth_consistency import consistency_cap
from app.screener.percentiles import percentile_rank, percentile_to_score
from app.screener.price_takers import is_price_taker, load_price_takers
from app.screener.revenue_trajectory import classify_revenue_trajectory
from app.services.cached_edgar_annual_series import CachedEdgarAnnualSeries

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
UNIVERSUM_DIR = ROOT / "output" / "Universum"
DEFAULT_CIK_MAP = ROOT / "cache" / "sec_ticker_cik_map.json"
PRE_SCORING_STAGES = ("resolution", "basis_gates", "edgar_gates")
THRESHOLD = 4.0
MIN_DIMENSIONS = 3  # production value; NOT settings (local .env carries a stale 2)
CSV_FIELDS = [
    "ticker",
    "stage",
    "reason_code",
    "severity_bucket",
    "is_large_cap",
    "sector_wide",
    "market_cap_eur",
    "gics_sector",
    "detail",
]
BATCH = 300
ROIC_MISSING_CAP = 3
EQUITY_SOURCE = {
    "roic": "book",
    "roic-de": "de",
    "roic-de-icfree": "de",
    "roic-de-icfree-fin": "de",
}
# Variant (b): invested capital <= 0 is not capped -- the axis runs on op margin alone
UNCAPPED_REASONS = {
    "roic-de-icfree": frozenset({"invested_capital_nonpositive"}),
    "roic-de-icfree-fin": frozenset({"invested_capital_nonpositive"}),
}
# ... except in these sectors, where invested capital <= 0 is client money
CAPPED_SECTORS = {"roic-de-icfree-fin": frozenset({"Financial Services"})}


class ReadOnlyStore:
    """In-memory snapshot of prefetched Firestore docs. Writes are a bug here."""

    def __init__(self, docs: dict[tuple[str, str], dict[str, Any]]) -> None:
        self._docs = docs
        self.misses: Counter = Counter()

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        doc = self._docs.get((collection, document_id))
        if doc is None:
            self.misses[collection] += 1
        return doc

    def peek(self, collection: str, document_id: str) -> dict[str, Any] | None:
        """Like get, without touching the miss counter (second reads)."""
        return self._docs.get((collection, document_id))

    def set(self, collection: str, document_id: str, data: dict[str, Any]) -> None:
        raise RuntimeError(f"read-only simulation: refused write {collection}/{document_id}")

    def delete(self, collection: str, document_id: str) -> None:
        raise RuntimeError(f"read-only simulation: refused delete {collection}/{document_id}")


class ReadOnlyRevenueSeries:
    """Read path of CachedRevenueSeries without the yfinance fallback.

    A missing doc is an empty series (consistency n/a), counted, never fetched.
    Freshness is ignored: a stale doc is what the run would have refetched, but the
    400-day TTL makes that rare and the miss count shows it."""

    def __init__(self, store: ReadOnlyStore, collection: str) -> None:
        self._store = store
        self._collection = collection
        self.empty = 0

    def get_revenue_series(self, ticker: str) -> list[float]:
        doc = self._store.get(self._collection, ticker)
        if not doc or "revenues" not in doc:
            self.empty += 1
            return []
        return [float(x) for x in doc["revenues"]]


class NoOpTracker:
    def __init__(self) -> None:
        self.steadiness_lookups: Counter = Counter()

    def record_ticker(self, tokens_in: int, tokens_out: int) -> None:
        return None

    def record_steadiness_lookup(self, status: str) -> None:
        self.steadiness_lookups[status] += 1


def read_dropouts(month: str) -> list[dict[str, str]]:
    path = UNIVERSUM_DIR / f"{month}-dropouts.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def real_crosshits(month: str) -> list[str]:
    text = (UNIVERSUM_DIR / f"{month}-Crosshits.md").read_text("utf-8")
    text = text.split("## Am Stetigkeits-Gate")[0]
    return sorted(
        line.split("|")[2].split()[0]
        for line in text.splitlines()
        if line.startswith("| ") and line.split("|")[1].strip().isdigit()
    )


def prefetch(
    db: firestore.Client, collection: str, ids: list[str]
) -> dict[tuple[str, str], dict[str, Any]]:
    docs: dict[tuple[str, str], dict[str, Any]] = {}
    for i in range(0, len(ids), BATCH):
        refs = [db.collection(collection).document(d) for d in ids[i : i + BATCH]]
        for snap in db.get_all(refs):
            if snap.exists:
                docs[(collection, snap.id)] = snap.to_dict() or {}
    return docs


def refresh_cik_map(path: Path, universe: list[str]) -> None:
    from app.services.edgar_client import EdgarClientImpl

    edgar = EdgarClientImpl(settings.edgar_user_agent)  # map loads once, one GET
    mapping = {t: edgar.get_cik(t) for t in universe}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({t: c for t, c in mapping.items() if c}, indent=0, sort_keys=True),
        encoding="utf-8",
    )
    print(f"CIK-Map geschrieben: {path} ({sum(1 for c in mapping.values() if c)} CIKs)")


def resilience_failures(scored: list[ScreenerRecord]) -> list[dict[str, Any]]:
    """Would-be crosshits that fail only on the leverage red flag (attribute may be
    absent on the pre-change code -> empty list)."""
    out = []
    for r in scored:
        if not getattr(r, "resilience_red_flag", None):
            continue
        dims = r.gemini_dimensions or {}
        if dims.get("growth", 0) < THRESHOLD or dims.get("profitability", 0) < THRESHOLD:
            continue
        if steadiness_is_assessable(r) and (r.steadiness or 0.0) < THRESHOLD:
            continue
        out.append(
            {
                "ticker": r.ticker,
                "flag": r.resilience_red_flag,
                "evidence": (r.gemini_evidence or {}).get("resilience"),
            }
        )
    return sorted(out, key=lambda e: e["ticker"])


def write_dropouts(
    path: Path,
    pre_rows: list[dict[str, str]],
    below: list[ScreenerRecord],
    real_rows: dict[str, dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in pre_rows:
            writer.writerow({k: row[k] for k in CSV_FIELDS})
        for r in below:
            # market_cap_eur needs an FX rate (network); reuse the real run's row
            # when it has one, else leave it blank. reference_check never reads it.
            real = real_rows.get(r.ticker, {})
            writer.writerow(
                {
                    "ticker": r.ticker,
                    "stage": "crosshits",
                    "reason_code": "SCORE_BELOW_THRESHOLD",
                    "severity_bucket": "BENIGN",
                    "is_large_cap": real.get("is_large_cap", "False"),
                    "sector_wide": "False",
                    "market_cap_eur": real.get("market_cap_eur", ""),
                    "gics_sector": r.gics_sector,
                    "detail": _score_detail(r),
                }
            )


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def equity_from_info(info: dict[str, Any], source: str = "book") -> float | None:
    """Book equity for the ROIC denominator.

    book: bookValue x sharesOutstanding. Two measured defects (diagnose_roic.py,
      2026-10): bookValue is in the QUOTE currency while debt/cash are in the
      financial currency (EQNR.OL: NOK vs USD, ~x10), and sharesOutstanding counts
      one share class only (GOOG: equity too small, ROIC 95 %).
    de: totalDebt / (debtToEquity / 100) -- balance-sheet currency, whole company.
      Falls back to `book` only when debt is 0/missing AND quote and financial
      currency agree; otherwise unknown."""
    book, shares = _num(info.get("bookValue")), _num(info.get("sharesOutstanding"))
    book_equity = book * shares if book is not None and shares is not None else None
    if source == "book":
        return book_equity
    debt, de = _num(info.get("totalDebt")), _num(info.get("debtToEquity"))
    if debt is not None and debt > 0 and de is not None and de != 0:
        return debt / (de / 100.0)
    fin = info.get("financialCurrency")
    if fin is None or fin == info.get("currency"):
        return book_equity
    return None


def roic_from_info(
    info: dict[str, Any], equity_source: str = "book"
) -> tuple[float | None, str | None]:
    """(ROIC, None) or (None, reason). Reasons: no_ebit, no_equity, no_debt_cash,
    invested_capital_nonpositive. A missing debt or cash side counts as 0 only if
    the other is present (same rule as net_debt)."""
    margin, revenue = _num(info.get("operatingMargins")), _num(info.get("totalRevenue"))
    equity = equity_from_info(info, equity_source)
    debt, cash = _num(info.get("totalDebt")), _num(info.get("totalCash"))
    if margin is None or revenue is None:
        return None, "no_ebit"
    if equity is None:
        return None, "no_equity"
    if debt is None and cash is None:
        return None, "no_debt_cash"
    ic = (debt or 0.0) + equity - (cash or 0.0)
    if ic <= 0:
        return None, "invested_capital_nonpositive"
    return margin * revenue / ic, None


def apply_roic_inputs(
    records: list[ScreenerRecord],
    infos: dict[str, dict[str, Any]],
    equity_source: str = "book",
) -> dict[str, str | None]:
    """Before scoring: ROIC takes the ROE slot (percentile + negative red flag).
    Returns the missing-reason per ticker (None = ROIC known)."""
    reasons: dict[str, str | None] = {}
    for r in records:
        r.return_on_equity, reasons[r.ticker] = roic_from_info(
            infos[r.ticker], equity_source
        )
    return reasons


def cap_missing_roic(
    records: list[ScreenerRecord],
    reasons: dict[str, str | None],
    uncapped: frozenset[str] = frozenset(),
    capped_sectors: frozenset[str] = frozenset(),
) -> None:
    """After scoring: a missing ROIC never scores better than neutral -- except for
    reasons in `uncapped`, where the axis runs on operating margin alone."""
    for r in records:
        dims = r.gemini_dimensions or {}
        ev = r.gemini_evidence or {}
        if "profitability" in ev:
            ev["profitability"] = ev["profitability"].replace("ROE", "ROIC")
        if r.return_on_equity is None:
            if (
                (reasons.get(r.ticker) not in uncapped or r.gics_sector in capped_sectors)
                and dims.get("profitability", 0) > ROIC_MISSING_CAP
            ):
                dims["profitability"] = ROIC_MISSING_CAP
                ev["profitability"] += f" — capped at {ROIC_MISSING_CAP}"
            r.gemini_data_gaps = [*(r.gemini_data_gaps or []), "roic"]
            r.data_confidence = "low"
        merit = {k: dims[k] for k in ("growth", "profitability", "resilience") if k in dims}
        if merit:
            r.gemini_weakest_dimension = min(merit, key=lambda k: merit[k])


def load_inputs(
    month: str, cik_map_path: Path, refresh: bool
) -> tuple[
    list[dict[str, str]], dict[str, dict[str, str]], list[str], dict[str, str], ReadOnlyStore
]:
    """(pre-scoring rows, real crosshit rows, cohort, cik map, prefetched store)."""
    universe: list[str] = json.loads((ROOT / "data" / "universe.json").read_text("utf-8"))
    if refresh:
        refresh_cik_map(cik_map_path, universe)
    if not cik_map_path.exists():
        sys.exit(f"CIK-Map fehlt: {cik_map_path} -- einmal mit --refresh-cik-map holen")
    cik_map: dict[str, str] = json.loads(cik_map_path.read_text("utf-8"))

    rows = read_dropouts(month)
    pre_rows = [r for r in rows if r["stage"] in PRE_SCORING_STAGES]
    dropped = {r["ticker"] for r in pre_rows}
    real_cross_rows = {r["ticker"]: r for r in rows if r["stage"] == "crosshits"}
    cohort = [t for t in universe if t not in dropped]

    db = firestore.Client(project=settings.gcp_project_id)
    docs = prefetch(db, settings.ticker_collection, cohort)
    docs |= prefetch(db, settings.revenue_series_collection, cohort)
    ciks = sorted({cik_map[t].zfill(10) for t in cohort if t in cik_map})
    docs |= prefetch(db, settings.edgar_annual_series_collection, ciks)
    return pre_rows, real_cross_rows, cohort, cik_map, ReadOnlyStore(docs)


def build_and_score(
    store: ReadOnlyStore,
    cohort: list[str],
    cik_map: dict[str, str],
    profitability: str = "roe",
    growth: str = "yoy",
    growth_missing: str = "fallback",
) -> tuple[list[ScreenerRecord], list[str], ReadOnlyRevenueSeries, NoOpTracker]:
    """Records from the cached .info, scored like the monthly run (+ ROIC variant).
    Call once per variant: scoring mutates the records."""
    if profitability != "roe":
        sys.exit(
            "ROIC-Varianten sind seit dem ROIC-Scorer gesperrt (der Default rechnet "
            "schon ROIC); Analysestand: git checkout 5e63b53"
        )
    if growth != "yoy":
        sys.exit(
            "growth-Varianten sind seit dem Median-Scorer gesperrt (der Default rechnet "
            "schon das Median-Jahreswachstum); Analysestand: git checkout 8831c13"
        )
    records: list[ScreenerRecord] = []
    infos: dict[str, dict[str, Any]] = {}
    missing_info: list[str] = []
    for t in cohort:
        info = store.get(settings.ticker_collection, t)
        if not info:
            missing_info.append(t)
            continue
        rec = ScreenerRecord.from_yfinance_info(t, info)
        rec.cik = cik_map.get(t)  # mirrors runner._evaluate_edgar (company_tickers)
        records.append(rec)
        infos[t] = info
    reasons: dict[str, str | None] = {}
    if profitability.startswith("roic"):
        reasons = apply_roic_inputs(records, infos, EQUITY_SOURCE[profitability])

    revenue = ReadOnlyRevenueSeries(store, settings.revenue_series_collection)
    annual = CachedEdgarAnnualSeries(
        client=None,  # type: ignore[arg-type]  # read path never touches the client
        firestore=store,
        collection=settings.edgar_annual_series_collection,
    )
    tracker = NoOpTracker()
    scored = run_deterministic_scoring(
        records, revenue_cache=revenue, run_tracker=tracker, annual_series=annual
    )
    if profitability.startswith("roic"):
        cap_missing_roic(
            scored,
            reasons,
            UNCAPPED_REASONS.get(profitability, frozenset()),
            CAPPED_SECTORS.get(profitability, frozenset()),
        )
    if growth != "yoy":
        apply_growth_variant(scored, store, growth, growth_missing)
    return scored, missing_info, revenue, tracker


def revenue_cagrs(
    store: ReadOnlyStore, tickers: list[str], method: str = "endpoint"
) -> dict[str, float | None]:
    """Endpoint CAGR of the cached fiscal-year revenue series, None below 4 GJ
    (same definedness rule as the consistency cap). Reads past the miss counter.
    method=median: median of the annual growth rates instead -- one definitional
    break (ADYEN.AS gross->net revenue: endpoint CAGR -33 %, median +19 %) cannot
    drag it."""
    out: dict[str, float | None] = {}
    for t in tickers:
        doc = store.peek(settings.revenue_series_collection, t)
        series = [float(x) for x in doc["revenues"]] if doc and "revenues" in doc else []
        cagr, _, definedness = classify_revenue_trajectory(series)
        if definedness is not DefinednessOutcome.DEFINED:
            out[t] = None
        elif method == "median":
            yoy = sorted(series[i] / series[i - 1] - 1 for i in range(1, len(series)))
            mid = len(yoy) // 2
            out[t] = yoy[mid] if len(yoy) % 2 else (yoy[mid - 1] + yoy[mid]) / 2
        else:
            out[t] = cagr
    return out


def apply_growth_variant(
    scored: list[ScreenerRecord], store: ReadOnlyStore, growth: str, missing: str
) -> None:
    """Re-score the growth axis after the production scorer ran.

    cagr:  global percentile of the multi-year revenue CAGR replaces the quarterly
           YoY percentile; without a CAGR (<4 GJ) the YoY percentile stands in.
    blend: mean of the CAGR and YoY percentiles (whichever exist).
    The consistency cap stays. missing=cap3: a missing CAGR caps growth at 3
    (otherwise the existing <4-GJ consistency cap of 4 applies)."""
    method = "median" if growth.endswith("-median") else "endpoint"
    growth = growth.removesuffix("-median")
    cagrs = revenue_cagrs(store, [r.ticker for r in scored], method)
    dist = [c for c in cagrs.values() if c is not None]
    for r in scored:
        pcts = r.input_percentiles or {}
        p_yoy = pcts.get("revenue_growth_yoy")
        cagr = cagrs[r.ticker]
        p_cagr = percentile_rank(cagr, dist) if cagr is not None else None
        if growth == "cagr":
            parts = [p_cagr] if p_cagr is not None else [p for p in (p_yoy,) if p is not None]
        else:
            parts = [p for p in (p_cagr, p_yoy) if p is not None]
        score = percentile_to_score(sum(parts) / len(parts)) if parts else 3
        score = min(score, consistency_cap(r.growth_consistency))
        if cagr is None and missing == "cap3":
            score = min(score, 3)
        dims = r.gemini_dimensions or {}
        dims["growth"] = score
        ev = r.gemini_evidence or {}
        cagr_txt = "n/a (<4 GJ)" if cagr is None else f"{cagr:.1%} (P{p_cagr:.0f})"
        ev["growth"] = f"{ev.get('growth', '')}, rev CAGR {cagr_txt}"
        merit = {k: dims[k] for k in ("growth", "profitability", "resilience") if k in dims}
        if merit:
            r.gemini_weakest_dimension = min(merit, key=lambda k: merit[k])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--cik-map", type=Path, default=DEFAULT_CIK_MAP)
    ap.add_argument("--refresh-cik-map", action="store_true")
    ap.add_argument("--profitability", choices=tuple(["roe", *EQUITY_SOURCE]), default="roe")
    ap.add_argument("--growth", choices=("yoy", "cagr", "blend", "cagr-median", "blend-median"), default="yoy")
    ap.add_argument("--growth-missing", choices=("fallback", "cap3"), default="fallback")
    args = ap.parse_args()
    month: str = args.month
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    pre_rows, real_cross_rows, cohort, cik_map, store = load_inputs(
        month, args.cik_map, args.refresh_cik_map
    )
    scored, missing_info, revenue, tracker = build_and_score(
        store, cohort, cik_map, args.profitability, args.growth, args.growth_missing
    )
    records = scored

    cross = [r for r in scored if is_crosshit(r, THRESHOLD, MIN_DIMENSIONS)]
    below = [r for r in scored if not is_crosshit(r, THRESHOLD, MIN_DIMENSIONS)]
    write_dropouts(out_dir / f"{month}-dropouts.csv", pre_rows, below, real_cross_rows)

    table = load_price_takers(ROOT / "data" / "price_takers.json")
    takers = [r.ticker for r in cross if is_price_taker(r.ticker, r.gics_industry, table)]
    sim_list = sorted(r.ticker for r in cross)
    real_list = real_crosshits(month)
    res_dist = Counter((r.gemini_dimensions or {}).get("resilience") for r in scored)
    has_flag_field = "resilience_red_flag" in ScreenerRecord.model_fields
    red_flags = (
        sum(1 for r in scored if getattr(r, "resilience_red_flag", None))
        if has_flag_field
        else None
    )
    capped = [
        r.ticker
        for r in scored
        if "capped at" in (r.gemini_evidence or {}).get("resilience", "")
    ]
    flags_by_sector = Counter(
        r.gics_sector for r in scored if getattr(r, "resilience_red_flag", None)
    )
    steadiness_failed = [
        e["record"].ticker
        for e in _compute_steadiness_failures(scored, THRESHOLD, MIN_DIMENSIONS)
    ]
    prof_dist = Counter((r.gemini_dimensions or {}).get("profitability") for r in scored)
    summary = {
        "month": month,
        "profitability_variant": args.profitability,
        "growth_variant": f"{args.growth}/{args.growth_missing}",
        "growth_distribution": {
            str(k): v
            for k, v in sorted(
                Counter((r.gemini_dimensions or {}).get("growth") for r in scored).items(),
                key=lambda kv: str(kv[0]),
            )
        },
        "profitability_distribution": {
            str(k): prof_dist[k] for k in sorted(prof_dist, key=str)
        },
        "cohort": len(cohort),
        "scored": len(scored),
        "missing_ticker_info": missing_info,
        "cache_misses": dict(store.misses),
        "revenue_series_empty": revenue.empty,
        "steadiness_lookups": dict(tracker.steadiness_lookups),
        "records_with_cik": sum(1 for r in records if r.cik),
        "crosshit_count": len(cross),
        "crosshits": sim_list,
        "price_takers": sorted(takers),
        "price_taker_share": round(len(takers) / len(cross), 4) if cross else None,
        "resilience_distribution": {str(k): res_dist[k] for k in sorted(res_dist, key=str)},
        "resilience_zero_count": res_dist.get(0, 0),
        "resilience_red_flag_count": red_flags,
        "resilience_red_flags_by_sector": dict(flags_by_sector.most_common()),
        "resilience_capped_missing_leverage": len(capped),
        "data_confidence_low": sum(1 for r in scored if r.data_confidence == "low"),
        "leverage_red_flag_failures": resilience_failures(scored),
        "steadiness_failed": sorted(steadiness_failed),
        "real_crosshit_count": len(real_list),
        "diff_vs_real": {
            "added": sorted(set(sim_list) - set(real_list)),
            "removed": sorted(set(real_list) - set(sim_list)),
        },
    }
    out_json = out_dir / f"{month}-sim-summary.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Simulation {month}: Kohorte {len(cohort)}, bewertet {len(scored)}, "
          f"ohne .info {len(missing_info)} {missing_info[:10]}")
    print(f"Cache-Fehltreffer: {dict(store.misses)}; Umsatzreihe leer: {revenue.empty}; "
          f"Stetigkeit: {dict(tracker.steadiness_lookups)}; mit CIK: {summary['records_with_cik']}")
    print(f"Crosshits: {len(cross)} (echter Lauf: {len(real_list)})")
    print(f"  {sim_list}")
    print(f"  neu: {summary['diff_vs_real']['added']}  raus: {summary['diff_vs_real']['removed']}")
    print(f"Preisnehmer: {len(takers)}/{len(cross)} = {summary['price_taker_share']} {sorted(takers)}")
    print(f"profitability ({args.profitability}): {summary['profitability_distribution']}")
    print(f"growth ({summary['growth_variant']}): {summary['growth_distribution']}")
    print(f"resilience-Verteilung: {summary['resilience_distribution']}")
    print(f"resilience=0: {summary['resilience_zero_count']}; Red-Flags (Feld): {red_flags} "
          f"{summary['resilience_red_flags_by_sector']}")
    print(f"Verschuldung fehlt (gedeckelt auf 3): {len(capped)}; "
          f"data_confidence low: {summary['data_confidence_low']}")
    print(f"Am Verschuldungs-Red-Flag gescheitert: {summary['leverage_red_flag_failures']}")
    print(f"Am Stetigkeits-Gate gescheitert: {summary['steadiness_failed']}")
    print(f"geschrieben: {out_json}")


if __name__ == "__main__":
    main()
