# Funnel-Instrumentierung + Report-Header — Design (Phase 1)

> Status: Spec, vor Implementierung. Branch `feature/funnel-instrumentation-phase1`.
> Datum: 2026-06-06.

## Ziel

Das einmalige 35er-Audit in **stehende Instrumentierung** verwandeln. Jeder
Funnel-Austritt bekommt einen benannten Grund (`reason_code`) und eine
Schwere-Klasse (`severity_bucket`), sodass „fallen nur Uninteressante raus,
oder auch welche, die rein gehören?" bei jedem Lauf eine **Zahl** ist statt
ein Gefühl.

## Nicht-Ziel / Disziplin (harte Grenze)

- **Reine Instrumentierung — null Änderung an Gate-/Filter-/Score-Logik.**
  Kein Drop-Ergebnis, kein Stufen-Count ändert sich durch dieses Ticket.
- Bei jedem Hinweis, dass der Code einen Logik-Eingriff nahelegt:
  **STOP/BLOCKED melden, nicht selbst entscheiden.**
- Funnel-Zahlen nur aus **Cold-Run** lesen (Cache-Purge `universe_cache` +
  `dev_edgar_cache`), sonst maskiert warmer Cache die Counts.
- `reason_code` + Tripwires aus Whitelist-Enums, deterministisch, objektive
  Signale — **kein subjektives Urteil, kein erfundener Code.**
- Sequenzielle Sub-Phasen, eigener Branch, kein Push/Merge ohne Stephans Go,
  Paid-Acceptance-Run als separates Gate.

---

## 1. `reason_code`-Enum (verifiziert gegen `filters.py`)

Jeder Code hat **genau eine** Emit-Stelle. Mapping 1:1 zum tatsächlichen
`record.filter_failed_reason`:

| reason_code | Code-Quelle (`filter_failed_reason` / Stage) |
|---|---|
| `RESOLUTION_DEGRADED_DICT` | `DegradedDataError` an Catch-Site in `run_basis_filter` |
| `RESOLUTION_UNRESOLVED` | generischer `DataSourceError`/`ValidationError` ebd. |
| `GATE_VOLUME` | `"avg_volume"` (`filters.py:43`) |
| `GATE_MARKET_CAP` | `"market_cap"` (`filters.py:45`) |
| `GATE_GROSS_MARGIN` | `"gross_margin"` (`filters.py:47`) |
| `GATE_REVENUE_GROWTH` | `"revenue_growth"` (`filters.py:49`) |
| `GATE_RESTATEMENT` | `"restatement"` (`filters.py:86`) |
| `GATE_GOING_CONCERN` | `"going_concern"` (`filters.py:90`) |
| `GATE_ENFORCEMENT` | `"enforcement"` (`filters.py:94`) |
| `SCORE_BELOW_THRESHOLD` | gescort, aber `<min_dimensions` Dims `≥ score_threshold` |
| `SCORE_NOT_SCORED` | `gemini_dimensions is None` (Gemini-Call schlug fehl) |

**Verifikations-Korrekturen gegenüber dem Start-Vorschlag:**
- `GATE_MARKET_CAP` + `GATE_RESTATEMENT` ergänzt (existieren im Code, fehlten
  im Vorschlag — ohne sie zählten echte Drops still als nichts).
- `DUPLICATE_BENIGN` gestrichen: kein Erzeuger im Lauf. Dedup passiert in
  `build_universe` (`combined = sorted(set(...))`); Duplikat-Provenienz gehört
  zu Phase 2 (Membership / Dual-Line / Roche-Klasse).
- Resolution: Code hat heute nur **einen** undifferenzierten `unresolved`-Topf.
  Phase 1 trennt nur `DEGRADED_DICT` (sauber abgrenzbar, Regressions-Tripwire)
  vs. `UNRESOLVED`. `DELISTED` vs. `UNCLEAR` = eigenes Ticket (bräuchte
  zusätzlichen `get_historical`-Probe-Call) → bewusst nicht hier.
  **Tripwire-Baseline (kalibriert am Gate-A-Cold-Run 2026-06-06):** `DEGRADED_DICT`
  ist **nicht** ~0 — die 5 bekannten UNCLEAR (AMS.VI, RIGN.SW, ROL.L, SANO.HE,
  SCHA.OL) scheitern technisch genau über den Degraded-Dict-Pfad und sind die
  erwartete Baseline. Der Tripwire ist **mengen-basiert, nicht zähl-basiert**:
  Alarm bei einem **neuen oder veränderten** Eintrag gegenüber dieser Baseline,
  nicht bei `count > 0`. (Punkt 0a/0b dieses Folge-Tickets können die Baseline
  verkleinern, sobald Symbolfehler bereinigt sind.)
- Scoring: Gemini-Ausfall (`SCORE_NOT_SCORED`) ist strukturell vom niedrigen
  Score (`SCORE_BELOW_THRESHOLD`) getrennt — ein Ausfall darf nicht als
  „niedrige Qualität" maskieren.

---

## 2. Funnel-Stufen (`funnel_summary.json`)

`Universum → Resolution → Basis-Gates → EDGAR-Gates → Scoring → Crosshits`,
je `rein / raus / übrig`.

**Pass-Through, kein Austritt:** `edgar_skipped`-Records (`no_cik` /
`data_source_error`, `filter_passed_edgar=None`) passieren EDGAR und laufen
weiter. Sie werden als Pass-Through-Annotation gezählt, **nicht** als Drop.

`build_funnel` arbeitet mit `scored=None` (Dry-Run): Scoring/Crosshit-Stufen
werden dann als `"not_run"` markiert statt mit Null-Counts gefälscht.

---

## 3. Modul `app/screener/funnel.py` (neu)

Reiner Datensammler. Enthält:

- `ReasonCode(str, Enum)` — die Whitelist aus §1.
- `SeverityBucket(str, Enum)` — `BENIGN | REVIEW`.
- `Dropout` (dataclass, frozen): `ticker`, `stage`, `reason_code`,
  `severity_bucket`, Tripwire-Flags (`is_large_cap`, `sector_wide`),
  `market_cap_eur`, `gics_sector`.
- `FunnelSummary` (dataclass): Stufen-Counts + STOXX-Provenienz + `to_dict()`.
- `build_funnel(...)` — leitet alles deterministisch aus den bereits
  vorhandenen Records/Reports ab.
- Severity-Tabelle als Modul-Konstante (§4).

### Plumbing (additiv, kein Verhaltenswechsel)

Heute verwirft `run_screener` die ausgeschiedenen Records. Minimal-invasiv:

1. `BasisFilterResult` um `resolved: list[ScreenerRecord]` erweitern (alle
   aufgelösten Records, passed **und** failed). `passed` bleibt unverändert.
   Basis-Gate-Drops = `resolved \ passed`, jeder trägt `filter_failed_reason`.
2. EDGAR-Gate-Drops liest `build_funnel` aus der Basis-passed-Liste
   (`r.filter_passed_edgar is False`). Keine Signatur-Änderung nötig.
3. `run_screener` benennt Variablen so um, dass die Zwischenlisten erhalten
   bleiben (`basis_passed`, `edgar_passed`, `scored`) statt sie zu überschreiben.

**Keine Filter-Bedingung wird angefasst.**

### Resolution-Split typisiert (kein String-Matching)

- Neue `DegradedDataError(DataSourceError)` in `app/errors.py`.
- `yfinance_client.get_ticker_info` wirft sie im Degraded-Fall statt
  generischem `DataSourceError`. Subklasse → alle bestehenden
  `except DataSourceError` fangen weiterhin (kein Verhaltenswechsel).
- Catch-Site in `run_basis_filter` trennt per `isinstance`:
  `DegradedDataError → DEGRADED_DICT`, sonst `UNRESOLVED`. Reihenfolge:
  spezifische Exception zuerst fangen.
- Entspricht „Fehler strukturell unterscheidbar machen".

> ⚠️ **Verifikationspunkt Cold-Run:** `CachedYFinanceClient` darf den
> typisierten Fehler nicht zu generischem `DataSourceError` verflachen
> (warm-cache-Bypass-Lehre). Im Cold-Run prüfen, dass `DEGRADED_DICT`
> tatsächlich durchschlägt.

---

## 4. Tripwires + Severity (feste Tabelle, kein Urteil)

Deterministisch aus Daten, die ohnehin durch die Pipeline laufen
(`market_cap_eur`, `gics_sector`, `revenue_growth_yoy`, Resolution-Status).

### Modul-Konstanten (tunbar)

```python
LARGE_CAP_VOLUME_EUR = 3_000_000_000     # GATE_VOLUME-Schwelle
LARGE_CAP_GROWTH_EUR = 10_000_000_000    # GATE_REVENUE_GROWTH-Schwelle
SECTOR_WIDE_FRACTION = 0.5               # Anteil Sektor-Drops für sector_wide
SECTOR_WIDE_MIN_SIZE = 5                 # Mindest-Sektorgröße
SECTORS_WITHOUT_GROSS_MARGIN = {"Financial Services", "Real Estate"}
```

**Large-Cap-Schwelle ist nach Gate entkoppelt** (Verfeinerung A): Volumenausfall
bei großem Titel ist fast immer ein Datenbug (vgl. US-Liquiditäts-Bug) → niedrige
Schwelle, sensibler. Großes reifes Unternehmen kann real schrumpfen → Growth-
Schwelle höher. `is_large_cap` bleibt als Flag im Dropout; die **geprüfte**
Schwelle hängt am `reason_code`.

**None-Guard (Pflicht):** `market_cap_eur` kann `None` sein (FX-Fehlschlag, oder
Resolution-Drop ohne Marktkap). `is_large_cap` und alle Schwellen-Vergleiche
behandeln `None` als „nicht large-cap" → BENIGN, niemals `None >= int`
(TypeError). Gilt für alle `market_cap_eur`-Vergleiche in `funnel.py`.

**`SECTORS_WITHOUT_GROSS_MARGIN` verifiziert** gegen echte Output-Daten
(`output/Universum/2026-05-Crosshits.md`): yfinance liefert `"Financial Services"`
(nicht „Financials") und `"Real Estate"`. Banken/Versicherer/REITs haben keine
sinnvolle Bruttomarge → ohne Ausschluss feuert REVIEW jeden Lauf deterministisch
= Rauschen.

### Severity-Tabelle (`reason_code` × Tripwire → Bucket)

| reason_code | Tripwire-Bedingung | → Bucket |
|---|---|---|
| `GATE_VOLUME` | `market_cap_eur >= LARGE_CAP_VOLUME_EUR` | REVIEW, sonst BENIGN |
| `GATE_REVENUE_GROWTH` | `market_cap_eur >= LARGE_CAP_GROWTH_EUR` | REVIEW, sonst BENIGN |
| `GATE_GROSS_MARGIN` | `sector_wide` (s.u.) | REVIEW, sonst BENIGN |
| `GATE_MARKET_CAP` | — | BENIGN (zu klein = erwartet) |
| `GATE_GOING_CONCERN` / `GATE_ENFORCEMENT` / `GATE_RESTATEMENT` | — | BENIGN (gewollte Ausschlüsse) |
| `RESOLUTION_DEGRADED_DICT` | immer | REVIEW (Regressions-Tripwire; Baseline = 5 bekannte UNCLEAR, Alarm bei neuem/verändertem Eintrag — NICHT „count muss ~0") |
| `RESOLUTION_UNRESOLVED` | — | BENIGN (Phase 2: REVIEW bei Major-Index-Mitglied) |
| `SCORE_BELOW_THRESHOLD` | — | BENIGN |
| `SCORE_NOT_SCORED` | immer | REVIEW (Scoring-Ausfall ≠ Qualitätsurteil) |

### `sector_wide`-Logik (Verfeinerung B, sektor-bewusst)

**Vorbedingung (verifiziert):** Basis-Gates short-circuiten — `_get_fail_reason`
(`filters.py:41-50`) gibt beim ersten Fehler zurück, genau **ein**
`filter_failed_reason` pro Record, Reihenfolge volume→market_cap→gross_margin
→revenue_growth. Hielte das nicht (mehrere Gründe pro Record), wäre die
Nenner-Herleitung falsch → STOP/BLOCKED. Hält.

**Nenner-Korrektur:** Der Nenner ist **nicht** „alle aufgelösten Records im
Sektor". Ein Titel, der schon an volume/market_cap scheitert, erreicht den
gross_margin-Gate nie und kann nie als `GATE_GROSS_MARGIN`-Drop auftauchen —
steckte er im Nenner, wäre der Anteil systematisch zu niedrig und `sector_wide`
feuerte zu selten. Korrekter Nenner = Records im Sektor, die den Margin-Gate
**erreicht** haben:

```
reached_margin(sektor) =
    basis_passed-Records im Sektor
  + Drops im Sektor mit reason_code ∈ {GATE_GROSS_MARGIN, GATE_REVENUE_GROWTH}
```

(revenue_growth liegt **nach** gross_margin → ein revenue_growth-Drop hat den
Margin-Gate passiert. volume-/market_cap-Drops haben ihn nicht erreicht und
fallen aus dem Nenner.)

Für `GATE_GROSS_MARGIN`:
```python
if gics_sector in SECTORS_WITHOUT_GROSS_MARGIN:
    sector_wide = False                      # BENIGN, kein Rauschen
else:
    n = count(reached_margin im Sektor)
    m = count(GATE_GROSS_MARGIN-Drops im Sektor)
    sector_wide = (n >= SECTOR_WIDE_MIN_SIZE) and (n > 0) \
                  and (m / n >= SECTOR_WIDE_FRACTION)
```

Division-Guard: `n == 0` → `sector_wide = False` (kein ZeroDivision).

**Gewollter Nebeneffekt:** `SECTOR_WIDE_MIN_SIZE = 5` greift jetzt auf den
reached-Gate-Nenner, nicht auf alle aufgelösten Records → der Floor schützt
Sektoren, in denen fast alles schon vor dem Margin-Gate rausfiel, vor
Rausch-REVIEW. MIN_SIZE ist damit wieder wirksam, nicht inert. Alles aus der
vorhandenen `resolved`-Liste ableitbar; kein Gate angefasst, betroffen ist nur
`severity_bucket`.

> **STOP/BLOCKED — nicht in dieser Phase:** Die `GATE_GROSS_MARGIN` selbst läuft
> weiterhin **unverändert auf alle Sektoren**. Ob sie für Financials/Real Estate
> überhaupt greifen sollte, ist eine Filter-Logik-Frage → separate Entscheidung.
> B) unterdrückt nur Tripwire-Rauschen, ändert **kein** Drop-Ergebnis und keinen
> Stufen-Count.

**`Review-Flags: N`** = Anzahl Dropouts mit `severity_bucket == REVIEW`.

---

## 5. Output-Artefakte

Konvention `output/Universum/`, Monats-Präfix wie die übrigen Outputs:

- `output/Universum/YYYY-MM-funnel_summary.json`
- `output/Universum/YYYY-MM-dropouts.csv`
  Spalten: `ticker, stage, reason_code, severity_bucket, is_large_cap,
  sector_wide, market_cap_eur, gics_sector`.

Geschrieben in `run_screener` (vollständig) und in `run_filter_preview`
(Stufen bis inkl. EDGAR, $0).

---

## 6. Report-Header (`app/output/report_header.py`, neu)

Rendert aus `funnel_summary.json`. **Heimat: Crosshits-Datei** (die „Titelseite"
des Laufs), eingehängt nach der H1 in `crosshits_generator._build_body`. Nicht in
allen drei Outputs dupliziert.

Inhalt:
- Stichtag · Universum-Größe + Quellen (S&P 500 / S&P 400 / STOXX 600) ·
  **tatsächlich genutzte STOXX-Quellstufe**
- Datenbasis: yfinance (Kurs/Vol/Fundamentals) · SEC EDGAR (Filings;
  DEF-14A/Form-4 nur US-Filer)
- Funnel-Tabelle (Stufe | rein | raus | Grund | übrig)
- **Review-Flags: N** (Aufschlüsselung im Anhang)
- Schwelle in Klartext: „Jede Aktie wird auf mehreren Fisher-Dimensionen 0–5
  bewertet. Crosshit = ≥2 Dimensionen ≥4.0 — kein Einzelausreißer, sondern über
  mehrere unabhängige Achsen bestätigte Qualität."

---

## 7. STOXX-Provenienz (Phase-1-Anteil)

`build_universe.py` schreibt beim Lauf ein Sidecar
`data/universe_provenance.json`:

```json
{ "stoxx_tier": "wikipedia|ishares-b|ishares-c|hardcoded-fallback",
  "sp500_count": 0, "sp400_count": 0, "stoxx600_count": 0 }
```

- `fetch_stoxx600()` gibt zusätzlich die gegriffene Quellstufe zurück (Tuple
  statt nur `list`), `main()` schreibt das Sidecar neben `universe.json`.
- Report liest das Sidecar **falls vorhanden**, sonst graceful „nicht erfasst".
- Phase 1: nur Emitter-Code + Unit-Test. Der **Live-`build_universe`-Lauf**
  (Netz: Wikipedia/iShares) ist das **Phase-2-Gate**.
- Voll-Membership `universe_membership.json` (Ticker → `[sp500|sp400|stoxx600]`)
  = Phase 2.

---

## 8. Cold-Run-Validierung — gestaffelt, $0 zuerst

1. **$0-Cold-Dry-Run** (`POST /run/monthly?dry_run=true`): nach Cache-Purge
   (`universe_cache` + `dev_edgar_cache`). `run_filter_preview` emittiert
   `funnel_summary.json` + `dropouts.csv` für die Stufen bis inkl. EDGAR — dort
   sitzen die Gate-Review-Flags (Roche-Klasse). Stephan bekommt
   `funnel_summary.json` + die Review-Flag-Liste **bevor** Phase 2.
2. **Paid-Acceptance-Run** (separates Gate): ergänzt Scoring/Crosshit-Stufen.

---

## 9. Testing & Arbeitsweise

TDD, alle Unit-Tests offline (Fixtures/DI-Mocks, kein Netz):
- `build_funnel`: Stufen-Counts, `reason_code`-Mapping, Pass-Through-Zählung.
- Severity-Tabelle: Entkopplung — Titel mit `market_cap` zwischen 3 und 10 Mrd
  → REVIEW bei `GATE_VOLUME`, BENIGN bei `GATE_REVENUE_GROWTH` (Grenzfall
  beweist die Trennung).
- Sektor-Ausschluss: Financials-Fixture mit >50 % Margin-Drops → alle BENIGN,
  kein `sector_wide`-Flag. Identischer Aufbau in z. B. Industrials → REVIEW.
- Gegenprobe: Stufen-Counts in `funnel_summary` **identisch mit/ohne B)**;
  B) berührt ausschließlich `severity_bucket`.
- `DegradedDataError`-Trennung: degraded → `DEGRADED_DICT`, sonst `UNRESOLVED`.
- Header-Render, CSV-Format, `build_universe`-Provenienz-Sidecar.

### Erhaltungssatz-Test (Reconciliation-Invariante) — wichtigster Test

Garantiert „**kein Record zählt still als nichts**" — die Bug-Klasse, die
`GATE_MARKET_CAP`/`GATE_RESTATEMENT` überhaupt erst nötig machte.

Synthetisches Universum-Fixture mit bekanntem Endzustand jedes Tickers.
Invariante über den `build_funnel`-Output, **stufen-bewusst** (reconciliert nur
bis zur letzten tatsächlich gelaufenen Stufe; im Dry-Run `scored=None` →
Scoring/Crosshit ausgeklammert):

```
|Universum| == Σ(Drops über alle gelaufenen Stufen)
             + |am Ende noch passierende Records|
               (Crosshits; im Dry-Run die am EDGAR-Ende Übrigen)
```

Zusätzliche Assertions:
- Jeder `Dropout.ticker` ist Mitglied des Ausgangs-Universums.
- Jeder Ticker hat **höchstens einen** Dropout (keine Doppelzählung).
- `Menge(gedroppte) ∩ Menge(passierende) == ∅` (disjunkt).
- Pass-Through-Records (`edgar_skipped`: `no_cik`/`data_source_error`) sind
  **nicht** in der Drop-Menge und tauchen in der nachgelagerten „übrig"-Zahl auf.

Empfehlung: parametrisierter/Property-Test, der bei jedem künftig **fehlenden**
`reason_code`-Emitter automatisch bricht (Universum-Summe geht dann nicht mehr
auf).

Produktiv-Code an `backend-developer` / `qa-engineer`-Subagents delegiert;
Claude Code orchestriert. Subagent-Commit-Hygiene: nach jedem Subagent
`git log`/`status` prüfen.

---

## 10. Phasen-Schnitt

- **Phase 1** (dieser Spec): Funnel-Emitter + Severity + Report-Header +
  STOXX-Provenienz-Emitter (offline), validiert per $0-Cold-Dry-Run, dann
  Paid-Acceptance-Run.
- **Phase 2** (eigener Spec, später): `universe_membership.json`,
  Membership-Join zur Severity-Gewichtung (Major-Index-Mitglied an Hard-Gate →
  starkes Fehl-Ausschluss-Flag), optional Funnel-Breakdown nach Region (US/EU).
  Braucht Live-`build_universe`-Lauf als separates Gate.
