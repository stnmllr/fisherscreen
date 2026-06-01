# Phase 1.4 — Insider-Transactions (Form-4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tool B pulls a US filer's Form-4 insider filings via EDGAR, classifies them code-side, and feeds a code-computed `InsiderSummary` into the Gemini synthesis prompt (anchoring Fisher P15) and the dossier.

**Architecture:** A self-contained insider mini-subsystem that does NOT touch the HTML filing parser: EDGAR client extension (index + raw-XML fetch) → accession-keyed immutable pre-netting cache → XML parser → three-bucket netting/significance → `InsiderSummary` → renderer (shared by synthesis + dossier) → pipeline stage [2b] (fail-soft, additive).

**Tech Stack:** Python 3.12, pydantic v2 (`extra="forbid"`), `xml.etree.ElementTree`, httpx (existing EDGAR wrapper), pytest + dependency-injection. Spec: `docs/superpowers/specs/2026-06-01-phase-1-4-insider-form4-design.md`.

**Canonical test invocation (SOPRA-EPDR):** `uv run python -m pytest` (NEVER `uv run pytest`). Running a single test file exits 1 on the global 90 % coverage gate — that is expected in isolation; the `N passed` line is the signal. A full-suite run at the end (Task 12) confirms the gate.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `app/models/deep_dive_record.py` | `InsiderTransaction`, `InsiderSummary`, literals; `DeepDiveRecord.insider_summary` | Modify |
| `app/deepdive/insider_parser.py` | `parse_form4`, `classify_bucket`, `derive_role`, `_parse_10b5_1` | Create |
| `app/deepdive/insider_summary.py` | `INSIDER_SIGNIFICANCE_USD`, `compute_insider_summary` | Create |
| `app/services/edgar_client.py` | `Form4Ref`, `get_form4_index`, `get_form4_document` | Modify |
| `app/deepdive/insider_cache.py` | `InsiderFetchResult`, `CachedInsiderFetcher`, `INSIDER_CACHE_SCHEMA_VERSION` | Create |
| `app/deepdive/insider_block.py` | `render_insider_block`, `insider_coverage_label` | Create |
| `app/deepdive/synthesis.py` | `Form-4` marker, `_p15_floor`, insider prompt block, P15 floor logic | Modify |
| `app/config.py` | `insider_lookback_days` | Modify |
| `app/deepdive/compose.py` | `build_insider_fetcher` | Modify |
| `app/deepdive/pipeline.py` | Stage [2b], `insider_fetcher`/`no_insider`/`insider_lookback_days` params, coverage label | Modify |
| `app/deepdive/__main__.py` | `--no-insider`, wiring | Modify |
| `app/deepdive/dossier_generator.py` | `## Insider-Transaktionen` section + frontmatter digest | Modify |

Test files mirror source: `tests/models/`, `tests/deepdive/`, `tests/services/`.

---

## Task 1: Data model

**Files:**
- Modify: `app/models/deep_dive_record.py`
- Test: `tests/models/test_deep_dive_record.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/models/test_deep_dive_record.py`:

```python
from app.models.deep_dive_record import (
    InsiderTransaction,
    InsiderSummary,
    DeepDiveRecord,
)


def test_insider_transaction_minimal_and_forbids_extra():
    t = InsiderTransaction(owner_name="Doe Jane", role="CEO", code="P", bucket="buy")
    assert t.significant is False
    assert t.is_10b5_1 is None
    assert t.value is None
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        InsiderTransaction(owner_name="X", role="CEO", code="P", bucket="buy", bogus=1)


def test_insider_summary_defaults():
    s = InsiderSummary(coverage_state="empty")
    assert s.n_filings_total == 0 and s.n_transactions_total == 0
    assert s.significant_buys == [] and s.routine_count == 0
    assert s.window_label == "letzte 12 Monate"


def test_deep_dive_record_insider_summary_optional(_deep_dive_record_kwargs=None):
    # insider_summary defaults to None and accepts an InsiderSummary
    s = InsiderSummary(coverage_state="fpi_exempt")
    assert s.coverage_state == "fpi_exempt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/models/test_deep_dive_record.py::test_insider_transaction_minimal_and_forbids_extra -v`
Expected: FAIL — `ImportError: cannot import name 'InsiderTransaction'`.

- [ ] **Step 3: Write minimal implementation**

In `app/models/deep_dive_record.py`, after the `ValuationHistory` class (before `QuantSnapshot`), add:

```python
InsiderRole = Literal["CEO", "CFO", "Director", "Officer", "TenPercentOwner", "Other"]
InsiderBucket = Literal["buy", "sell", "routine"]
InsiderCoverage = Literal[
    "ok", "partial", "empty", "fetch_failed", "fpi_exempt", "skipped"
]


class InsiderTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_name: str
    role: InsiderRole
    officer_title: str | None = None
    is_director: bool = False
    is_officer: bool = False
    is_ten_pct: bool = False
    date: str | None = None
    code: str
    bucket: InsiderBucket
    shares: float | None = None
    price: float | None = None
    value: float | None = None
    acquired_disposed: Literal["A", "D"] | None = None
    security_title: str | None = None
    is_derivative: bool = False
    shares_after: float | None = None
    direct_or_indirect: Literal["D", "I"] | None = None
    is_10b5_1: bool | None = None
    significant: bool = False


class InsiderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage_state: InsiderCoverage
    window_label: str = "letzte 12 Monate"
    n_filings_total: int = 0
    n_parsed: int = 0
    n_transactions_total: int = 0
    significant_buys: list[InsiderTransaction] = Field(default_factory=list)
    significant_sells: list[InsiderTransaction] = Field(default_factory=list)
    immaterial_sell_count: int = 0
    routine_count: int = 0
    net_buy_value: float = 0.0
    net_sell_value: float = 0.0
    by_role: dict[str, dict[str, float]] = Field(default_factory=dict)
```

In the `DeepDiveRecord` class, after `filing_date: str | None = None`, add:

```python
    insider_summary: InsiderSummary | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/models/test_deep_dive_record.py -v`
Expected: PASS (all three new tests + existing). Coverage-gate exit 1 in isolation is expected.

- [ ] **Step 5: Commit**

```bash
git add app/models/deep_dive_record.py tests/models/test_deep_dive_record.py
git commit -m "Add InsiderTransaction/InsiderSummary models + DeepDiveRecord field"
```

---

## Task 2: Form-4 XML parser

**Files:**
- Create: `app/deepdive/insider_parser.py`
- Test: `tests/deepdive/test_insider_parser.py`

- [ ] **Step 1: Write the failing test**

Create `tests/deepdive/test_insider_parser.py`:

```python
from app.deepdive.insider_parser import (
    parse_form4,
    classify_bucket,
    derive_role,
)

_XML_SELL = """<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <aff10b5One>1</aff10b5One>
  <issuer><issuerTradingSymbol>NVDA</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Huang Jensen</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector><isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>President and Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-05-29</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10000</value></transactionShares>
        <transactionPricePerShare><value>150.0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>90000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <derivativeTable>
    <derivativeTransaction>
      <securityTitle><value>RSU</value></securityTitle>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </derivativeTransaction>
  </derivativeTable>
</ownershipDocument>
"""


def test_parse_form4_extracts_nonderivative_and_derivative():
    txns = parse_form4(_XML_SELL)
    assert len(txns) == 2
    sell = txns[0]
    assert sell.owner_name == "Huang Jensen"
    assert sell.role == "CEO"  # title precedence over Director flag
    assert sell.code == "S" and sell.bucket == "sell"
    assert sell.shares == 10000 and sell.price == 150.0
    assert sell.value == 1_500_000.0
    assert sell.acquired_disposed == "D"
    assert sell.shares_after == 90000 and sell.direct_or_indirect == "D"
    assert sell.is_derivative is False
    assert sell.is_10b5_1 is True
    deriv = txns[1]
    assert deriv.is_derivative is True and deriv.bucket == "routine"  # derivative => routine
    assert deriv.value is None  # no price


def test_classify_bucket_unknown_code_warns_routine(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        assert classify_bucket("X", False) == "routine"
    assert any("unknown transactionCode" in r.message for r in caplog.records)
    assert classify_bucket("P", False) == "buy"
    assert classify_bucket("S", False) == "sell"
    assert classify_bucket("S", True) == "routine"  # derivative always routine


def test_derive_role_precedence():
    assert derive_role("EVP, Chief Financial Officer", True, True, False) == "CFO"
    assert derive_role("Principal Executive Officer", False, True, False) == "CEO"
    assert derive_role(None, True, True, False) == "Officer"   # officer beats director
    assert derive_role(None, True, False, False) == "Director"
    assert derive_role(None, False, False, True) == "TenPercentOwner"
    assert derive_role(None, False, False, False) == "Other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_insider_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.insider_parser'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/deepdive/insider_parser.py`:

```python
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from app.models.deep_dive_record import (
    InsiderBucket,
    InsiderRole,
    InsiderTransaction,
)

logger = logging.getLogger(__name__)

_ROUTINE_CODES = {"A", "M", "F", "G"}
_CEO_TITLES = ("chief executive", "ceo", "principal executive officer")
_CFO_TITLES = ("chief financial", "cfo", "principal financial officer")


def classify_bucket(code: str, is_derivative: bool) -> InsiderBucket:
    if is_derivative:
        return "routine"  # derivatives are compensation by construction
    if code == "P":
        return "buy"
    if code == "S":
        return "sell"
    if code in _ROUTINE_CODES:
        return "routine"
    logger.warning("insider: unknown transactionCode %r -> routine bucket", code)
    return "routine"


def derive_role(
    officer_title: str | None,
    is_director: bool,
    is_officer: bool,
    is_ten_pct: bool,
) -> InsiderRole:
    """Display-only precedence (significance uses title+flags directly)."""
    t = (officer_title or "").lower()
    if any(k in t for k in _CEO_TITLES):
        return "CEO"
    if any(k in t for k in _CFO_TITLES):
        return "CFO"
    if is_officer:
        return "Officer"
    if is_director:
        return "Director"
    if is_ten_pct:
        return "TenPercentOwner"
    return "Other"


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    return found.text.strip() if (found is not None and found.text) else None


def _float(el: ET.Element | None, path: str) -> float | None:
    raw = _text(el, path)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _flag(el: ET.Element | None, path: str) -> bool:
    return _text(el, path) == "1"


def _parse_10b5_1(root: ET.Element) -> bool | None:
    """aff10b5One/noAff10b5One pair (SEC schema). aff==1 -> True (planned);
    noAff==1 or aff==0 -> False; both absent -> None."""
    aff = _text(root, "aff10b5One")
    noaff = _text(root, "noAff10b5One")
    if aff == "1":
        return True
    if noaff == "1":
        return False
    if aff == "0":
        return False
    return None


def parse_form4(xml: str) -> list[InsiderTransaction]:
    """One reporting owner per Form-4; iterate non-derivative + derivative tables."""
    root = ET.fromstring(xml)
    owner = root.find("reportingOwner")
    owner_name = _text(owner, "reportingOwnerId/rptOwnerName") or "Unknown"
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    is_director = _flag(rel, "isDirector")
    is_officer = _flag(rel, "isOfficer")
    is_ten_pct = _flag(rel, "isTenPercentOwner")
    officer_title = _text(rel, "officerTitle")
    role = derive_role(officer_title, is_director, is_officer, is_ten_pct)
    is_10b5_1 = _parse_10b5_1(root)

    txns: list[InsiderTransaction] = []
    for table, tag, is_deriv in (
        ("nonDerivativeTable", "nonDerivativeTransaction", False),
        ("derivativeTable", "derivativeTransaction", True),
    ):
        tbl = root.find(table)
        if tbl is None:
            continue
        for tx in tbl.findall(tag):
            code = _text(tx, "transactionCoding/transactionCode") or ""
            shares = _float(tx, "transactionAmounts/transactionShares/value")
            price = _float(tx, "transactionAmounts/transactionPricePerShare/value")
            value = (
                shares * price
                if (shares is not None and price is not None)
                else None
            )
            txns.append(
                InsiderTransaction(
                    owner_name=owner_name,
                    role=role,
                    officer_title=officer_title,
                    is_director=is_director,
                    is_officer=is_officer,
                    is_ten_pct=is_ten_pct,
                    date=_text(tx, "transactionDate/value"),
                    code=code,
                    bucket=classify_bucket(code, is_deriv),
                    shares=shares,
                    price=price,
                    value=value,
                    acquired_disposed=_text(
                        tx, "transactionAmounts/transactionAcquiredDisposedCode/value"
                    ),
                    security_title=_text(tx, "securityTitle/value"),
                    is_derivative=is_deriv,
                    shares_after=_float(
                        tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"
                    ),
                    direct_or_indirect=_text(
                        tx, "ownershipNature/directOrIndirectOwnership/value"
                    ),
                    is_10b5_1=is_10b5_1,
                )
            )
    return txns
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_insider_parser.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/insider_parser.py tests/deepdive/test_insider_parser.py
git commit -m "Add Form-4 XML parser with bucket/role/10b5-1 classification"
```

---

## Task 3: Netting & significance summary

**Files:**
- Create: `app/deepdive/insider_summary.py`
- Test: `tests/deepdive/test_insider_summary.py`

- [ ] **Step 1: Write the failing test**

Create `tests/deepdive/test_insider_summary.py`:

```python
from app.deepdive.insider_summary import compute_insider_summary
from app.models.deep_dive_record import InsiderTransaction


def _t(owner, role, code, bucket, value, ad, **kw):
    return InsiderTransaction(
        owner_name=owner, role=role, code=code, bucket=bucket,
        value=value, acquired_disposed=ad, **kw
    )


def test_three_bucket_netting_and_reconciliation():
    txns = [
        _t("A", "CEO", "P", "buy", 500_000, "A"),        # buy: always significant
        _t("B", "Officer", "S", "sell", 2_000_000, "D"), # sell >1M: significant
        _t("C", "Officer", "S", "sell", 300_000, "D"),   # sell <1M, not CEO/CFO: immaterial
        _t("D", "Officer", "F", "routine", None, "D"),   # routine
    ]
    s = compute_insider_summary(
        txns, coverage_state="ok", n_filings_total=4, n_parsed=4
    )
    assert len(s.significant_buys) == 1
    assert len(s.significant_sells) == 1
    assert s.immaterial_sell_count == 1
    assert s.routine_count == 1
    # reconciliation invariant
    assert s.n_transactions_total == (
        len(s.significant_buys) + len(s.significant_sells)
        + s.immaterial_sell_count + s.routine_count
    )
    assert s.net_buy_value == 500_000
    assert s.net_sell_value == 2_000_000


def test_ceo_sell_significant_regardless_of_value():
    txns = [_t("X", "CFO", "S", "sell", 50_000, "D")]
    s = compute_insider_summary(txns, coverage_state="ok", n_filings_total=1, n_parsed=1)
    assert len(s.significant_sells) == 1 and s.immaterial_sell_count == 0


def test_per_owner_aggregate_marks_all_constituents():
    txns = [
        _t("Y", "Officer", "S", "sell", 400_000, "D"),
        _t("Y", "Officer", "S", "sell", 400_000, "D"),
        _t("Y", "Officer", "S", "sell", 400_000, "D"),  # aggregate 1.2M > 1M
    ]
    s = compute_insider_summary(txns, coverage_state="ok", n_filings_total=3, n_parsed=3)
    assert len(s.significant_sells) == 3
    assert s.immaterial_sell_count == 0
    assert all(t.significant for t in s.significant_sells)


def test_by_role_aggregation():
    txns = [
        _t("A", "CEO", "P", "buy", 1_000_000, "A"),
        _t("B", "CFO", "S", "sell", 2_000_000, "D"),
    ]
    s = compute_insider_summary(txns, coverage_state="ok", n_filings_total=2, n_parsed=2)
    assert s.by_role["CEO"]["buy"] == 1_000_000
    assert s.by_role["CFO"]["sell"] == 2_000_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_insider_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.insider_summary'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/deepdive/insider_summary.py`:

```python
from __future__ import annotations

from app.models.deep_dive_record import (
    InsiderCoverage,
    InsiderSummary,
    InsiderTransaction,
)

# Single source of truth for the absolute significance floor. Tunable; the
# pre-netting cache (insider_cache) lets a re-net pick up a changed value
# without refetching Form-4 XML.
INSIDER_SIGNIFICANCE_USD = 1_000_000.0


def compute_insider_summary(
    transactions: list[InsiderTransaction],
    *,
    coverage_state: InsiderCoverage,
    n_filings_total: int,
    n_parsed: int,
    window_label: str = "letzte 12 Monate",
) -> InsiderSummary:
    # per-owner aggregate of discretionary sell value (for the aggregate trigger)
    owner_sell_total: dict[str, float] = {}
    for t in transactions:
        if t.bucket == "sell" and t.value is not None:
            owner_sell_total[t.owner_name] = (
                owner_sell_total.get(t.owner_name, 0.0) + abs(t.value)
            )

    sig_buys: list[InsiderTransaction] = []
    sig_sells: list[InsiderTransaction] = []
    immaterial = 0
    routine = 0
    for t in transactions:
        if t.bucket == "buy":
            t.significant = True
            sig_buys.append(t)
        elif t.bucket == "sell":
            sig = (
                (t.value is not None and abs(t.value) > INSIDER_SIGNIFICANCE_USD)
                or t.role in ("CEO", "CFO")
                or owner_sell_total.get(t.owner_name, 0.0) > INSIDER_SIGNIFICANCE_USD
            )
            t.significant = sig
            if sig:
                sig_sells.append(t)
            else:
                immaterial += 1
        else:
            routine += 1

    net_buy = sum(
        t.value for t in sig_buys
        if t.value is not None and t.acquired_disposed == "A"
    )
    net_sell = sum(
        t.value for t in sig_sells
        if t.value is not None and t.acquired_disposed == "D"
    )
    by_role: dict[str, dict[str, float]] = {}
    for t in sig_buys:
        if t.value is not None and t.acquired_disposed == "A":
            by_role.setdefault(t.role, {"buy": 0.0, "sell": 0.0})["buy"] += t.value
    for t in sig_sells:
        if t.value is not None and t.acquired_disposed == "D":
            by_role.setdefault(t.role, {"buy": 0.0, "sell": 0.0})["sell"] += t.value

    return InsiderSummary(
        coverage_state=coverage_state,
        window_label=window_label,
        n_filings_total=n_filings_total,
        n_parsed=n_parsed,
        n_transactions_total=len(transactions),
        significant_buys=sig_buys,
        significant_sells=sig_sells,
        immaterial_sell_count=immaterial,
        routine_count=routine,
        net_buy_value=float(net_buy),
        net_sell_value=float(net_sell),
        by_role=by_role,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_insider_summary.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/insider_summary.py tests/deepdive/test_insider_summary.py
git commit -m "Add insider netting/significance summary with reconciliation"
```

---

## Task 4: EDGAR client — Form-4 index & document

**Files:**
- Modify: `app/services/edgar_client.py`
- Test: `tests/services/test_edgar_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/services/test_edgar_client.py` (add `from unittest.mock import patch` / `MagicMock` at top if absent):

```python
from app.services.edgar_client import EdgarClientImpl, Form4Ref


def _client():
    return EdgarClientImpl(user_agent="FisherScreen test test@example.com")


def test_get_form4_index_filters_form_and_date():
    c = _client()
    payload = {"filings": {"recent": {
        "form": ["10-K", "4", "4", "8-K"],
        "accessionNumber": ["a0", "a1", "a2", "a3"],
        "primaryDocument": ["d0", "xslF345X06/d1.xml", "d2.xml", "d3"],
        "filingDate": ["2026-05-01", "2026-04-01", "2024-01-01", "2026-03-01"],
    }}}
    with patch.object(c, "_get", return_value=payload):
        refs = c.get_form4_index("789019", since="2025-06-01")
    assert [r.accession_number for r in refs] == ["a1"]  # a2 too old, others not form 4
    assert refs[0].primary_document == "xslF345X06/d1.xml"


def test_get_form4_document_strips_xsl_prefix():
    c = _client()
    captured = {}

    def fake_text(url):
        captured["url"] = url
        return "<ownershipDocument/>"

    with patch.object(c, "_get_text", side_effect=fake_text):
        xml = c.get_form4_document("789019", "0000789019-26-000075", "xslF345X06/form4.xml")
    assert xml == "<ownershipDocument/>"
    assert captured["url"].endswith("/000078901926000075/form4.xml")
    assert "xslF345X06" not in captured["url"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/services/test_edgar_client.py::test_get_form4_index_filters_form_and_date -v`
Expected: FAIL — `ImportError: cannot import name 'Form4Ref'`.

- [ ] **Step 3: Write minimal implementation**

In `app/services/edgar_client.py`, after the `RawFiling` dataclass, add:

```python
@dataclass(frozen=True)
class Form4Ref:
    accession_number: str
    primary_document: str
    filing_date: str
```

In the `EdgarClient` Protocol, add:

```python
    def get_form4_index(self, cik: str, since: str) -> list["Form4Ref"]: ...
    def get_form4_document(
        self, cik: str, accession_number: str, primary_document: str
    ) -> str: ...
```

In `EdgarClientImpl`, add these methods:

```python
    def get_form4_index(self, cik: str, since: str) -> list[Form4Ref]:
        """Form-4 refs filed on/after `since` (ISO date). Deliberate single
        re-fetch of submissions.json (negligible vs the N per-XML pulls)."""
        padded = cik.zfill(10)
        data = self._get(f"{self._SEC_BASE}/submissions/CIK{padded}.json")
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        dates = recent.get("filingDate", [])
        refs: list[Form4Ref] = []
        oldest: str | None = None
        for i, form in enumerate(forms):
            d = dates[i] if i < len(dates) else None
            if d and (oldest is None or d < oldest):
                oldest = d
            if form == "4" and d and d >= since:
                refs.append(Form4Ref(accs[i], docs[i], d))
        if oldest is not None and oldest > since:
            logger.warning(
                "edgar: form-4 window starts %s but oldest recent filing is %s "
                "(cik=%s) — older Form-4 not in recent (files-overflow not implemented)",
                since, oldest, cik,
            )
        return refs

    def get_form4_document(
        self, cik: str, accession_number: str, primary_document: str
    ) -> str:
        """Raw Form-4 XML. primaryDocument is the xslF.../ HTML render path;
        strip the prefix to reach the raw .xml in the same accession folder."""
        cik_int = str(int(cik))
        acc_nodash = accession_number.replace("-", "")
        raw_doc = primary_document.split("/")[-1]
        url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik_int}/{acc_nodash}/{raw_doc}"
        )
        return self._get_text(url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/services/test_edgar_client.py -v`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add app/services/edgar_client.py tests/services/test_edgar_client.py
git commit -m "Add EDGAR get_form4_index/get_form4_document"
```

---

## Task 5: Cache & fetcher with coverage states

**Files:**
- Create: `app/deepdive/insider_cache.py`
- Test: `tests/deepdive/test_insider_cache.py`

- [ ] **Step 1: Write the failing test**

Create `tests/deepdive/test_insider_cache.py`:

```python
from pathlib import Path

from app.deepdive.insider_cache import CachedInsiderFetcher
from app.errors import DataSourceError
from app.services.edgar_client import Form4Ref

_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>EVP</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>100</value></transactionShares>
      <transactionPricePerShare><value>10</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>
"""


class _FakeEdgar:
    def __init__(self, refs, docs=None, index_raises=False):
        self._refs = refs
        self._docs = docs or {}
        self._index_raises = index_raises
        self.doc_calls = 0

    def get_form4_index(self, cik, since):
        if self._index_raises:
            raise DataSourceError("index boom")
        return self._refs

    def get_form4_document(self, cik, accession_number, primary_document):
        self.doc_calls += 1
        if accession_number not in self._docs:
            raise DataSourceError("doc boom")
        return self._docs[accession_number]


def _fetcher(tmp_path, edgar):
    return CachedInsiderFetcher(edgar=edgar, cache_dir=tmp_path)


def test_empty_index_is_empty_not_fetch_failed(tmp_path):
    res = _fetcher(tmp_path, _FakeEdgar([])).get_summary_input("1", "2025-01-01")
    assert res.coverage_state == "empty"
    assert res.n_filings_total == 0 and res.n_parsed == 0


def test_all_xml_fail_is_fetch_failed_not_empty(tmp_path):
    refs = [Form4Ref("a1", "form4.xml", "2026-01-01")]
    res = _fetcher(tmp_path, _FakeEdgar(refs, docs={})).get_summary_input("1", "2025-01-01")
    assert res.coverage_state == "fetch_failed"
    assert res.n_filings_total == 1 and res.n_parsed == 0


def test_partial_when_some_xml_fail(tmp_path):
    refs = [Form4Ref("a1", "form4.xml", "2026-01-01"),
            Form4Ref("a2", "form4.xml", "2026-02-01")]
    edgar = _FakeEdgar(refs, docs={"a1": _XML})  # a2 missing -> fails
    res = _fetcher(tmp_path, edgar).get_summary_input("1", "2025-01-01")
    assert res.coverage_state == "partial"
    assert res.n_filings_total == 2 and res.n_parsed == 1
    assert len(res.transactions) == 1


def test_ok_and_accession_cache_hit_skips_refetch(tmp_path):
    refs = [Form4Ref("a1", "form4.xml", "2026-01-01")]
    edgar = _FakeEdgar(refs, docs={"a1": _XML})
    f = _fetcher(tmp_path, edgar)
    r1 = f.get_summary_input("1", "2025-01-01")
    assert r1.coverage_state == "ok" and edgar.doc_calls == 1
    r2 = f.get_summary_input("1", "2025-01-01")  # second run: cache hit
    assert r2.coverage_state == "ok" and edgar.doc_calls == 1  # no second fetch


def test_index_error_propagates_for_pipeline_failsoft(tmp_path):
    import pytest
    edgar = _FakeEdgar([], index_raises=True)
    with pytest.raises(DataSourceError):
        _fetcher(tmp_path, edgar).get_summary_input("1", "2025-01-01")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_insider_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.insider_cache'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/deepdive/insider_cache.py`:

```python
from __future__ import annotations

import json
import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.deepdive.insider_parser import parse_form4
from app.errors import DataSourceError
from app.models.deep_dive_record import InsiderCoverage, InsiderTransaction

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient

logger = logging.getLogger(__name__)

# bump on any Add/Remove/Rename of a read-path InsiderTransaction field.
INSIDER_CACHE_SCHEMA_VERSION = 1


@dataclass
class InsiderFetchResult:
    transactions: list[InsiderTransaction] = field(default_factory=list)
    coverage_state: InsiderCoverage = "empty"
    n_filings_total: int = 0
    n_parsed: int = 0


class CachedInsiderFetcher:
    """Accession-keyed, immutable, pre-netting Form-4 cache.
    cache/insider/<cik>/<accession>.json. Form-4 are immutable after filing ->
    no TTL freshness check, only a schema_version gate. The accession LIST is
    re-derived each run from submissions.json (picks up new filings)."""

    def __init__(self, edgar: "EdgarClient", cache_dir: Path) -> None:
        self._edgar = edgar
        self._dir = Path(cache_dir)

    def get_summary_input(
        self, cik: str, since: str, use_cache: bool = True
    ) -> InsiderFetchResult:
        # Index errors propagate -> the pipeline's fail-soft wrap turns them into
        # coverage_state="fetch_failed". Per-XML errors are caught below.
        refs = self._edgar.get_form4_index(cik, since)
        n_total = len(refs)
        if n_total == 0:
            return InsiderFetchResult([], "empty", 0, 0)
        txns: list[InsiderTransaction] = []
        n_parsed = 0
        for ref in refs:
            try:
                txns.extend(self._load_or_fetch(cik, ref, use_cache))
                n_parsed += 1
            except (DataSourceError, ET.ParseError, ValidationError) as exc:
                logger.warning(
                    "insider: skip accession %s (%s)", ref.accession_number, exc
                )
        if n_parsed == 0:
            return InsiderFetchResult([], "fetch_failed", n_total, 0)
        state: InsiderCoverage = "ok" if n_parsed == n_total else "partial"
        return InsiderFetchResult(txns, state, n_total, n_parsed)

    def _load_or_fetch(
        self, cik: str, ref, use_cache: bool
    ) -> list[InsiderTransaction]:
        path = self._dir / cik / f"{ref.accession_number}.json"
        if use_cache:
            cached = self._load(path)
            if cached is not None:
                return [InsiderTransaction(**t) for t in cached]
        xml = self._edgar.get_form4_document(
            cik, ref.accession_number, ref.primary_document
        )
        txns = parse_form4(xml)
        if use_cache:
            self._write(path, txns)
        return txns

    def _load(self, path: Path) -> list[dict] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("insider cache: corrupt %s (%s) — cache miss", path, exc)
            return None
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != INSIDER_CACHE_SCHEMA_VERSION
        ):
            return None
        return data.get("transactions", [])

    def _write(self, path: Path, txns: list[InsiderTransaction]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": INSIDER_CACHE_SCHEMA_VERSION,
            "_cached_at": datetime.now(timezone.utc).isoformat(),
            "transactions": [t.model_dump() for t in txns],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_insider_cache.py -v`
Expected: PASS (5 tests) — note the critical `empty` ≠ `fetch_failed` pair.

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/insider_cache.py tests/deepdive/test_insider_cache.py
git commit -m "Add accession-keyed insider cache + fetcher with coverage states"
```

---

## Task 6: Renderer (insider_block)

**Files:**
- Create: `app/deepdive/insider_block.py`
- Test: `tests/deepdive/test_insider_block.py`

- [ ] **Step 1: Write the failing test**

Create `tests/deepdive/test_insider_block.py`:

```python
from app.deepdive.insider_block import render_insider_block, insider_coverage_label
from app.models.deep_dive_record import InsiderSummary, InsiderTransaction


def test_fpi_and_skipped_and_failed_and_empty_states():
    assert "nicht anwendbar" in render_insider_block(
        InsiderSummary(coverage_state="fpi_exempt"), "20-F")
    assert "--no-insider" in render_insider_block(
        InsiderSummary(coverage_state="skipped"), "10-K")
    failed = render_insider_block(
        InsiderSummary(coverage_state="fetch_failed", n_filings_total=122), "10-K")
    assert "fehlgeschlagen" in failed and "kein Urteil" in failed
    empty = render_insider_block(InsiderSummary(coverage_state="empty"), "10-K")
    assert "0 Form-4" in empty


def test_ok_denominator_line_uses_explicit_units():
    s = InsiderSummary(
        coverage_state="ok", n_filings_total=122, n_parsed=122,
        n_transactions_total=140, immaterial_sell_count=10, routine_count=127,
        significant_sells=[InsiderTransaction(
            owner_name="Doe Jane", role="CFO", code="S", bucket="sell",
            date="2026-05-14", shares=1000, price=400.0, value=400_000,
            acquired_disposed="D", shares_after=9000, direct_or_indirect="D",
            is_10b5_1=True, significant=True)],
        significant_buys=[InsiderTransaction(
            owner_name="Roe Sam", role="CEO", code="P", bucket="buy",
            shares=500, price=400.0, value=200_000, acquired_disposed="A",
            shares_after=1500, direct_or_indirect="D", significant=True)],
    )
    out = render_insider_block(s, "10-K")
    assert "122 Form-4-Filings" in out and "140 Transaktionen" in out
    assert "2 signifikant" in out  # 1 buy + 1 sell
    assert "10 immateriell" in out and "127 Routine" in out
    assert "−10%" in out          # sell: 1000/(9000+1000)
    assert "+50%" in out          # buy: 500/(1500-500)
    assert "10b5-1-geplant" in out


def test_percent_suffix_failsoft_omits_on_indirect_or_missing():
    s = InsiderSummary(
        coverage_state="ok", n_filings_total=1, n_parsed=1, n_transactions_total=1,
        significant_sells=[InsiderTransaction(
            owner_name="X", role="CFO", code="S", bucket="sell",
            shares=1000, price=400.0, value=400_000, acquired_disposed="D",
            shares_after=9000, direct_or_indirect="I", significant=True)],
    )
    assert "%" not in render_insider_block(s, "10-K").split("Transaktionen")[1]


def test_coverage_label_states():
    assert "nicht anwendbar" in insider_coverage_label(
        InsiderSummary(coverage_state="fpi_exempt"))
    assert "übersprungen" in insider_coverage_label(
        InsiderSummary(coverage_state="skipped"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_insider_block.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.insider_block'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/deepdive/insider_block.py`:

```python
from __future__ import annotations

from app.models.deep_dive_record import InsiderSummary, InsiderTransaction

_HEAD = "**Insider-Transaktionen:**"


def _money(v: float | None) -> str:
    return f"{v:,.0f}" if v is not None else "n/a"


def _pct_suffix(t: InsiderTransaction) -> str:
    """Sign coupled to acquired/disposed; only for direct holdings with a valid
    denominator. Omitted otherwise (no misleading number)."""
    if t.shares is None or t.shares_after is None or t.direct_or_indirect != "D":
        return ""
    if t.acquired_disposed == "D":
        pre = t.shares_after + t.shares
        if pre <= 0:
            return ""
        return f" — hält nun {_money(t.shares_after)} = −{t.shares / pre:.0%} der direkten Holdings"
    if t.acquired_disposed == "A":
        pre = t.shares_after - t.shares
        if pre <= 0:
            return ""
        return f" — hält nun {_money(t.shares_after)} = +{t.shares / pre:.0%} der direkten Holdings"
    return ""


def _b5_suffix(t: InsiderTransaction) -> str:
    if t.is_10b5_1 is True:
        return " (10b5-1-geplant)"
    if t.is_10b5_1 is False:
        return " (ungeplant)"
    return ""


def _tx_line(t: InsiderTransaction) -> str:
    base = (
        f"{t.owner_name} ({t.role}) {t.date or '?'}: {t.code} "
        f"{_money(t.shares)} @ {t.price if t.price is not None else 'n/a'} "
        f"= {_money(t.value)}"
    )
    return f"- {base}{_pct_suffix(t)}{_b5_suffix(t)}"


def render_insider_block(summary: InsiderSummary | None, form_type: str) -> str:
    if summary is None or summary.coverage_state == "fpi_exempt":
        return (
            f"{_HEAD} nicht anwendbar (Foreign Private Issuer, "
            f"Section-16-exempt — kein Form-4)."
        )
    cs = summary.coverage_state
    win = summary.window_label
    if cs == "skipped":
        return f"{_HEAD} übersprungen (`--no-insider`)."
    if cs == "fetch_failed":
        return (
            f"{_HEAD} Fetch fehlgeschlagen "
            f"({summary.n_parsed}/{summary.n_filings_total} XMLs) — "
            f"kein Urteil möglich (nicht „kein Signal")."
        )
    if cs == "empty":
        return (
            f"{_HEAD} 0 Form-4 in {win} (für einen US-Filer auffällig — "
            f"ggf. Datenlücke)."
        )
    # ok / partial
    n_sig = len(summary.significant_buys) + len(summary.significant_sells)
    parsed_note = (
        f" · {summary.n_parsed} von {summary.n_filings_total} geparst"
        if cs == "partial" else ""
    )
    header = (
        f"{_HEAD} {summary.n_filings_total} Form-4-Filings · darin "
        f"{summary.n_transactions_total} Transaktionen → {n_sig} signifikant "
        f"({len(summary.significant_buys)} Käufe, "
        f"{len(summary.significant_sells)} Verkäufe) · "
        f"{summary.immaterial_sell_count} immateriell · "
        f"{summary.routine_count} Routine (A/M/F/G){parsed_note}"
    )
    lines = [header]
    for t in summary.significant_buys + summary.significant_sells:
        lines.append(_tx_line(t))
    return "\n".join(lines)


def insider_coverage_label(summary: InsiderSummary | None) -> str:
    """One-line SourceCoverage.insider value."""
    if summary is None or summary.coverage_state == "fpi_exempt":
        return "nicht anwendbar (FPI, Section-16-exempt)"
    cs = summary.coverage_state
    if cs == "skipped":
        return "übersprungen (--no-insider)"
    if cs == "fetch_failed":
        return f"Fetch fehlgeschlagen ({summary.n_parsed}/{summary.n_filings_total})"
    if cs == "empty":
        return "0 Form-4 in 12M (auffällig für US-Filer)"
    n_sig = len(summary.significant_buys) + len(summary.significant_sells)
    return (
        f"12M Form-4: {summary.n_parsed}/{summary.n_filings_total} geparst, "
        f"{n_sig} signifikant ({len(summary.significant_buys)} Käufe, "
        f"{len(summary.significant_sells)} Verkäufe)"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_insider_block.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/insider_block.py tests/deepdive/test_insider_block.py
git commit -m "Add insider_block renderer + coverage label"
```

---

## Task 7: Synthesis integration (Form-4 marker, P15 floor, prompt block)

**Files:**
- Modify: `app/deepdive/synthesis.py`
- Test: `tests/deepdive/test_synthesis.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/deepdive/test_synthesis.py`:

```python
from app.deepdive.synthesis import _p15_floor, _normalize_sources, _build_user_prompt
from app.models.deep_dive_record import InsiderSummary


def test_p15_floor_three_tier():
    assert _p15_floor(None) == "🔴"
    assert _p15_floor(InsiderSummary(coverage_state="empty")) == "🔴"
    assert _p15_floor(InsiderSummary(coverage_state="fetch_failed")) == "🔴"
    assert _p15_floor(InsiderSummary(coverage_state="fpi_exempt")) == "🔴"
    assert _p15_floor(InsiderSummary(coverage_state="partial", n_parsed=3)) == "🟡"
    assert _p15_floor(InsiderSummary(coverage_state="ok", n_parsed=5)) is None


def test_form4_marker_recognized_not_inferenz():
    assert _normalize_sources(["Form-4"]) == ["Form-4"]


def test_insider_block_present_in_prompt():
    from app.models.deep_dive_record import (
        PointInTimeQuant, QuantSnapshot, HistoricalSeries, TrendMetrics,
    )
    qs = QuantSnapshot(
        point_in_time=PointInTimeQuant(ticker="X"),
        historical_series=HistoricalSeries(), trend_metrics=TrendMetrics())
    prompt = _build_user_prompt(
        "X", "10-K", {}, qs, filing_date=None,
        insider_summary=InsiderSummary(coverage_state="fpi_exempt"))
    assert "Insider-Transaktionen" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py::test_p15_floor_three_tier -v`
Expected: FAIL — `ImportError: cannot import name '_p15_floor'`.

- [ ] **Step 3: Write minimal implementation**

In `app/deepdive/synthesis.py`:

(a) Add the import near the top:

```python
from app.deepdive.insider_block import render_insider_block
from app.models.deep_dive_record import FisherPoint, QuantSnapshot, InsiderSummary
```

(Replace the existing `from app.models.deep_dive_record import FisherPoint, QuantSnapshot` line with the one above.)

(b) Add `Form-4` to the soft-marker vocabulary:

```python
_SOFT_MARKER_VOCAB = ("yfinance, 5J", "Marktkontext", "Inferenz", "Form-4")
```

(c) Add the floor helper (after `_format_vintage_hint`):

```python
def _p15_floor(summary: InsiderSummary | None) -> str | None:
    """Code-decided P15 confidence floor by evidence strength (2a.3 hybrid).
    Returns the cap char to enforce, or None for 'no floor' (model is free)."""
    if summary is None:
        return "🔴"
    if summary.coverage_state == "ok" and summary.n_parsed > 0:
        return None
    if summary.coverage_state == "partial":
        return "🟡"
    return "🔴"
```

(d) Change `_build_user_prompt` to accept and render the insider block. Replace the signature and body:

```python
def _build_user_prompt(
    ticker: str,
    form_type: str,
    sections: dict[str, str],
    quant: QuantSnapshot,
    filing_date: str | None = None,
    insider_summary: InsiderSummary | None = None,
) -> str:
    titles = "\n".join(f"{n}. {t}" for n, t in FISHER_POINTS)
    sec_txt = "\n\n".join(
        f"### {_section_label(k)}\n{v}" for k, v in sections.items()
    ) or "(keine Filing-Sections extrahiert)"
    days = _days_since_filing(filing_date)
    vintage = _format_vintage_line(filing_date, days)
    hint = _format_vintage_hint(days)
    vintage_block = f"{vintage}\n{hint}" if hint else vintage
    insider_block = render_insider_block(insider_summary, form_type)
    return (
        f"Ticker: {ticker} (Filing-Typ {form_type})\n\n"
        f"Fishers 15 Punkte:\n{titles}\n\n"
        f"Quant-Snapshot (JSON):\n{quant.model_dump_json()}\n\n"
        f"{render_valuation_block(quant)}\n\n"
        f"{insider_block}\n\n"
        f"{vintage_block}\n\n"
        f"Filing-Sections:\n{sec_txt}"
    )
```

(e) Add `insider_summary` to `run_synthesis` signature and pass it through; change the P14/P15 logic. In `run_synthesis`, change the signature to add the param after `filing_date`:

```python
def run_synthesis(
    *,
    ticker: str,
    form_type: str,
    sections: dict[str, str],
    quant: QuantSnapshot,
    synthesizer: DeepDiveSynthesizer,
    max_input_tokens: int,
    filing_date: str | None = None,
    insider_summary: InsiderSummary | None = None,
) -> list[FisherPoint]:
    system = _SYSTEM_PROMPT
    user = _build_user_prompt(
        ticker, form_type, sections, quant, filing_date, insider_summary
    )
```

Then replace the existing block:

```python
        if rp.get("number") in (14, 15):
            rp = {**rp, "confidence": "🔴"}
```

with:

```python
        # P14: candor needs language data (B.4) -> still hard 🔴.
        # P15: integrity now has a hard source (Form-4); floor by evidence
        # strength, code-decided (not model judgement).
        if rp.get("number") == 14:
            rp = {**rp, "confidence": "🔴"}
        elif rp.get("number") == 15:
            floor = _p15_floor(insider_summary)
            if floor == "🔴":
                rp = {**rp, "confidence": "🔴"}
            elif floor == "🟡" and rp.get("confidence") == "🟢":
                rp = {**rp, "confidence": "🟡"}
```

(f) Update the system-prompt CONFIDENCE line. In `_SYSTEM_PROMPT`, replace:

```
    "(Filing-Section oder Quant) belegbar ist. Inferenz, Allgemeinwissen oder "
    "Marktkontext ⇒ höchstens 🟡. Punkte 14 und 15 ohne Sprach-/Insider-Daten "
    "⇒ 🔴.\n"
```

with:

```
    "(Filing-Section oder Quant) belegbar ist. Inferenz, Allgemeinwissen oder "
    "Marktkontext ⇒ höchstens 🟡. Punkt 14 ohne Sprachdaten ⇒ 🔴. Punkt 15 "
    "(Integrität): nutze den Insider-Block — Open-Market-Käufe (P) sind ein "
    "starkes Alignment-Signal, ungewöhnlich große Verkäufe Vorsicht, "
    "Routine-RSU-Vesting/Steuer-Einbehalt NICHT überinterpretieren; bei "
    "'nicht anwendbar'/keinen Daten bleibt P15 🔴 = fehlende Quelle, kein "
    "Negativ-Urteil. Insider-belegte Aussagen markieren mit 'Form-4'.\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -v`
Expected: PASS (new + existing). If an existing test calls `_build_user_prompt` positionally with the old arity, it still works (new param defaults to None).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/synthesis.py tests/deepdive/test_synthesis.py
git commit -m "Wire insider summary into synthesis (P15 floor, Form-4 marker, prompt block)"
```

---

## Task 8: Config + compose builder

**Files:**
- Modify: `app/config.py`
- Modify: `app/deepdive/compose.py`
- Test: `tests/deepdive/test_compose.py` (create if absent)

- [ ] **Step 1: Write the failing test**

Create/append `tests/deepdive/test_compose.py`:

```python
from app.deepdive.compose import build_insider_fetcher
from app.deepdive.insider_cache import CachedInsiderFetcher
from app.config import settings


def test_build_insider_fetcher_returns_cached_fetcher():
    f = build_insider_fetcher()
    assert isinstance(f, CachedInsiderFetcher)


def test_insider_lookback_setting_default():
    assert settings.insider_lookback_days == 365
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_compose.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_insider_fetcher'`.

- [ ] **Step 3: Write minimal implementation**

In `app/config.py`, after `historical_cache_ttl_days: int = 90`, add:

```python
    insider_lookback_days: int = 365
```

In `app/deepdive/compose.py`: add to the `__all__` list the string `"build_insider_fetcher"`; add the cache-dir constant next to the others:

```python
_INSIDER_CACHE_DIR = Path("cache/insider")
```

add the import:

```python
from app.deepdive.insider_cache import CachedInsiderFetcher
```

and add the builder:

```python
def build_insider_fetcher() -> CachedInsiderFetcher:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    return CachedInsiderFetcher(edgar=edgar, cache_dir=_INSIDER_CACHE_DIR)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_compose.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/deepdive/compose.py tests/deepdive/test_compose.py
git commit -m "Add insider_lookback_days setting + build_insider_fetcher"
```

---

## Task 9: Pipeline stage [2b]

**Files:**
- Modify: `app/deepdive/pipeline.py`
- Test: `tests/deepdive/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/deepdive/test_pipeline.py` (reuse the file's existing fakes/fixtures; this test injects a fake insider fetcher). If the file has a helper to run the pipeline, mirror it; otherwise this self-contained test:

```python
from app.deepdive import pipeline as pipeline_mod


def test_pipeline_fpi_skips_insider_fetch(monkeypatch, tmp_path):
    """A 20-F filer must never call the insider fetcher; summary is fpi_exempt."""
    captured = {}

    class _Fetcher:
        def get_summary_input(self, *a, **k):
            captured["called"] = True
            raise AssertionError("must not be called for 20-F")

    # build the InsiderSummary the stage should produce for a 20-F filer
    from app.models.deep_dive_record import InsiderSummary
    summary = pipeline_mod._build_insider_summary(
        cik="123", form_type="20-F", no_insider=False,
        insider_fetcher=_Fetcher(), use_cache=True, lookback_days=365,
    )
    assert summary.coverage_state == "fpi_exempt"
    assert "called" not in captured


def test_pipeline_no_insider_flag_skips(tmp_path):
    class _Fetcher:
        def get_summary_input(self, *a, **k):
            raise AssertionError("must not be called when no_insider")
    summary = pipeline_mod._build_insider_summary(
        cik="123", form_type="10-K", no_insider=True,
        insider_fetcher=_Fetcher(), use_cache=True, lookback_days=365,
    )
    assert summary.coverage_state == "skipped"


def test_pipeline_insider_failsoft_on_datasource_error():
    from app.errors import DataSourceError

    class _Fetcher:
        def get_summary_input(self, *a, **k):
            raise DataSourceError("index boom")
    summary = pipeline_mod._build_insider_summary(
        cik="123", form_type="10-K", no_insider=False,
        insider_fetcher=_Fetcher(), use_cache=True, lookback_days=365,
    )
    assert summary.coverage_state == "fetch_failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_pipeline.py::test_pipeline_fpi_skips_insider_fetch -v`
Expected: FAIL — `AttributeError: module 'app.deepdive.pipeline' has no attribute '_build_insider_summary'`.

- [ ] **Step 3: Write minimal implementation**

In `app/deepdive/pipeline.py`, add imports:

```python
from datetime import date, timedelta

from app.deepdive.insider_block import insider_coverage_label
from app.deepdive.insider_summary import compute_insider_summary
from app.errors import DataSourceError, DeepDiveError
from app.models.deep_dive_record import DeepDiveRecord, InsiderSummary
```

(Merge with the existing `DeepDiveError` / `DeepDiveRecord` imports — do not duplicate.)

Add the helper (above `run_deep_dive`):

```python
def _build_insider_summary(
    *,
    cik: str,
    form_type: str,
    no_insider: bool,
    insider_fetcher: Any,
    use_cache: bool,
    lookback_days: int,
) -> InsiderSummary:
    """Stage [2b]: additive, fail-soft. NEVER aborts the deep dive — only
    DataSourceError degrades to fetch_failed; logic bugs propagate (fail-loud)."""
    if no_insider:
        return InsiderSummary(coverage_state="skipped")
    if form_type == "20-F":
        return InsiderSummary(coverage_state="fpi_exempt")
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    try:
        res = insider_fetcher.get_summary_input(cik, since, use_cache=use_cache)
    except DataSourceError as exc:
        logger.warning("deepdive: insider stage failed (%s) — fetch_failed", exc)
        return InsiderSummary(coverage_state="fetch_failed")
    return compute_insider_summary(
        res.transactions,
        coverage_state=res.coverage_state,
        n_filings_total=res.n_filings_total,
        n_parsed=res.n_parsed,
    )
```

Add the two new parameters to `run_deep_dive` (after `peer_resolver`):

```python
    insider_fetcher: Any,
    insider_lookback_days: int,
    no_insider: bool = False,
```

Insert stage [2b] after the `# [2] EDGAR-Pull` block:

```python
    # [2b] Insider Form-4 (additive mini-subsystem, fail-soft)
    insider_summary = _build_insider_summary(
        cik=resolved.cik,
        form_type=resolved.form_type,
        no_insider=no_insider,
        insider_fetcher=insider_fetcher,
        use_cache=use_cache,
        lookback_days=insider_lookback_days,
    )
```

In the `# [5] Gemini-Synthesis` call, add `insider_summary=insider_summary,`. After `coverage.edgar = ...` (stage [4]), set the coverage label:

```python
    coverage.insider = insider_coverage_label(insider_summary)
```

In the `DeepDiveRecord(...)` construction, add `insider_summary=insider_summary,`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_pipeline.py -v`
Expected: PASS (3 new + existing). Existing `run_deep_dive` callers in tests need the new required params — if an existing pipeline test breaks on the new `insider_fetcher`/`insider_lookback_days` required args, update that test's call to pass a fake fetcher and `insider_lookback_days=365` (same fail-soft fake as above).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/pipeline.py tests/deepdive/test_pipeline.py
git commit -m "Add insider stage [2b] to deep-dive pipeline (fail-soft)"
```

---

## Task 10: CLI wiring (--no-insider)

**Files:**
- Modify: `app/deepdive/__main__.py`
- Test: `tests/deepdive/test_cli.py` (or the existing CLI test file)

- [ ] **Step 1: Write the failing test**

Append to the existing CLI test file (e.g. `tests/deepdive/test_cli.py` / `test_main.py`):

```python
from app.deepdive.__main__ import build_parser


def test_parser_accepts_no_insider_flag():
    args = build_parser().parse_args(["deepdive", "MSFT", "--no-insider"])
    assert args.no_insider is True


def test_parser_no_insider_defaults_false():
    args = build_parser().parse_args(["deepdive", "MSFT"])
    assert args.no_insider is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_cli.py::test_parser_accepts_no_insider_flag -v`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'no_insider'`.

- [ ] **Step 3: Write minimal implementation**

In `app/deepdive/__main__.py`:

(a) Add the argument in `build_parser` (after `--peer-rationale`):

```python
    deepdive.add_argument(
        "--no-insider",
        action="store_true",
        help="Skip the Form-4 insider stage (faster iteration)",
    )
```

(b) Add the builder import:

```python
from app.deepdive.compose import (
    build_adr_resolver,
    build_filing_fetcher,
    build_insider_fetcher,
    build_peer_resolver,
    build_quant_builder,
    build_synthesizer,
)
```

(c) Pass the new args into `run_deep_dive(...)`:

```python
            insider_fetcher=build_insider_fetcher(),
            insider_lookback_days=settings.insider_lookback_days,
            no_insider=args.no_insider,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/__main__.py tests/deepdive/test_cli.py
git commit -m "Wire insider fetcher + --no-insider into the CLI"
```

---

## Task 11: Dossier section + frontmatter digest

**Files:**
- Modify: `app/deepdive/dossier_generator.py`
- Test: `tests/deepdive/test_dossier_generator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/deepdive/test_dossier_generator.py` (reuse the file's `_record()` helper):

```python
import frontmatter as _fm
from app.models.deep_dive_record import InsiderSummary


def test_dossier_renders_insider_section_and_frontmatter():
    rec = _record()
    rec.insider_summary = InsiderSummary(
        coverage_state="ok", n_filings_total=10, n_parsed=10,
        n_transactions_total=12, net_buy_value=200_000, net_sell_value=0,
    )
    out_dir = rec  # placeholder so reviewer notices: use the test's tmp output dir
```

Replace the placeholder body with the file's real dossier-generation call (mirror an existing test in this file), then assert:

```python
    # after generating the dossier into a tmp dir and reading it back:
    #   text = out.read_text(encoding="utf-8")
    #   post = _fm.loads(text)
    # assert "## Insider-Transaktionen" in text
    # assert post.metadata["insider_coverage_state"] == "ok"
    # assert post.metadata["insider_significant_count"] == 0
    # assert post.metadata["insider_net_buy"] == 200000
```

(Use the exact generate-and-read idiom already present in this test file; the three assertions above are the contract.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_dossier_generator.py::test_dossier_renders_insider_section_and_frontmatter -v`
Expected: FAIL — assertion on missing `## Insider-Transaktionen` / `KeyError: 'insider_coverage_state'`.

- [ ] **Step 3: Write minimal implementation**

In `app/deepdive/dossier_generator.py`:

(a) Add the import:

```python
from app.deepdive.insider_block import render_insider_block
```

(b) Insert the section after the `render_valuation_block(...)` line in the `lines` list (before `"## Fishers 15 Punkte"`):

```python
        "",
        "## Insider-Transaktionen",
        render_insider_block(record.insider_summary, record.form_type),
```

(c) Add the frontmatter digest. In `post.metadata.update({...})`, add:

```python
        "insider_coverage_state": (
            record.insider_summary.coverage_state
            if record.insider_summary else None
        ),
        "insider_n_filings": (
            record.insider_summary.n_filings_total
            if record.insider_summary else None
        ),
        "insider_significant_count": (
            len(record.insider_summary.significant_buys)
            + len(record.insider_summary.significant_sells)
            if record.insider_summary else None
        ),
        "insider_net_buy": (
            record.insider_summary.net_buy_value if record.insider_summary else None
        ),
        "insider_net_sell": (
            record.insider_summary.net_sell_value if record.insider_summary else None
        ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_dossier_generator.py -v`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/dossier_generator.py tests/deepdive/test_dossier_generator.py
git commit -m "Add insider section + frontmatter digest to the dossier"
```

---

## Task 12: Full-suite verification & acceptance prep

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite with coverage**

Run: `uv run python -m pytest`
Expected: All pass; `Required test coverage of 90% reached` (target ≥ the pre-1.4 level, currently 97.12 %). If coverage dipped below 96 %, add focused tests for the uncovered insider lines before proceeding.

- [ ] **Step 2: Black formatting check**

Run: `uv run python -m black --check app/deepdive/insider_parser.py app/deepdive/insider_summary.py app/deepdive/insider_cache.py app/deepdive/insider_block.py`
Expected: `All done!` (or run without `--check` to format, then re-commit).

- [ ] **Step 3: Free end-to-end probe (NO Gemini, NO paid run)**

Build a throwaway probe that exercises `build_insider_fetcher` + `compute_insider_summary` + `render_insider_block` against real MSFT (`cik=789019`) Form-4 over a short window, and prints the rendered block. This verifies the EDGAR wiring, raw-XML strip, parser, netting, and renderer end-to-end deterministically — no model needed. Confirm: denominator line reconciles, significant lines render with sign-correct %-suffix and 10b5-1 annotation.

- [ ] **Step 4: Commit any formatting/coverage follow-ups**

```bash
git add -A
git commit -m "Phase 1.4 insider Form-4: formatting + coverage follow-ups"
```

- [ ] **Step 5: Acceptance gate (separate, manual — NOT part of this plan run)**

A paid Gemini deep-dive on a US 10-K filer (e.g. `uv run python -m app.deepdive deepdive MSFT`) plus a 20-F filer (`NOVO-B.CO`) confirms: P15 confidence lifts off 🔴 for the US filer with insider data, NOVO shows the FPI honest-label and P15 stays 🔴. Stephan judges usefulness. Push (the bundled doc + code commits → one deploy) happens with explicit go AFTER acceptance.

---

## Self-Review (against the spec)

**Spec coverage:** §3 model → T1; §4 EDGAR → T4; §5 cache/coverage-states → T5 (incl. empty≠fetch_failed); §6 parser+netting+significance+role → T2/T3; §6.3 role precedence → T2; §7 renderer (6 states, %-sign, 10b5-1) → T6; §8 P15 floor + Form-4 marker + prompt + system edit → T7; §9 pipeline [2b] fail-soft + FPI + --no-insider → T9/T10; §10 dossier + frontmatter digest → T11; §11 config → T8; §12 TDD targets → covered across T1–T11; §13 deferred (10b5-1 stored-not-netted, %-display-only) honored (no netting/trigger use). 

**Placeholder scan:** T11 Step 1 intentionally points the engineer to this file's existing generate-and-read idiom rather than guessing its fixture API — the three assertions are concrete; this is the one spot requiring the engineer to mirror an existing test, flagged explicitly.

**Type consistency:** `InsiderTransaction`/`InsiderSummary` fields identical across T1/T2/T3/T6/T11; `compute_insider_summary(transactions, *, coverage_state, n_filings_total, n_parsed, window_label)` consistent T3/T9; `get_form4_index`/`get_form4_document`/`Form4Ref` consistent T4/T5; `get_summary_input(cik, since, use_cache)` consistent T5/T9; `_p15_floor` / `render_insider_block` / `insider_coverage_label` consistent T6/T7/T9/T11; coverage literal set identical everywhere.
