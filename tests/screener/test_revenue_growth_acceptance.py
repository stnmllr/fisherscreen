"""Network-free acceptance lock: the vintage-2026-06 drop cohort (189) must split
81 DECLINE_DROP / 107 TRAJECTORY_RESCUE / 1 UNASSESSABLE_PASS under the production gate.
Reconstructs each record from the committed diagnostic CSV's raw trajectory columns."""
import csv
from collections import Counter
from pathlib import Path

from app.models.definedness import DefinednessOutcome
from app.models.screener_record import ScreenerRecord
from app.screener.filters import revenue_growth_outcome

_AUDIT_DIR = (
    Path(__file__).resolve().parents[2]
    / "docs" / "superpowers" / "audits" / "2026-06-10-punkt-3-revenue-growth"
)
CSV = _AUDIT_DIR / "revenue_growth_drops.csv"
SLIP_CSV = _AUDIT_DIR / "full_sweep_slipthrough.csv"

# Pinned vintage-2026-06 residuum size (X = TTM>=0 AND CAGR<0 AND down_years>=2 over the
# basis survivors). Independently derived by scripts/diagnose_revenue_growth_drops.py
# --full-sweep; see calibration.md.
RESIDUUM_X = 104


def _f(x):
    return float(x) if x not in ("", "None", None) else None


def _i(x):
    return int(x) if x not in ("", "None", None) else None


def _outcome_for_row(row: dict) -> str:
    cagr, dy, ny = _f(row["multiyear_cagr"]), _i(row["down_years"]), _i(row["n_years"])
    defn = (
        DefinednessOutcome.DEFINED
        if (cagr is not None and ny is not None and ny >= 4)
        else DefinednessOutcome.UNASSESSABLE
    )
    rec = ScreenerRecord(
        ticker=row["ticker"],
        revenue_growth_yoy=_f(row["revenue_growth_yoy"]),
        multiyear_revenue_cagr=cagr,
        revenue_down_years=dy,
        revenue_growth_definedness=defn,
    )
    return revenue_growth_outcome(rec)


def test_vintage_2026_06_cohort_splits_81_107_1():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    assert len(rows) == 189
    dist = Counter(_outcome_for_row(r) for r in rows)
    assert dist["DECLINE_DROP"] == 81
    assert dist["TRAJECTORY_RESCUE"] == 107
    assert dist["UNASSESSABLE_PASS"] == 1
    assert dist.get("TTM_PASS", 0) == 0  # all 189 had TTM<0 or None -> none short-circuit


def test_residuum_blob_is_gamma_consistent_and_pinned():
    """The frozen residuum provenance blob (full_sweep_slipthrough.csv) must describe EXACTLY
    the gamma set: every row satisfies CAGR<0 AND down_years>=2, and the count is pinned to the
    vintage-2026-06 derivation X. This catches alpha-vs-gamma drift between the diagnostic sweep
    and the documented residuum (a stale alpha blob carried positive-CAGR / down_years==1 rows)."""
    rows = list(csv.DictReader(SLIP_CSV.open(encoding="utf-8")))
    assert len(rows) == RESIDUUM_X
    offenders = [
        r["ticker"]
        for r in rows
        if not (_f(r["multiyear_cagr"]) < 0 and _i(r["down_years"]) >= 2)
    ]
    assert offenders == [], f"non-gamma rows in residuum blob: {offenders}"
