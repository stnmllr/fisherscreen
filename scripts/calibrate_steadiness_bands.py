r"""Kalibrierung der absoluten Baender fuer die Dimension "Stetigkeit" (Spec 9.2).

Liest NUR den Zwischenstand der Machbarkeitsprobe (cache/edgar_history_coverage.json,
Schema 2) -- kein Netz, kein Firestore, kein GCP. Rechnet S1/S2/S3 ueber das
Zehn-Jahres-Fenster je Titel und zeigt

  1. die Verteilung jeder Teilgroesse ueber alle bewertbaren Titel (Perzentile),
  2. je Kandidaten-Bandtabelle: wie viele Titel >=4 bekaemen (die eigentliche Stellschraube),
  3. die Werte der acht Preisnehmer und der Prueftitel im Klartext, samt Jahresreihen.

Zusaetzlich zu den Spec-Groessen werden zwei Varianten mitgemessen, damit die
Entscheidung an Zahlen haengt und nicht an einer Vermutung:
  - S2 als groesster Margenrueckgang vom Hoch (pp) statt Standardabweichung
    (die Standardabweichung bestraft auch eine stetig STEIGENDE Marge),
  - S3 als schlechteste Nettomarge statt schlechteste EK-Rendite
    (negatives Eigenkapital nach Rueckkaeufen -- FICO, TDG -- macht die EK-Rendite
    unbestimmbar und den Titel neutral, obwohl er das Gegenteil eines Zyklikers ist).

Aufruf (cmd.exe):
  uv run python scripts\calibrate_steadiness_bands.py
  uv run python scripts\calibrate_steadiness_bands.py --state cache\edgar_history_coverage.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = REPO_ROOT / "cache" / "edgar_history_coverage.json"

WINDOW_MAX = 10
WINDOW_MIN = 7

PRICE_TAKERS = ("HL", "NEM", "MU", "RGLD", "TPL", "SNDK", "EDV.L", "ANTO.L")
POSITIVES = ("MEDP", "FAST", "FICO")
WATCH = ("NVDA", "TER", "TDG", "META", "GOOG", "MNST", "PLTR", "ABNB")

# (label, S1-Baender, S2-Baender, S3-Baender); jede Bandliste absteigend
# (Schwelle, Score); unterhalb der letzten Schwelle -> 1.
# S1: Anteil Nicht-Rueckgangs-Uebergaenge (>=), S2: pp (<=), S3: Prozent (>=).
CANDIDATES = [
    (
        "Spec 5.1",
        ((0.90, 5), (0.75, 4), (0.60, 3), (0.45, 2)),
        ((3.0, 5), (6.0, 4), (10.0, 3), (15.0, 2)),
        ((10.0, 5), (5.0, 4), (0.0, 3), (-10.0, 2)),
    ),
    (
        "S1 nach Rueckgangsjahren (0/1/2/3)",
        # 9 Uebergaenge: 0 Rueckgaenge=1.0, 1=0.889, 2=0.778, 3=0.667 -- Schwellen
        # in der Mitte zwischen den erreichbaren Werten, damit die Quantisierung
        # nicht zufaellig entscheidet (0.889 < 0.90 waere sonst "kein 5er").
        ((0.95, 5), (0.83, 4), (0.72, 3), (0.61, 2)),
        ((3.0, 5), (6.0, 4), (10.0, 3), (15.0, 2)),
        ((10.0, 5), (5.0, 4), (0.0, 3), (-10.0, 2)),
    ),
    (
        "lockerer S2 (4/8/12/18)",
        ((0.95, 5), (0.83, 4), (0.72, 3), (0.61, 2)),
        ((4.0, 5), (8.0, 4), (12.0, 3), (18.0, 2)),
        ((10.0, 5), (5.0, 4), (0.0, 3), (-10.0, 2)),
    ),
]


@dataclass
class Steadiness:
    ticker: str
    years: list[int]
    revenue: list[float]
    op_income: list[float]
    net_income: list[float]
    equity: list[float]
    window: int
    down_years: int
    s1: float
    margin_std_pp: float
    margin_drawdown_pp: float
    worst_roe: float | None  # None: zu viele Jahre mit equity <= 0
    equity_nonpos_years: int
    worst_net_margin: float


def _series(record: dict[str, Any], key: str) -> dict[int, float]:
    cov = record.get("concepts_extended", {}).get(key) or {}
    return dict(zip(cov.get("years", []), cov.get("values", [])))


def _window(labels: Sequence[int]) -> list[int]:
    """Laengster zusammenhaengender Lauf, der im juengsten Jahr endet; auf WINDOW_MAX gekappt."""
    if not labels:
        return []
    ordered = sorted(labels)
    run = [ordered[-1]]
    for y in reversed(ordered[:-1]):
        if y == run[-1] - 1:
            run.append(y)
        else:
            break
    run.reverse()
    return run[-WINDOW_MAX:]


def _pstdev(xs: Sequence[float]) -> float:
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def compute(ticker: str, record: dict[str, Any]) -> Steadiness | None:
    rev, opi, ni, eq = (_series(record, k) for k in ("revenue", "operating_income", "net_income", "equity"))
    common = set(rev) & set(opi) & set(ni)
    years = _window(sorted(common))
    if len(years) < WINDOW_MIN:
        return None
    r = [rev[y] for y in years]
    o = [opi[y] for y in years]
    n = [ni[y] for y in years]
    e = [eq.get(y, 0.0) for y in years]
    if any(x <= 0 for x in r):
        return None  # Umsatz <= 0: keine Marge definierbar

    transitions = len(r) - 1
    down = sum(1 for a, b in zip(r, r[1:]) if b < a)
    s1 = (transitions - down) / transitions

    margins = [100.0 * oi / rv for oi, rv in zip(o, r)]
    peak = margins[0]
    drawdown = 0.0
    for m in margins:
        peak = max(peak, m)
        drawdown = max(drawdown, peak - m)

    roes = [100.0 * x / y for x, y in zip(n, e) if y > 0]
    nonpos = len(years) - len(roes)
    worst_roe = min(roes) if len(roes) >= WINDOW_MIN else None
    worst_nm = min(100.0 * x / rv for x, rv in zip(n, r))

    return Steadiness(
        ticker, years, r, o, n, e, len(years), down, s1,
        _pstdev(margins), drawdown, worst_roe, nonpos, worst_nm,
    )


def band(value: float | None, bands, *, lower_is_better: bool) -> int | None:
    if value is None:
        return None
    for thr, score in bands:
        if (value <= thr) if lower_is_better else (value >= thr):
            return score
    return 1


def score(st: Steadiness, cand, *, s2="std", s3="roe") -> tuple[int, int, int | None, float | None]:
    _, b1, b2, b3 = cand
    v2 = st.margin_std_pp if s2 == "std" else st.margin_drawdown_pp
    v3 = st.worst_roe if s3 == "roe" else st.worst_net_margin
    x1 = band(st.s1, b1, lower_is_better=False)
    x2 = band(v2, b2, lower_is_better=True)
    x3 = band(v3, b3, lower_is_better=False)
    cap = 5 if st.window >= 10 else 4
    total = None if x3 is None else min(cap, round((x1 + x2 + x3) / 3, 2))
    return x1, x2, x3, total


def pct(xs: Sequence[float], p: float) -> float:
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def fmt_series(years, values, scale=1e9, unit="Mrd") -> str:
    return ", ".join(f"{y}: {v / scale:.2f} {unit}" for y, v in zip(years, values))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    args = ap.parse_args()
    path = Path(args.state)
    if not path.exists():
        print(f"Zwischenstand fehlt: {path} -- zuerst scripts/probe_edgar_history.py laufen lassen")
        return 1
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != 2:
        print(f"Schema {state.get('schema')} != 2 -- Probe neu laufen lassen")
        return 1

    results: dict[str, Steadiness] = {}
    for ticker, rec in state.get("tickers", {}).items():
        if rec.get("status") != "ok":
            continue
        st = compute(ticker, rec)
        if st:
            results[ticker] = st
    ten = [s for s in results.values() if s.window >= 10]
    print(f"bewertbar (>= {WINDOW_MIN} J.): {len(results)}, davon >= 10 J.: {len(ten)}")
    roe_undef = [s.ticker for s in results.values() if s.worst_roe is None]
    print(f"S3 (EK-Rendite) unbestimmbar wegen equity <= 0: {len(roe_undef)} -> {', '.join(sorted(roe_undef)[:25])}")

    print("\n== Verteilung (Titel mit >= 10 Jahren) ==")
    rows = [
        ("S1 Anteil Nicht-Rueckgang", [s.s1 for s in ten], "{:.2f}"),
        ("Rueckgangsjahre (von 9)", [float(s.down_years) for s in ten], "{:.0f}"),
        ("S2 Margen-Std (pp)", [s.margin_std_pp for s in ten], "{:.1f}"),
        ("S2' Margen-Drawdown (pp)", [s.margin_drawdown_pp for s in ten], "{:.1f}"),
        ("S3 schlechteste EK-Rendite %", [s.worst_roe for s in ten if s.worst_roe is not None], "{:.1f}"),
        ("S3' schlechteste Nettomarge %", [s.worst_net_margin for s in ten], "{:.1f}"),
    ]
    print(f"{'Groesse':32} {'P10':>8} {'P25':>8} {'P50':>8} {'P75':>8} {'P90':>8}")
    for label, xs, f in rows:
        print(f"{label:32} " + " ".join(f"{f.format(pct(xs, p)):>8}" for p in (0.1, 0.25, 0.5, 0.75, 0.9)))

    print("\n== Wie viele Titel bekaemen Stetigkeit >= 4,0? (Gate-Relevanz) ==")
    variants = [("std/roe", "std", "roe"), ("drawdown/roe", "dd", "roe"), ("std/netmargin", "std", "nm"), ("drawdown/netmargin", "dd", "nm")]
    print(f"{'Baender':36} " + " ".join(f"{v[0]:>20}" for v in variants))
    for cand in CANDIDATES:
        cells = []
        for _, s2, s3 in variants:
            totals = [score(s, cand, s2=s2, s3=s3)[3] for s in results.values()]
            ok = sum(1 for t in totals if t is not None and t >= 4.0)
            und = sum(1 for t in totals if t is None)
            cells.append(f"{ok:>4}/{len(totals)} ({100*ok/len(totals):.0f}%) n/a {und}")
        print(f"{cand[0]:36} " + " ".join(f"{c:>20}" for c in cells))

    print("\n== Preisnehmer, Positivfaelle, Prueftitel (Spec 5.1-Baender, Mittelwert) ==")
    print(f"{'Ticker':8} {'J.':>3} {'down':>4} {'S1':>5} {'Std':>6} {'DD':>6} {'wROE':>7} {'wNM':>6} | {'Score':>5} {'min':>4} | {'DD/NM':>5}")
    for t in PRICE_TAKERS + POSITIVES + WATCH:
        s = results.get(t)
        if not s:
            print(f"{t:8} -- nicht bewertbar (kein SEC / < {WINDOW_MIN} J. / Umsatzluecke)")
            continue
        x1, x2, x3, tot = score(s, CANDIDATES[0])
        _, _, _, tot_alt = score(s, CANDIDATES[1], s2="dd", s3="nm")
        mn = min(v for v in (x1, x2, x3) if v is not None)
        roe = "n/a" if s.worst_roe is None else f"{s.worst_roe:.1f}"
        print(f"{t:8} {s.window:>3} {s.down_years:>4} {s.s1:>5.2f} {s.margin_std_pp:>6.1f} {s.margin_drawdown_pp:>6.1f} {roe:>7} {s.worst_net_margin:>6.1f} | {tot if tot is not None else 'n/a':>5} {mn:>4} | {tot_alt:>5}")

    print("\n== Primaerevidenz: Jahresreihen (Umsatz / operative Marge %) ==")
    for t in ("HL", "NEM", "MU", "TPL", "MEDP", "FAST", "FICO", "NVDA"):
        s = results.get(t)
        if not s:
            continue
        margins = [100.0 * o / r for o, r in zip(s.op_income, s.revenue)]
        print(f"- {t}: Umsatz {fmt_series(s.years, s.revenue)}")
        print(f"  {t}: op. Marge " + ", ".join(f"{y}: {m:.1f}%" for y, m in zip(s.years, margins)))
        if s.equity_nonpos_years:
            print(f"  {t}: {s.equity_nonpos_years} Jahr(e) mit Eigenkapital <= 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
