---
title: Phase 1.3 — Mehrjahres-Bewertungs-Range (historische Multiple-Bänder im Bewertungsblock)
status: genehmigt (Brainstorm + Review 2026-05-30; Task-0-Probe re-scoped 5J→Mehrjahres)
created: 2026-05-30
phase: 1.3 (Master-Plan docs/superpowers/plans/2026-05-27-phase-1-pareto-b2.md §Phase 1.3)
scope: code + unit-tests; ein bezahlter Akzeptanz-Lauf (NOVO + GOOGL)
predecessor: Phase 1.2 (2a.1c Marker-Vokabular, Merge 0d79495)
---

# Phase 1.3 — Mehrjahres-Bewertungs-Range

> Erweitert den Stage-2a-Bewertungsblock (Prompt + Dossier + Frontmatter) um historische
> Multiple-Bänder: P/E, EV/EBIT, FCF-Yield als „TTM x vs Median y (25-Perz. z)" über die
> real verfügbare Mehrjahres-Tiefe. Genau die am 2026-05-19 als Option (ii) zurückgestellte
> Substanz — jetzt richtig gebaut, mit den drei dort benannten harten Stellen (Splits / FX /
> Restatements) explizit gelöst.
>
> **Re-Scope nach Task-0-Probe (2026-05-30):** Der Master-Plan nannte „5J". Der freie
> yfinance-Probe-Pull belegte jedoch nur 4 Jahres-GJ Fundamental-Tiefe → mit Reporting-Lag
> ~3,1J nutzbar. Entscheidung (Stephan): ehrliches **Mehrjahres**-Label statt aspirational
> „5J". Die Architektur ist quellen-agnostisch (`compute_valuation_history` nimmt
> `list[AnnualFundamental]`, quellenblind) — echte 5J+-Tiefe ist später ein reiner
> Fundamental-Source-Swap (SEC-XBRL, Phase-2-Ticket §13), kein Rebuild. 1.3 baut das volle
> wiederverwendbare Gerüst auf den heute verfügbaren Daten.

## 1 — Ziel & Akzeptanz

Der Bewertungsblock zeigt für jeden der drei Multiples eine historische Vergleichs-Range
(Median + unteres 25-Perzentil über die real verfügbare Mehrjahres-Tiefe, ~3J) neben dem
heutigen TTM-Wert.

**Akzeptanz:** Tool-B-Re-Run gegen NOVO-B.CO + GOOGL (`--peers` Pflicht). Erfüllt, wenn das
NOVO-Dossier „TTM x vs Median y (25-Perz. z)" mit Perzentil-Anker und ehrlichem
Spannen-Label („~3J, N Wo") zeigt.

**Zusätzliches Akzeptanz-Kriterium (Split-Kanarienvogel, siehe §3):** GOOGLs Median-P/E
liegt in einem plausiblen Bereich (Größenordnung ~20–35), **nicht** um den Faktor ~20
daneben. Alphabet hatte am 2022-07-18 einen 20:1-Split innerhalb des Fensters.
Inkonsistente Split-Basen zwischen Preis- und EPS-Bein würden GOOGLs Prä-2022-P/E um genau
diesen Faktor verzerren und wären im Median sofort sichtbar.

> **Probe-Korrektur (Task 0, 2026-05-30):** NOVO-B.CO hatte — entgegen der ursprünglichen
> Annahme — sehr wohl einen Split im Fenster (2023-09-13, 2:1), und dieser liegt **im
> nutzbaren Fundamental-Fenster** (ab ~2023-03). Damit wird die `cum_split`-Normalisierung
> (§3a) an BEIDEN Akzeptanz-Tickern end-to-end getestet (GOOGL 20:1, NOVO 2:1) — eine
> stärkere Probe als geplant, nicht nur unit.

**Honest-Label-Caveat (Regime-Abdeckung, NICHT Rauschen):** ~164 Wochenpunkte sind
statistisch robust — Median/p25 brauchen keine 5 Jahre Punkte. Die Limitation ist die
**Regime-Abdeckung**: ~3 Jahre decken ein Marktregime ab, keine volle historische Spanne.
NOVO-spezifisch: das nutzbare Fenster beginnt ~2023-03, also großteils **nach** der
Ozempic/Wegovy-Re-Rating → der „vs Median"-Anker zeigt evtl. weniger Cheapness als ein
echtes 5–10J-Bild. Genau das behebt der SEC-XBRL-Tiefe-Swap später (§13).

## 2 — Methode (Datenherleitung der Bänder)

Plan-Annahme war „Quarterly-Financials". **Korrektur nach Code-/Realitäts-Check:** yfinance
liefert kein verlässliches 5-Jahres-Quarterly (nur ~5 Quartale). Daher:

- **Preis-Bein (Dichte-Quelle):** wöchentliche Schlusskurse über 5J (~260 Punkte verfügbar),
  **split-bereinigt, NICHT dividenden-bereinigt** (Dividenden-Adjustierung verschöbe das
  historische Kurs-Niveau und damit das P/E-Niveau).
- **Fundamental-Bein (Stufen-Quelle):** Jahres-GJ-Werte aus den Annual-Statements,
  **forward-filled** mit Reporting-Lag (siehe §4). Pro Wochenpunkt gilt der jüngste GJ-Wert,
  dessen Periodenende + Lag ≤ Wochendatum liegt. **Realität (Task 0):** freie yfinance liefert
  nur 4 GJ → die ältesten Wochen haben kein Fundamental zum Forward-Fillen und fallen raus →
  effektiv ~164 verwertbare Punkte über ~3,1J (nicht die vollen ~260).
- **Multiple-Reihe:** Pro Woche ein Quotient (Preis-Bein / Fundamental-Bein), ~164 verwertbare
  Werte. Die Streuung kommt aus dem Preis; das Fundamental ist über jeweils ~52 Wochen konstant.
- **Statistik:** Median + 25-Perzentil über die Wochen-Reihe via stdlib
  `statistics.quantiles(data, n=4, method="inclusive")[0]` (25%) und `statistics.median`.
  **Keine neue Dependency.**

**Ausschluss-Regeln pro Wochenpunkt:**
- Nicht-finite Werte (NaN/inf) ausgeschlossen.
- P/E: EPS ≤ 0 ausgeschlossen (negatives KGV ist nicht interpretierbar).
- EV/EBIT: EBIT ≤ 0 ausgeschlossen (gleiche Begründung).
- FCF-Yield: negative Werte **behalten** (negativer FCF-Yield ist eine echte, aussagekräftige
  Beobachtung — asymmetrisch zu EPS/EBIT bewusst).

## 3 — Die drei harten Stellen

### 3a — Splits (Kern-Lynchpin, propagiert über P/E hinaus)

yfinance `.history` liefert Preise auf **current split basis** (back-adjusted). yfinance
`income_stmt` „Diluted EPS" ist **as-reported** (Basis des jeweiligen Berichtsjahres) — für
Prä-Split-Jahre also auf Prä-Split-Basis. Ungeprüft kombiniert ergibt das
`adjusted_price / unadjusted_EPS` → P/E um den kumulativen Split-Faktor daneben.

**Kontingenz-Zweig (deterministisch, kein Pass/Fail-Hoffen):** Der Preis ist bereits
back-adjusted (current basis); **nur das EPS-Bein** wird über einen **kumulativen
Split-Faktor** auf dieselbe Basis gebracht. Quelle: `yf.Ticker(t).splits` (Split-Ratio je
Ex-Datum, z.B. 20.0 für einen 20:1-Split). Für GJ `t`:

```
cum_split(t) = Produkt aller Split-Ratios mit Ex-Datum > GJ-Periodenende(t)
EPS_current(t) = EPS_reported(t) / cum_split(t)
```

Damit liegt EPS auf derselben Basis wie der back-adjusted Preis. Liefert eine künftige
yfinance-Version EPS bereits current-basis-normalisiert, sind alle `cum_split` = 1.0 und der
Schritt ist ein No-op — die Korrektur ist in beiden Fällen korrekt, nicht von der
yfinance-Variante abhängig.

Die TDD-Probe stellt fest, **ob** die Beine roh schon konsistent sind; der Code wendet die
Normalisierung **immer** an (No-op falls schon konsistent). GOOGL ist das End-to-End-Gate (§1).

### 3b — Historische EV / Markt-Kap (explizite Ableitung)

EV/EBIT über die Historie braucht eine historische Markt-Kap. Es gibt keine
yfinance-Shares-Reihe → **implizite Aktienzahl** aus den ohnehin gepullten Feldern:

```
shares_current(t) = net_income(t) / EPS_current(t)        # deshalb net_income UND EPS gepullt
market_cap(woche) = preis_current(woche) × shares_current(GJ ff.)
EV(woche)         = market_cap(woche) + total_debt(GJ ff.) − cash(GJ ff.)
EV/EBIT(woche)    = EV(woche) / EBIT(GJ ff.)
```

`shares_current` erbt die Split-Basis von `EPS_current` (§3a): net_income ist
split-invariant (Währungs-Aggregat), also ist `shares_current` automatisch current-basis und
mit dem back-adjusted Preis konsistent. **EV/EBIT ist damit NICHT split-/FX-neutral** — es
läuft über die implizite-Shares-Brücke und teilt deren Basis-Annahmen.

**Honest-Label:** total_debt/cash/EBIT sind GJ-granular forward-filled; nur die Markt-Kap
variiert wöchentlich. Innerhalb des Jahres ändern sich Debt/Cash → die EV-Reihe ist eine
Approximation (im Dossier als Mehrjahres-Band gelabelt, nicht als tagesgenaue EV-Historie).

**Honest-Label (zweite Approximationsquelle):** `shares = net_income / diluted_EPS`
unterstellt `net_income ≈ net-income-to-common`. Bei Filern mit materiellem
Minderheitsanteil oder Vorzugskapital weicht das leicht ab → kleine Verzerrung in den
impliziten Shares → EV/EBIT. Für die Large-Cap-Targets vernachlässigbar, aber als bekannte
Quelle benannt.

**Edge:** `EPS_current(t) == 0` oder Vorzeichen-Mismatch `net_income/EPS` → `shares_current`
nicht ableitbar → dieser GJ für EV/EBIT übersprungen (P/E unabhängig behandelt).

**EPS-Verfügbarkeit gated BEIDE Multiples:** fehlt/NaN das `diluted_eps` eines GJ, scheitert
nicht nur das P/E-Bein, sondern auch die implizite-Shares-Brücke → EV/EBIT für diesen GJ
weg. yfinance-Feld-Wackligkeit ist aus Stage 2a bekannt (`.analysis` weg, EBIT nur aus
income_stmt) → die Per-GJ-EPS-Verfügbarkeit ist expliziter §14-Probe-Output, damit eine
dünne EPS-Reihe eine erwartete `partial`-Einstufung ist, keine Akzeptanz-Überraschung.

### 3c — FX (Cross-Currency) und Restatements

Alle drei Multiples mischen Listing-Währung (Preis/Markt-Kap) mit Reporting-Währung
(EPS/EBIT/Debt/Cash): P/E = Preis(listing)/EPS(financial); EV/EBIT enthält Markt-Kap(listing)
+ Debt/Cash(financial). Sie sind FX-neutral **genau dann**, wenn Listing == Financial.

- **listing == financial:** volle Range rechnen (NOVO-B.CO: DKK/DKK ✓, GOOGL: USD/USD ✓).
- **listing ≠ financial:** Status `skipped_fx`, Renderer „n/a (FX: Listing≠Reporting)",
  `currency_note` gesetzt, Phase-2-Backlog-Marker. Kein fragiler historischer FX-Reihen-Eigenbau.
- **listing oder financial None/fehlt (§3d):** Status `na_data` — **nicht** auf „gleich"
  defaulten (stiller Cross-Currency-Mix wäre ein latenter Bug).

**Restatements:** yfinance liefert keine point-in-time-as-reported Stände. Honest-Label:
„Fundamentaldaten in der aktuell-restated yfinance-Fassung". Kein stiller Mix as-reported/restated.

### 3d — Währungs-Bestimmung & None-Handling

`listing_ccy = info["currency"]`, `financial_ccy = info["financialCurrency"]`. Wenn eine None
oder fehlt → `na_data` (siehe §3c). Beide Akzeptanz-Ticker testen den None-Fall nicht live →
**dedizierter Unit-Test** für currency-None.

## 4 — Look-ahead-Milderung

Forward-Fill nach Periodenende statt Filing-Datum ist für einen Kontext-Anker über ~260
Punkte vertretbar (gelabelt). Billige materielle Milderung ohne neuen Datenpfad: ein fixer
Reporting-Lag.

```
REPORTING_LAG_DAYS = 90    # benannte Konstante, Single-Source
as_of_fundamental(woche) = jüngstes GJ mit (Periodenende + REPORTING_LAG_DAYS) ≤ Wochendatum
```

Reduziert den Look-ahead materiell (Fundamentaldaten sind erst ~1 Quartal nach Periodenende
veröffentlicht). Kein Filing-Datum nötig.

## 5 — Datenmodell (`app/models/deep_dive_record.py`)

```python
MultipleStatus = Literal["complete", "partial", "skipped_fx", "na_data"]

class MultipleStats(BaseModel):       # model_config = ConfigDict(extra="forbid")
    median: float | None = None
    p25: float | None = None
    n_obs: int = 0
    span_years: float | None = None
    status: MultipleStatus = "na_data"

class ValuationHistory(BaseModel):    # extra="forbid"
    pe: MultipleStats
    ev_ebit: MultipleStats
    fcf_yield: MultipleStats

# QuantSnapshot += valuation_history: ValuationHistory | None = None
```

**Status-Schwellen als benannte Konstanten** (Single-Source neben der Logik, analog
`VINTAGE_THRESHOLD_DAYS`). Zwei Klassen — die Unterscheidung ist bewusst:

```python
# POLICY — jetzt fixiert, NICHT an Ticker-Pulls kalibriert. Das ist ein Urteil
# ("wie dicht muss ein Band sein, um aussagekräftig zu sein"), das nicht davon
# abhängen darf, was zwei Ticker zufällig liefern. Ein löchriger Pull soll
# AUFFALLEN, nicht die Schwelle nach unten ziehen.
VALUATION_COMPLETE_MIN_DENSITY = 40     # obs pro Jahr (Dichte-Prüfung gegen löchrige Reihen)
VALUATION_PARTIAL_MIN_OBS      = 52     # >= 1 Jahr wöchentlich

# DATEN-GEDECKELT — der realen Fundamental-Tiefe folgend (Task-0-Probe 2026-05-30).
# Probe-Befund: freie yfinance income_stmt = NUR 4 GJ [2025..2022]; mit
# REPORTING_LAG=90 ist der älteste GJ erst ~2023-03-31 verfügbar → effektiv
# Fundamental-gedeckte Spanne ~3,1J (~164 Wochen, Dichte ~52/J). 5J ist mit der
# freien Quelle strukturell NICHT erreichbar. 2.8 = knapp unter der realen ~3J-
# Tiefe: "complete" = "volle verfügbare ~3J erreicht"; ein IPO-junger 2J-Ticker
# bleibt korrekt `partial` (statt sich fälschlich complete zu nennen).
VALUATION_COMPLETE_MIN_SPAN_YEARS = 2.8
```

- `complete`: `span_years ≥ MIN_SPAN` UND `n_obs / span_years ≥ 40`
- `partial`:  `n_obs ≥ 52` aber nicht `complete` (z.B. IPO-junger 2J-Ticker)
- `na_data`:  `n_obs < 52`, oder Daten-/Preis-Pull-Fehler
- `skipped_fx`: Listing ≠ Financial (überschreibt obs-basierte Einstufung)

Die Dichte-Prüfung (`obs/span`) verhindert, dass eine zeitlich breite, aber löchrige Reihe
fälschlich als `complete` gilt.

**Policy-gegen-Daten-Regel (Richtungs-Umkehr):** Die Dichte-/obs-Policy (40/52) bleibt fix;
sie wird NICHT gesenkt, um einen löchrigen Pull „complete" zu machen — ein löchriger Pull
soll auffallen. `MIN_SPAN` ist die EINZIGE daten-gedeckelte Schwelle und folgt der realen,
vom Probe-Pull belegten Fundamental-Tiefe.

**Label-Provenance (Task-0-Befund, entschieden):** Der Probe-Pull belegte ~3,1J reale
Fundamental-Tiefe (4 GJ, Lag-gedeckelt). „5J" ist mit der freien yfinance-Quelle nicht
einlösbar. Entscheidung (Stephan, 2026-05-30): **ehrliches Mehrjahres-Label**. Konkret:
- Heading + Zeilen-Label tragen NICHT „5J", sondern „Mehrjahres" bzw. die real gerenderte
  Spanne (`(~{span}J, {n} Wo)`-Prefix aus den tatsächlichen `MultipleStats`).
- `MIN_SPAN = 2.8`, damit ein gesundes ~3J-Band `complete` erreicht.
- `SourceCoverage.valuation` nennt die reale Spanne als Honest-Label.
Ein als „5J-Median" gerendertes ~3J-Band wäre genau die Provenance-Lücke, die wir vermeiden;
das dynamische Spannen-Label schließt sie strukturell. Die Schwäche ist Regime-Abdeckung
(ein ~3J-Marktregime), nicht statistisches Rauschen — 164 Punkte tragen Median/p25 robust.

## 6 — Pure-Berechnung: `app/deepdive/valuation_history.py`

Neues Modul analog `trend_metrics.py` — reine Funktionen, keine I/O, voll unit-testbar:

```python
def compute_valuation_history(
    weekly_close: list[tuple[date, float]],      # split-adj, NICHT div-adj
    annual: list[AnnualFundamental],             # GJ-Ende, net_income, diluted_eps, ebit,
                                                 #   free_cashflow, total_debt, cash
    splits: list[tuple[date, float]],            # Ex-Datum, Ratio (für cum_split, §3a)
    listing_ccy: str | None,
    financial_ccy: str | None,
) -> ValuationHistory: ...
```

Verantwortung: cum_split-Normalisierung (§3a), implizite-Shares-/EV-Ableitung (§3b),
as-of-Forward-Fill mit Lag (§4), Ausschluss-Regeln (§2), Median/p25, Status-Einstufung (§5),
FX-/None-Gates (§3c/§3d). Kein Netzwerk, kein Cache, keine yfinance-Imports.

## 7 — I/O-Service: `app/services/historical_data_service.py`

- **YFinance-Protokoll + Impl:** neue Methode `get_weekly_close_5y(ticker)` → wöchentliche
  Schlusskurse (split-adj, nicht div-adj) + `get_splits(ticker)` → Split-Events. (Exakte
  yfinance-API-Flags — `auto_adjust`, `interval="1wk"`, `.splits` — werden in TDD gegen
  Realdaten verifiziert.)
- **`get_annual_series` erweitert:** zieht zusätzlich `net_income`, `diluted_eps`,
  `free_cashflow`, `total_debt`, `cash` aus den **bereits geholten** Statements (kein
  Extra-Pull), pullt Wochen-Preis + Splits, ruft `compute_valuation_history`, legt das
  Ergebnis als `valuation_history`-Key in den series-Dict.
- **Fail-soft:** Preis-/Split-Pull-Fehler → `ValuationHistory` mit allen Stats `na_data` +
  WARNING; der Deep Dive läuft weiter (kein Abbruch — Präzedenz: Forward-Estimates in
  `quant_join.py`).

## 8 — Cache: `app/deepdive/historical_cache.py`

- `CACHE_SCHEMA_VERSION` **2 → 3** (neues Read-Pfad-Feld). Lese-Pfad behandelt Mismatch als
  Cache-Miss → Lazy-Refetch + Re-Write (Mechanik existiert bereits, Z. 33-44).
- Payload bekommt eine **kompakte valuation_history-Summary** (die `ValuationHistory`-Stats)
  neben `series`. **Die ~260-Wochen-Preisreihe wird NICHT gecached** — nur bei Miss frisch
  gepullt; gecached wird ausschließlich das berechnete Band.
- TTL 90 Tage bleibt: das Band bewegt sich langsam; der frische TTM-Wert kommt ohnehin live
  aus `point_in_time`, nicht aus dem Band.

## 9 — quant_join: `app/deepdive/quant_join.py`

- `build_quant_snapshot`: `raw["valuation_history"]` → `ValuationHistory` →
  `snapshot.valuation_history`.
- `SourceCoverage.valuation`-Default aktualisiert auf status-bewusste Beschreibung (skipped_fx
  sichtbar machen).
- **`compose.py` braucht KEINE Konstruktions-Änderung:** verifiziert `compose.py:54`
  `CachedHistoricalData(service=HistoricalDataServiceImpl(...))` — der Service erweitert sich
  intern, die neuen yfinance-Methoden liegen im schon injizierten Impl.
  `pipeline.py`/`__main__.py` reichen nur das `build_quant`-Callable durch — unverändert.

## 10 — Renderer: `app/deepdive/valuation_block.py`

- `_HEADING`: „## Bewertung & Kapitalstruktur (TTM-Stand + Mehrjahres-Median/Perzentil-
  Vergleich)". **Betrifft 3 bestehende Test-Asserts** (`test_valuation_block.py` Z. 28, 176,
  258 — re-verifiziert) → mit aktualisieren.
- **Eine neue konsolidierte Zeile** „Bewertungs-Range (~{span}J, {n} Wo): …" **nach** der
  `Bewertung:`-Zeile, **vor** `Kapitalstruktur:`. Der `(~{span}J, {n} Wo)`-Prefix kommt aus
  dem repräsentativen Multiple (P/E bevorzugt, sonst erstes nicht-`na`/-`skipped`) und macht
  die reale Spanne sichtbar (Label-Provenance, §5). Pro Multiple `TTM x vs Median y
  (25-Perz. z)`. Die TTM-Legs stammen aus den **schon im Renderer berechneten** Werten
  (Byte-Gleichheit mit der Bewertung-Zeile).
- **fail-soft pro Multiple** nach Status: `complete`/`partial` → Werte zeigen (die Spanne
  steht im Zeilen-Prefix, kein per-Segment-Wo-Suffix nötig); `skipped_fx` → „n/a (FX:
  Listing≠Reporting)"; `na_data` → „n/a (Historie unvollständig)". Sind ALLE drei
  `skipped_fx` → „Bewertungs-Range: n/a (FX: Listing≠Reporting)"; alle `na_data` →
  „Bewertungs-Range: n/a (Mehrjahres-Historie unvollständig)". `valuation_history is None` →
  „Bewertungs-Range: n/a (Historie nicht verfügbar)" (kein stilles Weglassen — fail loud per
  Honest-Label).
- **facts-only:** der Renderer interpretiert nicht („teuer/billig"); er liefert die Zahlen,
  das Modell ordnet ein.
- **2b/2c byte-identisch:** Consensus-, Forward-, Peer-Zeilen unverändert; Ordering bleibt
  `kapital < consensus < forward < peers`. Der geteilte Block fließt automatisch in Prompt +
  Dossier + Frontmatter.

## 11 — SourceCoverage (`app/models/deep_dive_record.py`)

`valuation`-Default neu: „TTM + Mehrjahres-Median/Perzentil (KGV/EV-EBIT/FCF-Yield;
Wochen-Preis × GJ-Fundamental, split-normalisiert; reale Tiefe ~3J, da freie yfinance nur
4 GJ liefert — 5J+ via SEC-XBRL ist Phase-2); cross-currency Honest-Label-Skip;
restated-Fassung".

## 12 — Tests (RED zuerst, Coverage ≥ 96 %)

**Pure (`test_valuation_history.py`):**
- Median/p25 hand-gerechnet gegen bekannte Eingabe.
- cum_split-Normalisierung: GOOGL-artiger 20:1-Fall — Prä-Split-EPS wird korrekt auf current
  basis gebracht, P/E-Reihe ohne Faktor-20-Sprung.
- as-of-Forward-Fill **mit** REPORTING_LAG_DAYS (Wochenpunkt vor Lag-Grenze nimmt das
  Vorjahr).
- implizite-Shares-/EV-Ableitung; Edge EPS==0 / Vorzeichen-Mismatch → GJ übersprungen.
- Ausschluss: EPS≤0 & EBIT≤0 raus, FCF-Yield-Negative bleiben; NaN/inf raus.
- Status-Schwellen: complete/partial/na_data inkl. **Dichte-Prüfung** (löchrige 4,5J-Reihe →
  nicht complete).
- FX-Skip (listing≠financial → skipped_fx) **und currency-None → na_data**.

**Modell:** `MultipleStats`/`ValuationHistory` Validierung, `status`-Literal, `extra="forbid"`.

**Renderer (`test_valuation_block.py`):** per-Multiple-Status-Varianten; all-skipped_fx &
all-na_data Collapse; None → Honest-Label; Spannen-Prefix („~3J, N Wo", **kein „5J"**);
TTM-Leg byte-gleich zur Bewertung-Zeile; **3 Heading-Asserts aktualisiert**; 2b/2c
byte-identisch + Ordering-Guard.

**Service (`test_historical_data_service.py`):** neue Annual-Zeilen vorhanden;
`get_weekly_close_5y`/`get_splits` (gemockt); fail-soft bei Preis-Pull-Fehler → na_data.

**Cache (`test_historical_cache.py`):** v2→3-Invalidierung (alter Cache = Miss);
Summary-Roundtrip; Wochenreihe wird **nicht** persistiert.

**quant_join (`test_quant_join.py`):** Feld gesetzt; status durchgereicht; fail-soft.

## 13 — Nicht-Ziele & Follow-ups

- **Kein Prompt-Text-Edit in 1.3** — der erweiterte Block fließt automatisch in den Prompt.
- **Marker-Vokabular-Nachzug** (`[Median]`/`[Bewertungs-Range]` o.ä.): erwarteter
  Katalog-Wachstums-Hit aus 1.2. Wenn das Modell die neue Substanz mit neuem Quant-Label
  zitiert → eine Zeile in `_QUANT_MARKER_VOCAB` (`synthesis.py:53`) — **separater
  Mini-Commit nach Akzeptanz**, nicht im 1.3-Kern.
- **SEC-XBRL-Tiefe-Swap (definiertes Phase-2-Tiefe-Ticket):** Echte 5–10J-Fundamental-Tiefe
  via SEC EDGAR `companyfacts` (frei, ~10J, CIK-Lookup + HTTP-Plumbing aus Punkt 5 schon da).
  Der Seam ist bereit: `compute_valuation_history(annual: list[AnnualFundamental], …)` ist
  quellenblind → nur ein neuer Fundamental-Source-Adapter, kein Rebuild. **Aufwands-Flag:**
  companyfacts-JSON-Parsing, Unit-Handling, Fiscal-Period-Alignment, und vor allem
  **us-gaap vs. ifrs-full-Taxonomie** — NOVO bilanziert IFRS, seine 20-F-XBRL-Tags heißen
  anders als bei us-gaap-Filern. Sprengt die 1.3-Schätzung → bewusst eigenes Phase-2-Ticket,
  kein Mid-Stream-Quellen-Tausch (Sequenz-Disziplin, Lesson v). Behebt die Regime-Abdeckungs-
  Schwäche + den NOVO-Ozempic-Caveat aus §1.
- **Cross-Currency-Hist-FX** (Per-Periode-FX-Reihe): Phase-2-Backlog.
- **Kein 1.4-Vorgriff** (Form-4-Insider). Kein PROJEKTSTAND-Edit vor Merge.

## 14 — Verifizierte Code-Fakten (Start-Check 2026-05-30, sauber re-grep)

- Konstruktions-Stelle: `app/deepdive/compose.py:54` (`build_quant_builder`). `_build_services`
  existiert nicht. `pipeline.py`/`__main__.py` unverändert.
- `CachedHistoricalData` + `CACHE_SCHEMA_VERSION = 2` in `app/deepdive/historical_cache.py:15`.
- `HistoricalDataServiceImpl` (kein Cache) in `app/services/historical_data_service.py:34`.
- 3 Heading-Asserts in `tests/deepdive/test_valuation_block.py` (Z. 28, 176, 258).
- **TDD-Start:** vor dem ersten RED erneut re-grep dieser Fakten (Anti-Pattern
  plan-doc-verify-against-code).

**Probe-Pull-Ergebnisse (Task 0, ausgeführt 2026-05-30, NOVO-B.CO + GOOGL):**
1. **GJ-Fundamental-Tiefe = 4** für beide (`income_stmt`-Spalten [2025, 2024, 2023, 2022]) —
   NICHT 5. → `MIN_SPAN = 2.8`, Label „Mehrjahres" + reale Spanne (§5/§10).
2. **`diluted_eps` voll verfügbar** (keine NaN) für beide; Label exakt „Diluted EPS".
3. **Annual-Zeilen-Labels byte-bestätigt:** „Net Income", „EBIT", „Free Cash Flow",
   „Total Debt", „Cash And Cash Equivalents" — alle present. Keine Label-Drift.
4. **Wochen-Preis:** 261 Punkte, span 4,98J; `history(period="5y", interval="1wk",
   auto_adjust=True)` ok. Effektiv Fundamental-gedeckt nach Lag: ~3,1J / ~164 Wochen.
5. **Splits:** GOOGL 20:1 (2022-07-18) ✓ Haupt-Kanarienvogel; NOVO-B.CO 2:1 (2023-09-13) —
   im nutzbaren Fenster, zweiter End-to-End-Split-Test (§1). `.splits` = pandas Series
   {Timestamp: ratio}.
6. Currencies: GOOGL USD/USD, NOVO-B.CO DKK/DKK — beide gleichwährig, volle Range.
