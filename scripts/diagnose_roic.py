r"""Diagnose: ROIC statt ROE in der profitability-Achse -- Schritt 1, nur Analyse.

Bewertet den Monat zweimal auf denselben Caches (ROE = Produktivcode, ROIC =
Variante aus simulate_month_scoring) und beantwortet drei offene Fragen:

  A  Investiertes Kapital <= 0: wer, welche Sektoren, was kostet die Deckelung auf 3?
  B  Stimmt bookValue x sharesOutstanding mit der Bilanzwaehrung? Gegenproben:
     Eigenkapital aus totalDebt / (debtToEquity/100) und aus marketCap / priceToBook.
  C  Woran scheitert ROIC bei Financial Services?

Dazu die Tabelle alt gegen neu fuer die Fokus- und Gegenproben-Titel und die
Wirkung auf Crosshits. NUR LESEN, $0 -- dieselben Read-only-Adapter wie die
Simulation, kein Schreiben nach Firestore.

Aufruf:
    uv run python scripts\diagnose_roic.py --month 2026-10
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from simulate_month_scoring import (
    DEFAULT_CIK_MAP,
    EQUITY_SOURCE,
    MIN_DIMENSIONS,
    THRESHOLD,
    _num,
    equity_from_info,
    build_and_score,
    load_inputs,
    roic_from_info,
)

from app.config import settings
from app.models.screener_record import ScreenerRecord
from app.screener.dimensions import is_crosshit

sys.stdout.reconfigure(encoding="utf-8")

FOCUS = ["MA", "MTD", "MSFT", "AAPL", "KLAC", "MCO", "ISRG", "V"]
COUNTER_PROBES = [
    "HD", "MCD", "SBUX", "LOW", "BKNG",  # negatives / winziges Eigenkapital
    "TDG", "FICO",  # hohe Verschuldung
    "JPM", "GS",  # Banken
    "NEE", "DUK", "CAT",  # kapitalintensiv
    "AZN.L", "REL.L", "LSEG.L",  # GBp-Notiz
    "NOVO-B.CO", "SAP.DE",  # EU, nicht GBp
]
# |log10(Eigenkapital_book / Eigenkapital_Gegenprobe)| ab hier gilt als Abweichung
LOG_TOL = 0.3
EQ = "book"  # set from --variant in main()


def suffix(ticker: str) -> str:
    return "." + ticker.rsplit(".", 1)[1] if "." in ticker else "US"


def equity_book(info: dict[str, Any]) -> float | None:
    b, s = _num(info.get("bookValue")), _num(info.get("sharesOutstanding"))
    return b * s if b is not None and s is not None else None


def equity_from_de(info: dict[str, Any]) -> float | None:
    debt, de = _num(info.get("totalDebt")), _num(info.get("debtToEquity"))
    if debt is None or de is None or debt <= 0 or de <= 0:
        return None
    return debt / (de / 100.0)


def equity_from_pb(info: dict[str, Any]) -> float | None:
    mc, pb = _num(info.get("marketCap")), _num(info.get("priceToBook"))
    if mc is None or pb is None or pb <= 0:
        return None
    return mc / pb


def log_ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a <= 0 or b <= 0:
        return None
    return math.log10(a / b)


def fmt(v: float | None, kind: str = "pct") -> str:
    if v is None:
        return "n/a"
    if kind == "pct":
        return f"{v:.1%}"
    if kind == "bn":
        return f"{v / 1e9:.1f}"
    return f"{v:.2f}"


def p(r: ScreenerRecord, field: str) -> str:
    v = (r.input_percentiles or {}).get(field)
    return "—" if v is None else f"P{v:.0f}"


def prof(r: ScreenerRecord) -> int | None:
    return (r.gemini_dimensions or {}).get("profitability")


def question_a(new: dict[str, ScreenerRecord], old: dict[str, ScreenerRecord], infos) -> None:
    print("\n## A — investiertes Kapital <= 0\n")
    hits = [t for t in new if roic_from_info(infos[t], EQ)[1] == "invested_capital_nonpositive"]
    print(f"{len(hits)} Titel. Sektoren: {dict(Counter(new[t].gics_sector for t in hits))}\n")
    print("| Ticker | Sektor | Industrie | EK (bn) | Schulden | Cash | EBIT | ROE | prof alt | prof neu |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for t in sorted(hits):
        i = infos[t]
        ebit = None
        if _num(i.get("operatingMargins")) is not None and _num(i.get("totalRevenue")) is not None:
            ebit = _num(i.get("operatingMargins")) * _num(i.get("totalRevenue"))
        print(f"| {t} | {new[t].gics_sector} | {new[t].gics_industry} | {fmt(equity_from_info(i, EQ), 'bn')} "
              f"| {fmt(_num(i.get('totalDebt')), 'bn')} | {fmt(_num(i.get('totalCash')), 'bn')} "
              f"| {fmt(ebit, 'bn')} | {fmt(old[t].return_on_equity)} | {prof(old[t])} | {prof(new[t])} |")


def question_b(infos: dict[str, dict[str, Any]]) -> None:
    print("\n## B — Waehrung von bookValue (log10-Abweichung > "
          f"{LOG_TOL} = Faktor {10 ** LOG_TOL:.1f})\n")
    by_suffix: dict[str, Counter] = defaultdict(Counter)
    outliers = []
    for t, i in infos.items():
        eb = equity_book(i)
        lr_de = log_ratio(eb, equity_from_de(i))
        lr_pb = log_ratio(eb, equity_from_pb(i))
        c = by_suffix[suffix(t)]
        c["n"] += 1
        for name, lr in (("de", lr_de), ("pb", lr_pb)):
            if lr is None:
                c[f"{name}_na"] += 1
            elif abs(lr) > LOG_TOL:
                c[f"{name}_off"] += 1
            else:
                c[f"{name}_ok"] += 1
        if (lr_de is not None and abs(lr_de) > LOG_TOL) or (lr_pb is not None and abs(lr_pb) > LOG_TOL):
            outliers.append((t, i, eb, lr_de, lr_pb))
    print("| Suffix | n | D/E ok | D/E abweichend | D/E n/a | P/B ok | P/B abweichend | P/B n/a |")
    print("|---|---|---|---|---|---|---|---|")
    for s, c in sorted(by_suffix.items(), key=lambda kv: -kv[1]["n"]):
        print(f"| {s} | {c['n']} | {c['de_ok']} | {c['de_off']} | {c['de_na']} "
              f"| {c['pb_ok']} | {c['pb_off']} | {c['pb_na']} |")
    print(f"\nAbweichler ({len(outliers)}):\n")
    print("| Ticker | currency | financialCurrency | EK book (bn) | log10 vs D/E | log10 vs P/B | ROIC |")
    print("|---|---|---|---|---|---|---|")
    for t, i, eb, lr_de, lr_pb in sorted(outliers):
        roic, why = roic_from_info(i, EQ)
        print(f"| {t} | {i.get('currency')} | {i.get('financialCurrency')} | {fmt(eb, 'bn')} "
              f"| {fmt(lr_de, 'x')} | {fmt(lr_pb, 'x')} | {fmt(roic) if roic is not None else why} |")


def question_c(new: dict[str, ScreenerRecord], infos) -> None:
    print("\n## C — Abdeckung nach Sektor und Ursache\n")
    by_sector: dict[str, Counter] = defaultdict(Counter)
    by_region: dict[str, Counter] = defaultdict(Counter)
    fin_missing = []
    for t, r in new.items():
        _, why = roic_from_info(infos[t], EQ)
        key = why or "ok"
        by_sector[r.gics_sector or "?"][key] += 1
        by_region["EU" if "." in t else "US"][key] += 1
        if r.gics_sector == "Financial Services" and why:
            fin_missing.append((t, r.gics_industry, why))
    reasons = ["ok", "no_ebit", "no_equity", "no_debt_cash", "invested_capital_nonpositive"]
    print("| Gruppe | n | Abdeckung | " + " | ".join(reasons[1:]) + " |")
    print("|---|---|---|" + "---|" * (len(reasons) - 1))
    for label, groups in (("Region", by_region), ("Sektor", by_sector)):
        for g, c in sorted(groups.items(), key=lambda kv: -sum(kv[1].values())):
            n = sum(c.values())
            print(f"| {label} {g} | {n} | {c['ok'] / n:.0%} | "
                  + " | ".join(str(c[k]) for k in reasons[1:]) + " |")
    print("\nFinancial Services ohne ROIC:\n")
    for t, ind, why in sorted(fin_missing):
        print(f"- {t} ({ind}): {why}")
    print("\nFinancial Services nach Industrie (ok / gesamt):")
    ind_c: dict[str, Counter] = defaultdict(Counter)
    for t, r in new.items():
        if r.gics_sector == "Financial Services":
            ind_c[r.gics_industry or "?"]["n"] += 1
            if roic_from_info(infos[t], EQ)[1] is None:
                ind_c[r.gics_industry or "?"]["ok"] += 1
    for ind, c in sorted(ind_c.items(), key=lambda kv: -kv[1]["n"]):
        print(f"- {ind}: {c['ok']}/{c['n']}")


def comparison_table(old: dict[str, ScreenerRecord], new: dict[str, ScreenerRecord]) -> None:
    print("\n## Tabelle alt (ROE) gegen neu (ROIC)\n")
    print("| Ticker | Sektor | op. Marge | ROE | ROIC | prof alt | prof neu | res | growth | Crosshit alt | Crosshit neu |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for t in FOCUS + ["—"] + COUNTER_PROBES:
        if t == "—":
            print("| **Gegenproben** | | | | | | | | | | |")
            continue
        if t not in new:
            print(f"| {t} | nicht in der Scoring-Kohorte | | | | | | | | | |")
            continue
        o, n = old[t], new[t]
        dims = n.gemini_dimensions or {}
        print(f"| {t} | {n.gics_sector} | {fmt(o.operating_margin)} ({p(o, 'operating_margin')}) "
              f"| {fmt(o.return_on_equity)} ({p(o, 'return_on_equity')}) "
              f"| {fmt(n.return_on_equity)} ({p(n, 'return_on_equity')}) "
              f"| {prof(o)} | {prof(n)} | {dims.get('resilience')} | {dims.get('growth')} "
              f"| {'✅' if is_crosshit(o, THRESHOLD, MIN_DIMENSIONS) else '—'} "
              f"| {'✅' if is_crosshit(n, THRESHOLD, MIN_DIMENSIONS) else '—'} |")


def effect(old: dict[str, ScreenerRecord], new: dict[str, ScreenerRecord]) -> None:
    print("\n## Wirkung\n")
    co = {t for t, r in old.items() if is_crosshit(r, THRESHOLD, MIN_DIMENSIONS)}
    cn = {t for t, r in new.items() if is_crosshit(r, THRESHOLD, MIN_DIMENSIONS)}
    print(f"Crosshits {len(co)} -> {len(cn)}; neu {sorted(cn - co)}; raus {sorted(co - cn)}")
    for label, recs in (("alt", old), ("neu", new)):
        d = Counter(prof(r) for r in recs.values())
        print(f"profitability {label}: " + " ".join(f"{k}:{d[k]}" for k in range(6))
              + f"  (>=4: {d[4] + d[5]})")
    flag_old = {t for t, r in old.items() if prof(r) == 0}
    flag_new = {t for t, r in new.items() if prof(r) == 0}
    roe_only = {t for t in flag_old
                if (old[t].operating_margin or 0) >= 0 and (old[t].return_on_equity or 0) < 0}
    print(f"profitability=0: {len(flag_old)} -> {len(flag_new)}; "
          f"nur durch ROE<0 (op. Marge >= 0): {len(roe_only)}")
    print(f"  davon jetzt: {dict(Counter(prof(new[t]) for t in roe_only))}")
    moves = Counter((prof(old[t]), prof(new[t])) for t in new)
    print("Uebergaenge alt->neu (ohne gleich): "
          + ", ".join(f"{a}->{b}: {c}" for (a, b), c in sorted(moves.items(), key=str) if a != b))
    sector_net = Counter()
    for t in new:
        delta = (prof(new[t]) or 0) - (prof(old[t]) or 0)
        sector_net[new[t].gics_sector] += delta
    print(f"Netto-Score-Delta nach Sektor: {dict(sector_net.most_common())}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--cik-map", type=Path, default=DEFAULT_CIK_MAP)
    ap.add_argument("--variant", choices=tuple(EQUITY_SOURCE), default="roic")
    args = ap.parse_args()
    global EQ
    EQ = EQUITY_SOURCE[args.variant]

    _, _, cohort, cik_map, store = load_inputs(args.month, args.cik_map, False)
    scored_old, *_ = build_and_score(store, cohort, cik_map, "roe")
    scored_new, *_ = build_and_score(store, cohort, cik_map, args.variant)
    old = {r.ticker: r for r in scored_old}
    new = {r.ticker: r for r in scored_new}
    infos = {t: store.get(settings.ticker_collection, t) or {} for t in new}

    comparison_table(old, new)
    effect(old, new)
    question_a(new, old, infos)
    question_c(new, infos)
    question_b(infos)


if __name__ == "__main__":
    main()
