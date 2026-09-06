r"""Messlauf: wie alt ist das juengste Jahresformular je Titel, der heute ein
volles Dossier bekommt?

Beantwortet die Frage, die VOR dem Aktualitaetsschnitt in `detect_annual_form`
steht (ticket 2026-09-04-detect-annual-form-has-no-recency-cutoff): welches
Fenster ist richtig? 18-24 Monate ist ein Vorschlag, kein Fakt. Zu eng, und ein
verspaeteter Filer faellt heraus; zu weit, und Deregistrierte bleiben drin.

Das Ticket verlangt ausdruecklich, das Fenster GEGEN DEN BESTAND zu messen statt
zu schaetzen. Der Bestand sind drei Quellen:

  cache/eu_sec_source_census_v3.json   Buckets resolved_20f / resolved_10k (60)
  data/adr_table.json                  die positiven Override-Zeilen (7)
  output/Watchlist/*.md                jeder Ticker, fuer den je ein Dossier entstand

Die ersten beiden tragen die CIK bereits; fuer den Rest wird sie ueber die
SEC-Tickermap aufgeloest. Pro CIK genau EIN submissions.json-Abruf.

Der Bericht zeigt bewusst die volle Verteilung und nennt die Verlierer jedes
Kandidatenfensters BEIM NAMEN. Ein Count allein beweist nicht, dass der
Mechanismus greift -- die Abnahmefrage lautet: ist unter den Verlierern ein
Titel, der TATSAECHLICH noch einreicht?

Resumierbar: Ergebnisse werden nach jedem Titel fortgeschrieben, ein erneuter
Aufruf ueberspringt bereits gemessene Titel.

Aufruf (cmd.exe):
  set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
  uv run python scripts\measure_annual_form_recency.py
  uv run python scripts\measure_annual_form_recency.py --report-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from app.config import settings
from app.deepdive.adr_table import load_adr_table
from app.errors import DataSourceError
from app.services.edgar_client import EdgarClientImpl

REPO_ROOT = Path(__file__).resolve().parents[1]
CENSUS = REPO_ROOT / "cache" / "eu_sec_source_census_v3.json"
WATCHLIST = REPO_ROOT / "output" / "Watchlist"
DEFAULT_OUT = REPO_ROOT / "cache" / "annual_form_recency.json"

ANNUAL_FORMS = ("10-K", "20-F")

# Form 15 ist die Bescheinigung ueber die BEENDIGUNG der Registrierung
# (15-12B/15-12G fuer US-Registranten, 15F-12B/15F-12G fuer Foreign Private
# Issuers). Sie ist der einzige harte Beleg dafuer, dass ein Emittent nicht
# bloss spaet dran ist, sondern die Berichtspflicht aufgegeben hat -- und damit
# das objektive Signal, an dem die Abnahmefrage dieses Messlaufs haengt, statt
# an einer Einschaetzung.
DEREGISTRATION_PREFIX = "15"

# Kandidatenfenster in Monaten. 18 ist die untere Grenze, die sich noch
# begruenden laesst: ein 20-F ist bis zu vier Monate nach Geschaeftsjahresende
# faellig, ein verspaeteter Filer kommt also legitim auf ~16 Monate Abstand zum
# Vorjahresformular. Alles darunter ist begruendungspflichtig.
WINDOWS_MONTHS = (12, 18, 24, 30, 36)

# Wie im uebrigen Repo (has_restatement, has_going_concern): Monate werden mit
# 30 Tagen gerechnet, damit das Fenster eine ganzzahlige Tagesgrenze hat.
DAYS_PER_MONTH = 30


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        print(f"WARNUNG: {path} unlesbar -- beginne neu")
        return {}


def save_results(path: Path, results: dict[str, Any]) -> None:
    """Atomar schreiben, aber mit Nachsicht gegenueber dem Virenscanner.

    WatchGuard EPDR haelt eine frisch geschriebene Datei gelegentlich kurz
    offen, waehrend es sie scannt; `os.replace` scheitert dann mit WinError 5.
    Das ist eine Eigenschaft der Maschine, kein Fehler der Messung -- also kurz
    erneut versuchen statt den Lauf zu verlieren."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.3)


def watchlist_tickers() -> list[str]:
    """Ticker, fuer die je ein Dossier entstand. Dateiname ist <TICKER>_<datum>.md;
    OnePager-Artefakte tragen einen abweichenden Mittelteil, das fuehrende
    Segment vor dem ersten '_' ist aber auch dort der Ticker."""
    if not WATCHLIST.is_dir():
        return []
    return sorted({p.name.split("_", 1)[0] for p in WATCHLIST.glob("*.md")})


def build_corpus(edgar: EdgarClientImpl) -> dict[str, dict[str, str]]:
    """ticker -> {cik, source, claimed_form}.

    Ticker ohne aufloesbare CIK werden mit cik='' aufgenommen und im Bericht
    getrennt ausgewiesen -- sie sind kein Messwert, aber auch kein stiller
    Ausfall."""
    corpus: dict[str, dict[str, str]] = {}

    for ticker, entry in load_json(CENSUS).items():
        if entry.get("bucket") in ("resolved_10k", "resolved_20f"):
            corpus[ticker] = {
                "cik": entry["cik"],
                "source": "census_v3",
                "claimed_form": entry.get("form_type", ""),
            }

    for ticker, entry in load_adr_table().items():
        if "no_sec_source_reason" in entry:
            continue
        corpus[ticker] = {
            "cik": entry["cik"],
            "source": "adr_table",
            "claimed_form": entry["form_type"],
        }

    for ticker in watchlist_tickers():
        if ticker in corpus:
            continue
        cik = edgar.get_cik(ticker)
        corpus[ticker] = {
            "cik": cik.zfill(10) if cik else "",
            "source": "watchlist",
            "claimed_form": "",
        }

    return corpus


def measure(edgar: EdgarClientImpl, cik: str) -> dict[str, Any]:
    """Juengstes 10-K/20-F unter dieser CIK.

    Kein oeffentlicher Accessor liefert den rohen Submissions-Index; fuer eine
    einmalige Messung die Protocol-Flaeche zu erweitern waere die groessere
    Aenderung, deshalb greift dieses Diagnose-Skript direkt auf `_get` zu."""
    padded = cik.zfill(10)
    data = edgar._get(f"{edgar._SEC_BASE}/submissions/CIK{padded}.json")
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    if not dates:
        return {"status": "no_filing_dates", "filings_in_window": len(forms)}

    hits = [(d, f) for f, d in zip(forms, dates) if f in ANNUAL_FORMS and d]
    newest_any_date, newest_any_form = max(
        (d, f) for f, d in zip(forms, dates) if d
    )
    form15 = sorted(
        (d, f)
        for f, d in zip(forms, dates)
        if d and f.startswith(DEREGISTRATION_PREFIX)
    )
    common = {
        "filings_in_window": len(forms),
        "oldest_recent_filing": min(dates),
        "newest_filing_any": newest_any_date,
        "newest_filing_any_form": newest_any_form,
        "form15": [f"{d} {f}" for d, f in form15],
    }
    if not hits:
        return {"status": "no_annual_form", **common}
    newest_date, newest_form = max(hits)
    return {
        "status": "ok",
        "newest_form": newest_form,
        "newest_filing_date": newest_date,
        "annual_forms_in_window": len(hits),
        **common,
    }


def age_days(iso_date: str, today: date) -> int:
    return (today - date.fromisoformat(iso_date)).days


def report(corpus: dict[str, dict[str, str]], results: dict[str, Any]) -> None:
    today = date.today()
    measured: list[tuple[int, str, dict[str, Any]]] = []
    unresolved: list[str] = []
    anomalies: list[tuple[str, str]] = []

    for ticker, meta in sorted(corpus.items()):
        if not meta["cik"]:
            unresolved.append(ticker)
            continue
        res = results.get(ticker)
        if res is None:
            anomalies.append((ticker, "(nicht gemessen)"))
        elif res["status"] != "ok":
            anomalies.append((ticker, res["status"]))
        else:
            measured.append((age_days(res["newest_filing_date"], today), ticker, res))

    measured.sort(reverse=True)

    print(
        f"\n=== Verteilung: Alter des juengsten Jahresformulars "
        f"({len(measured)} Titel) ==="
    )
    print(f"    Stichtag {today.isoformat()}\n")
    for age, ticker, res in measured:
        flag = "  <-- ueber 18 Monate" if age > 18 * DAYS_PER_MONTH else ""
        print(
            f"  {ticker:<12} {res['newest_form']:<5} {res['newest_filing_date']}  "
            f"{age:>5} Tage ({age / 30.44:>5.1f} Monate){flag}"
        )

    if anomalies:
        print(f"\n=== Kein Messwert ({len(anomalies)}) ===")
        for ticker, why in anomalies:
            print(f"  {ticker:<12} {why}")
    if unresolved:
        print(f"\n=== Keine CIK aufloesbar ({len(unresolved)}) ===")
        print("  " + ", ".join(unresolved))

    print("\n=== Beweislage je Kandidat ===")
    print("  Jeder Titel, dessen juengstes Jahresformular aelter ist als das")
    print("  engste Kandidatenfenster. Ein Form 15 (15-12B/15F-12B ...) ist die")
    print("  Bescheinigung ueber die Beendigung der Registrierung -- wo es steht,")
    print("  ist 'reicht nicht mehr ein' belegt und nicht vermutet.\n")
    narrowest = min(WINDOWS_MONTHS) * DAYS_PER_MONTH
    for age, ticker, res in measured:
        if age <= narrowest:
            continue
        f15 = ", ".join(res.get("form15", [])) or "KEIN Form 15"
        print(
            f"  {ticker:<12} juengstes {res['newest_form']} "
            f"{res['newest_filing_date']} ({age / 30.44:.1f} Monate)"
        )
        print(
            f"               juengstes Filing ueberhaupt: "
            f"{res.get('newest_filing_any')} {res.get('newest_filing_any_form')}"
        )
        print(f"               Abmeldung: {f15}")

    print("\n=== Wirkung der Kandidatenfenster ===")
    print("  Ein Fenster ist nur dann richtig, wenn unter seinen Verlierern KEIN")
    print("  Titel ist, der tatsaechlich noch einreicht. Namen deshalb pruefen,")
    print("  nicht nur die Anzahl lesen.\n")
    for months in WINDOWS_MONTHS:
        cutoff = months * DAYS_PER_MONTH
        losers = [(a, t) for a, t, _ in measured if a > cutoff]
        print(
            f"  {months:>2} Monate ({cutoff} Tage): "
            f"{len(losers):>3} von {len(measured)} fallen heraus"
        )
        for age, ticker in losers:
            print(f"        {ticker:<12} {age / 30.44:>5.1f} Monate")
        if not losers:
            print("        (keiner)")
    print()


def run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    results = load_json(out)

    if not settings.edgar_user_agent:
        print("FEHLER: FISHERSCREEN_EDGAR_USER_AGENT ist nicht gesetzt.")
        return 2
    edgar = EdgarClientImpl(
        user_agent=settings.edgar_user_agent,
        max_requests_per_second=settings.edgar_max_requests_per_second,
    )

    corpus = build_corpus(edgar)
    print(
        f"Pruefbestand: {len(corpus)} Titel "
        f"(Zensus + Override-Tabelle + Watchlist-Dossiers)"
    )

    if not args.report_only:
        todo = [t for t, m in sorted(corpus.items()) if m["cik"] and t not in results]
        print(f"Zu messen: {len(todo)} (bereits im Cache: {len(results)})\n")
        for n, ticker in enumerate(todo, 1):
            cik = corpus[ticker]["cik"]
            try:
                res = measure(edgar, cik)
            except DataSourceError as exc:
                # Ein API-Fehler ist eine Aussage ueber die API, nie ueber den
                # Titel. Nicht buchen, damit der naechste Lauf es erneut versucht.
                print(f"[{n:>3}/{len(todo)}] {ticker:<12} FEHLER: {exc}", flush=True)
                continue
            res["cik"] = cik
            res["source"] = corpus[ticker]["source"]
            results[ticker] = res
            save_results(out, results)
            shown = res.get("newest_filing_date", res["status"])
            print(f"[{n:>3}/{len(todo)}] {ticker:<12} {shown}", flush=True)

    report(corpus, results)
    print(f"Rohdaten: {out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=str(DEFAULT_OUT), help="Ergebnis-JSON")
    p.add_argument(
        "--report-only",
        action="store_true",
        help="nichts abrufen, nur den vorhandenen Messstand auswerten",
    )
    return run(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
