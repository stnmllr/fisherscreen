# scripts/probe_valuation_history.py — einmaliger freier yfinance-Probe-Pull (Task 0).
# NICHT committen (wie scripts/diagnose_*). Output deckelt MIN_SPAN + Label.
from __future__ import annotations

import math

import yfinance as yf


def _rows(df):
    return list(df.index) if df is not None and not df.empty else []


def probe(ticker: str) -> None:
    t = yf.Ticker(ticker)
    info = t.info
    inc = t.income_stmt
    cash = t.cashflow
    bal = t.balance_sheet

    print(f"\n===== {ticker} =====")
    print("currency:", info.get("currency"),
          "| financialCurrency:", info.get("financialCurrency"))

    cols = list(getattr(inc, "columns", []))
    years = [getattr(c, "year", c) for c in cols]
    print(f"income_stmt GJ-Tiefe: {len(cols)} -> {years}")

    # Per-GJ diluted_eps availability (gates BOTH multiples, spec 3b)
    eps_label = next((r for r in _rows(inc)
                      if "diluted eps" in str(r).lower()), None)
    print("diluted_eps row label:", eps_label)
    if eps_label is not None:
        vals = inc.loc[eps_label].tolist()
        print("  per-GJ EPS:",
              [None if (v is None or (isinstance(v, float) and math.isnan(v)))
               else round(float(v), 2) for v in vals])

    # Other annual rows — exact label hunt (yfinance label drift)
    print("  income rows:", [str(r) for r in _rows(inc)])
    print("  cash rows:", [str(r) for r in _rows(cash)])
    print("  balance rows:", [str(r) for r in _rows(bal)])
    for label, frame in [("Net Income", inc), ("EBIT", inc),
                         ("Free Cash Flow", cash),
                         ("Total Debt", bal),
                         ("Cash And Cash Equivalents", bal)]:
        present = any(str(r) == label for r in _rows(frame))
        print(f"  row {label!r} present: {present}")

    # Weekly price + splits (spec 3a / 7)
    hist = t.history(period="5y", interval="1wk", auto_adjust=True)
    print("weekly close points:", len(hist),
          "| span(years):",
          round((hist.index[-1] - hist.index[0]).days / 365.25, 2)
          if len(hist) else 0)
    print("splits:", dict(t.splits))


if __name__ == "__main__":
    for tk in ("NOVO-B.CO", "GOOGL"):
        probe(tk)
