# Gate-A Kalibrierung — Punkt 2 (sektor-bewusster gross_margin-Floor)

> Lauf: 2026-06-09, lokal warm-cache + live income_stmt (A1), $0, kein Gemini.
> Skripte: `scripts/diagnose_gross_margin_definedness.py` (A1), `diagnose_sector_median_table.py` (A2),
> `diagnose_k_calibration.py` (A3). Roh-Output: `k_calibration.txt`, `metrik_na_tickers.json`,
> `sector_median_table.candidate.json` (dieser Ordner).

## ✅ PHASE E — FINAL & GESHIPPT (2026-06-10) — supersedes ALLES darunter

Dies ist der kanonische Record der live geshippten Punkt-2-Config. Alle Abschnitte darunter
(KORREKTUR, A1/A2/A3-Erstlauf, k=0,3) sind **historischer Verlauf**, NICHT bindend.

### Akzeptanz-Test: absoluter Below-Median-Regime-Gap (v4)

Der finale Akzeptanz-Test (`app/screener/bucket_acceptance.py::is_bucket_acceptable`) rejectet einen
Bucket gdw. **constituent-median-spread > 0,15** (Multi-Industry-Heterogenität) **ODER** es eine
**Bruttomargen-Lücke ≥ 0,10 (10 Pp) UNTER dem Bucket-Median mit ≥ 20 % der Masse darunter** gibt
(`has_below_median_regime_gap`). Eine Lücke ÜBER dem Median feuert nie (schützt kontinuierlich-weite
Buckets wie Aerospace & Defense, Median im dichten Kern).

**Warum absolut, nicht relativ — der entscheidende Befund (Stephan-Beweis):** JEDE skalen-relative
Normierung kollabiert an den zwei kritischen Buckets, weil Gap und Streuung ko-skalieren —
das benigne **Grocery** erscheint **anomaler** als das schädliche **SBS**:

| Maß | Grocery (benign) | SBS (schädlich) |
|---|---|---|
| gap/median | 0,064/0,210 = **0,30** | 0,15/0,475 = 0,32 |
| gap/IQR | 0,064/0,193 = **0,33** | 0,15/0,408 = 0,37 |
| gap/std | 0,064/0,105 = **0,61** | 0,15/0,224 = 0,67 |
| KDE-Trog (gap/Silverman-h) | h≈0,062, gap≈1×h | h≈0,117, gap≈1×h — SBS' breite bw glättet die eigene Lücke weg |

Alle drei Relativ-Maße ranken Grocery ≈ SBS oder Grocery **drüber**; KDE-Silverman ist `gap/h` mit
Glättung = wieder relativ, mit derselben Rückwärts-Sortierung. **Nur der rohe absolute Gap trennt**
(0,064 vs 0,15). Konsequenz: margenblinde Akzeptanz ist hier nicht „schwer", sondern **unmöglich** —
Grocery und SBS sind strukturell identisch, separierbar nur durch Gap-Magnitude in Margen-Prozentpunkten.
**Margenblindheit fällt daher NUR für den Akzeptanz-Test, NICHT fürs Bucketing** (GICS-Achse bleibt
exogen, Buckets werden nicht margen-gerrymandert → kein `adaptive-stat-swallows-judgment`-Loop; der
Akzeptanz-Test ist ein nachgelagerter Eigenschafts-Check auf den fixen Bucket). Schwellen 0,10/0,20
sind a-priori interpretierbar deklariert (10 Pp = echter Kostenstruktur-/Regime-Bruch), nicht
verdikt-getunt. Voll-68-Bucket-Scan beidseitig validiert: SBS/Computer-Hardware → REJECT,
Airlines/Auto-Mfrs → ACCEPT (Antimode über Median), Specialty Chemicals → ACCEPT (kontinuierlich, der
k-Arm sortiert den Commodity-Tail). Asset Management ACCEPT bei Gap ≈ 0,09 < 0,10 (Schwellen-Borderline,
bewusst nicht getunt).

### Table + k

- **`data/sector_median_table.json`**: **52 PINNED Buckets** (16 rejected-fail-safe), n_min = 8,
  vintage 2026-06. Cleaning vereinheitlicht (`clean_universe`: METRIK_NA + gm≤0 raus, KEIN Sektor-String).
- **`GROSS_MARGIN_RELATIVE_K = 0.5`** (`app/screener/filters.py`). **Decke bei ~0,51:** der erste gesunde
  Name (AES, gm 0,193 / Utilities-Diversified 0,3757) kippt bei k > 0,514; das Sub-k-Band darunter ist
  broken-dominiert (OCI 0,022 / Boeing 0,048 / ATOS 0,042 / commodity chem). k=0,5 ist die maximal-clean
  Rundzahl an der Kante. k=0,6 zieht die Specialty-Chem/Utility-Mittelschicht (Arkema/Albemarle/LANXESS)
  rein → über dem Kriterium. k=0,3 war maskierend (kontaminierter Lauf).

### Gate-B Cold-Run ($0, echte aktivierte Config) — GRÜN

`scripts/diagnose_gateB_additivity.py`:
- **Additivität:** Pass(k=0,5) ⊇ Pass(k=None), **884 → 1059**, kein Vor-Passer fällt (OR-Arm rein additiv).
- **Identity:** RELATIVE_RESCUE-Tag-Count == |DELTA| == **175** (Sub-Floor-Def korrekt; kein Absolut-Passer
  fehl-getaggt — sonst Count > Delta).
- **Vorhersage-Match:** |DELTA| 175 == A3-k=0,5-Rescue-Vorhersage 175.
- Prod-Audit: `gross_margin_pass_reason` taggt `ABSOLUTE_PASS` / `RELATIVE_RESCUE`; `FunnelSummary.relative_rescues`.

### Harte False-Negatives — bewusst, KEIN Bug (Future-Stef: nicht debuggen)

`gross_margin` ist ein **Pre-Scoring-Knock-out** (Basis-Filter vor Gemini, `runner.py` scoring läuft nur auf
basis-passed). Diese realen Namen fallen hart und erreichen den Scorer NIE — strukturell erzwungen, **kein k
rettet sie ohne Floor-Masking:**
- **Costco** (gm 0,129, Discount Stores 0,281) — Membership-Modell, Niedrig-Brutto-by-design; bräuchte k≤0,46.
- **Accor** (gm 0,224, Lodging 0,6125) — bräuchte k≤0,37.
- **Tesco/Sainsbury** (gm 0,076/0,068, Grocery 0,2102) — UK-Accounting-Regime unter US-gewichtetem Median
  (akzeptierter Regime-Spread); bräuchte k≤0,36.
Es gibt kein k, das diese rettet, ohne den Floor aufzuweichen (= Masking-Regime). Akzeptierte Kasualitäten der
Viability-Floor-Philosophie (Gate irrt bewusst Richtung Ausschluss). Membership-Carve-out (Costco) wäre separat
& modell-bewusst, außerhalb dieses Zyklus.

### Provenance (vintage 2026-06, eingefroren in diesem Ordner, Commit `0552582`)

- `metrik_na_tickers.json` — A1-METRIK_NA-Set, **220 Ticker** (REIT-korrigiert), git-blob **`293ea92d`**.
- `sector_median_table.candidate.json` — A2-v4-Candidate, git-blob **`e0f884c7`**, **bit-identisch** zur
  geshippten `data/sector_median_table.json`.
- yfinance ist live → ein Re-Run reproduziert diese Inputs NICHT exakt; daher eingefroren als Input-of-Record.
- Kette: live-config (`data/`, blob e0f884c7) ← Provenance (`audits/`, blobs e0f884c7 + 293ea92d) ← diese Rationale.

### Reversibilität

Arm ist rein additiv + config-gated: bei Prod-Smoke-Auffälligkeit `GROSS_MARGIN_RELATIVE_K=None` → sofort
zurück im verifiziert-dormanten Zustand, kein Code-Revert. **Merge ≠ verifiziert** — der kalte Prod-Smoke
(`POST /run/monthly?dry_run=true`, $0) ist Gate-B-in-Prod (Pass = `relative_rescues`-Liste erscheint ~175 &
reconciliert, NICHT „200 OK"; `relative_rescues=[]` = stiller Dormant-Arm = der Fehler, siehe
`prod-logging-dormant-and-cache-masks-verification`).

---

## ⚠️ KORREKTUR (Stephan-Review 2026-06-09) — supersedes A2/A3 unten

Die untenstehende A2/A3-Erstlesung („CT-B deferred", „k=0,30") ist **widerlegt** und NICHT bindend.
Bindend ist dieser Abschnitt:

- **Der Kandidat-Table ist flächig kontaminiert.** Smoking Gun: **byte-identische `bucket_median` über
  distinkte Industries** = Sektor-Catch-all-Median. `0.3508` (Industrials-Sektor) steht bei Marine Shipping,
  Staffing, Consulting, Rental&Leasing, Security, Metal Fabrication, Trucking, Railroads, Waste Mgmt,
  Conglomerates; `0.3387` (Basic Materials) bei Chemicals, Other Metals, Ag Inputs, Aluminum, Paper, Lumber.
  Diese Industries sind im Universum dünn (< n_min=8) und rollen auf den **multimodalen Sektor** hoch →
  der relative Arm feuert für sie auf einem bedeutungslosen Blend (Maersk gegen 0,3508 statt Shipping ~0,16).
- **k=0,30 war maskierend, nicht kalibriert.** Bei nur 34/305 Fails ist „Sub-k-Band broken-dominiert"
  trivial erfüllt, weil fast nichts failt; die 0,3×Median-Latte überdeckt die aufgeblähten Blends UND die
  Within-Bucket-Heterogenität (Grocery mischt US ~25 % mit UK-Tesco 7,6 %/Sainsbury 6,75 % — zwei
  Accounting-Regime). Nicht attribuierbar (rettet k=0,3 das Richtige oder nur den Table?) und fragil
  (k≥0,5 → Maersk/Dell/HP false-rejected). Wahrscheinlich ist k zu niedrig: auf sauberen Buckets hielte
  k=0,5–0,7 normale-für-Sektor-Titel ohne false-rejects.
- **REIT-Positiv-Kante (Property C):** A1 lässt reine Equity-REITs als DEFINED durch (AvalonBay/BXP/Brixmor/
  Alexandria — Miete − Property-Opex erfüllt die Wasserfall-Konsistenz), aber Spec-Intent ist REIT = METRIK_NA.
  → Property-C-Cross-Check muss feuern (`"REIT" in industry` → METRIK_NA), sonst landen REITs im Fisher-Scoring.
  RE-Services mit echtem COGS (CBRE/JLL, kein „REIT" im Industry-Label) bleiben DEFINED.

**Korrigierte Entscheidungen:** CT-A bauen (inkl. REIT-Property-C-Cross-Check); **CT-B von deferred auf REQUIRED
gehoben** (Industry→Industry-Group-Mapping statt Sektor-Catch-all); A1/A2/A3 neu fahren auf sauberen Medianen;
**k erst gegen den sauberen Table benennen** (Erwartung höher/schärfer als 0,3). Phase E wartet auf den sauberen Table.
**Audit-Detektionsregel:** jeder Median, der wortgleich über mehrere distinkte Industries steht, ist ein
Catch-all → diese Industries haben keinen echten Bucket.

---

## A1 — Definiertheit: CT-A ERZWUNGEN

Korb 287 (Financials/REITs ∪ gm≤0 ∪ ~29), 0 Fetch-Errors. Wasserfall-Form-Klassifikation:

- **NULL-Kante = 3** (gm≤0 aber DEFINED_NEGATIVE): **CLF** (Basic Materials −0,029), **CYTK** (Healthcare −2,91),
  **FLR** (Industrials −0,016). Reale Negativmarger mit echtem COGS-Wasserfall → gehören zu FAIL, NICHT METRIK_NA.
- **POSITIV-Kante = 82** (Financial/REIT, gm>0 aber UNDEFINED): Banken/Versicherer/Broker ohne echtes COGS —
  GS, MS, SCHW, BX, AXP, ALL, MET, PRU, BRK-B, … Würden durch ein `.info`-only-Prädikat ins Fisher-Scoring
  rutschen (die BNP/ACA-Sorge, in groß).

**→ Property A KIPPT → `.info`-only-Default verworfen → CT-A (Wasserfall-Prädikat im Runtime) ist erforderlich.**

Validierung des Ansatzes: der Wasserfall-Diskriminator trennt Financials datengetrieben — **behält** die
Fisher-tauglichen Capital-Markets-Compounder (MA, V, SPGI, MSCI, MCO, ICE, CME, NDAQ, BLK, KKR, APO → DEFINED,
echtes COGS) und **schließt** die Bilanz-Financials aus (Banken/Versicherer → UNDEFINED). Genau die im Brainstorm
gewollte Klasse überlebt.

METRIK_NA-Set (Wasserfall): **162** Ticker (vs. 87 `.info`-Proxy). A2 konsumiert die 162 via
`metrik_na_tickers.json` (kein Sektor-Sweep).

## A2 — Sektor-Median-Table: Fix wirkt, 11 multimodale Sektor-Fallbacks

- Cleaned-Universe **1030/1155** Records (162 METRIK_NA korrekt ausgeschlossen). Beweis, dass der A1→A2-Handoff-Fix
  greift: die Capital-Markets-Buckets EXISTIEREN (`Financial Data & Stock Exchanges` n=14 Median 0,82;
  `Asset Management` n=17 Median 0,52) — der alte Sektor-Sweep hätte sie ausgelöscht.
- n_min=8 → 73 Buckets, **11 `[SECTOR-FALLBACK]`** (Industry < n_min → Roll-up auf multimodalen Sektor:
  Consumer Defensive 0,04→0,87; Healthcare 0,04→0,89; Financial Services 0,03→1,0; Industrials 0,03→0,80; …).
  Zur Laufzeit würde der relative Arm auf diesen Müll-Medianen feuern — **aber bei k=0,3 vernachlässigbar** (s. A3).
- **GICS-Nest-Finding:** `.info` liefert nur 2 Ebenen (sector+industry), kein Industry-Group. → CT-B-Kandidat,
  aber durch niedriges k entschärft → **deferred**.

## A3 — k-Kalibrierung: k = 0,30

Sub-floor-Band (gm<0,30) = 305 Records. Sweep:

| k | rescued | still-failing | Sub-k-Band-Charakter |
|---|---|---|---|
| **0,3** | **270** | **34** | pathologisch/ultradünn dominiert (Glencore 0,025, OCI 0,022, PBF 0,018, ATOS, Boeing, Hays, Distributoren McKesson/Cardinal/Cencora 0,036–0,04, commodity ADM/Bunge/Tyson/Dow/LYB). ~2–3 diskutabel (Barry Callebaut, WPP). **Kriterium erfüllt.** |
| 0,4 | 241 | 63 | zieht viable Low-Margin-Modelle rein (Sysco 0,185, US Foods, Accor 0,224, Omnicom, Whirlpool, Electrolux, Autohändler). **Kriterium degradiert** (nicht mehr leer von Gesunden). |
| 0,5–0,7 | 219→152 | 85→152 | Band füllt sich zunehmend mit gesunden Namen (Costco, Defense-Primes). |

**Entscheidung k=0,30** = größtes k, dessen Sub-k-Band noch broken-dominiert und ~leer von Gesunden ist
(dein Akzeptanzkriterium). Floor-Prinzip-treu: schneidet nur den pathologischen Tail, Qualität macht der Scorer.

**Kanaren-Check @ k=0,3:** alle gerettet — Maersk 0,16 (Industrials-Fallback ×0,3=0,105), Colruyt, DIA, NVR,
Costco, Carrefour + Autos/Airlines/Grocers. Maersk wäre bei k≥0,5 verfehlt worden → niedriges k holt den
Thin-Industry-Kanari rein UND macht die Fallback-Multimodalität vergebend (CT-B unnötig dringend).

**Erkenntnis:** Bruttomarge trennt selbst sektor-relativ nicht sauber „dünn-aber-exzellent" von „dünn-weil-schwach"
(Buckets intrinsisch heterogen — Confectioners mischt B2B-Callebaut + Marken-Hershey). Bestätigt das Leitprinzip:
Gate = Viabilitäts-Floor, Qualität = Scorer.

**Bewusste Konsequenz:** k=0,3 rettet 270/305 → Funnel vor dem Scoring deutlich breiter (alter 30%-Flat droppte
alle 305). Nachgelagerte Gates (revenue_growth/Punkt 3, EDGAR, Wert-Gate) + Gemini-Cost-Cap fangen das Volumen ab.

## Entscheidungen (korrigiert — s. KORREKTUR oben)

| # | Entscheidung | Wert |
|---|---|---|
| 1 | CT-A Wasserfall-Prädikat im Runtime **+ REIT-Property-C-Cross-Check** | **Bauen** (erzwungen; bounded auf Verdachts-Korb-Fetch; koppelt Punkt 2 an income_stmt/Punkt-3-Datenquelle) |
| 2 | CT-B Industry→Industry-Group-Mapping (statt Sektor-Catch-all) | **REQUIRED** (war fälschlich deferred; Table flächig kontaminiert) |
| 3 | n_min | **8** (gegen sauberen Table re-validieren) |
| 4 | k (relativer Arm) | **NOCH NICHT benannt** — erst gegen den sauberen Table re-sweepen (Erwartung höher/schärfer als 0,3) |

## Reversibilitäts-Trigger (Future-Stef, nicht wegrationalisieren)

- **k=0,3 ist kalibriert gegen das Sub-k-Band**, nicht 4-Namen-optimiert: re-evaluieren, wenn das still-failing-Band
  bei einem Re-Lauf gesunde Namen aufnimmt (Verteilungsdrift) oder der pathologische Tail nicht mehr dominiert.
- **Kanarienvögel** (unterste gerettete @ k=0,3, Thin-Industry/Fallback-abhängig): **Maersk** (Marine Shipping→Industrials-Fallback),
  **PCAR** 0,136, **STLAM** 0,058 — fällt einer ohne Ursache aus dem Rescue, ist es Drift, kein k-Tuning.
- **CT-B-Trigger:** wenn der Funnel zeigt, dass Sektor-Fallback-Buckets bei k=0,3 doch Müll-Rescues erzeugen
  (gesunde-sektor-Namen fälschlich gerettet über inflationierten Sektor-Median), GICS-Mapping-Layer bauen.
- **Residuum REITs:** datengetrieben gespalten (O/OHI DEFINED via COGS-Zeile → ins Scoring; VICI/MRL UNDEFINED → raus).
  Akzeptiert (keine gepflegte Liste); eigenes Ticket falls REIT-Coverage unerwünscht.
