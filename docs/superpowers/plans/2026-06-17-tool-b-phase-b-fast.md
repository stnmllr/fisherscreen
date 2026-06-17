# Tool B Phase B-Fast — Implementation Plan (US-Pfad + Pre-Flight-Gate)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tool B end-to-end lauffähig für **beliebige US-Ticker** (heute am `cik=""`-Defekt blockiert) machen und den OpenFIGI→US-ADR→CIK-**Pre-Flight als Go/No-Go-Gate** für den EU-ADR-Pfad durchführen.

**Architecture:** Der `ADRResolver` bekommt einen injizierten `EdgarClient`. Auflösungs-Reihenfolge: statische Tabelle (Override) → US-Pfad (`get_cik` + `detect_annual_form`) → non-US-Ticker ohne Tabelleneintrag = fail-loud (EU-ADR-Pfad ist Post-Gate). Der Pipeline-Guard (`pipeline.py:71-76`) entfällt, weil der Resolver jetzt eine CIK garantiert oder laut scheitert. Der EU-ADR-Pfad (OpenFIGI-Service) wird **bewusst nicht** hier gebaut — er hängt an der Response-Form, die das Pre-Flight erst beweist (ADR-BF-3), und bekommt einen eigenen Plan nach dem dokumentierten Go-Befund.

**Tech Stack:** Python 3.12, FastAPI-Projekt, pytest (DI-Mocks, `uv run python -m pytest`), httpx (EDGAR), OpenFIGI REST (`api.openfigi.com/v3/`, nur im Pre-Flight-Skript).

**Brainstorm-Referenz:** `docs/superpowers/brainstorm/2026-06-17-tool-b-phase-b-fast.md` (ADR-BF-3 Gate/Fork, ADR-BF-4 Form-Detektion, ADR-BF-5 Failure≠Empty, ADR-BF-7 Einzel-Ticker).

---

## Scope & Fork (aus ADR-BF-3)

Dieser Plan liefert **zwei Endgestalten-unabhängige** Bausteine:

1. **Pre-Flight-Gate** (Task 1) — entscheidet, ob der **EU-ADR-Pfad** (eigener Folge-Plan) überhaupt gebaut wird. **Go** → Folge-Plan; **No-Go** → EU-ADR ist Phase-2-Material.
2. **US-Pfad** (Tasks 2–4) — der **gate-unabhängige sichere Kern**. Liefert sofort lauffähige US-Deep-Dives, egal wie das Gate ausfällt.
3. **$0-Akzeptanz** (Task 5) — beweist US-Pfad + EU-fail-loud ohne Gemini-Kosten.

Reihenfolge frei: Task 1 (Stephan, Netz-Investigation) und Tasks 2–4 (Code) sind unabhängig. Empfehlung: Task 1 zuerst laufen lassen, damit der EU-Folge-Plan parallel terminiert werden kann, während der US-Pfad implementiert wird.

---

## File Structure

| Datei | Verantwortung | Aktion |
|---|---|---|
| `scripts/preflight_adr_resolution.py` | Netz-Probe OpenFIGI→US-ADR→CIK für NVO/ASML/SAP; druckt Rohbefund | **Create** |
| `docs/superpowers/diagnostic-reports/2026-06-17-adr-resolution-preflight.md` | Dokumentierter Befund + Go/No-Go-Verdikt | **Create** |
| `app/services/edgar_client.py` | `detect_annual_form(cik)` ergänzen (Protocol + Impl) | **Modify** |
| `app/deepdive/adr_resolver.py` | injizierter `edgar`; US-Pfad-Auflösung; EU-fail-loud-Message | **Modify** |
| `app/deepdive/compose.py:41-42` | `build_adr_resolver` verdrahtet `EdgarClientImpl` | **Modify** |
| `app/deepdive/pipeline.py:71-76` | toten `cik=""`-Guard entfernen | **Modify** |
| `tests/services/test_edgar_client.py` | `detect_annual_form`-Tests | **Modify** |
| `tests/deepdive/test_adr_resolver.py` | Helper + US-Pfad-Tests; EU-Message-Match | **Modify** |
| `tests/deepdive/test_pipeline.py:119-124` | obsoleten Guard-Test entfernen | **Modify** |
| `scripts/acceptance_adr_resolution.py` | $0-Akzeptanz (US-Resolve+Fetch, EU-fail-loud) | **Create** |

---

## Task 1: ADR-Resolution Pre-Flight (Go/No-Go-Gate)

**Kein Unit-Test** — manuelle Netz-Investigation, analog `scripts/preflight_gemini_pro.py` und dem Dual-Line-Audit. Ergebnis ist ein **dokumentierter Befund + Verdikt**, das den EU-ADR-Folge-Plan freigibt oder absagt.

**Files:**
- Create: `scripts/preflight_adr_resolution.py`
- Create: `docs/superpowers/diagnostic-reports/2026-06-17-adr-resolution-preflight.md`

- [ ] **Step 1: Pre-Flight-Skript schreiben**

```python
"""Pre-Flight (Brainstorm B-Fast, ADR-BF-3): laesst sich der Pfad
EU-Yahoo-Ticker -> OpenFIGI US-ADR-Linie -> SEC-CIK fuer 20-F-ADR-Filer
zuverlaessig aufloesen? Go/No-Go-Gate fuer den EU-ADR-Pfad.

Druckt Rohbefund pro Filer. KEIN Pass/Fail-Assert — der Mensch liest die
Ausgabe und faellt das Verdikt im Diagnostic-Report.

Aufruf (cmd.exe):
  set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
  uv run python scripts\\preflight_adr_resolution.py
"""
from __future__ import annotations

import json
import sys

import httpx

from app.services.edgar_client import EdgarClientImpl
from app.config import settings

FIGI_URL = "https://api.openfigi.com/v3/"
US_EXCH = {"US", "UN", "UW", "UQ", "UR", "UA", "UV", "PQ"}

# (yahoo_ticker, local_symbol, home_exchCode) — 20-F-ADR-Filer.
FILERS = [
    ("NOVO-B.CO", "NOVO B", "DC"),
    ("ASML.AS", "ASML", "NA"),
    ("SAP.DE", "SAP", "GY"),
]


def _figi(path: str, payload) -> object:
    r = httpx.post(FIGI_URL + path, json=payload,
                   headers={"Content-Type": "application/json"}, timeout=25)
    r.raise_for_status()
    return r.json()


def _home_identity(local: str, exch: str) -> dict:
    res = _figi("mapping", [{"idType": "TICKER", "idValue": local,
                             "exchCode": exch, "securityType2": "Common Stock"}])
    data = (res[0] or {}).get("data") if isinstance(res, list) and res else None
    return data[0] if data else {"_warning": "no home identity"}


def _us_lines(issuer_name: str) -> list[dict]:
    res = _figi("search", {"query": issuer_name, "marketSecDes": "Equity"})
    out = []
    for d in (res.get("data", []) if isinstance(res, dict) else []):
        if (d.get("exchCode") or "").strip() in US_EXCH:
            out.append({"ticker": d.get("ticker"), "exchCode": d.get("exchCode"),
                        "name": d.get("name"), "securityType2": d.get("securityType2"),
                        "shareClassFIGI": d.get("shareClassFIGI")})
    return out


def main() -> int:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    for yahoo, local, exch in FILERS:
        print(f"\n===== {yahoo} (local {local!r}, home {exch}) =====")
        ident = _home_identity(local, exch)
        print("home identity:", json.dumps(ident, ensure_ascii=False))
        name = ident.get("name", "")
        lines = _us_lines(name) if name else []
        print(f"US-listed lines ({len(lines)}):")
        for ln in lines:
            cik = edgar.get_cik((ln.get("ticker") or "").strip())
            print(f"  {ln['ticker']:8} {ln['exchCode']:4} cik={cik} "
                  f"type={ln['securityType2']} name={ln['name']!r}")
    print("\nRead the output, then fill the diagnostic report + Go/No-Go verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Skript laufen lassen (echtes Netz)**

Run (cmd.exe):
```
set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
uv run python scripts\preflight_adr_resolution.py
```
Erwartung: pro Filer eine Home-Identität + 0..n US-Listings mit CIK. Genau hinsehen: **eindeutige** US-ADR-Linie? `get_cik` ≠ None? Mehrere US-Linien (Mehrdeutigkeit)?

- [ ] **Step 3: Befund + Verdikt dokumentieren**

Lege `docs/superpowers/diagnostic-reports/2026-06-17-adr-resolution-preflight.md` an mit: pro Filer (NVO/ASML/SAP) Tabelle `eindeutige US-Linie? | get_cik? | Mehrdeutigkeit?`, der **OpenFIGI-Methode die funktioniert hat** (für den Folge-Plan), und dem **Verdikt**:
- **GO** → für ≥2 der 3 Filer eindeutige US-ADR-Linie mit auflösender CIK, kein Falsch-Match → EU-ADR-Folge-Plan terminieren.
- **NO-GO** → unzuverlässig/mehrdeutig → B-Fast bleibt US-Pfad allein; EU-ADR wird Phase 2 (Honest-Label im PROJEKTSTAND).

- [ ] **Step 4: Commit**

```bash
git add scripts/preflight_adr_resolution.py docs/superpowers/diagnostic-reports/2026-06-17-adr-resolution-preflight.md
git commit -m "Add ADR-resolution pre-flight gate + documented finding"
```

---

## Task 2: `detect_annual_form` auf dem EDGAR-Client (ADR-BF-4)

**Files:**
- Modify: `app/services/edgar_client.py` (Protocol `EdgarClient` ~Zeile 41-52; Impl ~nach Zeile 377)
- Test: `tests/services/test_edgar_client.py`

- [ ] **Step 1: Failing tests schreiben**

In `tests/services/test_edgar_client.py` anhängen:

```python
@patch("app.services.edgar_client.httpx")
def test_detect_annual_form_returns_10k(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"filings": {"recent": {"form": ["8-K", "10-K", "4"]}}}
    mock_httpx.get.return_value = mock_resp
    assert _make_client().detect_annual_form("320193") == "10-K"


@patch("app.services.edgar_client.httpx")
def test_detect_annual_form_returns_20f(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"filings": {"recent": {"form": ["6-K", "20-F"]}}}
    mock_httpx.get.return_value = mock_resp
    assert _make_client().detect_annual_form("353278") == "20-F"


@patch("app.services.edgar_client.httpx")
def test_detect_annual_form_returns_none_when_no_annual(mock_httpx):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"filings": {"recent": {"form": ["8-K", "4", "S-1"]}}}
    mock_httpx.get.return_value = mock_resp
    assert _make_client().detect_annual_form("111") is None


@patch("app.services.edgar_client.httpx")
def test_detect_annual_form_most_recent_wins(mock_httpx):
    # recent[] is reverse-chronological -> first annual form encountered wins.
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"filings": {"recent": {"form": ["20-F", "10-K"]}}}
    mock_httpx.get.return_value = mock_resp
    assert _make_client().detect_annual_form("999") == "20-F"
```

- [ ] **Step 2: Tests laufen, Fehlschlag bestätigen**

Run: `uv run python -m pytest tests/services/test_edgar_client.py -k detect_annual_form -v`
Expected: FAIL — `AttributeError: 'EdgarClientImpl' object has no attribute 'detect_annual_form'`

- [ ] **Step 3: Methode implementieren**

In `app/services/edgar_client.py`, im `EdgarClient`-Protocol (nach `get_latest_annual_filing`-Zeile) ergänzen:

```python
    def detect_annual_form(self, cik: str) -> str | None: ...
```

In `EdgarClientImpl` (z. B. direkt nach `get_latest_annual_filing`) ergänzen:

```python
    def detect_annual_form(self, cik: str) -> str | None:
        """Most recent annual form the filer uses: '10-K' (US domestic) or
        '20-F' (foreign private issuer). None if neither appears in recent
        submissions. A network failure raises DataSourceError via self._get
        (failure != empty, ADR-BF-5) — None means 'genuinely no annual form'."""
        padded = cik.zfill(10)
        data = self._get(f"{self._SEC_BASE}/submissions/CIK{padded}.json")
        forms = data.get("filings", {}).get("recent", {}).get("form", [])
        for form in forms:
            if form in ("10-K", "20-F"):
                return form
        return None
```

- [ ] **Step 4: Tests laufen, Erfolg bestätigen**

Run: `uv run python -m pytest tests/services/test_edgar_client.py -k detect_annual_form -v`
Expected: PASS (4 Tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/edgar_client.py tests/services/test_edgar_client.py
git commit -m "Add EdgarClient.detect_annual_form (10-K vs 20-F from submissions)"
```

---

## Task 3: ADRResolver US-Pfad mit injiziertem EDGAR-Client

**Files:**
- Modify: `app/deepdive/adr_resolver.py`
- Test: `tests/deepdive/test_adr_resolver.py`

- [ ] **Step 1: Test-Helper auf injizierten EDGAR umstellen + Failing tests schreiben**

In `tests/deepdive/test_adr_resolver.py` den Import-Block + Helper ersetzen und die geänderten/neuen Tests setzen:

```python
import pytest
from unittest.mock import MagicMock

from app.deepdive.adr_resolver import ADRResolver, ResolvedTicker
from app.errors import DeepDiveError


def _resolver(table=None, edgar=None):
    if table is None:
        table = {"NOVO-B.CO": {"adr_ticker": "NVO", "cik": "0000353278", "form_type": "20-F"}}
    if edgar is None:
        edgar = MagicMock()
    return ADRResolver(table=table, edgar=edgar)


def test_us_ticker_resolves_cik_and_form_via_edgar():
    edgar = MagicMock()
    edgar.get_cik.return_value = "320193"
    edgar.detect_annual_form.return_value = "10-K"
    r = _resolver(edgar=edgar).resolve("AAPL")
    assert r.adr_ticker is None
    assert r.cik == "0000320193"  # zero-padded, table-consistent
    assert r.form_type == "10-K"
    edgar.get_cik.assert_called_once_with("AAPL")


def test_us_ticker_not_in_sec_map_raises():
    edgar = MagicMock()
    edgar.get_cik.return_value = None
    with pytest.raises(DeepDiveError, match="not found in the SEC company_tickers"):
        _resolver(edgar=edgar).resolve("NOTAREAL")


def test_us_filer_without_annual_form_raises():
    edgar = MagicMock()
    edgar.get_cik.return_value = "111"
    edgar.detect_annual_form.return_value = None
    with pytest.raises(DeepDiveError, match="neither 10-K nor 20-F"):
        _resolver(edgar=edgar).resolve("WEIRD")


def test_unknown_eu_ticker_raises_postgate_message():
    with pytest.raises(DeepDiveError, match="post-gate B-Fast step"):
        _resolver().resolve("SAP.DE")
```

Die bestehenden Tabellen-Tests `test_resolves_eu_adr_entry`, `test_is_case_insensitive_on_ticker`, `test_di_mockable_via_injected_table` **bleiben unverändert** (Tabellen-Treffer rührt den EDGAR-Mock nicht an). Den alten `test_us_ticker_passthrough_when_not_in_table` und den alten `test_unknown_eu_ticker_raises_actionable_error` **löschen** (durch die vier Tests oben ersetzt).

- [ ] **Step 2: Tests laufen, Fehlschlag bestätigen**

Run: `uv run python -m pytest tests/deepdive/test_adr_resolver.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'edgar'`

- [ ] **Step 3: Resolver implementieren**

`app/deepdive/adr_resolver.py` — `__init__` + `resolve` ersetzen:

```python
    def __init__(self, table: dict[str, dict[str, str]], edgar) -> None:
        self._table = {k.upper(): v for k, v in table.items()}
        self._edgar = edgar

    def resolve(self, ticker: str) -> ResolvedTicker:
        key = ticker.upper()
        entry = self._table.get(key)
        if entry is not None:
            return ResolvedTicker(
                ticker=ticker,
                adr_ticker=entry["adr_ticker"],
                cik=entry["cik"],
                form_type=entry["form_type"],
            )
        if _EU_MARKER in ticker:
            # EU-ADR dynamic resolution is the post-gate B-Fast step (OpenFIGI,
            # pending the ADR-resolution pre-flight). Until then: override table
            # or a US-listed ticker. Distinct, actionable message — never a silent
            # wrong match.
            raise DeepDiveError(
                f"Ticker {ticker} is a non-US listing not in the ADR table. "
                f"Dynamic EU-ADR resolution is the post-gate B-Fast step (pending "
                f"the OpenFIGI pre-flight) — add an entry to data/adr_table.json "
                f"or pick a US-listed ticker."
            )
        # US path: resolve the CIK + detect the annual form from EDGAR.
        cik = self._edgar.get_cik(ticker)
        if not cik:
            raise DeepDiveError(
                f"US ticker {ticker} not found in the SEC company_tickers map — "
                f"check the symbol or add an ADR table entry."
            )
        form = self._edgar.detect_annual_form(cik)
        if form is None:
            raise DeepDiveError(
                f"{ticker} (CIK {cik}) files neither 10-K nor 20-F in recent "
                f"submissions — not deep-dive-eligible (other forms are Phase 2)."
            )
        return ResolvedTicker(
            ticker=ticker, adr_ticker=None, cik=cik.zfill(10), form_type=form
        )
```

Den alten `_EU_MARKER`-Kommentarblock (Zeilen 7-16) sinngemäß belassen; den Hinweis „Dynamic resolution … is Phase B.2" auf „… is the post-gate B-Fast EU step" aktualisieren.

> **Honest-Label-Notiz (in den Code-Kommentar oder den Diagnostic-Report):** `get_cik`
> faltet einen Netzfehler beim Laden von `company_tickers.json` zu `None`
> (`edgar_client.py:129-141`, bewusste Screener-Degradation). Im Resolver heißt das:
> ein transienter Map-Fetch-Fehler erscheint als „ticker not found" statt
> DataSourceError. Pre-existing, in diesem Inkrement **nicht** geändert (geteilter
> Screener-Pfad); als Folge-Ticket vermerken. `detect_annual_form` ist korrekt
> failure≠empty (raised DataSourceError bei Netzfehler).

- [ ] **Step 4: Tests laufen, Erfolg bestätigen**

Run: `uv run python -m pytest tests/deepdive/test_adr_resolver.py -v`
Expected: PASS (alle Tabellen- + US-Pfad-Tests)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/adr_resolver.py tests/deepdive/test_adr_resolver.py
git commit -m "Resolve US-ticker CIK + form via injected EdgarClient in ADRResolver"
```

---

## Task 4: Compose-Verdrahtung + Pipeline-Guard entfernen

**Files:**
- Modify: `app/deepdive/compose.py:41-42`
- Modify: `app/deepdive/pipeline.py:71-76`
- Test: `tests/deepdive/test_compose.py` (Verifikation), `tests/deepdive/test_pipeline.py` (obsoleten Test entfernen)

- [ ] **Step 1: Obsoleten Pipeline-Guard-Test entfernen**

In `tests/deepdive/test_pipeline.py` den Test entfernen, der den `cik=""`-Guard prüft (aktuell ~Zeile 119-124, `match="US-passthrough CIK resolution is Phase B.2"`). Begründung als Kommentar an die Stelle setzen:

```python
# Removed: the pipeline-level empty-CIK guard test. The ADRResolver now
# guarantees a non-empty CIK or raises (see tests/deepdive/test_adr_resolver.py);
# a ResolvedTicker with cik="" can no longer occur, so the guard is gone (Task 4).
```

- [ ] **Step 2: Compose verdrahten**

`app/deepdive/compose.py` — `build_adr_resolver` ersetzen:

```python
def build_adr_resolver() -> ADRResolver:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    return ADRResolver(table=load_adr_table(), edgar=edgar)
```

(`EdgarClientImpl` + `settings` sind in `compose.py` bereits importiert — `build_filing_fetcher`/`build_insider_fetcher` konstruieren ihn identisch.)

- [ ] **Step 3: Pipeline-Guard entfernen**

`app/deepdive/pipeline.py` — den Block direkt nach `resolved = resolver.resolve(ticker)` (Zeilen 71-76) **löschen**:

```python
    # [1] ADR-Lookup
    resolved = resolver.resolve(ticker)

    # [2] EDGAR-Pull (local-FS cache, ADR-4)
    raw = filing_fetcher.get(resolved.cik, resolved.form_type, use_cache=use_cache)
```

- [ ] **Step 4: Volle Deepdive-Suite laufen**

Run: `uv run python -m pytest tests/deepdive -v`
Expected: PASS. Insbesondere `tests/deepdive/test_compose.py::test_build_adr_resolver_resolves_seed` bleibt grün (NOVO-B.CO ist Tabellen-Treffer, kein Netz; `EdgarClientImpl`-Konstruktion verhält sich wie bei `test_build_insider_fetcher_returns_cached_fetcher`). Falls die UA-Konstruktion in der Testumgebung scheitert, gilt dasselbe Fixup wie bei den bestehenden Compose-Tests (UA via Settings/`.env` gesetzt).

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/compose.py app/deepdive/pipeline.py tests/deepdive/test_pipeline.py
git commit -m "Wire EdgarClient into ADR resolver; drop dead empty-CIK pipeline guard"
```

---

## Task 5: $0-Akzeptanz (US-Resolve + Fetch, EU-fail-loud)

**Kein Unit-Test** — manuelles $0-Gate (kein Gemini), analog `scripts/acceptance_deepdive.py`. Beweist Akzeptanz-Fälle 1 (US dynamisch) + 3 (EU fail-loud) aus dem Brainstorm §5.

**Files:**
- Create: `scripts/acceptance_adr_resolution.py`

- [ ] **Step 1: Akzeptanz-Skript schreiben**

```python
"""$0-Akzeptanz B-Fast US-Pfad (kein Gemini): loest ein US-Ticker NICHT in der
statischen Tabelle dynamisch auf und zieht sein Annual Filing; prueft, dass ein
reiner EU-Titel ohne ADR fail-loud scheitert.

Aufruf (cmd.exe):
  set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
  uv run python scripts\\acceptance_adr_resolution.py
"""
from __future__ import annotations

import sys

from app.deepdive.compose import build_adr_resolver, build_filing_fetcher
from app.errors import DeepDiveError

US_TICKER = "AVGO"   # US 10-K filer, NOT in data/adr_table.json
EU_NO_ADR = "RMV.L"  # pure-EU, no US ADR -> must fail loud


def main() -> int:
    resolver = build_adr_resolver()
    fetcher = build_filing_fetcher()

    # Case 1: US dynamic resolution + filing fetch (NO synthesis -> $0).
    r = resolver.resolve(US_TICKER)
    print(f"[case1] {US_TICKER} -> cik={r.cik} form={r.form_type} adr={r.adr_ticker}")
    assert r.cik and r.cik != "" and r.adr_ticker is None
    raw = fetcher.get(r.cik, r.form_type, use_cache=True)
    print(f"[case1] filing fetched: accession={raw.accession_number} "
          f"date={raw.filing_date} chars={len(raw.document_text)}")
    assert len(raw.document_text) > 1000

    # Case 3: pure-EU no-ADR -> fail loud (DeepDiveError, not a wrong match).
    try:
        resolver.resolve(EU_NO_ADR)
        print(f"[case3] FAIL: {EU_NO_ADR} resolved but should have failed loud")
        return 1
    except DeepDiveError as exc:
        print(f"[case3] OK fail-loud: {exc}")

    print("\nACCEPTANCE OK: US-path resolves + fetches; EU-no-ADR fails loud.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Akzeptanz laufen lassen**

Run (cmd.exe):
```
set FISHERSCREEN_EDGAR_USER_AGENT=Name admin@example.com
uv run python scripts\acceptance_adr_resolution.py
```
Expected: `[case1]` druckt CIK + Form `10-K` + gezogenes Filing; `[case3]` druckt `OK fail-loud`; Schluss `ACCEPTANCE OK`. Exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/acceptance_adr_resolution.py
git commit -m "Add $0 acceptance for B-Fast US-path resolution + EU fail-loud"
```

---

## Self-Review (gegen Brainstorm)

- **ADR-BF-1 (Override-Layer):** statische Tabelle bleibt erste Auflösungsschicht (Task 3 `resolve`) — ✅. Dynamischer Cache (Schicht 2) gehört zum EU-Pfad → Folge-Plan.
- **ADR-BF-2 (OpenFIGI-Service):** bewusst **nicht** hier — gate-abhängig; nur Pre-Flight-Probe (Task 1). ✅ dokumentiert.
- **ADR-BF-3 (Gate/Fork):** Task 1 ist das Go/No-Go-Gate; US-Pfad (2–4) gate-unabhängig; EU-Pfad-Folge-Plan nur bei Go. ✅
- **ADR-BF-4 (Form-Detektion):** Task 2 `detect_annual_form`. ✅
- **ADR-BF-5 (Failure≠Empty):** `detect_annual_form` raised bei Netzfehler (DataSourceError), `None` nur bei echtem Kein-Annual; `get_cik`-Faltung als ehrliche Pre-existing-Notiz markiert (Task 3). ✅
- **ADR-BF-6 (lokaler Cache):** Cache gehört zum EU-Pfad (Schicht 2) → Folge-Plan. US-Pfad braucht keinen ADR-Cache (get_cik hat eigenen In-Instance-Map-Cache). ✅
- **ADR-BF-7 (Einzel-Ticker):** kein Batch — unverändert, CLI bleibt. ✅
- **Akzeptanz §5:** Fall 1 (US dynamisch) + Fall 3 (EU fail-loud) in Task 5; Fall 2 (EU-ADR) ist Post-Gate; Fall 4 (transienter Fehler) durch `detect_annual_form`-DataSourceError-Pfad abgedeckt (Unit, Task 2 Failure-Semantik).
- **Platzhalter-Scan:** keine TBD/„handle errors"; jeder Code-Step zeigt vollen Code. ✅
- **Typ-Konsistenz:** `detect_annual_form(cik) -> str | None`, `ResolvedTicker(ticker, adr_ticker, cik, form_type)`, `get_cik(ticker) -> str | None` — über Tasks 2/3/4 konsistent verwendet. ✅

---

## Nächster Schritt nach diesem Plan

- **Pre-Flight = GO** → eigener `writing-plans`-Lauf „B-Fast EU-ADR-Pfad" (OpenFIGI-Service ADR-BF-2, 3-Schichten-Cache ADR-BF-1/6, EU-Branch im Resolver, Failure≠Empty ADR-BF-5 für OpenFIGI).
- **Pre-Flight = NO-GO** → B-Fast endet mit dem US-Pfad; EU-ADR + EU-Native-Layer wandern als ein Phase-2-Block; PROJEKTSTAND-Honest-Label aktualisieren.
- Danach Akzeptanz-Gate 1.6 (drei reale Deep-Dives) auf der erreichbaren Survivor-Teilmenge.
```
