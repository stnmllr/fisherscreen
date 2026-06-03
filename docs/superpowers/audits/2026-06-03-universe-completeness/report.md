# Unabhängiges Vollständigkeits-Audit — Tool-A-Universum (Cold-Run 2026-06-03)

> **Zweck:** unabhängige Falsifikation der Cold-Run-Self-Report-Zahlen — reproduzierbare
> Artefakte, von Stephan spot-checkbar, NICHT cc's Schlussfolgerung.
> **Grundannahme:** die Bug-Klasse war STILLE Attrition; Survivorship-Bias ist der Feind.
> **Methode:** Ground-truth-first aus `data/universe.json` + Roh-Cloud-Run-Logs + eigenes
> Re-Resolutionsskript; jeder Drop mit benanntem Grund, jede Divergenz adversarial bestätigt.

## Artefakte in diesem Ordner (alles roh & reproduzierbar)
| Datei | Inhalt |
|---|---|
| `coldrun_raw.log` | Roh-Cloud-Run-Logs (gcloud), enthält Run 1 (13:xx) + Run 2 (16:xx) |
| `re_resolution.py` / `re_resolution.json` | unabhängige yfinance-Auflösung aller 1349 (NICHT Pipeline-Pfad) |
| `confirm35.py` / `confirm35.json` | 1×-Bestätigungs-Reprobe der 35 Failures + Alias-Tests |
| `funnel.py` / `funnel_drops.csv` / `funnel_summary.json` | Funnel-Rekonstruktion + 659-Zeilen-Drop-CSV |
| `post_funnel.py` / `restatement_hits.json` / `healthy_largecap_drops.csv` | 8 Restatement-IDs + Large-Cap-Scan |
| `classify35.py` / `unresolved35_classified.csv` | finale Klassifikation der 35 unresolved |
| `run2_no_cik.txt` | die 140 EDGAR-no_cik-Namen (Beweis-Liste) |

**Zwei Läufe heute** — nur **Run 2** ist der auditierte Cold-Run:
- **Run 1** (13:10–13:12): PRE EU-Korrektur (1389) UND PRE Polaritäts-Fix → 5 GC-Drops.
- **Run 2** (16:16–16:44): POST EU-Korrektur (1349) UND POST Polaritäts-Fix → 0 GC-Drops.
- Fix-Deploy-Grenze nachweislich zwischen 13:12 und 16:16 (aus den Logs).

---

## TL;DR — Verdikt je Claim

| Cold-Run-Claim | Verdikt | Belegtyp |
|---|---|---|
| N_universe = 1349 | ✅ **wahr** | universe.json + Commit `eb37dd7` |
| yfinance_unresolved = 0 | ⚠️ **technisch wahr, irreführend** | 35 Ticker lösen unabhängig NICHT auf (0 davon transient) |
| basis_filter = 690/1349 (EU 140) | ✅ **wahr, unabhängig exakt rekonstruiert** | funnel.py → 690 (US 550 / EU 140) |
| EU basis-passed 126 → 140 | ✅ **wahr** | Run-1- vs Run-2-Logs |
| data_source_error 11 → 1 (COLM) | ✅ Residuum=1 bestätigt; „11"-Baseline außerhalb Fenster | Logs + EDGAR |
| enforcement-spam 538 → 0 | ✅ **wahr** (Log entfernt, 0 Drops strukturell) | Quelle `d69f119` |
| going_concern_drops = [] | ✅ **wahr** (Run 2 = 0; Run 1 droppte exakt die 5 FPs) | Rohlogs |

**Kernbefund:** „unresolved=0" ist die einzige Zahl, die in die Irre führt. Sie verbirgt
**35 Universe-Ticker, die nicht sauber auflösen** — darunter **13 reale, gesunde Firmen, die
still aus dem Screen ausgeschlossen sind** (falsches Ticker), und **12 echte Delistings**.
Alle anderen Claims halten der unabhängigen Rekonstruktion stand.

---

## AUDIT 1 — Funnel-Rekonziliation (Run 2)

Stufen an die **tatsächlich geloggten** Zeilen ausgerichtet:

| Stufe | rein | raus | Drops | Beleg (Log) |
|---|---:|---:|---:|---|
| universe input | — | 1349 | — | `runner: universe input … total=1349` |
| yfinance-Resolution | 1349 | 1349 | **0** (self-report) | `runner: fetched … 1349/1349` |
| basis_filter | 1349 | 690 | **659** | `basis_filter: 690/1349 (US 550/905, EU 140/444)` |
| edgar_filter | 690 | 682 | **8** (Restatement) | `edgar_filter: 682/690` |
| ├ no_cik (Pass-Through) | | | 140 | = **exakt die 140 EU-Basis-Passer** (alle dotted) |
| ├ data_source_error (PT) | | | 1 | `['COLM']` (transienter EFTS-500) |
| ├ going_concern | | | **0** | `filter_preview: 0 gc-drops` |
| └ enforcement | | | **0** | No-op `return False` (Quelle) |
| **final (pre-Gemini)** | | **682** | | |

**Arithmetischer Abschluss — kein unerklärter Gap:**
```
1349 = 682 (final) + 659 (basis) + 8 (restatement) + 0 (unresolved) + 0 (GC) + 0 (enforcement) ✓
```
**Unabhängige Rekonstruktion** (`funnel.py`, eigener Pfad) trifft die Pipeline **bitgenau**:
basis_passed = **690 (US 550 / EU 140)** — identisch zu drei geloggten Zahlen. Drop-Itemisierung
in `funnel_drops.csv` (659 Zeilen). Drop-Gründe: gross_margin 396, revenue_growth 140,
avg_volume 51, market_cap 37, unresolved 35.

---

## AUDIT 2 — Unabhängige Re-Resolution (das Rückgrat des Befunds)

`re_resolution.py` löst jedes der 1349 Symbole frisch gegen `yf.Ticker(t).info` auf (eigener
Codepfad). **Methodik-Härtung:** ein naiver Erst-Sweep traf eine harte yfinance-Throttle-Klippe
bei ~764 Requests; Gegenmaßnahme = Pacing ~1.2 s/Req + Chunk-Cooldowns + Trip-Erkennung +
Mehrfach-Pässe. **Cache-Masking widerlegt:** `universe_cache` existiert in `app/` nicht;
`get_ticker_info` trifft live yfinance → „fetched 1349/1349" ist eine **echte** Live-Messung,
das lokale Throttling ein IP-Artefakt (Cloud-Run-IP frisch).

### Ergebnis: 35 unresolved vs. Pipeline-0 — und **0 davon transient**
`re_resolution.json`: resolved **1314/1349**, 35 unresolved. Jede der 35 wurde mit sauberer
Einzelprobe (gesunde IP) + Alias-Test **1× bestätigt** (`confirm35.py`):
**0 lösten bei Reprobe auf → die Divergenz ist zu 100 % real, kein Flakiness-Artefakt.**

### Maskierungs-Mechanismus (quell-belegt)
Run 2 loggt 0 „data fetch failed", aber **4 yfinance-404-ERROR** (SANO.HE, LIN.L, INP.L, EFGI.PA).
Bei 404 gibt `.info` ein **nicht-leeres, degradiertes** Dict zurück → `get_ticker_info` raised
nicht (Quell-Kommentar: „does not catch partial-data dicts") → Titel zählt als „resolved",
fällt dann am basis_filter als „missing field". Die übrigen 31 der 35 sind genau dieselbe
Klasse (degradierte Dicts, keys 6–33, ohne name/marketCap), die die Pipeline still als basis-
Miss verbucht. **Survivorship-maskierte Attrition.**

### Klassifikation der 35 (`unresolved35_classified.csv`)
| Klasse | Anzahl | Bedeutung |
|---|---:|---|
| **WRONG_TICKER → still ausgeschlossen** | **13** | reale gesunde Firma, korrektes Ticker fehlt im Universum |
| WRONG_TICKER → benigne Dublette | 5 | korrektes Ticker ist ohnehin im Universum |
| **DELISTED (prune)** | 12 | M&A / Take-Private / Verstaatlichung |
| UNCLEAR (investigate) | 5 | keine Live-Alias-Bestätigung |

**13 still ausgeschlossene reale Firmen** (← der materielle Vollständigkeits-Defekt):
Ericsson (`ERIC-B.ST`), Atlas Copco (`ATCO-A.ST`), H&M (`HM-B.ST`), ASM International (`ASM.AS`),
DSM-Firmenich (`DSFIR.AS`), Flutter (`FLTR.L`), ICG (`ICG.L`), Teva (`TEVA`), Indivior (`INDV`),
Barratt Redrow (`BTRW.L`), Aker BP (`AKRBP.OL`), EFG Intl (`EFGN.SW`, Financial), Investec
(`INVP.L`, Financial). Ursachen: Kleinbuchstaben-Share-Class (`ERICb.ST`→`ERIC-B.ST`), Rename
(`ASMI.AS`→`ASM.AS`), Exchange-Wechsel (`FLTR.IR`→`FLTR.L`), Merger-Rename (`BDEV.L`→`BTRW.L`).

Diese fallen **nicht** an Fisher-Kriterien, sondern am falschen Ticker — mit korrektem Ticker
(volle Daten) hätten mehrere die Basis bestanden.

---

## AUDIT 3 — Must-Have-Watchlist: finale Disposition

Identität: in finaler Basis ⇔ in no_cik-Liste (EU-Pass-Through) ODER US-Basis-Passer.
Bestätigt: die 140 no_cik sind **exakt** die 140 EU-Basis-Passer.

### Anker & Korrekturen (unabhängig gerechnet)
| Name | Ticker | Disposition | Grund |
|---|---|---|---|
| SAP | `SAP.DE` | ✅ **in Basis** | no_cik (EU-PT) |
| Novo Nordisk | `NOVO-B.CO` | ✅ **in Basis** | no_cik |
| Ferrari | `RACE.MI` | ✅ **in Basis** | no_cik; PASS bestätigt |
| Roche | `RO.SW` | ❌ gedroppt | avg_volume 36k<100k (illiquide Inhaber-Linie; ROG.SW 404) |
| Swiss Re | `SREN.SW` | ❌ gedroppt | gross_margin 0.20<0.30 (Financial) |
| Engie | `ENGI.PA` | ❌ gedroppt | revenue_growth −6.6% (legitim) |
| Pandora | `PNDORA.CO` | ❌ gedroppt | revenue_growth −3.2% (legitim, grenzwertig) |
| BT Group | `BT-A.L` | ❌ gedroppt | revenue_growth −3.9% (legitim) |
| ArcelorMittal | `MT.AS` | ❌ gedroppt | gross_margin 7.4%<30% (legitim) |

**Befund:** Erwartung „EU-Korrekturen stehen in der Basis" ist für **alle außer RACE.MI falsch** —
aber überwiegend aus **legitimen, explizit gerechneten** Gründen (keine stille Attrition: alle
lösen sauber mit vollen Daten auf). Ausnahme RO.SW siehe „Verdächtige Fälle".

### Ehemalige GC-False-Positives {ADC, FR, HIMS, LIVN, WTW}
- Run 1 (13:12): **exakt diese 5** going_concern-gedroppt (mit Accession/Form/Datum im Log).
- Run 2: **0** GC-Drops; **alle 5 stehen in der finalen Basis** (passten basis, post-Fix nicht GC-gedroppt). ✅
- Keiner der 5 unter den 8 Restatement-Drops. Finale Disposition je Name: **in Basis**.

### Gegenprobe FRQN & Anker JNJ
- `FRQN` = Frequency Holdings (OTC, Form 15-12G Deregistrierung) → **nicht im Universum** (kein
  Index-Member) → legitim draußen, kein Bug.
- `JNJ` → ✅ **in Basis** (Regressions-Anker; nicht fälschlich fenster-gedroppt).
- ⚠️ **Caveat:** Da kein echter GC-Titel im 1349-Universum ist, prüft dieser Cold-Run den
  **affirmativen** GC-Pfad nicht live (`going_concern_drops=[]` = Abwesenheit-von-Evidenz für
  den TRUE-Zweig). Gemildert: EFTS-Pre-Filter feuert live (JNJ=8, HON=1 Boilerplate-Hits), der
  Polaritäts-Diskriminator weist die 5 FPs korrekt zu False ab → Detektor **läuft und verwirft
  Boilerplate**; nur der affirmative Zweig ist in-Universum unbenutzt (Live-Beleg nur im separaten
  reduzierten Paid-Run, FRQN=True).

---

## AUDIT 4 — Drop-Plausibilität

### going_concern_drops unabhängig **leer** bestätigt
Run 2: `filter_preview: 0 gc-drops`, keine `going_concern drop`-Zeile im 16:xx-Fenster.

### Die 8 edgar_filter-Drops (Restatement) — unabhängig namentlich
`post_funnel.py` repliziert `has_restatement` (8-K Item 4.02, 3 J) über die 550 US-Basis-Passer
und findet **exakt 8** → **AXON, CPAY, DOCN, ELS, MPWR, RGEN, SITM, TRU** (us_passers_without_cik=0,
error=0). Zahl deckt sich bitgenau mit `edgar_filter: 682/690`. Legitime Drops.

### 325 Large-Cap-Drops (≥10 bn EUR) — überwiegend BY DESIGN, drei Muster zur Beurteilung
`healthy_largecap_drops.csv`: 325 Large-Caps fielen am basis_filter (TSLA, BRK-B, WMT, JPM, XOM,
COST, UNH, NESN.SW, MC.PA, NOVN.SW …). Das ist **kein Bug** — Fishers Hochmargen-/Wachstums-Gates
schließen Retail/Banken/Energie/Rohstoffe bewusst aus. ABER:

1. **Strukturell — Financials-Auslöschung:** **103** Financial-Services-Titel fallen am
   gross_margin-Gate (davon **74 mit gross_margin == 0.0** = Metrik unanwendbar): JPM, BAC, WFC,
   C, HSBA.L, SAN.MC, Allianz … Falls Banken/Versicherer in-scope sein sollen, ist das ein
   **stiller Branchen-Total-Ausfall** (kein Qualitäts-, sondern Metrik-Problem).
2. **Brittle — revenue_growth≥0 auf einem TTM-Snapshot** droppt Top-Compounder auf Mini-Dips:
   Nestlé −2.2 %, LVMH −4.7 %, Novartis −0.7 %, Qualcomm −3.5 %.
3. **Datenartefakt:** Roche fällt am Volumen (illiquide Inhaber-Linie RO.SW).

---

## UNERKLÄRTE / VERDÄCHTIGE FÄLLE

1. **13 reale Firmen still aus dem Screen ausgeschlossen** (falsches Ticker) — Ericsson, Atlas
   Copco, H&M, ASM Intl, DSM-Firmenich, Flutter, ICG, Teva, Indivior, Barratt Redrow, Aker BP
   (+ EFG/Investec). Liste + korrekte Ticker in `unresolved35_classified.csv`. **Höchste
   Materialität** — exakt die Fisher-Qualitätsnamen, die das Tool finden soll.
2. **12 delistete/übernommene Titel im Universum** (MAN SE, MorphoSys, Morrisons, Neoen, DS Smith,
   Swedish Match, Direct Line, Uniper, Varta, Software AG, Lundin Energy, TP Group) → Universe-
   Pflege/Prune nötig; aktuell still als „resolved"+basis-Miss verbucht.
3. **„unresolved=0" maskiert (1)+(2)** — Ursache: `get_ticker_info` wertet degradierte 404-Dicts
   als Erfolg. Mechanismus quell-belegt (Kommentar „does not catch partial-data dicts").
4. **gross_margin≥30% löscht strukturell alle Financials** (103 Drops, 74 mit gm=0).
5. **RO.SW-Roche-„Restauration" wirkungslos** — Anker fällt am Volumen (Inhaber-Linie); liquide
   ROG.SW fehlt + 404t.
6. **5 UNCLEAR-Ticker** (AMS.VI, SCHA.OL, ROL.L, RIGN.SW, SANO.HE) — keine Live-Alias-Bestätigung;
   einzeln nachzuschlagen.

> Hinweis: Befunde 1–5 sind **keine Pipeline-Logik-Bugs** im Sinne falscher Survivor — die
> Survivor-Menge (690/682) ist unabhängig exakt bestätigt. Es sind **Universe-Daten- und
> Filter-Design-Defekte**, die als legitime Drops getarnt sind. Stephan urteilt über Scope/Fix.

---

## Was dieser Cold-Run NICHT beweist (Ehrlichkeits-Vermerk)
- Den affirmativen GC-TRUE-Zweig (kein echter GC-Titel im Universum).
- Die „11"-data_source_error-Baseline (außerhalb des 12h-Log-Fensters; nur Residuum=1 belegt).
- Vollständigkeit gegen die *beabsichtigten* Index-Konstituenten — geprüft wurde gegen
  `universe.json` als Ist-Vollmenge; ob diese Datei selbst alle gewünschten Titel enthält, ist
  eine separate Frage (Befunde 1+2 zeigen: sie enthält kaputte/delistete Einträge).
