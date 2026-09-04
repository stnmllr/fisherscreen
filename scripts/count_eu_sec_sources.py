r"""Zaehllauf: wie viele der dotted EU-Titel im Universum haben ueberhaupt eine
SEC-Quelle fuer Tool-B-Hard-Scuttlebutt?

Beantwortet die Frage, die vor jeder Entscheidung ueber eine EU-Native-Quellenschicht
steht: schmerzt die Luecke? Klassifiziert jeden Titel in einen von sechs Toepfen,
statt beim ersten Fehlschlag abzubrechen.

  resolved_10k / resolved_20f   Tool B kann ein volles Dossier bauen
  no_us_line                    keine US-Notierung (reines EU-Listing)
  not_sec_registrant            US-Linie vorhanden, aber kein CIK (OTC/unsponsored)
  no_annual_form                CIK vorhanden, aber weder 10-K noch 20-F
  unverifiable_identity         OpenFIGI/yfinance liefern keine verifizierbare Identitaet
  transient_error               API-Fehler -- KEIN Befund ueber den Emittenten

Der letzte Topf ist bewusst getrennt: ein DataSourceError ist eine Aussage ueber die
API, nie ueber den Titel. Er wird nicht gecacht und beim naechsten Lauf erneut versucht.

Resumierbar: Ergebnisse werden nach jedem Ticker fortgeschrieben, ein erneuter Aufruf
ueberspringt bereits klassifizierte Titel (ausser transient_error). Zusaetzlich waermt
der Lauf den echten ADR-Cache, kuenftige Deep Dives sind fuer diese Titel also sofort.

Modus 2 (--analyse-no-us-line) beantwortet die Frage des _same_issuer-Tickets: unter
den no_us_line-Titeln -- bei wie vielen hat OpenFIGI US-Linien geliefert, die
_same_issuer alle verworfen hat? Nur die sind echte False Negatives; ein Titel ohne
jede US-Linie ist ein sauberes pure-EU-Listing.

Aufruf (cmd.exe):
  set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
  uv run python scripts\count_eu_sec_sources.py --limit 20
  uv run python scripts\count_eu_sec_sources.py
  uv run python scripts\count_eu_sec_sources.py --analyse-no-us-line
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.deepdive.eu_adr_resolution import (
    US_EXCH,
    _same_issuer,
    find_home_identity,
    issuer_name,
    norm_issuer,
    resolve_eu_adr,
)
from app.errors import DataSourceError, DeepDiveError
from app.services.edgar_client import EdgarClientImpl
from app.services.openfigi_client import OpenFIGIClientImpl
from app.services.yfinance_client import YFinanceClientImpl

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = REPO_ROOT / "data" / "universe.json"
ADR_CACHE = REPO_ROOT / "cache" / "adr_resolved.json"
DEFAULT_OUT = REPO_ROOT / "cache" / "eu_sec_source_census.json"

# transient_error ist absichtlich NICHT terminal: beim naechsten Lauf erneut versuchen.
TERMINAL = {
    "resolved_10k",
    "resolved_20f",
    "no_us_line",
    "not_sec_registrant",
    "no_annual_form",
    "unverifiable_identity",
}


def load_eu_tickers(suffix: str | None) -> list[str]:
    raw = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    entries = raw.get("tickers") if isinstance(raw, dict) else raw
    if entries is None:
        entries = list(raw)
    tickers = [t if isinstance(t, str) else t.get("ticker") for t in entries]
    dotted = [t for t in tickers if t and "." in t]
    if suffix:
        dotted = [t for t in dotted if t.rsplit(".", 1)[1].upper() == suffix.upper()]
    return sorted(dotted)


def load_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        print(f"WARNUNG: {path} unlesbar -- beginne neu")
        return {}


def save_results(path: Path, results: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def classify(ticker: str, *, openfigi, edgar, yfinance) -> dict[str, Any]:
    """Ein Ticker -> ein Topf. Nur die beiden erwarteten Fehlerklassen werden
    gefangen und klassifiziert; alles andere propagiert (fail loud)."""
    try:
        resolved = resolve_eu_adr(
            ticker,
            openfigi=openfigi,
            edgar=edgar,
            yfinance=yfinance,
            cache_path=ADR_CACHE,
            ttl_days=settings.adr_cache_ttl_days,
            negative_ttl_days=settings.adr_negative_cache_ttl_days,
        )
    except DeepDiveError as exc:
        return {"bucket": "unverifiable_identity", "detail": str(exc)[:300]}
    except DataSourceError as exc:
        return {"bucket": "transient_error", "detail": f"{type(exc).__name__}: {exc}"[:300]}

    if resolved.has_filing_source:
        bucket = "resolved_10k" if resolved.form_type == "10-K" else "resolved_20f"
        return {
            "bucket": bucket,
            "adr_ticker": resolved.adr_ticker,
            "cik": resolved.cik,
            "form_type": resolved.form_type,
        }
    return {
        "bucket": resolved.no_sec_source_reason,
        "detail": (resolved.no_sec_source_note or "")[:300],
    }


def run_census(args: argparse.Namespace) -> int:
    tickers = load_eu_tickers(args.suffix)
    if args.limit:
        tickers = tickers[: args.limit]
    out = Path(args.out)
    results = load_results(out)

    todo = [t for t in tickers if results.get(t, {}).get("bucket") not in TERMINAL]
    print(f"{len(tickers)} EU-Titel im Scope, {len(todo)} offen "
          f"({len(tickers) - len(todo)} bereits klassifiziert)")
    if not todo:
        summarise(results, tickers)
        return 0

    openfigi = OpenFIGIClientImpl(api_key=settings.openfigi_api_key)
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    yfinance = YFinanceClientImpl()

    started = time.time()
    for n, ticker in enumerate(todo, 1):
        outcome = classify(ticker, openfigi=openfigi, edgar=edgar, yfinance=yfinance)
        results[ticker] = outcome
        save_results(out, results)
        elapsed = time.time() - started
        rate = elapsed / n
        print(f"[{n:>4}/{len(todo)}] {ticker:<12} {outcome['bucket']:<22} "
              f"({elapsed / 60:.1f} min, Rest ~{rate * (len(todo) - n) / 60:.0f} min)",
              flush=True)

    summarise(results, tickers)
    return 0


def summarise(results: dict[str, Any], tickers: list[str]) -> None:
    counts = collections.Counter(
        results.get(t, {}).get("bucket", "(nicht gelaufen)") for t in tickers
    )
    total = len(tickers)
    print(f"\n=== Zaehlung ueber {total} EU-Titel ===")
    for bucket, n in counts.most_common():
        print(f"  {bucket:<24} {n:>5}  {n / total:>6.1%}")
    resolved = counts["resolved_10k"] + counts["resolved_20f"]
    print(f"\n  MIT SEC-Quelle           {resolved:>5}  {resolved / total:>6.1%}")
    print(f"  OHNE (quant-only)        {total - resolved - counts['transient_error']:>5}")
    by_suffix: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for t in tickers:
        by_suffix[t.rsplit(".", 1)[1].upper()][
            results.get(t, {}).get("bucket", "(nicht gelaufen)")
        ] += 1
    print("\n=== Nach Boerse (Anteil mit SEC-Quelle) ===")
    for suffix, c in sorted(by_suffix.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        ok = c["resolved_10k"] + c["resolved_20f"]
        print(f"  .{suffix:<3} {n:>4} Titel   mit SEC-Quelle: {ok:>3}  {ok / n:>6.1%}")


def analyse_no_us_line(args: argparse.Namespace) -> int:
    """Zweiter Pass fuer das _same_issuer-Ticket. Nur die no_us_line-Titel: ein
    False Negative kann sich NUR so aeussern (waere ein Geschwister akzeptiert
    worden, laege ein anderer Topf vor)."""
    results = load_results(Path(args.out))
    candidates = [t for t, r in results.items() if r.get("bucket") == "no_us_line"]
    print(f"{len(candidates)} Titel im Topf no_us_line -- pruefe auf verworfene US-Linien\n")
    if not candidates:
        return 0

    openfigi = OpenFIGIClientImpl(api_key=settings.openfigi_api_key)
    yfinance = YFinanceClientImpl()
    findings: list[dict[str, Any]] = []

    for n, ticker in enumerate(candidates, 1):
        try:
            info = yfinance.get_ticker_info(ticker)
            ref = info.get("longName") or info.get("shortName") or ""
            ident = find_home_identity(ticker, norm_issuer(ref), openfigi=openfigi)
            name = ident.get("name", "")
            ident_norm = norm_issuer(issuer_name(name))
            lines = openfigi.search_issuer(name)
        except (DeepDiveError, DataSourceError) as exc:
            print(f"[{n}/{len(candidates)}] {ticker:<12} uebersprungen: {exc}")
            continue

        us_lines = [ln for ln in lines if (ln.get("exchCode") or "").strip() in US_EXCH]
        rejected = [
            ln for ln in us_lines if not _same_issuer(ln.get("name", ""), ident_norm)
        ]
        verdict = "PURE-EU" if not us_lines else "FALSE-NEGATIVE-KANDIDAT"
        print(f"[{n}/{len(candidates)}] {ticker:<12} US-Linien={len(us_lines):>3} "
              f"davon verworfen={len(rejected):>3}  {verdict}", flush=True)
        if us_lines:
            findings.append({
                "ticker": ticker,
                "identity": name,
                "ident_norm": ident_norm,
                "us_lines_total": len(us_lines),
                "rejected": [
                    {"ticker": ln.get("ticker"), "name": ln.get("name"),
                     "securityType2": ln.get("securityType2")}
                    for ln in rejected
                ][:5],
            })

    print(f"\n=== Verdikt fuer das _same_issuer-Ticket ===")
    print(f"  no_us_line gesamt:                {len(candidates)}")
    print(f"  davon ECHTE False-Negative-Kandidaten (US-Linien vorhanden, alle "
          f"verworfen): {len(findings)}")
    if not findings:
        print("\n  -> Kein einziger Fall. Das Ticket kann auf 'kein Matcher noetig'")
        print("     heruntergestuft werden; die Luecke ist real, aber unbesetzt.")
    else:
        print("\n  Betroffene Titel:")
        for f in findings:
            print(f"    {f['ticker']:<12} {f['identity']}")
        out = Path(args.out).with_name("same_issuer_false_negatives.json")
        out.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Details: {out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=0, help="nur die ersten N Titel")
    p.add_argument("--suffix", default=None, help="nur eine Boerse, z.B. L")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="Ergebnis-JSON")
    p.add_argument("--analyse-no-us-line", action="store_true",
                   help="zweiter Pass fuer das _same_issuer-Ticket")
    args = p.parse_args()
    if args.analyse_no_us_line:
        return analyse_no_us_line(args)
    return run_census(args)


if __name__ == "__main__":
    sys.exit(main())
