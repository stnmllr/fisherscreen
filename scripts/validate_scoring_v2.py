"""Validation harness for the v2.1 flat anti-inflation scoring prompt.

Aggregate metrics (a falling crosshit count, a near-zero correlation) can move
WITHOUT the mechanism actually gripping — scores can stay clumped at 4, or the
mega-cap corner can keep scoring high on reputation while the overall correlation
washes out. So this harness pairs the aggregates with reads of the PRIMARY
artefact (the evidence notes), which is the only thing that proves the evidence
duty holds.

Two modes:
  Full run (default): runs the real pipeline against data/universe.json, writes
  output to output-test/ (NOT output/, no GitHub push), dumps the scored records
  to output-test/scored_records.json, then prints the validation report.
  PURGE dev_gemini_scores FIRST (scripts/purge_gemini_scores_all.py --apply),
  otherwise warm cache serves OLD-prompt scores.

  Analyze only (--analyze-only): re-reads the existing dump and reprints the
  report. $0, no run, no credentials — iterate on the analysis freely.

Requires (full run): .env with FISHERSCREEN_* + GCP Application Default Credentials
  (gcloud auth application-default login).

  uv run python scripts/purge_gemini_scores_all.py --apply
  uv run python scripts/validate_scoring_v2.py
  uv run python scripts/validate_scoring_v2.py --analyze-only
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Windows console defaults to cp1252; our report prints →/≥/– etc. Force UTF-8 so
# the summary print can't crash after a successful (paid) run.
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

from app.screener.dimensions import DIMENSIONS, MERIT_DIMENSIONS  # noqa: E402

_DUMP = Path("output-test/scored_records.json")
# Old all-five 5/5/5/5/5 names + one EU filer — read their evidence by eye.
_SAMPLE = ["NVDA", "MSFT", "AAPL", "ASML.AS", "MCD"]
_HIGH = 4  # score considered a "merit hit" / "high" score
_DIGIT = re.compile(r"\d")


def _run_and_dump() -> None:
    import logging

    from app.logging_config import configure_logging
    from app.screener.compose import (
        build_edgar_pipeline,
        build_gemini_pipeline,
        build_run_tracker,
        build_screener_pipeline,
    )
    from app.screener.runner import run_screener

    configure_logging()
    logger = logging.getLogger(__name__)

    tickers: list[str] = json.loads(Path("data/universe.json").read_text(encoding="utf-8"))
    logger.info("validate: universe loaded, %d tickers", len(tickers))

    output_dir = Path("output-test")
    output_dir.mkdir(exist_ok=True)

    records, run_record, paths = run_screener(
        tickers=tickers,
        yfinance=build_screener_pipeline(),
        edgar=build_edgar_pipeline(),
        gemini=build_gemini_pipeline(),
        run_tracker=build_run_tracker(),
        output_dir=output_dir,
    )

    scored = [r for r in records if r.gemini_dimensions is not None]
    dump = [
        {
            "ticker": r.ticker,
            "name": r.name,
            "sector": r.gics_sector,
            "market_cap": r.market_cap,
            "market_cap_eur": r.market_cap_eur,
            "dimensions": r.gemini_dimensions,
            "evidence": r.gemini_evidence or {},
            "weakest_dimension": r.gemini_weakest_dimension,
            "data_gaps": r.gemini_data_gaps or [],
        }
        for r in scored
    ]
    _DUMP.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\nRun {run_record.run_id} | status={run_record.status} | "
        f"processed={run_record.tickers_processed} | "
        f"est_cost=${run_record.estimated_cost_usd:.4f} | "
        f"scored={len(scored)} → {_DUMP}"
    )
    print("Output files (output-test/, NOT pushed):")
    for p in paths:
        print(f"  {p}")


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def _merit_avg(dims: dict[str, int]) -> float:
    vals = [dims.get(d, 0) for d in MERIT_DIMENSIONS]
    return sum(vals) / len(vals)


def _hist(rows: list[dict[str, Any]], dim: str) -> dict[int, int]:
    counts = {s: 0 for s in range(6)}
    for r in rows:
        v = (r.get("dimensions") or {}).get(dim)
        if isinstance(v, int) and 0 <= v <= 5:
            counts[v] += 1
    return counts


def analyze() -> None:
    if not _DUMP.exists():
        raise SystemExit(f"No dump at {_DUMP} — run without --analyze-only first.")
    rows: list[dict[str, Any]] = json.loads(_DUMP.read_text(encoding="utf-8"))
    n = len(rows)
    print("=" * 72)
    print(f"VALIDATION — v2.1 flat scoring prompt  ({n} scored records)")
    print("=" * 72)

    # 1. Score distribution per dimension — the real signal is healthy spread, not
    #    a fallen count with everything still clumped at 4.
    print("\n[1] SCORE DISTRIBUTION per dimension (count at each 0–5)")
    print(f"    {'dim':<14} " + "  ".join(f"{s:>4}" for s in range(6)) + "   merit?")
    for dim in DIMENSIONS:
        h = _hist(rows, dim)
        merit = "yes" if dim in MERIT_DIMENSIONS else "n/a (sentinel)"
        print(f"    {dim:<14} " + "  ".join(f"{h[s]:>4}" for s in range(6)) + f"   {merit}")

    # 2. All-three-merit >= 4 (the ex-"42 at 5/5/5/5/5" check)
    all3 = [r for r in rows if all((r.get("dimensions") or {}).get(d, 0) >= _HIGH for d in MERIT_DIMENSIONS)]
    print(f"\n[2] Titles with growth+profitability+resilience ALL >= {_HIGH}: {len(all3)}  (was 42)")
    for r in sorted(all3, key=lambda r: -_merit_avg(r["dimensions"]))[:60]:
        d = r["dimensions"]
        trip = "/".join(str(d.get(x, 0)) for x in MERIT_DIMENSIONS)
        print(f"      {r['ticker']:<10} {trip:<8} {r.get('name') or ''}")

    # 3. Correlation merit-avg <-> market cap, plus the mega-cap subgroup mean
    #    (correlation can wash out while the biggest names still cluster high).
    paired = [
        (r["market_cap_eur"] or r["market_cap"], _merit_avg(r["dimensions"]))
        for r in rows
        if (r.get("market_cap_eur") or r.get("market_cap"))
    ]
    caps = [c for c, _ in paired]
    scores = [s for _, s in paired]
    r_pear = _pearson(caps, scores)
    print(f"\n[3] Correlation(merit-avg, market_cap): "
          f"r = {r_pear:.3f}" if r_pear is not None else "\n[3] Correlation: n/a")
    if paired:
        order = sorted(paired, key=lambda p: -p[0])
        k = max(1, len(order) // 10)
        top_mean = sum(s for _, s in order[:k]) / k
        all_mean = sum(scores) / len(scores)
        print(f"    top-decile-by-cap mean merit-avg = {top_mean:.2f}  vs  overall = {all_mean:.2f}  "
              f"(gap {top_mean - all_mean:+.2f}; large gap => big names still score high)")

    # 4. Evidence duty: every score >= 4 must cite a figure. A 4+ evidence note
    #    with NO digit is a platitude — the duty is not gripping.
    total_high = 0
    platitudes: list[tuple[str, str, str]] = []
    for r in rows:
        d = r.get("dimensions") or {}
        ev = r.get("evidence") or {}
        for dim in MERIT_DIMENSIONS:
            if d.get(dim, 0) >= _HIGH:
                total_high += 1
                note = str(ev.get(dim, ""))
                if not _DIGIT.search(note):
                    platitudes.append((r["ticker"], dim, note))
    rate = (len(platitudes) / total_high * 100) if total_high else 0.0
    print(f"\n[4] EVIDENCE DUTY — {len(platitudes)}/{total_high} merit scores >= {_HIGH} "
          f"cite NO figure ({rate:.1f}% platitudes; lower is better)")
    for tk, dim, note in platitudes[:15]:
        print(f"      {tk:<10} {dim:<14} \"{note}\"")

    # 5. Sentinel integrity — management/innovation must all be exactly 3
    for dim in ("management", "innovation"):
        offenders = [r["ticker"] for r in rows if (r.get("dimensions") or {}).get(dim) != 3]
        status = "OK (all == 3)" if not offenders else f"DEVIATION: {offenders[:10]}"
        print(f"\n[5] Sentinel {dim}: {status}")

    # 6. Named-sample evidence dump (read by eye) + MCD regression
    print("\n[6] SAMPLE evidence (read by eye — real figures or platitudes?)")
    by_ticker = {r["ticker"]: r for r in rows}
    for tk in _SAMPLE:
        r = by_ticker.get(tk)
        if r is None:
            print(f"    {tk}: NOT IN SCORED SET (skipped/dropped)"
                  + ("  <-- MCD regression: still skipped!" if tk == "MCD" else ""))
            continue
        d, ev = r["dimensions"], r.get("evidence") or {}
        print(f"    {tk} ({r.get('name') or ''}) weakest={r.get('weakest_dimension')}")
        for dim in DIMENSIONS:
            print(f"        {dim:<14} {d.get(dim)}  — {ev.get(dim, '')}")
    if "MCD" in by_ticker:
        print("\n    MCD regression: PRESENT in scored set (not skipped). OK.")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analyze-only", action="store_true",
        help="Skip the run; re-analyze the existing output-test/scored_records.json ($0).",
    )
    args = parser.parse_args()
    if not args.analyze_only:
        _run_and_dump()
    analyze()


if __name__ == "__main__":
    main()
