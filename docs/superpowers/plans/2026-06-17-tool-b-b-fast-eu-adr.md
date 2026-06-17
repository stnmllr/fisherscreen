# Tool B B-Fast EU-ADR Path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve EU (`"."`) tickers to their US-ADR CIK live via OpenFIGI, so Tool B runs for EU-ADR filers beyond the 5 static-table entries — with a name-sanity-check against false matches.

**Architecture:** New thin `OpenFIGIClient` DI service. A focused `eu_adr_resolution` module does the variant-ladder local-symbol resolution (gated by a `norm_issuer` name-check against the yfinance `longName`), US-ADR line selection, CIK + form detection, and a local JSON cache. `ADRResolver` delegates `"."` tickers to an injected `eu_resolver` callable (built in `compose`). Failure ≠ empty throughout: transient API errors → `DataSourceError`; genuine no-match → `DeepDiveError`.

**Tech Stack:** Python 3.12, httpx (OpenFIGI REST), pytest (DI mocks, `uv run python -m pytest`). Builds on the merged US-path (`ADRResolver(table, edgar)`, `EdgarClient.detect_annual_form`).

**Spec:** `docs/superpowers/brainstorm/2026-06-17-tool-b-b-fast-eu-adr.md` (ADR-EU-1..5). **Source method:** `docs/superpowers/audits/2026-06-05-dual-line-sweep/classify_dual_line.py` (`norm_issuer`, `issuer_name`, `SUFFIX_HOME_EXCH`).

---

## File Structure & Interfaces (locked here, referenced by tasks)

| Datei | Verantwortung | Aktion |
|---|---|---|
| `app/services/openfigi_client.py` | `OpenFIGIClient` Protocol + Impl: `/mapping`, `/search`, Backoff, fail-loud | **Create** |
| `app/deepdive/eu_adr_resolution.py` | Variantenleiter, Namens-Check, Linien-Selektion, CIK/Form, Cache, `resolve_eu_adr` | **Create** |
| `app/deepdive/adr_resolver.py` | EU-Zweig delegiert an injizierten `eu_resolver` | **Modify** |
| `app/deepdive/compose.py` | `build_openfigi_client`, `build_eu_resolver`, `build_adr_resolver` injiziert eu_resolver | **Modify** |
| `app/config.py` | `openfigi_api_key`, `adr_cache_ttl_days` | **Modify** |
| `scripts/acceptance_adr_resolution.py` | EU-Fälle (NVO ground-truth, SAP, ULVR) | **Modify** |

**Locked signatures (use verbatim across tasks):**
- `OpenFIGIClient.map_ticker(self, local: str, exch_code: str) -> dict | None`
- `OpenFIGIClient.search_issuer(self, name: str) -> list[dict]`
- `eu_adr_resolution.resolve_eu_adr(ticker: str, *, openfigi, edgar, yfinance, cache_path: Path, ttl_days: int) -> ResolvedTicker`
- `ResolvedTicker(ticker, adr_ticker, cik, form_type)` — imported from `app.deepdive.adr_resolver`.
- `ADRResolver.__init__(self, table, edgar, eu_resolver: Callable[[str], ResolvedTicker])`

---

## Task 1: OpenFIGI client (DI service)

**Files:**
- Create: `app/services/openfigi_client.py`
- Test: `tests/services/test_openfigi_client.py`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock, patch

import pytest

from app.errors import DataSourceError


def _client():
    from app.services.openfigi_client import OpenFIGIClientImpl
    return OpenFIGIClientImpl(sleep=lambda _s: None)


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_returns_first_datum(mock_httpx):
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"data": [{"name": "ASML HOLDING NV", "ticker": "ASML"}]}]
    mock_httpx.post.return_value = resp
    out = _client().map_ticker("ASML", "NA")
    assert out["name"] == "ASML HOLDING NV"


@patch("app.services.openfigi_client.httpx")
def test_map_ticker_none_on_no_data(mock_httpx):
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"warning": "no identifier found"}]
    mock_httpx.post.return_value = resp
    assert _client().map_ticker("NOPE", "NA") is None


@patch("app.services.openfigi_client.httpx")
def test_search_issuer_returns_data_list(mock_httpx):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": [{"ticker": "ASML", "exchCode": "US"}]}
    mock_httpx.post.return_value = resp
    out = _client().search_issuer("ASML HOLDING NV")
    assert out == [{"ticker": "ASML", "exchCode": "US"}]


@patch("app.services.openfigi_client.httpx")
def test_raises_datasourceerror_after_retries_on_429(mock_httpx):
    resp = MagicMock(status_code=429)
    resp.headers = {}
    mock_httpx.post.return_value = resp
    with pytest.raises(DataSourceError, match="OpenFIGI"):
        _client().map_ticker("X", "NA")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/services/test_openfigi_client.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.openfigi_client`

- [ ] **Step 3: Implement the client**

Create `app/services/openfigi_client.py`:

```python
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol

import httpx

from app.errors import DataSourceError

logger = logging.getLogger(__name__)


class OpenFIGIClient(Protocol):
    def map_ticker(self, local: str, exch_code: str) -> dict | None: ...
    def search_issuer(self, name: str) -> list[dict]: ...


class OpenFIGIClientImpl:
    """Thin OpenFIGI /v3 wrapper (Master ADR-BF-2). Keyless by default; an API key
    raises the rate limit. Fail-loud: 429/5xx after retries -> DataSourceError,
    never a swallowed empty result (failure != empty, ADR-BF-5)."""

    _BASE = "https://api.openfigi.com/v3/"
    _MAX_ATTEMPTS = 4

    def __init__(
        self,
        api_key: str = "",
        *,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-OPENFIGI-APIKEY"] = api_key
        self._sleep = sleep if sleep is not None else time.sleep

    def _post(self, path: str, payload: Any) -> Any:
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                resp = httpx.post(
                    self._BASE + path, json=payload, headers=self._headers, timeout=25
                )
            except Exception as exc:
                raise DataSourceError(f"OpenFIGI request failed: {exc}") from exc
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self._MAX_ATTEMPTS:
                retry_after = (resp.headers or {}).get("Retry-After")
                wait = int(retry_after) if (retry_after or "").isdigit() else 2 ** attempt
                logger.warning(
                    "OpenFIGI %s for %s — retry %d/%d", resp.status_code, path,
                    attempt, self._MAX_ATTEMPTS,
                )
                self._sleep(wait)
                continue
            raise DataSourceError(f"OpenFIGI returned {resp.status_code} for {path}")
        raise DataSourceError(f"OpenFIGI exhausted retries for {path}")

    def map_ticker(self, local: str, exch_code: str) -> dict | None:
        res = self._post("mapping", [{
            "idType": "TICKER", "idValue": local,
            "exchCode": exch_code, "securityType2": "Common Stock",
        }])
        first = res[0] if isinstance(res, list) and res else {}
        data = first.get("data") if isinstance(first, dict) else None
        return data[0] if data else None

    def search_issuer(self, name: str) -> list[dict]:
        res = self._post("search", {"query": name, "marketSecDes": "Equity"})
        return res.get("data", []) if isinstance(res, dict) else []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/services/test_openfigi_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/openfigi_client.py tests/services/test_openfigi_client.py
git commit -m "Add thin OpenFIGI client (mapping/search, backoff, fail-loud)"
```

---

## Task 2: eu_adr_resolution pure helpers (variant ladder, name-check, line selection)

**Files:**
- Create: `app/deepdive/eu_adr_resolution.py`
- Test: `tests/deepdive/test_eu_adr_resolution.py`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock

import pytest

from app.errors import DeepDiveError


def test_norm_issuer_folds_legal_forms_and_spaces():
    from app.deepdive.eu_adr_resolution import norm_issuer
    assert norm_issuer("ASML Holding N.V.") == norm_issuer("ASML HOLDING NV")
    assert norm_issuer("ROCHE HOLDING AG") != norm_issuer("ROCHE BOBOIS SA")


def test_issuer_name_strips_class_token():
    from app.deepdive.eu_adr_resolution import issuer_name
    assert issuer_name("ROCHE HOLDING AG-BR") == "ROCHE HOLDING AG"
    assert issuer_name("COCA-COLA CO") == "COCA-COLA CO"  # hyphen with space kept


def test_local_symbol_variants_for_dashed_ticker():
    from app.deepdive.eu_adr_resolution import local_symbol_variants
    assert local_symbol_variants("NOVO-B.CO") == ["NOVO-B", "NOVO B", "NOVOB"]


def test_home_exch_codes_from_suffix():
    from app.deepdive.eu_adr_resolution import home_exch_codes
    assert home_exch_codes("NOVO-B.CO") == ["DC"]
    assert home_exch_codes("SAP.DE") == ["GY", "GR"]


def test_find_home_identity_accepts_only_name_match():
    # Wrong candidate returns a foreign issuer -> rejected; right one accepted.
    from app.deepdive.eu_adr_resolution import find_home_identity, norm_issuer
    openfigi = MagicMock()
    openfigi.map_ticker.side_effect = [
        {"name": "ROCHE BOBOIS SA"},          # NOVO-B  -> foreign, rejected
        {"name": "NOVO NORDISK A/S-B"},       # NOVO B  -> matches, accepted
    ]
    ref = norm_issuer("Novo Nordisk A/S")
    ident = find_home_identity("NOVO-B.CO", ref, openfigi=openfigi)
    assert ident["name"] == "NOVO NORDISK A/S-B"


def test_find_home_identity_fail_loud_when_no_match():
    from app.deepdive.eu_adr_resolution import find_home_identity, norm_issuer
    openfigi = MagicMock()
    openfigi.map_ticker.return_value = None
    with pytest.raises(DeepDiveError, match="no verifiable OpenFIGI"):
        find_home_identity("XX-Y.CO", norm_issuer("Whatever Inc"), openfigi=openfigi)


def test_pick_us_adr_line_prefers_depositary_receipt():
    from app.deepdive.eu_adr_resolution import pick_us_adr_line, norm_issuer, issuer_name
    ident_norm = norm_issuer(issuer_name("ASML HOLDING NV"))
    lines = [
        {"ticker": "ASMLF", "exchCode": "US", "securityType2": "Common Stock", "name": "ASML HOLDING NV"},
        {"ticker": "ASML", "exchCode": "US", "securityType2": "Depositary Receipt", "name": "ASML HOLDING NV-NY REG SHS"},
        {"ticker": "ASML", "exchCode": "GY", "securityType2": "Common Stock", "name": "ASML HOLDING NV"},
    ]
    assert pick_us_adr_line(lines, ident_norm)["ticker"] == "ASML"


def test_pick_us_adr_line_none_when_no_us_line():
    from app.deepdive.eu_adr_resolution import pick_us_adr_line, norm_issuer
    lines = [{"ticker": "RMV", "exchCode": "LN", "securityType2": "Common Stock", "name": "RIGHTMOVE PLC"}]
    assert pick_us_adr_line(lines, norm_issuer("RIGHTMOVE PLC")) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_eu_adr_resolution.py -v`
Expected: FAIL — `ModuleNotFoundError: app.deepdive.eu_adr_resolution`

- [ ] **Step 3: Implement the helpers**

Create `app/deepdive/eu_adr_resolution.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.errors import DeepDiveError

if TYPE_CHECKING:
    from app.services.openfigi_client import OpenFIGIClient

# Home-exchange codes per Yahoo suffix (lifted from the dual-line audit).
SUFFIX_HOME_EXCH: dict[str, list[str]] = {
    "SW": ["SW", "VX"], "DE": ["GY", "GR"], "PA": ["FP"], "MC": ["SM"],
    "L": ["LN"], "AS": ["NA"], "CO": ["DC"], "VI": ["AV"], "WA": ["PW"],
    "BR": ["BB"], "ST": ["SS"], "HE": ["FH"], "OL": ["NO"], "MI": ["IM"],
    "IR": ["ID"], "AT": ["GA"], "LS": ["PL"],
}
# US exchange codes for the ADR line (audit "(US)" bucket).
US_EXCH = {"US", "UN", "UW", "UQ", "UR", "UA", "UV", "PQ"}

_LEGAL_FORMS = (
    " AG", " SA", " S.A.", " N.V.", " NV", " PLC", " SE", " SPA", " S.P.A.",
    " ASA", " AB", " OYJ", " A/S", " HOLDING", " GROUP", " INC", " LTD",
    " LIMITED", " COMPANY", " HLDG", " HLDGS",
)


def norm_issuer(name: str) -> str:
    """Normalise an issuer name for equality matching: drop legal forms + spaces.
    'ROCHE HOLDING AG' -> 'ROCHEHOLDING'; 'ROCHE BOBOIS SA' -> 'ROCHEBOBOIS'
    (stays distinct -> Bobois noise excluded)."""
    n = (name or "").upper()
    for legal in _LEGAL_FORMS:
        n = n.replace(legal, " ")
    return "".join(n.split())


def issuer_name(figi_name: str) -> str:
    """Issuer identity from an OpenFIGI security name: strip a trailing
    '-CLASSTOKEN' whose token has no space ('ROCHE HOLDING AG-BR' -> 'ROCHE
    HOLDING AG'); the no-space guard keeps hyphenated real names ('COCA-COLA
    CO')."""
    n = (figi_name or "").upper().strip()
    if "-" in n:
        head, _, tail = n.rpartition("-")
        if head and tail and " " not in tail:
            return head.strip()
    return n


def home_exch_codes(ticker: str) -> list[str]:
    suffix = ticker.rsplit(".", 1)[1] if "." in ticker else ""
    return SUFFIX_HOME_EXCH.get(suffix.upper(), [])


def local_symbol_variants(ticker: str) -> list[str]:
    """Ordered candidate local symbols for OpenFIGI (the variant ladder against
    the documented NVO miss: 'NOVO B'/'NOVOB' instead of the dashed form)."""
    base = ticker.rsplit(".", 1)[0] if "." in ticker else ticker
    variants = [base, base.replace("-", " "), base.replace("-", "")]
    return list(dict.fromkeys(variants))  # order-preserving dedup


def find_home_identity(ticker: str, ref_norm: str, *, openfigi: "OpenFIGIClient") -> dict:
    """Variant ladder + NAME-SANITY-CHECK: accept the first candidate whose
    OpenFIGI issuer name matches the reference (ADR-EU-2). Never 'first answer
    wins' — guards the variant-ladder false hit (ROCHE -> ROCHE BOBOIS)."""
    for exch in home_exch_codes(ticker):
        for cand in local_symbol_variants(ticker):
            ident = openfigi.map_ticker(cand, exch)
            if ident and norm_issuer(issuer_name(ident.get("name", ""))) == ref_norm:
                return ident
    raise DeepDiveError(
        f"{ticker}: no verifiable OpenFIGI identity (no candidate local symbol "
        f"matched the reference issuer name) — fail-loud, no unverified match."
    )


def pick_us_adr_line(lines: list[dict], ident_norm: str) -> dict | None:
    """Among the issuer's US-listed lines, prefer the Depositary-Receipt line;
    else the first US line. None if the issuer has no US listing (pure-EU,
    EU-Native gap). Operative output downstream is the CIK (consistent across
    lines per the pre-flight); the chosen ticker also serves as adr_ticker."""
    us = [
        ln for ln in lines
        if (ln.get("exchCode") or "").strip() in US_EXCH
        and norm_issuer(issuer_name(ln.get("name", ""))) == ident_norm
    ]
    if not us:
        return None
    for ln in us:
        if (ln.get("securityType2") or "") == "Depositary Receipt":
            return ln
    return us[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_eu_adr_resolution.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/eu_adr_resolution.py tests/deepdive/test_eu_adr_resolution.py
git commit -m "Add EU-ADR resolution helpers (variant ladder, name-check, line select)"
```

---

## Task 3: eu_adr_resolution orchestration + cache (`resolve_eu_adr`)

**Files:**
- Modify: `app/deepdive/eu_adr_resolution.py`
- Test: `tests/deepdive/test_eu_adr_resolution.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/deepdive/test_eu_adr_resolution.py`:

```python
def _deps(longname="ASML Holding N.V."):
    openfigi = MagicMock()
    openfigi.map_ticker.return_value = {"name": "ASML HOLDING NV"}
    openfigi.search_issuer.return_value = [
        {"ticker": "ASML", "exchCode": "US", "securityType2": "Depositary Receipt",
         "name": "ASML HOLDING NV-NY REG SHS"},
    ]
    edgar = MagicMock()
    edgar.get_cik.return_value = "937966"
    edgar.detect_annual_form.return_value = "20-F"
    yfinance = MagicMock()
    yfinance.get_ticker_info.return_value = {"longName": longname}
    return openfigi, edgar, yfinance


def test_resolve_eu_adr_happy_path(tmp_path):
    from app.deepdive.eu_adr_resolution import resolve_eu_adr
    openfigi, edgar, yfinance = _deps()
    r = resolve_eu_adr("ASML.AS", openfigi=openfigi, edgar=edgar, yfinance=yfinance,
                       cache_path=tmp_path / "adr.json", ttl_days=180)
    assert r.adr_ticker == "ASML"
    assert r.cik == "0000937966"
    assert r.form_type == "20-F"


def test_resolve_eu_adr_persists_and_reads_cache(tmp_path):
    from app.deepdive.eu_adr_resolution import resolve_eu_adr
    cache = tmp_path / "adr.json"
    openfigi, edgar, yfinance = _deps()
    resolve_eu_adr("ASML.AS", openfigi=openfigi, edgar=edgar, yfinance=yfinance,
                   cache_path=cache, ttl_days=180)
    # second call: OpenFIGI must NOT be hit again (served from cache).
    openfigi2 = MagicMock()
    r = resolve_eu_adr("ASML.AS", openfigi=openfigi2, edgar=edgar, yfinance=yfinance,
                       cache_path=cache, ttl_days=180)
    assert r.cik == "0000937966"
    openfigi2.map_ticker.assert_not_called()


def test_resolve_eu_adr_no_us_line_fail_loud(tmp_path):
    from app.deepdive.eu_adr_resolution import resolve_eu_adr
    openfigi, edgar, yfinance = _deps(longname="Rightmove plc")
    openfigi.map_ticker.return_value = {"name": "RIGHTMOVE PLC"}
    openfigi.search_issuer.return_value = [
        {"ticker": "RMV", "exchCode": "LN", "securityType2": "Common Stock", "name": "RIGHTMOVE PLC"},
    ]
    with pytest.raises(DeepDiveError, match="no US ADR"):
        resolve_eu_adr("RMV.L", openfigi=openfigi, edgar=edgar, yfinance=yfinance,
                       cache_path=tmp_path / "adr.json", ttl_days=180)


def test_resolve_eu_adr_no_reference_name_fail_loud(tmp_path):
    from app.deepdive.eu_adr_resolution import resolve_eu_adr
    openfigi, edgar, yfinance = _deps()
    yfinance.get_ticker_info.return_value = {}  # no longName/shortName
    with pytest.raises(DeepDiveError, match="no reference name"):
        resolve_eu_adr("ASML.AS", openfigi=openfigi, edgar=edgar, yfinance=yfinance,
                       cache_path=tmp_path / "adr.json", ttl_days=180)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_eu_adr_resolution.py -k resolve_eu_adr -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_eu_adr'`

- [ ] **Step 3: Implement orchestration + cache**

Append to `app/deepdive/eu_adr_resolution.py` (add imports `json`, `Path`, `datetime`, `ResolvedTicker`):

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from app.deepdive.adr_resolver import ResolvedTicker

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient
    from app.services.yfinance_client import YFinanceClient


def _cache_get(cache_path: Path, ticker: str, ttl_days: int) -> ResolvedTicker | None:
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return None  # corrupt cache -> miss (fail-soft, mirrors filing_cache)
    entry = data.get(ticker.upper())
    if not entry:
        return None
    ts = datetime.fromisoformat(entry["_cached_at"])
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - ts).days >= ttl_days:
        return None
    return ResolvedTicker(ticker, entry["adr_ticker"], entry["cik"], entry["form_type"])


def _cache_put(cache_path: Path, resolved: ResolvedTicker) -> None:
    data = {}
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            data = {}
    data[resolved.ticker.upper()] = {
        "adr_ticker": resolved.adr_ticker,
        "cik": resolved.cik,
        "form_type": resolved.form_type,
        "_cached_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(cache_path)


def resolve_eu_adr(
    ticker: str,
    *,
    openfigi: "OpenFIGIClient",
    edgar: "EdgarClient",
    yfinance: "YFinanceClient",
    cache_path: Path,
    ttl_days: int,
) -> ResolvedTicker:
    """Live EU-ADR resolution (cache layer 2 + live layer 3). Failure != empty:
    transient OpenFIGI/EDGAR/yfinance errors propagate as DataSourceError;
    genuine no-match -> DeepDiveError."""
    cached = _cache_get(cache_path, ticker, ttl_days)
    if cached is not None:
        return cached

    info = yfinance.get_ticker_info(ticker)  # DataSourceError on transient failure
    ref = info.get("longName") or info.get("shortName")
    if not ref:
        raise DeepDiveError(
            f"{ticker}: no reference name from yfinance — cannot verify an OpenFIGI "
            f"match; fail-loud rather than accept an unverified identity."
        )
    ref_norm = norm_issuer(ref)

    ident = find_home_identity(ticker, ref_norm, openfigi=openfigi)
    us = pick_us_adr_line(
        openfigi.search_issuer(ident["name"]),
        norm_issuer(issuer_name(ident["name"])),
    )
    if us is None:
        raise DeepDiveError(
            f"{ticker}: no US ADR line for {ident['name']!r} — pure-EU listing, "
            f"EU-Native source layer is Phase 2."
        )
    us_ticker = (us.get("ticker") or "").strip()
    cik = edgar.get_cik(us_ticker)
    if not cik:
        raise DeepDiveError(
            f"{ticker}: US-ADR {us_ticker} not in SEC company_tickers map."
        )
    form = edgar.detect_annual_form(cik)
    if form is None:
        raise DeepDiveError(
            f"{ticker} (ADR {us_ticker}, CIK {cik}) files neither 10-K nor 20-F."
        )
    resolved = ResolvedTicker(
        ticker=ticker, adr_ticker=us_ticker, cik=cik.zfill(10), form_type=form
    )
    _cache_put(cache_path, resolved)
    return resolved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_eu_adr_resolution.py -v`
Expected: PASS (12 tests total)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/eu_adr_resolution.py tests/deepdive/test_eu_adr_resolution.py
git commit -m "Add resolve_eu_adr orchestration + local cache (failure != empty)"
```

---

## Task 4: ADRResolver delegation + compose wiring + config

**Files:**
- Modify: `app/config.py` (after `deepdive_peers_collection`)
- Modify: `app/deepdive/adr_resolver.py`
- Modify: `app/deepdive/compose.py`
- Test: `tests/deepdive/test_adr_resolver.py`, `tests/deepdive/test_compose.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/deepdive/test_adr_resolver.py`:

```python
def test_eu_ticker_delegates_to_eu_resolver():
    from app.deepdive.adr_resolver import ResolvedTicker
    eu = MagicMock(return_value=ResolvedTicker("ASML.AS", "ASML", "0000937966", "20-F"))
    r = ADRResolver(table={}, edgar=MagicMock(), eu_resolver=eu).resolve("ASML.AS")
    assert r.adr_ticker == "ASML"
    eu.assert_called_once_with("ASML.AS")
```

Update the `_resolver` helper in `tests/deepdive/test_adr_resolver.py` to pass `eu_resolver`:

```python
def _resolver(table=None, edgar=None, eu_resolver=None):
    if table is None:
        table = {"NOVO-B.CO": {"adr_ticker": "NVO", "cik": "0000353278", "form_type": "20-F"}}
    if edgar is None:
        edgar = MagicMock()
    if eu_resolver is None:
        eu_resolver = MagicMock()
    return ADRResolver(table=table, edgar=edgar, eu_resolver=eu_resolver)
```

Update `tests/deepdive/test_compose.py::test_build_adr_resolver_resolves_seed` (it already patches `EdgarClientImpl`; also patch the new builders so no network/config is needed):

```python
def test_build_adr_resolver_resolves_seed():
    from unittest.mock import patch

    from app.deepdive.compose import build_adr_resolver

    # NOVO-B.CO is a static-table hit -> edgar/eu_resolver never invoked; patch the
    # config-dependent construction (UA, OpenFIGI/yfinance) so the override path is
    # what's under test (mirrors the insider compose test).
    with patch("app.deepdive.compose.EdgarClientImpl"), \
         patch("app.deepdive.compose.OpenFIGIClientImpl"), \
         patch("app.deepdive.compose.YFinanceClientImpl"):
        assert build_adr_resolver().resolve("NOVO-B.CO").adr_ticker == "NVO"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_adr_resolver.py tests/deepdive/test_compose.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'eu_resolver'`

- [ ] **Step 3: Add config settings**

In `app/config.py`, after the `deepdive_peers_collection` line, add:

```python
    openfigi_api_key: str = ""
    adr_cache_ttl_days: int = 180  # ADR mappings drift rarely; long TTL is correct
```

- [ ] **Step 4: Wire the resolver delegation**

In `app/deepdive/adr_resolver.py`: extend imports and `__init__`, and replace the `_EU_MARKER` raise branch with delegation.

Imports block (add `Callable`):

```python
from typing import TYPE_CHECKING, Callable
```

`__init__`:

```python
    def __init__(
        self,
        table: dict[str, dict[str, str]],
        edgar: "EdgarClient",
        eu_resolver: Callable[[str], ResolvedTicker],
    ) -> None:
        self._table = {k.upper(): v for k, v in table.items()}
        self._edgar = edgar
        self._eu_resolver = eu_resolver
```

Replace the whole `if _EU_MARKER in ticker:` raise block with:

```python
        if _EU_MARKER in ticker:
            # Dynamic EU-ADR resolution (OpenFIGI). The delegate raises DeepDiveError
            # for a genuine no-US-ADR (EU-Native gap, Phase 2) or DataSourceError on
            # a transient API failure — failure != empty, never a silent wrong match.
            return self._eu_resolver(ticker)
```

- [ ] **Step 5: Wire compose**

In `app/deepdive/compose.py`: add imports + builders, and inject `eu_resolver` into `build_adr_resolver`.

Add imports near the other service imports:

```python
from app.deepdive.eu_adr_resolution import resolve_eu_adr
from app.services.openfigi_client import OpenFIGIClientImpl
```

Add a cache-dir constant near the others:

```python
_ADR_CACHE_PATH = Path("cache/adr_resolved.json")
```

Add builders and update `build_adr_resolver`:

```python
def build_openfigi_client() -> OpenFIGIClientImpl:
    return OpenFIGIClientImpl(api_key=settings.openfigi_api_key)


def build_eu_resolver() -> Callable[[str], Any]:
    openfigi = build_openfigi_client()
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    yfinance = YFinanceClientImpl()

    def _resolve(ticker: str):
        return resolve_eu_adr(
            ticker,
            openfigi=openfigi,
            edgar=edgar,
            yfinance=yfinance,
            cache_path=_ADR_CACHE_PATH,
            ttl_days=settings.adr_cache_ttl_days,
        )

    return _resolve


def build_adr_resolver() -> ADRResolver:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    return ADRResolver(
        table=load_adr_table(), edgar=edgar, eu_resolver=build_eu_resolver()
    )
```

Add `"build_openfigi_client"` and `"build_eu_resolver"` to `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_adr_resolver.py tests/deepdive/test_compose.py -v`
Expected: PASS. Then reproduce CI's empty-UA condition for the compose test:
Run: `FISHERSCREEN_EDGAR_USER_AGENT="" uv run python -m pytest tests/deepdive/test_compose.py -q`
Expected: PASS (the patched builders mean no UA is needed).

- [ ] **Step 7: Full deepdive suite (regression)**

Run: `uv run python -m pytest tests/deepdive -q`
Expected: PASS (resolver/compose/pipeline/cli all green).

- [ ] **Step 8: Commit**

```bash
git add app/config.py app/deepdive/adr_resolver.py app/deepdive/compose.py tests/deepdive/test_adr_resolver.py tests/deepdive/test_compose.py
git commit -m "Delegate EU tickers to OpenFIGI eu_resolver; wire compose + config"
```

---

## Task 5: $0 acceptance — NVO ground-truth gate + SAP + ULVR

**Files:**
- Modify: `scripts/acceptance_adr_resolution.py`

**Manual network gate** (Stephan runs it; no Gemini). NVO (Fall 1) is the mandatory variant-ladder verification against the documented pre-flight miss, with a known ground-truth CIK.

- [ ] **Step 1: Extend the acceptance script**

Append EU cases to `scripts/acceptance_adr_resolution.py` (after the existing US `[case1]`/`[case3]` block, before the final print). Add the import at the top: `from app.deepdive.compose import build_eu_resolver`. Insert:

```python
    # Case EU-1 (PFLICHT-GATE): NVO variant ladder against the documented pre-flight
    # miss, anchored on the static-table ground-truth CIK. Bypass the override table
    # (call the EU resolver directly) + a fresh cache so the LIVE path is tested.
    import os
    os.environ.setdefault("FISHERSCREEN_ADR_CACHE_TTL_DAYS", "180")
    eu = build_eu_resolver()
    nvo = eu("NOVO-B.CO")
    print(f"[eu1] NOVO-B.CO live -> adr={nvo.adr_ticker} cik={nvo.cik} form={nvo.form_type}")
    assert nvo.cik == "0000353278", f"NVO ground-truth CIK mismatch: {nvo.cik}"

    # Case EU-2: SAP.DE full resolve -> fetch (20-F ADR, not in table).
    sap = resolver.resolve("SAP.DE")
    print(f"[eu2] SAP.DE -> adr={sap.adr_ticker} cik={sap.cik} form={sap.form_type}")
    assert sap.cik == "0001000184" and sap.form_type == "20-F"
    sap_raw = fetcher.get(sap.cik, sap.form_type, use_cache=True)
    print(f"[eu2] filing fetched: {sap_raw.accession_number} ({len(sap_raw.document_text)} chars)")

    # Case EU-3: ULVR.L fresh filer (not in pre-flight set) -> US ADR UL.
    ulvr = resolver.resolve("ULVR.L")
    print(f"[eu3] ULVR.L -> adr={ulvr.adr_ticker} cik={ulvr.cik} form={ulvr.form_type}")
    assert ulvr.adr_ticker and ulvr.cik
```

The `cache/adr_resolved.json` must be absent/cleared before the run so EU-1 exercises the live path. Document in the script's docstring: `del cache\adr_resolved.json` (cmd.exe) before running.

- [ ] **Step 2: Verify the script compiles (no network here)**

Run: `uv run python -m py_compile scripts/acceptance_adr_resolution.py`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/acceptance_adr_resolution.py
git commit -m "Extend acceptance: NVO ground-truth gate + SAP/ULVR EU cases"
```

- [ ] **Step 4: Manual acceptance run (Stephan, network)**

```
del cache\adr_resolved.json
set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
uv run python scripts\acceptance_adr_resolution.py
```
Expected: `[eu1]` NOVO-B.CO live → CIK `0000353278` (**ground-truth match — the variant ladder hit**); `[eu2]` SAP.DE → CIK `0001000184`/`20-F` + filing; `[eu3]` ULVR.L → ADR `UL` + CIK; plus the original US `[case1]`/`[case3]`; `ACCEPTANCE OK`.

**B-Fast is NOT done until `[eu1]` is green** (the variant ladder verified against the problem that motivated it).

---

## Self-Review (against spec)

- **ADR-EU-1** (OpenFIGI service) → Task 1. ✅ httpx, keyless+key option, fail-loud after retries.
- **ADR-EU-2** (variant ladder + name-sanity-check) → Task 2 `find_home_identity` (name-match gate) + `local_symbol_variants`; reference = yfinance longName in Task 3. ✅
- **ADR-EU-3** (line selection) → Task 2 `pick_us_adr_line` (US exch + same issuer, prefer Depositary Receipt). ✅
- **ADR-EU-4** (own module, resolver delegates) → Task 2/3 module + Task 4 delegation. ✅
- **ADR-EU-5** (3-layer cache) → Task 3 `_cache_get`/`_cache_put` (`_cached_at`, TTL 180) + Task 4 override stays layer 1. ✅
- **Failure ≠ Empty** → yfinance/edgar/openfigi raise DataSourceError; genuine no-match → DeepDiveError. Tested in Task 1 (429) + Task 3 (no-US-line, no-ref). ✅
- **Acceptance §5** → Task 5: NVO ground-truth (1, mandatory), SAP (2), ULVR (3), RMV fail-loud (existing case3), transient → DataSourceError (Task1/Task3 unit). ✅
- **Placeholder scan:** no TBD; every code step shows full code.
- **Type consistency:** `map_ticker`/`search_issuer`, `resolve_eu_adr(...)`, `ResolvedTicker`, `eu_resolver` callable, `find_home_identity`/`pick_us_adr_line`/`norm_issuer`/`issuer_name` consistent across Tasks 1–4.
- **CI hermeticity:** Task 4 Step 6 reproduces the empty-UA condition that broke #42 — the compose test patches `EdgarClientImpl`/`OpenFIGIClientImpl`/`YFinanceClientImpl`.

---

## Notes / honest-label

- `pick_us_adr_line` returns one line; the pre-flight showed all US lines of an issuer share one CIK, so CIK is unambiguous. A genuine multi-CIK issuer (not observed) would resolve to whichever line is picked — if that ever surfaces, add a multi-CIK fail-loud + an override-table entry (don't guess). Logged as a follow-up, not built (YAGNI).
- The variant ladder is calibrated against the NVO miss; a new filer class whose local symbol no candidate form hits fails loud (no false match, thanks to the name-check) → ticket + ladder extension.
```
