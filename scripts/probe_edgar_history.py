r"""Machbarkeitsprobe: liefert die SEC-XBRL-companyfacts-API zehn Jahre
Jahreszahlen fuer das Tool-A-Universum?

Die Frage steht VOR jeder Aenderung am Scoring. Tool A bewertet growth,
profitability und resilience heute auf Momentaufnahmen; der einzige
Zyklik-Daempfer ist `consistency_cap` (app/screener/growth_consistency.py) und
der rechnet ueber die VIER Geschaeftsjahre, die yfinance liefert. Vier Jahre =
drei Uebergaenge -- in einem Rohstoffboom zeigen alle drei nach oben, der
Daempfer feuert also genau dort nicht, wo er gebraucht wird (Goldminen, Kupfer,
Speicher in der September-Crosshits-Liste). Eine vierte Dimension "Stetigkeit"
braucht zehn Jahre. Dieses Skript misst, ob es die gibt.

Read-only, $0, kein Firestore, kein GCP: `EdgarClientImpl` haengt nur an httpx
und FISHERSCREEN_EDGAR_USER_AGENT. Ein Request pro Titel (companyfacts buendelt
alle Konzepte und alle Jahre in einem Dokument), Rate Limit 8 req/s aus
`app/services/rate_limiter.py`.

DIE ENTSCHEIDENDE DESIGN-ENTSCHEIDUNG -- Perioden- statt fy-Schluessel:
In companyfacts benennen `fy`/`fp` das Geschaeftsjahr des MELDENDEN FILINGS,
nicht die Periode des Wertes. Der FY2025-10-K traegt seine Vergleichsjahre
FY2023 und FY2024 ebenfalls mit fy=2025, fp=FY. Nach `fy` zu schluesseln zieht
drei echte Jahre zu einem zusammen und unterschaetzt die Abdeckung dramatisch.
Geschluesselt wird deshalb nach der Periode selbst ((start,end) bzw. end), und
der Bericht nennt beide Zahlen nebeneinander, damit die Abweichung pruefbar ist
statt still.

Resumierbar: der Extrakt je Titel wird nach jedem Ticker fortgeschrieben (nie
das rohe JSON -- das waeren Gigabytes), ein erneuter Aufruf ueberspringt bereits
gemessene Titel. Ein Netzfehler wird NICHT persistiert: das ist eine Aussage
ueber die API, nicht ueber den Titel.

Der Bericht liegt unter docs/superpowers/diagnostic-reports/ -- dort, wo die
uebrigen Diagnose-Artefakte liegen. `reports/` im Repo-Root ist ausdruecklich
NICHT der Ort und in .gitignore gesperrt: ein zweiter Ablageort haette bei jedem
Lauf die handgeschriebene Empfehlung ins Leere laufen lassen.

Die gemessenen Abschnitte des Berichts werden bei jedem Lauf neu geschrieben;
alles unterhalb von HAND_MARKER bleibt stehen. Die Messung ist reproduzierbar,
die Bewertung darunter nicht -- deshalb ueberschreibt die eine die andere nicht.

Aufruf (cmd.exe):
  set FISHERSCREEN_EDGAR_USER_AGENT=FisherScreen/1.0 name@example.com
  uv run python scripts\probe_edgar_history.py
  uv run python scripts\probe_edgar_history.py --report-only
  uv run python scripts\probe_edgar_history.py --universe --limit 20
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.config import settings
from app.errors import DataSourceError
from app.services.edgar_client import EdgarClientImpl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MONTH = "2026-09"
UNIVERSE_JSON = REPO_ROOT / "data" / "universe.json"
DEFAULT_STATE = REPO_ROOT / "cache" / "edgar_history_coverage.json"
DEFAULT_REPORT = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "diagnostic-reports"
    / "2026-09-07-edgar-history-coverage.md"
)

# Nur der Jahresabschluss zaehlt. 20-F wird bewusst NICHT mitgezaehlt: ein
# US-notierter Foreign Private Issuer meldet unter ifrs-full mit anderen Tags,
# das waere eine zweite Messung mit eigener Konzeptliste. Der Bericht weist
# diese Titel getrennt aus, statt sie stumm als "keine Daten" zu fuehren.
ANNUAL_FORMS = ("10-K", "10-K/A")

# Eine Jahresperiode. 52/53-Wochen-Geschaeftsjahre (Handel) schwanken um einige
# Tage, ein Rumpfjahr nach Umstellung des Geschaeftsjahresendes faellt raus.
DURATION_MIN_DAYS = 340
DURATION_MAX_DAYS = 400

# Abstand zwischen zwei aufeinanderfolgenden Jahresenden. Grosszuegiger als das
# Periodenfenster, weil hier zwei Stichtage verglichen werden, keine Dauer.
GAP_MIN_DAYS = 300
GAP_MAX_DAYS = 430

# Wie weit ein Stichtag vom Jahresabschluss-Jahrestag abweichen darf. Ein 10-K
# taggt auch Quartals-Bilanzstichtage (nachgewiesen an Akamai, CIK 1086222:
# 2022-03-31/06-30/09-30 stehen neben den Jahresenden). Ohne Verankerung
# uebernimmt der 31.03.2022 das Etikett 2021 -- er ist der spaetere Stichtag --
# und verdraengt dort den echten Jahresabschluss. 45 Tage lassen
# 52/53-Wochen-Geschaeftsjahre und Jahreswechsel-Stichtage durch, ein Quartal
# nicht.
ANNIVERSARY_TOLERANCE_DAYS = 45

# Version der Extraktionslogik. Hochzaehlen, sobald sich aendert, WAS aus
# companyfacts gelesen wird -- der Zwischenstand wird dann verworfen.
EXTRACT_SCHEMA = 2

TAXONOMY = "us-gaap"

# Konzepte samt us-gaap-Fallbacks, in der Reihenfolge des Auftrags.
CONCEPTS: dict[str, tuple[str, list[str]]] = {
    "revenue": (
        "Umsatz",
        [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
        ],
    ),
    "operating_income": ("Operatives Ergebnis", ["OperatingIncomeLoss"]),
    "net_income": ("Nettogewinn", ["NetIncomeLoss"]),
    "equity": ("Eigenkapital", ["StockholdersEquity"]),
    "assets": ("Gesamtvermoegen", ["Assets"]),
}

# Zusaetzliche us-gaap-Tags, die dasselbe Konzept unter anderem Namen fuehren.
# Sie gehoeren NICHT zum Auftrag -- gemessen wird beides nebeneinander, damit
# der Bericht die Frage "welcher Fallback fehlt" mit einer Zahl beantwortet und
# nicht mit einer Vermutung. Zusammengetragen aus den Ausfaellen des
# Smoke-Laufs (AAON meldet ...IncludingAssessedTax und SalesRevenueGoodsNet,
# Agilent fuehrt Nettogewinn vor 2020 als ProfitLoss) plus den ueblichen
# Verdaechtigen bei Banken und Versicherern.
ALTERNATIVES: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "RevenuesNetOfInterestExpense",
        "InterestAndDividendIncomeOperating",
        "HealthCareOrganizationRevenue",
        "RealEstateRevenueNet",
    ],
    "operating_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "net_income": [
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "IncomeLossFromContinuingOperations",
    ],
    "equity": [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "assets": [],
}

# Tags, die im Bericht bei einer Konzeptnamen-Luecke gezeigt werden: nur die,
# aus denen ein fehlender Fallback ablesbar ist.
GAP_TAG_HINTS = ("revenue", "income", "asset", "equity", "sales", "premium")

# Die acht Preisnehmer der September-Crosshits-Liste, von Hand benannt: Gold
# (EDV.L, HL, NEM, RGLD), Kupfer (ANTO.L), Landbesitz (TPL), Speicher (MU,
# SNDK). Sie sind hier kein Filter, sondern der Regressionsfall: an ihnen
# entscheidet sich, ob eine Stetigkeits-Dimension das gemeldete Problem
# ueberhaupt erreicht.
PRICE_TAKERS = ("EDV.L", "HL", "NEM", "RGLD", "ANTO.L", "TPL", "MU", "SNDK")

# Alles unterhalb dieser Zeile im Bericht bleibt bei einem erneuten Lauf
# stehen. Die Messung schreibt sich neu, die Bewertung nicht.
HAND_MARKER = "<!-- HANDGESCHRIEBEN AB HIER — ein erneuter Lauf laesst dies stehen -->"

# Primaer-Evidenz: ein Aggregat beweist nicht, dass der Mechanismus greift.
# FAST = sauberer Fall, NEM = Preisnehmer, XOM = gemessener Konzeptausfall
# (JPM waere der Bank-Fall, ist aber gar nicht im gescorten Universum --
# Finanzwerte fallen frueher aus den Basis-Gates).
EVIDENCE_TICKERS = ("FAST", "NEM", "XOM")


# --------------------------------------------------------------------------
# reine Logik (ohne Netz, unter Test)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ConceptCoverage:
    concept: str | None
    unit: str | None
    years: tuple[int, ...]
    values: tuple[float, ...]
    contiguous: int
    restatements: int
    naive_fy_count: int


EMPTY_COVERAGE = ConceptCoverage(
    concept=None,
    unit=None,
    years=(),
    values=(),
    contiguous=0,
    restatements=0,
    naive_fy_count=0,
)


def is_us_ticker(ticker: str) -> bool:
    """Konvention aus app/screener/runner.py:263 -- US-Klassenaktien tragen
    einen Bindestrich (BRK-B), ein Punkt markiert eine Nicht-US-Boerse."""
    return "." not in ticker


def fiscal_label(end: date) -> int:
    """Geschaeftsjahr-Etikett eines Periodenendes. Ein Handelsjahr, das am
    31.01.2025 schliesst, ist Geschaeftsjahr 2024. Nur Anzeige -- die
    Zusammenhangspruefung rechnet auf den Stichtagen selbst."""
    return end.year if end.month >= 6 else end.year - 1


def contiguous_run(ends: Sequence[date]) -> int:
    """Laenge der Kette aufeinanderfolgender Jahre, die am JUENGSTEN Stichtag
    endet. Eine Luecke davor beendet die Kette -- zehn Jahre mit Loch in der
    Mitte sind keine zehn Jahre Historie."""
    if not ends:
        return 0
    ordered = sorted(ends)
    run = 1
    for newer, older in zip(reversed(ordered), reversed(ordered[:-1])):
        gap = (newer - older).days
        if GAP_MIN_DAYS <= gap <= GAP_MAX_DAYS:
            run += 1
        else:
            break
    return run


def taxonomies(facts: dict[str, Any]) -> list[str]:
    return sorted(facts.get("facts", {}))


def available_tags(facts: dict[str, Any], taxonomy: str) -> list[str]:
    return sorted(facts.get("facts", {}).get(taxonomy, {}))


def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _annual_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Jahres-Fakten aus 10-K/10-K/A, als (period_key, end, entry)."""
    out: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("form") not in ANNUAL_FORMS:
            continue
        end = _parse_date(entry.get("end", ""))
        if end is None:
            continue
        start_raw = entry.get("start")
        if start_raw is None:  # Bestandsgroesse: Stichtag
            out.append({"key": ("i", end), "end": end, "entry": entry})
            continue
        start = _parse_date(start_raw)
        if start is None:
            continue
        if not DURATION_MIN_DAYS <= (end - start).days <= DURATION_MAX_DAYS:
            continue
        out.append({"key": ("d", start, end), "end": end, "entry": entry})
    return out


def _coverage_for(pooled: list[dict[str, Any]], candidates: Sequence[str]) -> ConceptCoverage:
    # 1. Perioden-Bucket: dieselbe Periode, in mehreren Filings gemeldet --
    #    und moeglicherweise unter mehreren Tags.
    buckets: dict[Any, list[dict[str, Any]]] = {}
    for item in pooled:
        buckets.setdefault(item["key"], []).append(item)

    chosen: list[dict[str, Any]] = []
    for items in buckets.values():
        # 2. Gewinner: der frueheste Kandidat der Liste, darin das spaeteste
        #    `filed` -- die Korrektur schlaegt das Original.
        winner = min(
            items, key=lambda i: (i["priority"], _negated(i["entry"].get("filed", "")))
        )
        val = winner["entry"].get("val")
        if val is None:
            continue
        # 3. Restatement nur INNERHALB eines Tags. Zwei Tags koennen dieselbe
        #    Periode mit verschiedener Definition melden (Gesamtumsatz gegen
        #    Umsatz aus Vertraegen) -- das ist keine Korrektur.
        same_tag = {
            i["entry"].get("val") for i in items if i["tag"] == winner["tag"]
        }
        chosen.append(
            {
                "label": fiscal_label(winner["end"]),
                "end": winner["end"],
                "val": float(val),
                "restated": 1 if len(same_tag) > 1 else 0,
                "tag": winner["tag"],
                "unit": winner["unit"],
                "priority": winner["priority"],
            }
        )

    # 4. Auf den Jahresabschluss verankern. Der juengste Stichtag gibt den
    #    Jahrestag vor; was mehr als ANNIVERSARY_TOLERANCE_DAYS davon abweicht,
    #    ist kein Jahresabschluss und faellt raus, statt um ein Etikett zu
    #    konkurrieren.
    if not chosen:
        return EMPTY_COVERAGE
    anchor = max(chosen, key=lambda r: r["end"])["end"]
    for row in chosen:
        row["offset"] = _anniversary_distance(row["end"], anchor)
    chosen = [r for r in chosen if r["offset"] <= ANNIVERSARY_TOLERANCE_DAYS]

    # 5. Ein Geschaeftsjahr-Etikett, ein Wert: der Stichtag, der dem Jahrestag am
    #    naechsten liegt.
    per_label: dict[int, dict[str, Any]] = {}
    for row in chosen:
        held = per_label.get(row["label"])
        if held is None or (-row["offset"], row["end"], -row["priority"]) > (
            -held["offset"],
            held["end"],
            -held["priority"],
        ):
            per_label[row["label"]] = row
    if not per_label:
        return EMPTY_COVERAGE

    ordered = [per_label[label] for label in sorted(per_label)]
    contributing = [c for c in candidates if any(r["tag"] == c for r in ordered)]
    naive = {
        i["entry"].get("fy")
        for i in pooled
        if i["entry"].get("fp") == "FY" and i["entry"].get("fy") is not None
    }
    return ConceptCoverage(
        concept="+".join(contributing),
        unit=ordered[-1]["unit"],
        years=tuple(row["label"] for row in ordered),
        values=tuple(row["val"] for row in ordered),
        contiguous=contiguous_run([row["end"] for row in ordered]),
        restatements=sum(row["restated"] for row in ordered),
        naive_fy_count=len(naive),
    )


def _anniversary_distance(end: date, anchor: date) -> int:
    """Abstand in Tagen zum naechsten Jahrestag des Anker-Stichtags."""
    best = 10**6
    for year in (end.year - 1, end.year, end.year + 1):
        try:
            anniversary = date(year, anchor.month, anchor.day)
        except ValueError:  # 29. Februar in einem Nicht-Schaltjahr
            anniversary = date(year, anchor.month, anchor.day - 1)
        best = min(best, abs((end - anniversary).days))
    return best


def _negated(filed: str) -> tuple[int, ...]:
    """Sortierschluessel, der ein spaeteres `filed` nach vorne holt, damit
    `min()` ueber (priority, filed-absteigend) gebildet werden kann."""
    return tuple(-ord(c) for c in filed)


def extract_concept(
    facts: dict[str, Any],
    candidates: Sequence[str],
    *,
    taxonomy: str = TAXONOMY,
) -> ConceptCoverage:
    """Abdeckung EINES Konzepts ueber alle seine Kandidatenbezeichnungen.

    Die Kandidaten werden zusammengefuehrt, nicht der Reihe nach probiert: ASC
    606 hat die meisten US-Filer um 2018 von `Revenues` auf
    `RevenueFromContractWithCustomerExcludingAssessedTax` umgestellt. Wer den
    ersten Tag nimmt, der ueberhaupt Daten traegt, bekommt eine Reihe, die 2017
    endet, und misst die Abdeckung kaputt (nachgewiesen an Agilent, CIK 1090872).

    Bei Ueberschneidung gewinnt der frueher gelistete Kandidat -- die Reihenfolge
    der Liste ist die Definitionsrangfolge."""
    node = facts.get("facts", {}).get(taxonomy, {})
    pooled: list[dict[str, Any]] = []
    for priority, name in enumerate(candidates):
        units = node.get(name, {}).get("units", {})
        if not units:
            continue
        unit = "USD" if "USD" in units else sorted(units)[0]
        for item in _annual_entries(units[unit]):
            pooled.append({**item, "tag": name, "priority": priority, "unit": unit})
    if not pooled:
        return EMPTY_COVERAGE
    return _coverage_for(pooled, candidates)


def preserve_handwritten(body: str, existing: str) -> str:
    """Die gemessenen Abschnitte neu, die handgeschriebene Bewertung unangetastet.

    Ohne das waere jeder erneute Probelauf ein stiller Datenverlust -- und die
    Bewertung ist der Teil, der nicht reproduzierbar ist."""
    if HAND_MARKER not in existing:
        return body
    tail = existing.split(HAND_MARKER, 1)[1]
    return f"{body}\n{HAND_MARKER}{tail}"


def parse_dropouts_scored(csv_text: str) -> list[str]:
    """Die Titel, die gescort wurden und die Crosshit-Schwelle verfehlt haben --
    Stufe `crosshits` in der dropouts.csv."""
    reader = csv.DictReader(io.StringIO(csv_text))
    return [row["ticker"] for row in reader if row.get("stage") == "crosshits"]


def parse_crosshits_tickers(md_text: str) -> list[str]:
    """Ticker-Spalte der Crosshits-Tabelle, ohne die Flag-Marker der
    `_flags()`-Funktion aus app/output/crosshits_generator.py."""
    tickers: list[str] = []
    in_table = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not in_table:
            if len(cells) >= 2 and cells[1] == "Ticker":
                in_table = True
            continue
        if set(stripped) <= set("|- "):  # Trennzeile
            continue
        if len(cells) >= 2 and cells[1] and cells[1].split():
            tickers.append(cells[1].split()[0])
    return tickers


# --------------------------------------------------------------------------
# Ticker-Basis
# --------------------------------------------------------------------------


def scored_tickers(month: str) -> list[str]:
    """Die Titel, die der Monatslauf tatsaechlich gescort hat, aus zwei
    Artefakten rekonstruiert und gegen den Funnel geprueft. Weicht die Summe ab,
    ist die Basis falsch -- dann bricht die Probe ab, statt eine Quote auf einer
    unbekannten Grundgesamtheit auszurechnen."""
    base = REPO_ROOT / "output" / "Universum"
    dropouts = (base / f"{month}-dropouts.csv").read_text(encoding="utf-8")
    crosshits = (base / f"{month}-Crosshits.md").read_text(encoding="utf-8")
    funnel = json.loads((base / f"{month}-funnel_summary.json").read_text("utf-8"))

    tickers = parse_dropouts_scored(dropouts) + parse_crosshits_tickers(crosshits)
    expected = next(
        s["remaining"] for s in funnel["stages"] if s["stage"] == "scoring"
    )
    if len(tickers) != expected:
        raise SystemExit(
            f"FEHLER: rekonstruierte Basis {len(tickers)} != Funnel {expected} "
            f"({month}). Basis nicht vertrauenswuerdig, Abbruch."
        )
    return tickers


# --------------------------------------------------------------------------
# Messung
# --------------------------------------------------------------------------


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        print(f"WARNUNG: {path} unlesbar -- beginne neu")
        return {}
    # Der Zwischenstand haelt Extrakte, keine Rohdaten. Aendert sich die
    # Extraktion, sind die alten Werte falsch -- und ein warmer Cache, der eine
    # Verifikation maskiert, ist in diesem Repo schon einmal teuer gewesen.
    if state.get("schema") != EXTRACT_SCHEMA:
        print(
            f"Zwischenstand hat Schema {state.get('schema')}, Skript erwartet "
            f"{EXTRACT_SCHEMA} -- Messung beginnt neu"
        )
        return {}
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    """Atomar schreiben, mit Nachsicht gegenueber WatchGuard EPDR: der Scanner
    haelt eine frisch geschriebene Datei kurz offen, `replace` scheitert dann
    mit WinError 5 (siehe scripts/measure_annual_form_recency.py)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.3)


def measure_ticker(edgar: EdgarClientImpl, ticker: str) -> dict[str, Any]:
    """Ein Request, alle fuenf Konzepte. Kein oeffentlicher Accessor liefert
    companyfacts; fuer eine einmalige Messung die Protocol-Flaeche zu erweitern
    waere die groessere Aenderung -- Praezedenzfall in
    scripts/measure_annual_form_recency.py:151-158."""
    cik = edgar.get_cik(ticker)
    if not cik:
        return {"status": "no_cik"}

    padded = cik.zfill(10)
    facts = edgar._get(f"{edgar._SEC_BASE}/api/xbrl/companyfacts/CIK{padded}.json")

    record: dict[str, Any] = {
        "status": "ok",
        "cik": padded,
        "entity": facts.get("entityName", ""),
        "taxonomies": taxonomies(facts),
        "concepts": {},
        "concepts_extended": {},
    }
    missing = False
    for key, (_, candidates) in CONCEPTS.items():
        coverage = extract_concept(facts, candidates)
        record["concepts"][key] = asdict(coverage)
        record["concepts_extended"][key] = asdict(
            extract_concept(facts, list(candidates) + ALTERNATIVES[key])
        )
        if coverage.concept is None:
            missing = True
    if missing:
        tags = available_tags(facts, TAXONOMY)
        record["us_gaap_tag_count"] = len(tags)
        record["us_gaap_tag_hints"] = [
            t for t in tags if any(h in t.lower() for h in GAP_TAG_HINTS)
        ][:40]
    return record


def run_probe(
    tickers: Sequence[str], edgar: EdgarClientImpl, state_path: Path
) -> dict[str, Any]:
    state = load_state(state_path)
    state["schema"] = EXTRACT_SCHEMA
    results: dict[str, Any] = state.setdefault("tickers", {})
    state.setdefault("requests", 0)
    state.setdefault("elapsed_seconds", 0.0)

    todo = [t for t in tickers if t not in results]
    print(f"US-Titel gesamt {len(tickers)}, noch offen {len(todo)}")
    started = time.monotonic()
    errors = 0
    for n, ticker in enumerate(todo, start=1):
        try:
            record = measure_ticker(edgar, ticker)
        except DataSourceError as exc:
            message = str(exc)
            if "404" in message:
                # Ein Registrant ohne companyfacts: Aussage ueber den Titel,
                # also persistieren.
                results[ticker] = {"status": "no_companyfacts", "detail": message}
                state["requests"] += 1
            else:
                # Aussage ueber die API, nicht ueber den Titel -- nicht
                # persistieren, damit ein erneuter Lauf es nochmal versucht.
                errors += 1
                print(f"  {ticker}: {message}")
            continue
        results[ticker] = record
        state["requests"] += 1
        if n % 25 == 0 or n == len(todo):
            done = len(results)
            print(f"  [{n}/{len(todo)}] gemessen: {done}, Fehler: {errors}")
            state["elapsed_seconds"] = round(
                state["elapsed_seconds"] + (time.monotonic() - started), 1
            )
            started = time.monotonic()
            save_state(state_path, state)
    state["elapsed_seconds"] = round(
        state["elapsed_seconds"] + (time.monotonic() - started), 1
    )
    state["transient_errors"] = errors
    save_state(state_path, state)
    return state


# --------------------------------------------------------------------------
# Bericht
# --------------------------------------------------------------------------


def _bucket(contiguous: int) -> str:
    if contiguous >= 10:
        return ">=10"
    if contiguous >= 7:
        return ">=7"
    if contiguous > 0:
        return "<7"
    return "kein Konzept"


def _pct(n: int, total: int) -> str:
    return f"{n / total:.1%}" if total else "n/a"


def render_report(
    state: dict[str, Any],
    *,
    month: str,
    us_tickers: Sequence[str],
    non_us_tickers: Sequence[str],
    basis_label: str,
    crosshits: Sequence[str] = (),
) -> str:
    results: dict[str, Any] = state.get("tickers", {})
    ok = {t: r for t, r in results.items() if r.get("status") == "ok"}
    no_cik = sorted(t for t, r in results.items() if r.get("status") == "no_cik")
    no_facts = sorted(
        t for t, r in results.items() if r.get("status") == "no_companyfacts"
    )

    lines: list[str] = []
    add = lines.append
    add("# EDGAR companyfacts — Abdeckungsmessung Jahreshistorie")
    add("")
    add(f"**Erzeugt:** {date.today().isoformat()} · **Basis:** {basis_label}")
    add("")
    add(
        "Frage: reichen die SEC-XBRL-Jahresdaten fuer eine vierte Tool-A-Dimension "
        "**Stetigkeit** ueber zehn Jahre?"
    )
    add("")
    add("## Grundgesamtheit")
    add("")
    add("| | Anzahl |")
    add("|---|---|")
    add(f"| Titel im Lauf {month} (gescort) | {len(us_tickers) + len(non_us_tickers)} |")
    add(f"| davon US-Titel (kein `.` im Symbol) | {len(us_tickers)} |")
    add(f"| davon Nicht-SEC-Titel (uebersprungen) | {len(non_us_tickers)} |")
    add(f"| US-Titel mit companyfacts gemessen | {len(ok)} |")
    add(f"| US-Titel ohne CIK in company_tickers.json | {len(no_cik)} |")
    add(f"| US-Titel mit CIK, aber ohne companyfacts (404) | {len(no_facts)} |")
    add("")
    add(
        f"**Requests:** {state.get('requests', 0)} (ein companyfacts-Abruf je Titel, "
        f"plus einmal company_tickers.json) · "
        f"**Laufzeit:** {state.get('elapsed_seconds', 0.0) / 60:.1f} min · "
        f"**Kosten:** $0 · **transiente Fehler:** {state.get('transient_errors', 0)}"
    )
    add("")

    # --- Gesamtuebersicht je Konzept -------------------------------------
    add("## Abdeckung je Konzept")
    add("")
    add(
        "Gezaehlt werden **zusammenhaengende** Geschaeftsjahre, die am juengsten "
        "vorhandenen Jahr enden. Bezugsgroesse ist `US-Titel mit companyfacts "
        f"gemessen` ({len(ok)})."
    )
    add("")
    add("| Konzept | >=10 Jahre | >=7 Jahre | <7 Jahre | kein Konzept |")
    add("|---|---|---|---|---|")
    for key, (label, _) in CONCEPTS.items():
        counts: Counter[str] = Counter(
            _bucket(r["concepts"][key]["contiguous"]) for r in ok.values()
        )
        add(
            f"| {label} | {counts['>=10']} ({_pct(counts['>=10'], len(ok))}) "
            f"| {counts['>=7']} ({_pct(counts['>=7'], len(ok))}) "
            f"| {counts['<7']} ({_pct(counts['<7'], len(ok))}) "
            f"| {counts['kein Konzept']} ({_pct(counts['kein Konzept'], len(ok))}) |"
        )
    add("")
    add(
        "Die Spalten sind disjunkt: `>=7` meint sieben bis neun Jahre, nicht "
        "\"mindestens sieben\"."
    )
    add("")

    # --- die eigentliche Huerde: alle Kennzahlen gleichzeitig -------------
    def ext(record: dict[str, Any]) -> dict[str, Any]:
        return record.get("concepts_extended", record["concepts"])

    needed = ("revenue", "operating_income", "net_income", "equity")
    both10 = sum(
        1
        for r in ok.values()
        if all(r["concepts"][k]["contiguous"] >= 10 for k in needed)
    )
    both7 = sum(
        1 for r in ok.values() if all(r["concepts"][k]["contiguous"] >= 7 for k in needed)
    )
    ext10 = sum(
        1 for r in ok.values() if all(ext(r)[k]["contiguous"] >= 10 for k in needed)
    )
    ext7 = sum(
        1 for r in ok.values() if all(ext(r)[k]["contiguous"] >= 7 for k in needed)
    )
    add("## Was die Stetigkeits-Dimension wirklich braucht")
    add("")
    add(
        "Die drei vorgeschlagenen Kriterien (Jahre mit Umsatzwachstum, Schwankung "
        "der operativen Marge, schlechteste Eigenkapitalrendite) brauchen **vier "
        "Reihen gleichzeitig**: Umsatz, operatives Ergebnis, Nettogewinn, "
        "Eigenkapital. Eine Reihe allein genuegt nicht."
    )
    add("")
    add("| Anspruch | Konzeptliste | US-Titel | Anteil gemessene | Anteil aller US-Titel |")
    add("|---|---|---|---|---|")
    add(
        f"| alle vier Reihen >=10 Jahre | Auftrag | {both10} | {_pct(both10, len(ok))} "
        f"| {_pct(both10, len(us_tickers))} |"
    )
    add(
        f"| alle vier Reihen >=10 Jahre | erweitert | {ext10} | {_pct(ext10, len(ok))} "
        f"| {_pct(ext10, len(us_tickers))} |"
    )
    add(
        f"| alle vier Reihen >=7 Jahre | Auftrag | {both7} | {_pct(both7, len(ok))} "
        f"| {_pct(both7, len(us_tickers))} |"
    )
    add(
        f"| alle vier Reihen >=7 Jahre | erweitert | {ext7} | {_pct(ext7, len(ok))} "
        f"| {_pct(ext7, len(us_tickers))} |"
    )
    add("")
    add(
        "`Auftrag` ist die Konzeptliste aus der Aufgabenstellung. `erweitert` "
        "nimmt je Konzept zusaetzliche us-gaap-Tags dazu, die dieselbe Groesse "
        "unter anderem Namen fuehren (`ALTERNATIVES` im Skript) — die Differenz "
        "ist der Preis der Namensluecke, nicht der Datenluecke."
    )
    add("")
    add("### Was die erweiterte Liste je Konzept bringt")
    add("")
    add("| Konzept | >=10 Jahre (Auftrag) | >=10 Jahre (erweitert) | Differenz |")
    add("|---|---|---|---|")
    for key, (label, _) in CONCEPTS.items():
        a = sum(1 for r in ok.values() if r["concepts"][key]["contiguous"] >= 10)
        b = sum(1 for r in ok.values() if ext(r)[key]["contiguous"] >= 10)
        add(f"| {label} | {a} ({_pct(a, len(ok))}) | {b} ({_pct(b, len(ok))}) | +{b - a} |")
    add("")
    add("Die Tags, die den Unterschied machen, nach Haeufigkeit:")
    add("")
    for key, (label, _) in CONCEPTS.items():
        helpers: Counter[str] = Counter()
        for r in ok.values():
            if r["concepts"][key]["contiguous"] >= 10:
                continue
            used = (ext(r)[key].get("concept") or "").split("+")
            for tag in used:
                if tag in ALTERNATIVES[key]:
                    helpers[tag] += 1
        if helpers:
            listed = ", ".join(f"`{t}` ({n})" for t, n in helpers.most_common(5))
            add(f"- **{label}:** {listed}")
    add("")

    # --- Perioden- vs. fy-Schluessel -------------------------------------
    with_rev = [
        r for r in ok.values() if r["concepts"]["revenue"]["concept"] is not None
    ]
    if with_rev:
        period_mean = sum(
            r["concepts"]["revenue"]["contiguous"] for r in with_rev
        ) / len(with_rev)
        naive_mean = sum(
            r["concepts"]["revenue"]["naive_fy_count"] for r in with_rev
        ) / len(with_rev)
        naive10 = sum(
            1 for r in with_rev if r["concepts"]["revenue"]["naive_fy_count"] >= 10
        )
        period10 = sum(1 for r in with_rev if r["concepts"]["revenue"]["contiguous"] >= 10)
        add("## Perioden- gegen fy-Schluessel (Umsatz)")
        add("")
        add(
            "Der Auftrag sah Deduplizierung ueber `fy` vor. In companyfacts benennt "
            "`fy` aber das Geschaeftsjahr des **meldenden Filings**: der FY2025-10-K "
            "traegt FY2023 und FY2024 ebenfalls mit `fy=2025, fp=FY`. Beide Lesarten "
            "nebeneinander, damit die Abweichung pruefbar ist:"
        )
        add("")
        add("| Lesart | Mittelwert Jahre | Titel mit >=10 |")
        add("|---|---|---|")
        add(
            f"| Perioden-Schluessel (verwendet) | {period_mean:.1f} "
            f"| {period10} ({_pct(period10, len(with_rev))}) |"
        )
        add(
            f"| `fy`-Schluessel (verworfen) | {naive_mean:.1f} "
            f"| {naive10} ({_pct(naive10, len(with_rev))}) |"
        )
        add("")

    # --- Gegenprobe an der Septemberliste ---------------------------------
    if crosshits:
        add("## Gegenprobe: die 24 Crosshits des Septemberlaufs")
        add("")
        add(
            "Der eigentliche Abnahmetest. `PT` markiert die acht von Hand "
            "benannten Preisnehmer. `Jahre` ist die kuerzeste der vier "
            "benoetigten Reihen (erweiterte Konzeptliste) — sie bestimmt, ob ein "
            "Titel eine echte Stetigkeit bekommt oder nach dem Vorschlag "
            "\"neutral, nicht bestrafen\" durchgereicht wird."
        )
        add("")
        add("| Ticker | PT | Jahre (Auftragsliste) | Jahre (erweitert) | Folge |")
        add("|---|---|---|---|---|")
        scoreable: list[str] = []
        neutral: list[str] = []
        for ticker in crosshits:
            record = results.get(ticker)
            mark = "**PT**" if ticker in PRICE_TAKERS else ""
            if not record or record.get("status") != "ok":
                add(f"| {ticker} | {mark} | — | — | kein SEC-Registrant → neutral |")
                neutral.append(ticker)
                continue
            spec = min(record["concepts"][k]["contiguous"] for k in needed)
            extended = min(ext(record)[k]["contiguous"] for k in needed)
            if extended >= 10:
                scoreable.append(ticker)
                folge = "bewertbar"
            else:
                neutral.append(ticker)
                folge = "zu kurz → neutral"
            add(f"| {ticker} | {mark} | {spec} | {extended} | {folge} |")
        add("")
        pt_neutral = [t for t in neutral if t in PRICE_TAKERS]
        add(
            f"**{len(scoreable)} von {len(crosshits)}** Titeln bekaemen eine echte "
            f"Stetigkeit. Von den acht Preisnehmern blieben **{len(pt_neutral)} "
            f"unbewertet**: {', '.join(f'`{t}`' for t in pt_neutral)}."
        )
        add("")

    # --- Primaer-Evidenz --------------------------------------------------
    add("## Primaer-Evidenz (Stichprobe)")
    add("")
    add(
        "Ein Aggregat beweist nicht, dass der Mechanismus greift. Drei Reihen im "
        "Klartext, gegen die Filings pruefbar:"
    )
    add("")
    for ticker in EVIDENCE_TICKERS:
        record = results.get(ticker)
        if not record or record.get("status") != "ok":
            add(f"- **{ticker}**: {record.get('status') if record else 'nicht gemessen'}")
            continue
        cov = record["concepts"]["revenue"]
        add(f"- **{ticker}** ({record.get('entity', '')}) — Konzept `{cov['concept']}`, ")
        if cov["years"]:
            pairs = ", ".join(
                f"{y}: {v / 1e9:.2f} Mrd"
                for y, v in zip(cov["years"], cov["values"])
            )
            add(
                f"  {cov['contiguous']} zusammenhaengende Jahre, "
                f"{cov['restatements']} Restatement(s), Einheit {cov['unit']}"
            )
            add(f"  <br>{pairs}")
        else:
            tags = record.get("us_gaap_tag_hints", [])
            add(
                f"  kein Umsatzkonzept getroffen; vorhandene Tags (Auswahl): "
                f"{', '.join(tags[:12]) or 'keine'}"
            )
    add("")

    # --- Konzeptnamen-Luecken --------------------------------------------
    gaps = [
        (t, r)
        for t, r in sorted(ok.items())
        if r["concepts"]["revenue"]["concept"] is None
    ]
    add("## Titel ohne greifendes Umsatzkonzept")
    add("")
    add(
        f"{len(gaps)} Titel. Die Spalte `vorhandene us-gaap-Tags` zeigt, welcher "
        "Fallback fehlt (Banken und Versicherer melden Zinsertrag statt Umsatz)."
    )
    add("")
    if gaps:
        add("| Ticker | Name | Tags gesamt | vorhandene us-gaap-Tags (Auswahl) |")
        add("|---|---|---|---|")
        for ticker, record in gaps:
            hints = record.get("us_gaap_tag_hints", [])[:8]
            add(
                f"| {ticker} | {record.get('entity', '')[:40]} "
                f"| {record.get('us_gaap_tag_count', 0)} "
                f"| {', '.join(f'`{h}`' for h in hints) or '—'} |"
            )
        add("")

    if no_cik:
        add("## US-Titel ohne CIK in `company_tickers.json`")
        add("")
        add(", ".join(f"`{t}`" for t in no_cik))
        add("")
    if no_facts:
        add("## US-Titel mit CIK, aber ohne companyfacts")
        add("")
        add(", ".join(f"`{t}`" for t in no_facts))
        add("")

    add("## Nicht-SEC-Titel im Universum")
    add("")
    add(
        f"{len(non_us_tickers)} der {len(us_tickers) + len(non_us_tickers)} gescorten "
        f"Titel ({_pct(len(non_us_tickers), len(us_tickers) + len(non_us_tickers))}) "
        "tragen ein Boersensuffix und sind keine SEC-Registranten — sie kaemen "
        "ueber EDGAR ohnehin nicht."
    )
    add("")

    # --- Titeltabelle ------------------------------------------------------
    add("## Abdeckung je Titel")
    add("")
    add(
        "Zusammenhaengende Geschaeftsjahre je Konzept. `R` = Restatements auf der "
        "Umsatzreihe (Perioden mit mehr als einem gemeldeten Wert)."
    )
    add("")
    add("| Ticker | Umsatz | Op. Ergebnis | Nettogewinn | Eigenkapital | Vermoegen | R | Umsatzkonzept |")
    add("|---|---|---|---|---|---|---|---|")
    for ticker in sorted(ok):
        c = ok[ticker]["concepts"]
        add(
            f"| {ticker} | {c['revenue']['contiguous']} "
            f"| {c['operating_income']['contiguous']} "
            f"| {c['net_income']['contiguous']} "
            f"| {c['equity']['contiguous']} "
            f"| {c['assets']['contiguous']} "
            f"| {c['revenue']['restatements']} "
            f"| {c['revenue']['concept'] or '—'} |"
        )
    add("")

    # --- mechanisches Verdikt ---------------------------------------------
    add("## Verdikt (mechanisch)")
    add("")
    bar = len(us_tickers) / 2
    add(
        f"Schwelle laut Auftrag: >=10 Jahre bei klar ueber der Haelfte der US-Titel "
        f"(> {bar:.0f} von {len(us_tickers)})."
    )
    add("")
    for label, value in (("Auftrags-Konzeptliste", both10), ("erweiterte Liste", ext10)):
        verdict = "REICHT" if value > bar else "REICHT NICHT"
        add(
            f"- {label}: **{value}** Titel mit allen vier Reihen >=10 Jahre "
            f"({_pct(value, len(us_tickers))} aller US-Titel) → **{verdict}**"
        )
    add("")
    add(
        "Diese Zeile ist arithmetisch, nicht abschliessend. Die Bewertung steht "
        "darunter."
    )
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", default=DEFAULT_MONTH, help="Monatslauf als Basis")
    parser.add_argument(
        "--universe",
        action="store_true",
        help="statt der gescorten Titel das volle data/universe.json messen",
    )
    parser.add_argument("--limit", type=int, default=0, help="nur die ersten N US-Titel")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="nichts abrufen, nur den Bericht aus dem Zwischenstand neu rendern",
    )
    args = parser.parse_args()

    crosshits: list[str] = []
    if args.universe:
        tickers = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
        basis_label = f"data/universe.json ({len(tickers)} Titel)"
    else:
        crosshits = parse_crosshits_tickers(
            (
                REPO_ROOT / "output" / "Universum" / f"{args.month}-Crosshits.md"
            ).read_text(encoding="utf-8")
        )
        tickers = scored_tickers(args.month)
        basis_label = (
            f"gescorte Titel des Laufs {args.month} ({len(tickers)}), rekonstruiert "
            f"aus `{args.month}-dropouts.csv` + `{args.month}-Crosshits.md`, "
            "gegen `funnel_summary.json` geprueft"
        )

    us = [t for t in tickers if is_us_ticker(t)]
    non_us = [t for t in tickers if not is_us_ticker(t)]
    if args.limit:
        us = us[: args.limit]
        basis_label += (
            f" — **TEILLAUF, nur die ersten {args.limit} US-Titel**, "
            "keine belastbare Quote"
        )

    state_path = Path(args.state)
    if args.report_only:
        state = load_state(state_path)
        if not state:
            print(f"FEHLER: kein Zwischenstand unter {state_path}")
            return 2
    else:
        if not settings.edgar_user_agent:
            print("FEHLER: FISHERSCREEN_EDGAR_USER_AGENT ist nicht gesetzt")
            return 2
        edgar = EdgarClientImpl(
            user_agent=settings.edgar_user_agent,
            max_requests_per_second=settings.edgar_max_requests_per_second,
        )
        state = run_probe(us, edgar, state_path)

    report = render_report(
        state,
        month=args.month,
        us_tickers=us,
        non_us_tickers=non_us,
        basis_label=basis_label,
        crosshits=crosshits,
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    existing = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    report_path.write_text(preserve_handwritten(report, existing), encoding="utf-8")
    print(f"Bericht geschrieben: {report_path}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
