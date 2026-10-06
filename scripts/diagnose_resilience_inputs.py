"""Diagnose: kann eine buchkapital-unabhaengige Kennzahl debt_to_equity / ROE ersetzen?

Anlass: Referenzcheck 2026-10 -- MSFT, AAPL, KLAC, MCO, ISRG, AMAT, LRCX scheitern
ausschliesslich an resilience; MA und MTD stehen bei 0 (D/E-Red-Flag > 300 %). Ruecklauf-
starke Firmen haben winziges/negatives Buchkapital, D/E und ROE messen dort Kosmetik.

Liest NUR (kein Schreiben, $0):
  data/universe.json, output/Universum/<Monat>-dropouts.csv   Scoring-Kohorte + alte Achsen
  Firestore dev_ticker_cache                                  volles yfinance-.info je Titel

Optional `--statements-sample N`: holt fuer N zufaellige Kohorten-Titel die Jahres-
abschluesse live von yfinance (kostenlos, aber Netz), um zu messen, ob Zinsaufwand / EBIT /
Invested Capital -- die NICHT im .info stehen -- ueberhaupt verfuegbar waeren.

Varianten (nur hier im Skript, nicht im Produktivcode):
  resilience OLD   mean(P gross_margin, 100-P d/e); d/e > 300 -> 0
  resilience ND_EB mean(P gross_margin, 100-P netdebt/EBITDA); ND/EBITDA > 4 -> 0,
                   EBITDA <= 0 bei Nettoschuld -> 0, EBITDA <= 0 bei Nettocash -> n/a
  resilience ND_FCF dito mit freeCashflow; Red-Flag > 8
  profitability OLD  mean(P op_margin, P ROE); op_margin<0 oder ROE<0 -> 0
  profitability ROIC mean(P op_margin, P ROIC); ROIC = EBIT/(Debt+Equity-Cash),
                   EBIT = operatingMargins*totalRevenue, Equity = bookValue*sharesOutstanding

Aufruf:
    uv run python scripts\\diagnose_resilience_inputs.py
    uv run python scripts\\diagnose_resilience_inputs.py --statements-sample 60
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from google.cloud import firestore

from app.config import settings
from app.screener.percentiles import percentile_rank, percentile_to_score
from app.screener.sector_percentiles import MIN_SECTOR_N

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
PRE_SCORING_STAGES = {"resolution", "basis_gates", "edgar_gates"}
FOCUS = ["MA", "MTD", "MSFT", "AAPL", "KLAC", "MCO", "ISRG", "V", "AMAT", "LRCX"]
INFO_FIELDS = [
    "debtToEquity",
    "returnOnEquity",
    "totalDebt",
    "totalCash",
    "ebitda",
    "operatingMargins",
    "totalRevenue",
    "freeCashflow",
    "operatingCashflow",
    "returnOnAssets",
    "bookValue",
    "sharesOutstanding",
]
ND_EBITDA_REDFLAG = 4.0
ND_FCF_REDFLAG = 8.0
DE_REDFLAG = 300.0


def region(ticker: str) -> str:
    return "EU" if "." in ticker else "US"


def num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def load_cohort(month: str) -> tuple[list[str], dict[str, str]]:
    universe = json.loads((ROOT / "data" / "universe.json").read_text("utf-8"))
    dropped_early: set[str] = set()
    details: dict[str, str] = {}
    path = ROOT / "output" / "Universum" / f"{month}-dropouts.csv"
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["stage"] in PRE_SCORING_STAGES:
                dropped_early.add(row["ticker"])
            elif row["stage"] == "crosshits":
                details[row["ticker"]] = row["detail"]
    return [t for t in universe if t not in dropped_early], details


def derive(info: dict) -> dict:
    g = {f: num(info.get(f)) for f in INFO_FIELDS}
    d: dict = {"sector": info.get("sector"), "industry": info.get("industry")}
    d["gross_margin"] = num(info.get("grossMargins"))
    d["op_margin"] = g["operatingMargins"]
    d["roe"] = g["returnOnEquity"]
    d["de"] = g["debtToEquity"]
    debt, cash, ebitda, fcf = g["totalDebt"], g["totalCash"], g["ebitda"], g["freeCashflow"]
    nd = None
    if debt is not None or cash is not None:  # fehlendes Feld = 0 nur wenn das andere da ist
        nd = (debt or 0.0) - (cash or 0.0)
    d["net_debt"] = nd
    d["ebitda"] = ebitda
    d["fcf"] = fcf
    d["nd_ebitda"], d["nd_ebitda_flag"] = _ratio(nd, ebitda, ND_EBITDA_REDFLAG)
    d["nd_fcf"], d["nd_fcf_flag"] = _ratio(nd, fcf, ND_FCF_REDFLAG)
    ebit = None
    if g["operatingMargins"] is not None and g["totalRevenue"] is not None:
        ebit = g["operatingMargins"] * g["totalRevenue"]
    equity = None
    if g["bookValue"] is not None and g["sharesOutstanding"] is not None:
        equity = g["bookValue"] * g["sharesOutstanding"]
    d["equity"] = equity
    ic = None
    if equity is not None and (debt is not None or cash is not None):
        ic = (debt or 0.0) + equity - (cash or 0.0)
    d["invested_capital"] = ic
    d["roic"] = ebit / ic if (ebit is not None and ic is not None and ic > 0) else None
    d["roa"] = g["returnOnAssets"]
    d["_raw"] = g
    return d


def _ratio(nd, denom, redflag) -> tuple[float | None, bool]:
    """(Rangwert, Red-Flag). Nettocash -> negativer Wert (rankt am besten)."""
    if nd is None or denom is None:
        return None, False
    if denom <= 0:
        return None, nd > 0  # Nettoschuld ohne Ertragskraft = Flag; Nettocash = n/a
    r = nd / denom
    return r, r > redflag


def annotate(rows: dict[str, dict], field: str, invert: bool) -> None:
    """Sektor-relatives Perzentil wie sector_percentiles (Sektor >= MIN_SECTOR_N, sonst global)."""
    members: dict = defaultdict(list)
    for t, r in rows.items():
        members[r["sector"]].append(t)
    global_dist = [r[field] for r in rows.values() if r[field] is not None]
    for t, r in rows.items():
        v = r[field]
        if v is None:
            continue
        sec = r["sector"]
        if sec is not None and len(members[sec]) >= MIN_SECTOR_N:
            dist = [rows[m][field] for m in members[sec] if rows[m][field] is not None]
        else:
            dist = global_dist
        p = percentile_rank(v, dist)
        r.setdefault("pct", {})[field] = 100.0 - p if invert else p


def axis(r: dict, fields: tuple[str, ...]) -> int | None:
    vals = [r.get("pct", {})[f] for f in fields if f in r.get("pct", {})]
    return percentile_to_score(sum(vals) / len(vals)) if vals else None


def score(r: dict) -> dict:
    res_old = axis(r, ("gross_margin", "de")) or 3
    if r["de"] is not None and r["de"] > DE_REDFLAG:
        res_old = 0
    res_nd = axis(r, ("gross_margin", "nd_ebitda")) or 3
    if r["nd_ebitda_flag"]:
        res_nd = 0
    res_fcf = axis(r, ("gross_margin", "nd_fcf")) or 3
    if r["nd_fcf_flag"]:
        res_fcf = 0
    # ABS: Verschuldung absolut gebaendert statt Perzentil (Nettocash/<=1x = voll)
    lev = r["nd_ebitda"]
    if lev is None:
        res_abs = axis(r, ("gross_margin",)) or 3
    else:
        band = 100.0 if lev <= 1 else 75.0 if lev <= 2 else 50.0 if lev <= 3 else 25.0
        gm = r.get("pct", {}).get("gross_margin")
        res_abs = percentile_to_score((band + gm) / 2 if gm is not None else band)
    if r["nd_ebitda_flag"]:
        res_abs = 0
    # ABS2: strengere Baender; Utilities/Real Estate (reguliert/objektbesichert) ohne
    # absoluten Red-Flag, dort Band 0 statt Flag
    structural = r["sector"] in ("Utilities", "Real Estate")
    if lev is None:
        res_abs2 = axis(r, ("gross_margin",)) or 3
        if r["nd_ebitda_flag"] and not structural:
            res_abs2 = 0
    else:
        band2 = (100.0 if lev <= 0 else 85.0 if lev <= 1 else 65.0 if lev <= 2
                 else 45.0 if lev <= 3 else 25.0 if lev <= 4 else 0.0)
        gm = r.get("pct", {}).get("gross_margin")
        res_abs2 = percentile_to_score((band2 + gm) / 2 if gm is not None else band2)
        if lev > ND_EBITDA_REDFLAG and not structural:
            res_abs2 = 0
    neg = lambda v: v is not None and v < 0  # noqa: E731
    prof_old = axis(r, ("op_margin", "roe")) or 3
    if neg(r["op_margin"]) or neg(r["roe"]):
        prof_old = 0
    prof_roic = axis(r, ("op_margin", "roic")) or 3
    if neg(r["op_margin"]) or neg(r["roic"]):
        prof_roic = 0
    return {
        "res_old": res_old,
        "res_nd_ebitda": res_nd,
        "res_nd_fcf": res_fcf,
        "res_abs": res_abs,
        "res_abs2": res_abs2,
        "prof_old": prof_old,
        "prof_roic": prof_roic,
    }


def parse_detail(detail: str) -> dict[str, str]:
    return dict(p.split("=", 1) for p in detail.split() if "=" in p)


def coverage(rows: dict[str, dict]) -> None:
    keys = ["de", "roe", "net_debt", "ebitda", "fcf", "nd_ebitda", "roic", "roa", "gross_margin"]
    by_region: dict[str, list[dict]] = defaultdict(list)
    for t, r in rows.items():
        by_region[region(t)].append(r)
        if r["sector"] == "Financial Services":
            by_region["FIN"].append(r)
    print("\n## Abdeckung (Anteil mit Wert)\n")
    print("| Feld | " + " | ".join(f"{k} (n={len(v)})" for k, v in by_region.items()) + " |")
    print("|---|" + "---|" * len(by_region))
    for k in keys:
        cells = []
        for v in by_region.values():
            n = sum(1 for r in v if r[k] is not None)
            cells.append(f"{n / len(v):.1%}")
        print(f"| {k} | " + " | ".join(cells) + " |")
    # wie oft hat der Titel "n/a" bei nd_ebitda, weil EBITDA <= 0 bzw. fehlt
    for reg, v in by_region.items():
        c = Counter()
        for r in v:
            if r["ebitda"] is None:
                c["ebitda fehlt"] += 1
            elif r["ebitda"] <= 0:
                c["ebitda<=0"] += 1
            if r["de"] is not None and r["de"] < 0:
                c["d/e negativ (heute ausgeschlossen)"] += 1
            if r["de"] is not None and r["de"] > DE_REDFLAG:
                c["d/e > 300 (heute Red-Flag)"] += 1
            if r["nd_ebitda_flag"]:
                c["ND/EBITDA-Flag neu"] += 1
            if r["net_debt"] is not None and r["net_debt"] < 0:
                c["Nettocash"] += 1
        print(f"- {reg}: " + ", ".join(f"{k} {n}" for k, n in sorted(c.items())))


def statements_sample(tickers: list[str], n: int) -> None:
    from app.services.yfinance_client import YFinanceClientImpl

    yf = YFinanceClientImpl()
    rng = random.Random(20261006)
    sample = rng.sample(tickers, min(n, len(tickers)))
    want = {"Interest Expense": "inc", "EBIT": "inc", "Invested Capital": "bal"}
    hits: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    for t in sample:
        reg = region(t)
        try:
            inc, _cf, bal = yf.get_annual_statements(t)
        except Exception as exc:  # Diagnose: Fehler zaehlen, nicht abbrechen
            hits[reg]["fetch_error"] += 1
            print(f"  {t}: {exc}")
            totals[reg] += 1
            continue
        totals[reg] += 1
        for row, kind in want.items():
            frame = inc if kind == "inc" else bal
            if frame is not None and not frame.empty and row in frame.index:
                latest = frame.loc[row].dropna()
                if not latest.empty:
                    hits[reg][row] += 1
    print(f"\n## Jahresabschluss-Stichprobe live (n={len(sample)})\n")
    for reg in sorted(totals):
        parts = [f"{row} {hits[reg][row]}/{totals[reg]}" for row in want]
        if hits[reg]["fetch_error"]:
            parts.append(f"Fehler {hits[reg]['fetch_error']}")
        print(f"- {reg}: " + ", ".join(parts))


def fmt(v, kind="x") -> str:
    if v is None:
        return "n/a"
    if kind == "pct":
        return f"{v:.0%}"
    if kind == "de":
        return f"{v:.0f}%"
    return f"{v:.1f}x"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="2026-10")
    ap.add_argument("--extra", default="", help="weitere Ticker fuer die Tabelle, kommagetrennt")
    ap.add_argument("--statements-sample", type=int, default=0)
    args = ap.parse_args()

    cohort, details = load_cohort(args.month)
    db = firestore.Client(project=settings.gcp_project_id)
    rows: dict[str, dict] = {}
    missing = []
    refs = [db.collection(settings.ticker_collection).document(t) for t in cohort]
    for snap in db.get_all(refs):
        if snap.exists and snap.to_dict():
            rows[snap.id] = derive(snap.to_dict())
    missing = [t for t in cohort if t not in rows]
    print(f"Kohorte {args.month}: {len(cohort)} Titel, im Cache {len(rows)}, fehlen {len(missing)}")
    print(f"US {sum(1 for t in rows if region(t) == 'US')}, EU {sum(1 for t in rows if region(t) == 'EU')}")

    coverage(rows)

    for f, inv in [("gross_margin", False), ("de", True), ("nd_ebitda", True),
                   ("nd_fcf", True), ("op_margin", False), ("roe", False), ("roic", False)]:
        # d/e < 0 ist heute aus der Verteilung ausgeschlossen -- nachbilden
        if f == "de":
            for r in rows.values():
                if r["de"] is not None and r["de"] < 0:
                    r["de_excl"] = True
            saved = {t: r["de"] for t, r in rows.items()}
            for r in rows.values():
                if r.get("de_excl"):
                    r["de"] = None
            annotate(rows, f, inv)
            for t, r in rows.items():
                r["de"] = saved[t]
        else:
            annotate(rows, f, inv)
    scores = {t: score(r) for t, r in rows.items()}

    # Rekonstruktions-Check gegen den echten Lauf
    agree = Counter()
    for t, det in details.items():
        if t not in scores:
            continue
        ax = parse_detail(det)
        for a, k in (("resilience", "res_old"), ("profitability", "prof_old")):
            if a in ax:
                agree[(a, str(scores[t][k]) == ax[a])] += 1
    print("\n## Rekonstruktion alt vs. Lauf-CSV")
    for (a, ok), n in sorted(agree.items()):
        print(f"- {a}: {'gleich' if ok else 'abweichend'} {n}")

    # Verteilungs-Shift der Achse (nur Info)
    for k in ("res_old", "res_nd_ebitda", "res_nd_fcf", "res_abs", "res_abs2", "prof_old", "prof_roic"):
        c = Counter(s[k] for s in scores.values())
        print(f"- {k}: " + " ".join(f"{v}:{c[v]}" for v in range(6)) + f"  (>=4: {c[4] + c[5]})")

    # Crosshit-Vorschau: growth + steadiness aus dem Lauf, neue res/prof eingesetzt
    def is_ch(ax: dict, res: int, prof: int) -> bool:
        try:
            g = float(ax["growth"])
        except (KeyError, ValueError):
            return False
        if not (g >= 4 and res >= 4 and prof >= 4):
            return False
        st = ax.get("steadiness", "n/a")
        try:
            return float(st) >= 4
        except ValueError:
            return True

    text = (ROOT / "output" / "Universum" / f"{args.month}-Crosshits.md").read_text("utf-8")
    text = text.split("## Am Stetigkeits-Gate")[0]  # nur die Crosshit-Tabelle
    crosshits_old = set(
        line.split("|")[2].split()[0]
        for line in text.splitlines()
        if line.startswith("| ") and line.split("|")[1].strip().isdigit()
    )
    print(f"\n## Crosshit-Vorschau (growth/steadiness aus Lauf; Crosshits des Laufs: {len(crosshits_old)})")
    for label, rk, pk in [("ND/EBITDA", "res_nd_ebitda", "prof_old"),
                          ("ND/EBITDA + ROIC", "res_nd_ebitda", "prof_roic"),
                          ("ND/FCF", "res_nd_fcf", "prof_old"),
                          ("ND/EBITDA abs.", "res_abs", "prof_old"),
                          ("ND/EBITDA abs. + ROIC", "res_abs", "prof_roic"),
                          ("ND/EBITDA abs2", "res_abs2", "prof_old"),
                          ("ND/EBITDA abs2 + ROIC", "res_abs2", "prof_roic")]:
        new = set(t for t in crosshits_old if t in scores and scores[t][rk] >= 4 and scores[t][pk] >= 4)
        for t, det in details.items():
            if t in scores and is_ch(parse_detail(det), scores[t][rk], scores[t][pk]):
                new.add(t)
        print(f"- {label}: {len(new)}  neu: {sorted(new - crosshits_old)}  raus: {sorted(crosshits_old - new)}")

    # Tabelle
    tickers = FOCUS + [t for t in args.extra.split(",") if t]
    print("\n## Fokus-Titel\n")
    print("| Ticker | Sektor | GM (P) | D/E (P inv) | ND/EBITDA (P inv) | ND/FCF | ROE | ROIC | res alt | res ND/EBITDA pct | res ND/FCF pct | res ND/EBITDA abs | res abs2 | prof alt | prof ROIC |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in tickers:
        if t not in rows:
            print(f"| {t} | nicht in Kohorte/Cache |")
            continue
        r, s = rows[t], scores[t]
        pc = r.get("pct", {})
        P = lambda f: f" (P{pc[f]:.0f})" if f in pc else ""  # noqa: E731
        print(f"| {t} | {r['sector']} | {fmt(r['gross_margin'], 'pct')}{P('gross_margin')} | {fmt(r['de'], 'de')}{P('de')} "
              f"| {fmt(r['nd_ebitda'])}{P('nd_ebitda')}{' ⚑' if r['nd_ebitda_flag'] else ''} "
              f"| {fmt(r['nd_fcf'])}{' ⚑' if r['nd_fcf_flag'] else ''} | {fmt(r['roe'], 'pct')} | {fmt(r['roic'], 'pct')} "
              f"| {s['res_old']} | {s['res_nd_ebitda']} | {s['res_nd_fcf']} | {s['res_abs']} | {s['res_abs2']} | {s['prof_old']} | {s['prof_roic']} |")

    # Kandidaten fuer die Gegenprobe: hoechste ND/EBITDA ausserhalb Finanzen
    lev = sorted(((r["nd_ebitda"], t) for t, r in rows.items()
                  if r["nd_ebitda"] is not None and r["sector"] not in ("Financial Services", "Real Estate")),
                 reverse=True)[:15]
    print("\nHoechste ND/EBITDA (ohne Fin/RE): " + ", ".join(f"{t} {v:.1f}x" for v, t in lev))

    flag_breakdown(rows)

    if args.statements_sample:
        statements_sample(list(rows), args.statements_sample)



def flag_breakdown(rows: dict[str, dict]) -> None:
    """Wen trifft die neue Red-Flag-Regel, der heute nicht geflaggt ist -- nach Sektor."""
    newly, dropped = Counter(), Counter()
    newly_names: dict[str, list[str]] = defaultdict(list)
    for t, r in rows.items():
        old = r["de"] is not None and r["de"] > DE_REDFLAG
        if r["nd_ebitda_flag"] and not old:
            newly[r["sector"]] += 1
            newly_names[r["sector"]].append(t)
        if old and not r["nd_ebitda_flag"]:
            dropped[r["sector"]] += 1
    print("\n## ND/EBITDA>4-Flag neu (heute nicht geflaggt) nach Sektor")
    for sec, n in newly.most_common():
        print(f"- {sec}: {n}  {sorted(newly_names[sec])[:12]}")
    print("## D/E-Flag faellt weg nach Sektor: " + ", ".join(f"{s} {n}" for s, n in dropped.most_common()))
    fin_gap = sorted(t for t, r in rows.items() if r["sector"] == "Financial Services" and r["ebitda"] is None)
    print(f"## Financial Services ohne EBITDA: {fin_gap}")
    for thr in (4.0, 5.0, 6.0):
        n = sum(1 for r in rows.values() if r["nd_ebitda"] is not None and r["nd_ebitda"] > thr)
        n += sum(1 for r in rows.values() if r["nd_ebitda_flag"] and r["nd_ebitda"] is None)
        print(f"- Flag-Anzahl bei Schwelle {thr}: {n}")


if __name__ == "__main__":
    main()
