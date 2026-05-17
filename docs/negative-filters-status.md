# Negativ-Filter — Status-Audit

> Audit-Stand: 2026-05-17. Quelle des Soll: V3-Architektur §4.1.
> Belegt gegen Code-Stand Branch `chore/negative-filters-audit`.
> Reines Status-Dokument — keine Roadmap, keine Empfehlungen (siehe §4).

## 1. Methodik

TODO #10 spricht von „8 V3-Filtern". Dieses Audit deckt bewusst **alle real
wirkenden Filter** ab — die 9 Knock-out-Kriterien aus V3-Architektur §4.1
**plus** den Nicht-V3-Volume-Safeguard (`MIN_AVG_DAILY_VOLUME`) —, weil die
effektive Score-Basis von *jedem* aktiven Filter bestimmt wird, nicht nur
von den spezifizierten. Der Volume-Filter ist kein V3-Kriterium, wurde aber
am 2026-05-17 bewusst als praktischer Liquiditäts-Safeguard beibehalten
(Decisions-Log PROJEKTSTAND, 2026-05-17). Status- und Aufwands-Vokabular
sind unten fixiert, damit das Dokument vergleichbar altert.

**Status:** `Aktiv` (wirkt wie V3 spezifiziert) · `Aktiv (vereinfacht)`
(implementiert, aber methodisch reduziert ggü. V3) · `Aktiv (eingeschränkt)`
(Logik wie V3 spezifiziert, Wirkung aber auf eine Teilmenge des Universums
beschränkt — z. B. nur US-Ticker mit CIK) · `Stub` (Funktion existiert, gibt
konstant Pass zurück) · `Nicht implementiert` (kein Code, kein Datenfeld).

**Aktivierungsaufwand (Grobskala, keine Stunden):** `Trivial` (Schwellen-/
Config-Wert) · `Klein` (neues Feld aus vorhandenem yfinance-`info`-Dict +
Filterfunktion + Tests) · `Mittel` (neue Datenquelle wie yfinance
financials/balance-sheet-Historie + Mehrjahres-Aggregation + Tests) ·
`Groß` (neue externe Integration ohne saubere API) · `Unklar` (keine
bekannte verlässliche Datenquelle; Research-Spike nötig). `—` = entfällt
(Filter bereits aktiv).

## 2. Statustabelle

| # | Filter | V3-Bezug (§4.1 / Fisher) | V3-Soll | Code-Ist | Status | Datenquelle | Aktivierungsaufwand |
|---|---|---|---|---|---|---|---|
| 1 | Insolvenz / Chapter 11 / Going Concern | §4.1 Z1 / trivial | Knock-out bei Insolvenz/Chapter-11/Going-Concern | Going-Concern via EFTS-Volltext „raise substantial doubt" in 10-K/10-Q letzte 24 Mon. (`edgar_client.py:has_going_concern`); Insolvenz/Chapter-11-Status wird **nicht** separat geprüft | Aktiv (vereinfacht) | SEC EDGAR EFTS (nur US m. CIK) | Mittel (EU-Abdeckung) / Unklar (expliziter Chapter-11-Status) |
| 2 | Marktkapitalisierung < 2 Mrd EUR | §4.1 Z2 / Datenqualität | < €2 Mrd raus | `filters.py:passes_market_cap_filter` ≥ `MIN_MARKET_CAP_EUR` (2e9), FX-normalisiert via `runner.py:_resolve_market_cap_eur` | Aktiv | yfinance `marketCap` + `get_fx_rate` | — |
| 3 | Bruttomarge < 30 % in 8/10 Jahren | §4.1 Z3 / Punkt 5 | < 30 % in 8 von 10 Jahren | `filters.py:passes_gross_margin_filter`: **Single-Value** `grossMargins` ≥ 0.30, keine 10-Jahres-Historie | Aktiv (vereinfacht) | yfinance `info['grossMargins']` (Punktwert) | Mittel |
| 4 | Negative Bruttomarge in 2/3 letzten Jahren | §4.1 Z4 / Punkt 5 | negativ in 2 von 3 Jahren | kein Code, kein Datenfeld; lose von #3 (Single-Value) mit-abgedeckt | Nicht implementiert | yfinance financials-Historie | Mittel |
| 5 | Umsatz-CAGR 10J < 0 % | §4.1 Z5 / Punkt 1 | 10-Jahres-CAGR < 0 % | `filters.py:passes_revenue_growth_filter`: **Single-Value** `revenueGrowth` (YoY) ≥ 0.0, kein 10J-CAGR | Aktiv (vereinfacht) | yfinance `info['revenueGrowth']` (YoY-Punktwert) | Mittel |
| 6 | Aktien-Outstanding-Wachstum > 5 % p.a. / 5J | §4.1 Z6 / Punkt 13 | > 5 % p.a. über 5J raus | kein Filter, kein Datenfeld in `ScreenerRecord` | Nicht implementiert | yfinance shares-outstanding-Historie | Mittel |
| 7 | Verluste in 5/10 letzten Jahren | §4.1 Z7 / allgemein | Verlust in 5 von 10 Jahren | kein Filter, keine Net-Income-Historie in `ScreenerRecord` | Nicht implementiert | yfinance income-statement-Historie | Mittel |
| 8 | Aktive SEC-Enforcement | §4.1 Z8 / Punkt 15 | Knock-out bei aktiver Enforcement | `edgar_client.py:has_active_enforcement` loggt „not implemented" und gibt konstant `False` zurück; ungecacht (`cached_edgar_client.py:has_active_enforcement` delegiert nur) | Stub | SEC EDGAR Litigation Releases (keine saubere API) | Groß |
| 9 | Restatement letzte 3 Jahre | §4.1 Z9 / Punkt 10/15 | Restatement in letzten 3J | `edgar_client.py:has_restatement`: 8-K Item 4.02 letzte 3J aus `submissions.json`; greift nur für US-Ticker mit CIK, EU → `edgar_skipped` | Aktiv (eingeschränkt) | SEC EDGAR submissions (nur US) | Groß (EU-Abdeckung: Nicht-US-Filing-Quellen) |
| + | Volume ≥ 100k Avg-Daily (**Nicht-V3**) | nicht in V3 | — (kein V3-Kriterium) | `filters.py:passes_volume_filter` ≥ `MIN_AVG_DAILY_VOLUME` (100 000); bewusster Safeguard | Aktiv | yfinance `info['averageVolume']` | — |

Reihenfolge der Filterprüfung im Code (`filters.py:_get_fail_reason`):
Volume → Market Cap → Gross Margin → Revenue Growth; danach EDGAR-Stufe
(`filters.py:apply_edgar_filters`): Restatement → Going Concern →
Enforcement. EDGAR läuft erst auf der Basis-Filter-Restmenge
(`runner.py:run_screener` ruft `run_basis_filter` dann `run_edgar_filter`).

## 3. Querschnitts-Befunde

### 3.1 EU-CIK-Blindfleck (wichtigster Befund)

Die drei EDGAR-Filter (`has_restatement`, `has_going_concern`,
`has_active_enforcement`) greifen ausschließlich für Ticker, deren CIK
`edgar_client.py:get_cik` über die SEC-`company_tickers.json` (US-zentriert)
auflöst. `runner.py:run_edgar_filter` setzt für jeden Ticker ohne CIK
`record.edgar_skipped = True`; `filters.py:apply_edgar_filters` reicht
solche Records ungeprüft durch (`filter_passed_edgar = None`). Im
1.389-Ticker-Universum (Stand `data/universe.json`) sind ~485 EU-Ticker
(Ticker mit „." — Regions-Heuristik `"." in ticker`, vgl.
`filters.py:apply_basis_filters` / `runner.py:run_basis_filter`): für
dieses ~⅓ des Universums sind alle drei EDGAR-Filter still inaktiv. Ein EU-Titel
ohne Restatement-/Going-Concern-Flag wurde **nicht geprüft**, nicht
freigesprochen.

### 3.2 8-vs-9-Diskrepanz

V3-Architektur §4.1 listet **9** Knock-out-Zeilen. PROJEKTSTAND
konsolidiert sie als „8 V3-Filter", indem „Insolvenz / Chapter 11 / Going
Concern" und der Going-Concern-Aspekt als ein Punkt gezählt werden. Dieses
Audit führt alle 9 §4.1-Zeilen einzeln plus den Nicht-V3-Volume-Filter. Die
Diskrepanz ist eine reine Zähl-/Konsolidierungsfrage, kein fehlender Filter
— sie wird hier nur dokumentiert, die V3-Architektur-Doku wird **nicht**
geändert (separater PROJEKTSTAND-Backlog-Punkt zur V3-Doc-Drift).

### 3.3 Cache-Verhalten

`cached_edgar_client.py` speichert `has_restatement` und
`has_going_concern` gemeinsam in einem Firestore-Dokument pro CIK mit
7-Tage-TTL (`_TTL_SECONDS = 7 * 24 * 3600`). `has_active_enforcement` wird
nicht gecacht (Stub, delegiert direkt). Basis-Filter (yfinance) nutzen den
separaten `universe_cache`/`dev_`-Mechanismus, nicht den EDGAR-Cache.

## 4. Implikationen für die Score-Interpretation

*Strikt deskriptiv — was ist, nicht was zu tun ist.*

- Die Score-Basis eines Titels ist die Schnittmenge: Volume ≥ 100k **und**
  Market Cap ≥ €2 Mrd **und** Gross Margin (Punktwert) ≥ 30 % **und**
  Revenue Growth (YoY-Punktwert) ≥ 0 %. Die V3-Mehrjahres-Schärfen
  (8/10-Jahre-Marge, 10J-CAGR, Verlust-/Verwässerungs-Historie) wirken
  faktisch nicht; Titel mit schwacher Langzeit-, aber solider
  Momentaufnahme passieren die Basis-Stufe.
- Restatement/Going-Concern als Knock-out wirken nur für US-Titel mit CIK.
  Für EU-Titel ist das Fehlen dieser Flags Ausdruck eines übersprungenen
  Checks, nicht einer bestandenen Prüfung.
- Aktive SEC-Enforcement fließt derzeit in keine Entscheidung ein (Stub
  liefert konstant „kein Knock-out").
- Für die Tool-B-EDGAR-Pipeline ist der Ist-Stand: `has_restatement` und
  `has_going_concern` sind nutzbare, gecachte US-Signale; eine
  EU-Abdeckung und ein Enforcement-Signal existieren nicht und sind dort
  als Datenlücke vorzufinden.
