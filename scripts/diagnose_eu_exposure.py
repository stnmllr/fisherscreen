"""Diagnose (one-off): how large is the EU-Native exposure in the universe?
Counts universe tickers by Yahoo suffix -> the ceiling of titles that must go
through the EU-ADR path (and thus can fall into the EU-Native gap)."""
from __future__ import annotations
import json, collections
from pathlib import Path

for p in (Path("data/universe.json"),):
    if not p.exists():
        print("missing:", p); continue
    raw = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        tickers = raw.get("tickers") or list(raw.keys())
    else:
        tickers = raw
    tickers = [t if isinstance(t, str) else t.get("ticker") for t in tickers]
    tickers = [t for t in tickers if t]
    hist = collections.Counter(
        t.rsplit(".", 1)[1].upper() if "." in t else "(US)" for t in tickers
    )
    print(f"{p}: {len(tickers)} tickers")
    for k, v in hist.most_common():
        print(f"  {k:6} {v:5}")
    print("  dotted total:", sum(v for k, v in hist.items() if k != "(US)"))
