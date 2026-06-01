# Phase 1.4 — Insider-Transactions (Form-4): Brainstorm

> **Status:** Brainstorm abgeschlossen, Weichen entschieden. **KEIN Spec, KEIN Plan, KEIN Code** in dieser Session.
> Nächster Schritt: separate Spec-Session. Master-Plan: `docs/superpowers/plans/2026-05-27-phase-1-pareto-b2.md`.
> Datum: 2026-06-01.

## Ziel

Tool B (Deep Dive) zieht zusätzlich zum 10-K die **Form-4-Insider-Filings** desselben Filers über EDGAR. Synthesis-Prompt bekommt einen neuen Block „Insider-Transactions (letzte 12 Monate)"; das P11/P15-Reasoning (Management-Integrität, Aktionärs-Alignment) bezieht code-gerechnete Insider-Signale ein. **US-spezifisch:** Foreign Private Issuers (NOVO, ASML) sind Section-16-exempt → filen kein Form-4.

---

## Start-Check (gegen echten Code, nicht Plan-Doc)

- **`app/services/edgar_client.py`** — `EdgarClientImpl` nutzt `data.sec.gov/submissions/CIK<padded>.json` mit index-alignten `recent`-Arrays (`form[]`, `accessionNumber[]`, `primaryDocument[]`, `filingDate[]`). `get_cik` via `www.sec.gov/files/company_tickers.json` (lazy, instanz-gecached). Rate-Limit 0,5 s. `_get` (JSON) / `_get_text` (Roh-Text). `has_active_enforcement` ist Stub (→ False).
- **`app/deepdive/pipeline.py`** — `run_deep_dive` ist linear, Stages [1]–[6]: ADR-Lookup → EDGAR-Pull → Filing-Parse → Quant-Join → Gemini-Synthesis → Markdown. `peer_comparison` wird an `quant` angehängt, „so it flows into both the synthesis prompt and the DeepDiveRecord".
- **`app/deepdive/filing_cache.py`** — `CachedFilingFetcher`: lokaler FS-Cache `cache/filings/<cik>/<accession>.txt` + per-cik `_meta.json` `{form_type: {_cached_at, accession, filing_date}}`, TTL 30 d, atomic Write, fail-soft bei korruptem Meta (WARNING, kein Crash).
- **`app/services/cached_edgar_client.py`** — Firestore-Cache der Bool-Signale (restatement/going-concern), CIK-gekeyt, TTL 7 d.
- **`app/deepdive/compose.py`** — DI-Builder (`build_filing_fetcher`, `build_quant_builder`, …); hier dockt ein `build_insider_fetcher()` an.

**Konsequenz:** Form-4-Listing kommt **gratis** aus der `submissions.json`, die fürs 10-K ohnehin geladen wird — nur `form == "4"` filtern. Kein neuer Listing-Endpunkt.

---

## Freier Probe-Pull (echtes Form-4-XML, kein Gemini)

Feld-Realität byte-geprüft an **MSFT** (CIK 789019). Zwei Befunde, die aus keinem Plan-Doc zu raten gewesen wären:

1. **`xslF…/`-HTML-vs-Raw-XML-Falle.** `primaryDocument` = `xslF345X06/form4.xml` ist die **XSL-gerenderte HTML**-Variante (~16 KB). Das rohe, sauber parsebare XML liegt im selben Accession-Ordner **ohne** den `xslF…/`-Prefix (`form4.xml`, ~5 KB). → **Parser zielt auf das prefix-gestrippte Raw-XML** (`primaryDocument.split("/")[-1]`).

2. **Volumen.** MSFT = **122 Form-4 in 12 Monaten** (729 im ganzen `recent`-Fenster, 2019–2026). Jedes ist ein eigener XML-Fetch @ 0,5 s ≈ **60–70 s pro Erst-Lauf**. Gratis ($), aber spürbar — und die jüngsten sind überwiegend Routine (`S`/`F`/`A`). Das ist eine echte neue Weiche (→ Weiche 0), kein Planwort.

**XML-Schema** (`<ownershipDocument>`, schemaVersion X0609):
- `issuer` (`issuerCik`, `issuerName`, `issuerTradingSymbol`)
- `reportingOwner` → `reportingOwnerId` (`rptOwnerName`), `reportingOwnerRelationship` (`isDirector`/`isOfficer`/`isTenPercentOwner`/`isOther` als 0/1, `officerTitle` = **Freitext**, z. B. „EVP, Chief Human Resources Off")
- `aff10b5One` (**10b5-1-Indikator, strukturell in jedem Filing präsent** — Semantik 0/1/`noAff10b5One` noch zu pinnen)
- `nonDerivativeTable` → N × `nonDerivativeTransaction`: `securityTitle`, `transactionDate`, `transactionCoding.transactionCode` (**S/F/P/A/M/G…**), `transactionAmounts` (`transactionShares`, `transactionPricePerShare`, `transactionAcquiredDisposedCode` A/D), `postTransactionAmounts.sharesOwnedFollowingTransaction`, `ownershipNature.directOrIndirectOwnership` (D/I)
- `derivativeTable` (Optionen/RSUs — bei `A`-Grants vorhanden; per Konstruktion Comp)
- `footnotes`, `ownerSignature`

Beispiel: CHRO mit `S` (Verkauf 1.262 @ $411) + `F` (88 Steuer-Einbehalt), `aff10b5One=0` — comp-getriebene Routine, **kein** Conviction-Signal. Validiert das Drei-Eimer-Netting.

---

## Entschiedene Weichen

### Weiche 0 — Fetch-Volumen/Scope → **A: alle im 12M-Fenster, gecached**

Alle Form-4 im 12-Monats-Fenster ziehen, netten. (Cap-nach-Recency verworfen: biast systematisch gegen das Signal — der eine große `P`-Kauf des CEO kann irgendwo im Fenster liegen, die jüngsten sind Routine. „Seit letztem Annual" verworfen: koppelt zwei orthogonale Vintages und bricht die 12M-Semantik.) Erst-Lauf 60–70 s ist bei manuellem Tool B tolerabel — einzige Option ohne Korrektheits-Kosten am Kern.

**Vier Cache-/Label-Nachschärfungen:**
1. **Cache per `accessionNumber`, nicht per Fenster.** Form-4 sind nach Einreichung immutable → accession-gekeyt stabil; 12M ist ein **Read-Time-Filter**. Fenster-gekeyt würde täglich invalidieren (gleitendes Fenster). Re-Run einen Monat später zieht nur die ~8 neuen XMLs. Accession-Liste gratis aus `submissions.json`.
2. **Pre-Netting cachen** (geparste Transaktions-Liste), **nicht** die Netting-Summary. Signifikanz-/Netting-Schwelle (Weichen 1–2) wird nach dem Akzeptanz-Lauf vermutlich getunt → neu netten ohne 60–70 s erneut zu zahlen. Post-Netting-Cache würde jedes Schwellen-Tuning einen Voll-Refetch kosten.
3. **Honest-Label mit Nenner + Netting-Ergebnis:** „122 Form-4 / 12M → 3 signifikant (2 S, 1 P), Rest Routine genettet". Denominator-Transparenz wie bei Cite-Grounding — „kein Signal" muss als „122 durchgesehen, nichts Signifikantes" lesbar sein, nicht „5 angeschaut".
4. **Fail-soft pro Fetch** (TDD-Vormerk): ein kaputtes XML killt den Layer nicht → „N von M geparst", analog zum per-Peer-fail-soft in Stage 2c.

### Weiche 1 — Signal-Klassifikation & Netting → **Drei Eimer**

- **Discretionary BUY** = `P` (Open-Market-Kauf) → **ALLE zeigen, größenunabhängig** (Insider-Käufe sind selten = hohes Fisher-Signal).
- **Discretionary SELL** = `S` (Open-Market-Verkauf) → Schwellen-gefiltert (Weiche 2).
- **Routine/Comp** = `A` (Grant), `M` (Options-/RSU-Ausübung), `F` (Steuer-Einbehalt), `G` (Gift) → in einen **Routine-Zähler** genettet, **aus dem Signal-Net raus**, aber **im Nenner**. RSU-Vesting = kein Signal.

Net = Σ(`P`, acquired) − Σ(signifikante `S`, disposed); **Käufe und Verkäufe getrennt** ausweisen, nicht nur Netto. `M`-Ausübung selbst ist kein Signal — ein darauffolgender `S` (= eigener `S`-Eintrag) schon.

### Weiche 2 — Signifikanz-Schwelle (code-gerechnet)

Eine `S`-Transaktion ist signifikant bei:
- `|value| > $1M` (`value = shares × pricePerShare`), **ODER**
- Reporter ist **CEO/CFO** (Titel-String-Match, wert-unabhängig — nur 2 Personen, immer informativ, kein Flut-Risiko), **ODER**
- **Per-Owner-Aggregat > $1M im Fenster** (viele kleine Verkäufe einer Person, die sich summieren — wofür Netting da ist), **ODER**
- **%-Holdings-Reduktion** (neue Dimension, gratis aus XML, → siehe unten).

`P`-Käufe: immer signifikant (Rarität).

**Schärfung A — %-der-Holdings als Signifikanz-Dimension.** `sharesOwnedFollowingTransaction` + `transactionShares` geben die Stake-Reduktion gratis. Ein $2M-`S` ist als Signal völlig anders, wenn er 2 % vs. 40 % der Beteiligung abbaut — der **Anteil ist der eigentliche Fisher-Conviction-Tell**, nicht der absolute $-Betrag. Mindestens auf signifikanten Zeilen ausweisen („verkauft X, hält nun Y = −Z %"), evtl. als vierter Trigger. **Label-Caveat:** „der gemeldeten **direkten** Holdings" — direkt/indirekt-Split über mehrere Zeilen kann den Per-Zeilen-Prozentsatz verzerren, nicht überindexieren.

**Schärfung B — `isDirector=1 → signifikant unabhängig vom Wert` gestrichen.** Würde die Signifikant-Liste mit kleinen Routine-Director-Sells fluten und ist redundant mit Per-Owner-Aggregat. Ein $30k-Director-Sell ist kein Conviction-Signal. Directors laufen über $1M-Single + Aggregat + %-Reduktion; nur **CEO/CFO** bleibt wert-unabhängig — sonst verwässert man genau den P15-Anker, den der Layer schärfen soll.

### Weiche 3 — Datenmodell → **eigene Top-Level-Datenschicht**

- **`InsiderTransaction`** (frozen): `owner_name`, `role` (officer/director/10%+`title`), `date`, `code`, `shares`, `price`, `value`, `acquired_disposed` (A/D), `security_title`, `is_derivative`, `shares_after`, (Feld-Vormerk: `is_10b5_1`).
- **`InsiderSummary`**: `window_label`, `n_filings_total` (Nenner), `n_parsed` (fail-soft), signifikante `buys`/`sells` (Listen), `routine_count`, `net_buy_value`/`net_sell_value`, `by_role`.
- **Anhängen:** `insider_summary: InsiderSummary | None` als **eigenes Top-Level-Feld am `DeepDiveRecord`** + **expliziter Parameter an `run_synthesis`** — **NICHT** auf `quant_snapshot` huckepack wie `peer_comparison`. Insider ist EDGAR-/Filing-abgeleitet, kein Quant; das „eigenes Mini-Subsystem"-Prinzip will eine ehrliche eigene Datenschicht statt sie in Quant zu schmuggeln. (Kostet eine Zeile mehr Wiring, gewinnt klare Grenze — räumt den `peer_comparison`-Geruch weg.)

### Weiche 4 — Render + Honest-Label + FPI-Erkennung

- **US 10-K, Form-4 gefunden:** Summary-Block mit Nenner-Zeile + signifikante Transaktions-Zeilen (inkl. %-Reduktion).
- **US, null Form-4 im Fenster:** „Keine Insider-Transaktionen (Form-4) in den letzten 12 Monaten" — legitim leer (→ aber vom Fetch-Fehler unterscheidbar, siehe offene Details).
- **FPI / 20-F (NOVO, ASML):** „Insider-Transaktionen: nicht anwendbar (Foreign Private Issuer, Section-16-exempt — kein Form-4)". **Erkennung keyt auf `resolved.form_type`** — `20-F` → FPI-Pfad, Fetch komplett übersprungen; `10-K` → Versuch. Gratis, schon aufgelöst, kein Rate-Limit verbrannt.
- **Prompt-Disziplin** (`prompt-objective-trigger-not-subjective-judgment`): Signifikanz ist **code-gerechnet**; das Modell bekommt **vor-klassifizierte** signifikante Transaktionen + Nenner → P11/P15-Regel feuert deterministisch, nicht hinter Modell-Urteil (2a.3b-Lehre).

---

## Offene Details (in Spec festzurren — nicht verdunsten lassen)

1. **Unbekannter `transactionCode` → expliziter Default-Eimer.** `{P,S,A,M,F,G}` deckt nicht alles ab (`C`, `X`, `D`, `I`, `J`, `W`, `V`…). Rest in „other/routine, zählt im Nenner, **WARNING**" fangen — sonst verschwindet ein Code still aus dem Nenner (bricht die 122-Ehrlichkeit) oder mis-signalisiert. Warning = Katalog-Wachstums-Signal (1.2-Lehre).
2. **Titel-Match-False-Negatives.** „Principal Executive Officer" / „Principal Financial Officer" sind SEC-Standard-Titel = faktisch CEO/CFO; „President" oft auch. Muster über reine „CEO/CFO" hinaus erweitern, als **best-effort** labeln; `$1M` + Aggregat als struktureller Backstop.
3. **P/S-Conviction-Signal nur auf `nonDerivativeTable`.** Netting-Regel zieht **ausschließlich** `nonDerivativeTable` — Derivate (Optionen/RSUs) sind per Konstruktion Comp, egal welcher Code. `is_derivative` ist im Modell, aber die Regel muss es explizit sagen.
4. **Null-Form-4 ≠ Fetch-Fehler.** Für einen US-Large-Cap sind 0 Form-4/12M eher ein CIK-/Fetch-Problem als echte Abwesenheit. „EDGAR lieferte 0" vom „Fetch fehlgeschlagen" **unterscheidbar** machen — sonst liest sich ein stiller Fehler wie „sauber, kein Insider-Signal" (die „0-Downgrade-war-ein-Bypass"-Lehre aus dem Cite-Layer).

## Künftige Signal-Qualitäts-Felder (vormerken, nicht jetzt festzurren)

Der **Pre-Netting-Cache (Weiche 0.2)** erlaubt genau dieses Nachjustieren nach dem Akzeptanz-Lauf **ohne Refetch**:
- **10b5-1-Indikator** (`aff10b5One`, strukturell präsent → gratis): „geplant (10b5-1) vs. diskretionär" ist der stärkste gratis Signal-Qualitäts-Diskriminator — ein geplanter CEO-Verkauf ist Rauschen, ein ungeplanter ist Signal. **Semantik (0/1/`noAff10b5One`) im Parser-Schritt byte-pinnen.**
- **Exercise-and-sell-Erkennung:** ein `S`, der ein same-day-`M` monetarisiert, ist schwächeres Signal als ein Standalone-Open-Market-`S`.

---

## Architektur-Vorausschau (Kontext, nicht zementiert)

Eigenes Mini-Subsystem, greift **NICHT** in den HTML-Filing-Parser ein:
- `insider_client.get_form4_accessions(cik, since)` — filtert die ohnehin geladene `submissions.json` (`form=="4"`, `filingDate >= since`).
- `insider_xml_parser` — Raw-XML (prefix-gestrippt), `<ownershipDocument>` → `list[InsiderTransaction]`.
- `insider_summary` — Drei-Eimer-Netting + Signifikanz + Aggregation → `InsiderSummary`.
- Accession-Cache (filing_cache-Pattern, **pre-Netting**, eigene `CACHE_SCHEMA_VERSION`).
- `compose.build_insider_fetcher()` + neue Pipeline-Stage `[2b]` + Synthesis-Block + Dossier-Render.

---

## Disziplin / Nicht-Ziele dieser Session

- Kein 1.5-Vorgriff (DEF-14A-Proxy).
- Kein Spec, kein Plan, kein Code, kein PROJEKTSTAND-Edit — Spec ist die **nächste, separate** Session.
- Kanonische Aufrufform: `uv run python -m <modul>` (SOPRA-EPDR).
- Working-Tree-Drift bleibt bewusst uncommitted bis B.2 — nicht anfassen.
