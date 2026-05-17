# Brainstorm: US-Titel-Bug — Basis-Filter auf V3-Spec ausrichten

**Datum:** 2026-05-17  
**Kontext:** May-2026-Output enthält ausschließlich europäische Aktien (0 US-Titel).
Root Cause: `passes_liquidity_filter` in `app/screener/filters.py` killt alle US-Stocks,
weil yfinance bei US-Titeln außerhalb der Marktzeiten bid=0.0 / ask=0.0 liefert (`not 0.0 == True`).

---

## Diagnose

### Pipeline-Statistik (Mai 2026)

| Stage | Total | US | EU |
|---|---|---|---|
| Universe (Input) | 1.389 | 904 (65 %) | 485 (35 %) |
| Basis-Filter bestanden | 160 | 0 (0 %) | 160 (33 %) |
| Gemini-Scoring | 160 | 0 | 160 |
| In ≥1 Dimension | 104 | 0 | 104 |
| Crosshits | 50 | 0 | 50 |

### Root Cause

```python
# app/screener/filters.py:34
def passes_liquidity_filter(record: ScreenerRecord) -> bool:
    if not record.bid or not record.ask:   # not 0.0 == True → US-Titel rausgefiltert
        logger.warning("ticker=%s bid/ask missing or zero", record.ticker)
        return False
    ...
```

yfinance liefert für US-Stocks außerhalb der NYSE/NASDAQ-Öffnungszeiten (Cloud Run läuft
03:00 UTC = 23:00 ET) bid=0.0 und ask=0.0 zurück. Das ist kein Fehler in den Daten, sondern
ein bekanntes yfinance-Verhalten bei pre-market / after-hours-Abfragen.

---

## Geplante Änderungen

### Schritt 1 — Region-Logging

Region-Erkennung via Ticker-Suffix (`'.' in ticker` → EU, sonst US) in `run_basis_filter`
und `apply_basis_filters`. Logs zeigen US/EU-Verteilung pro Stage, ohne Produktions-Code
zu ändern.

### Schritt 2 — Bid/Ask-Filter ersatzlos entfernen

`passes_liquidity_filter` und `passes_penny_stock_filter` werden aus `filters.py` entfernt.
Begründung: €2B Market Cap (Schritt 3) schließt Penny Stocks strukturell aus; Bid/Ask-Filter
ist timing-sensitiv und taugt nicht als Qualitätsmerkmal.

### Schritt 3 — Basis-Filter auf V3-Spec ausrichten

Neue Filter (ersetzen die alten Pre-V3-Filter):

| Filter | Schwelle | Feld | Format |
|---|---|---|---|
| Market Cap | ≥ €2.000.000.000 | `market_cap_eur` (neu) | EUR, nach FX-Konversion |
| Gross Margin | ≥ 0.30 | `gross_margin` (neu) | Dezimal (0.30 = 30 %) |
| Revenue Growth | ≥ 0.0 | `revenue_growth_yoy` | Dezimal (0.05 = 5 %) |

**Beibehaltene Filter:**
- Volume ≥ 100.000 Avg-Daily-Volume (praktischer Liquiditäts-Safeguard, nicht in V3-Spec, 
  aber kein Schaden)

#### FX-Normalisierung

- yfinance liefert `marketCap` in Listing-Währung (USD für US, GBP für London, etc.)
- `YFinanceClientImpl.get_fx_rate(currency)` holt `{CURRENCY}EUR=X` via yfinance
- `run_basis_filter` führt FX-Konversion durch und speichert in `record.market_cap_eur`
- Lokaler Cache (Dict) pro Run verhindert wiederholte yfinance-Calls für dieselbe Währung
- Bei FX-Fehler: `market_cap_eur = None` → Ticker schlägt market_cap-Filter fehl

#### Datenformat-Hinweise (yfinance)

- `grossMargins`: Dezimal — 0.45 = 45 % (kein Prozent-Wert!)
- `revenueGrowth`: Dezimal — YoY, positiv = Wachstum
- `marketCap`: In Listing-Währung (USD, GBP, CHF, SEK, DKK, NOK, PLN etc.)

---

## Implementierungsplan

1. `app/services/yfinance_client.py` — `get_fx_rate(currency: str) -> float` zu Protocol + Impl
2. `app/models/screener_record.py` — `gross_margin` + `market_cap_eur` Felder; `from_yfinance_info` aktualisieren
3. `tests/screener/test_filters.py` — Tests zuerst (TDD): V3-Filter, FX-Konversion, Region-Logging
4. `app/screener/filters.py` — V3-Implementierung
5. `app/screener/runner.py` — FX-Konversion + Region-Logging

---

## Akzeptanzkriterien

- [ ] `uv run python -m pytest` grün (alle Tests)
- [ ] Tests decken: market_cap_eur ≥ 2B, gross_margin Dezimal-Format, revenue_growth, FX-Konversion
- [ ] `passes_liquidity_filter` und `passes_penny_stock_filter` nicht mehr exportiert
- [ ] Region-Logging in `run_basis_filter`: Info-Level, US/EU-Counts pro Stage
- [ ] (Production) ≥ 15 US-Titel in Top-50-Crosshits bei nächstem Lauf

---

## Verifikation

*(wird nach Implementierung ausgefüllt)*
