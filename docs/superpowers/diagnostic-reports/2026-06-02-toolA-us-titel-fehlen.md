# Diagnose: Tool A — US-Titel fehlen weiterhin in Production (Post-V3)

> **Typ:** DIAGNOSE-ONLY (systematic-debugging). Kein Fix, kein Code-Change, kein Plan,
> kein PROJEKTSTAND-Edit, kein Push. Fix/Plan = separate Folge-Session.
> **Datum:** 2026-06-02
> **Scope:** Tool A (Cloud-Run Monthly Screener). NICHT Tool B / nicht 1.4-Insider.
> **Auslöser-Befund:** Produktionslauf `run_id 2026-06-01T19:55:23`, status success,
> `universum_size 126`, Crosshits + Dimensions **EU-only, NULL US-Titel** — gleiches
> Bild wie Mai, obwohl der V3-Basis-Filter-Fix live ist.

---

## TL;DR — Belegter Root Cause

US-Titel werden **nicht** am Basis-Filter eliminiert (V3-Fix wirkt korrekt), sondern eine
Stufe später am **EDGAR-Filter**, durch einen **False-Positive in `has_going_concern`**:

`app/services/edgar_client.py::EdgarClientImpl.has_going_concern` baut eine EDGAR-Full-Text-
Search-(EFTS-)URL mit dem Scoping-Parameter **`&entity={cik}`**. Dieser Parameter ist
**kein gültiger EFTS-Parameter** und wird vom Server **stillschweigend ignoriert**. Die
Query nach `"raise substantial doubt"` läuft dadurch **ungescoped über das gesamte
EDGAR-Korpus** → `hits.total.value` = 10000 (EFTS-Max-Cap) → `> 0` → die Methode liefert
**`True` für jeden US-Ticker mit CIK**. Jeder US-Titel wird daraufhin in
`apply_edgar_filters` als `going_concern` verworfen und erreicht das Gemini-Scoring nie.

EU-Titel überleben, weil sie (mit Börsen-Suffix wie `.AS`/`.L`/`.DE`) **keine CIK** in
`company_tickers.json` finden → `edgar_skipped=True` → behalten. Der im Projektstand
dokumentierte „EU-CIK-Blindfleck" ist hier paradox der einzige Grund, warum überhaupt
Titel durchkommen.

**Stufe:** EDGAR-Filter (`run_edgar_filter` → `has_going_concern` → `apply_edgar_filters`).
**Hypothese H3 bestätigt** (US fällt NACH dem Basis-Filter raus). H1/H2/H4 widerlegt
bzw. auf Sekundärrolle reduziert (s.u.).

---

## Beweis-Evidenz (frei, kein Gemini, kein Geld)

Alle Proben gegen die **echte SEC-EFTS-API** mit dem **echten Produktions-Code**
(`EdgarClientImpl`), read-only GET, rate-limited.

### E1 — Der `entity=`-Parameter wird von EFTS ignoriert (Mechanismus)

Exakt die in `has_going_concern` gebaute URL vs. der korrekte Parameter `ciks=`:

| Probe | URL-Scoping | Status | `hits.total.value` |
|---|---|---|---|
| **PROD** (`&entity=0000789019`) | MSFT (so wie der Code es baut) | 200 (3/3) | **10000** |
| `&ciks=0000789019` (korrekt) | MSFT | 200 | **0** |
| ganz ohne Scoping (`q`+`forms`) | — | 200 | **10000** |

Die PROD-Variante ist **byte-identisch** zur ungescopeten Variante (beide 10000) →
`entity=` hat **keinerlei** filternde Wirkung. Mit dem korrekten `ciks=`-Parameter hat
MSFT **0** Going-Concern-Treffer (= die Wahrheit: MSFT hat keinen Going-Concern-Zweifel).

### E2 — Die Produktionsmethode liefert `True` für gesunde US-Mega-Caps (End-to-End)

`EdgarClientImpl.has_going_concern(cik)` direkt aufgerufen (Retry über die sporadischen
EFTS-500 hinweg):

```
MSFT  cik=789019  has_going_concern=True
AAPL  cik=320193  has_going_concern=True
JNJ   cik=200406  has_going_concern=True
KO    cik=21344   has_going_concern=True
```

Alle vier sind kerngesund — der False-Positive ist 100 %.

### E3 — EU-Ticker erhalten keine CIK → werden übersprungen → behalten

```
NOVO-B.CO  cik=None      ASML.AS  cik=None     AZN.L  cik=None
SAP.DE     cik=None      ITX.MC   cik=None
```

`get_cik` macht einen `ticker.upper()`-Lookup in `company_tickers.json`; die Suffix-Ticker
matchen dort nie → `record.cik is None` → `record.edgar_skipped = True` → in
`apply_edgar_filters` werden `edgar_skipped`-Records **durchgelassen**.

### E4 — Produktions-Output ist 100 % EU (direktes Artefakt)

`output/Universum/2026-06-{Dimensions,Crosshits}.md` (via GitHub-Sync, der 19:55-Lauf):
**jeder** Ticker in allen fünf Dimensionen trägt ein Länder-Suffix
(`.CO/.AS/.L/.DE/.PA/.MC/.MI/.SW/.ST/.HE/.OL/.BR/.LS`). **Kein einziger** suffixloser
US-Ticker. `universum_size: 126`.

### E5 — `has_going_concern` ist sporadisch fehlerhaft (EFTS-500), aber das killt nicht

Einzelne Aufrufe lieferten 500 (`{"message":"Internal server error"}`). Ein 500 →
`DataSourceError` → im Runner gefangen → `edgar_skipped=True` → Record **behalten**.
Ein 500 droppt also **nicht**; nur der 200-mit-10000-Pfad droppt. EFTS antwortet
weit überwiegend mit 200 → der Drop dominiert.

---

## Pipeline-Pfad & exakte Drop-Stelle (Code-verifiziert)

```
universe.json (1389)
   │
   ▼  run_basis_filter (runner.py)             ← V3 aktiv: bid/penny-Filter ENTFERNT (verifiziert filters.py)
   │   US passieren (Market-Cap≥€2B / GM≥30% / RevGrowth≥0% / Volume)   ✓ (03:00-Logs: US-CIKs erreichen EDGAR)
   ▼  run_edgar_filter (runner.py)
   │   get_cik(US) -> CIK
   │   has_restatement(cik)      -> meist False (korrekt per-CIK gescoped über submissions-JSON)
   │   has_going_concern(cik)    -> TRUE  ← ★ ROOT CAUSE (ungescopeter EFTS-Query, entity= ignoriert)
   │   apply_edgar_filters: going_concern True -> filter_passed_edgar=False, reason="going_concern", NICHT behalten
   ▼  run_gemini_scoring         ← US kommen hier NIE an
   ▼  output-Generatoren          ← bauen aus `scored` (gemini_dimensions != None) -> 0 US
```

Belegstellen:
- `app/screener/filters.py` — `apply_basis_filters`: nur Volume/MarketCap/GrossMargin/
  RevGrowth; **kein** Bid-/Penny-Filter mehr (V3 bestätigt im Code). `apply_edgar_filters`:
  `has_going_concern` True → Record wird **nicht** in `passed` aufgenommen.
- `app/screener/runner.py` — `run_edgar_filter`: `DataSourceError` → `edgar_skipped=True`
  (= behalten); ein echter `True`-Rückgabewert dagegen droppt.
- `app/services/edgar_client.py:110` — `has_going_concern`: die URL mit `&entity={padded}`.
- `app/output/*_generator.py` — region-agnostisch; filtern nur `gemini_dimensions != None`
  und Score ≥ Schwelle. **Kein** Region-Filter (H4 widerlegt).

---

## Hypothesen-Abgleich

| # | Hypothese | Verdikt | Begründung (Evidenz) |
|---|---|---|---|
| **H3** | US fällt NACH dem Basis-Filter raus (EDGAR) | ✅ **BESTÄTIGT** | E1/E2: `has_going_concern` ist ein 100 %-False-Positive für US; `apply_edgar_filters` droppt sie. Deckt sich mit den 03:00-EDGAR-CIK-Logs (US erreichen EDGAR, sterben dort). |
| **H1** | Cache-Bleed (Mai-Cache kurzschließt V3) | ⚠️ **Sekundär, nicht Root** | yfinance-Cache TTL=24h (Mai längst expired); `filter_passed_basis` wird pro Lauf **neu** berechnet (ScreenerRecord wird frisch gebaut), nicht über Läufe gecached. ABER: zwei Caches **verstärken/maskieren** den Bug (s. „Cache-Rolle"). |
| **H2** | V3 nicht im laufenden Image aktiv | ❌ widerlegt (für diesen Befund irrelevant) | Basis-Filter-Code ist V3; US passieren den Basis-Filter (03:00-Logs). Der Defekt liegt im EDGAR-Code, der nachweislich deployed ist. Image-Verifikation wäre Bonus, ändert Root Cause nicht. |
| **H4** | Output-Generatoren filtern nach Region | ❌ widerlegt (Code-Read) | Generatoren rendern region-agnostisch, nur Score-Schwelle. |

### Cache-Rolle (warum der 19:55-Lauf EU-only + $0 ist)

Der 19:55-Lauf ist — wie im Auftrag korrekt markiert — **kein gültiger V3-Test**, aber aus
einem präziseren Grund als „Cache-Replay allein":

1. **EDGAR-Cache** (`dev_edgar_cache`, TTL **7d**, CIK-gekeyt, speichert
   `has_restatement`+`has_going_concern`): Sobald ein US-CIK einmal ein 200 erhält, wird
   `has_going_concern=True` **persistiert**. Jeder Lauf im 7-Tage-Fenster droppt den Titel
   dann **ohne erneuten EFTS-Call** → der False-Positive wird deterministisch/„klebrig",
   auch über die EFTS-500-Flakiness hinweg.
2. **Gemini-Score-Cache** (`dev_gemini_scores`, TTL **30d**, **nur ticker-gekeyt**, Cache-Hit
   liefert bewusst `tokens_in/out=0`): Im Mai wurden US **nie gescort** (Bid-Filter killte
   sie vor dem Scoring) → es gibt **keine US-Einträge**. Die EU-Scores aus dem Mai sind
   < 30d alt → werden $0 repliziert. Da US am EDGAR sterben, gibt es nichts zu replizieren
   → der Lauf reproduziert getreu EU-only bei 0 Tokens.

**Schlussfolgerung aus der 0-Token-Evidenz:** Hätte irgendein US-Titel das Scoring erreicht,
wäre er **unkachiert** gewesen (Mai hat ihn nie gescort) → frische Gemini-Calls → Tokens > 0.
Da Tokens = 0, hat **kein** US-Titel das Scoring erreicht — konsistent mit dem EDGAR-Drop.

**Latenz-Muster:** Der V3-Fix (Bid-Filter raus) hat einen **vorher dormanten** Filter-Bug
freigelegt. Pre-V3 erreichten US die EDGAR-Stufe nie; der `has_going_concern`-Defekt war
unsichtbar. „Eine Schicht gefixt, die nächste latente Schicht exponiert."

### Offener Rest (ändert Root Cause NICHT)

Streng genommen könnte ein US-Titel, der in einem Lauf zufällig ein EFTS-**500** erwischt,
übersprungen → behalten → gescort → gecached werden und dann auftauchen. Im 19:55-Output
ist das bei **null** US-Titeln der Fall. Vollständig schließen ließe sich das mit zwei
freien Checks (mir war `gcloud` in dieser Session nicht freigegeben):

- **Cloud-Run-Logs** 03:00 + 19:55: `edgar_filter: X/Y passed` (großer Drop) und die
  per-Ticker-Zeilen `ticker=<US> ... reason="going_concern"` bzw.
  `EDGAR fetch failed ... skipping`. Plus die Region-Count-Zeile aus `apply_basis_filters`
  (`US a/b`) als Bisektor-Bestätigung, dass US den Basis-Filter passieren.
- **Firestore** `dev_edgar_cache`: US-CIKs mit `has_going_concern: true`. Und
  `dev_gemini_scores`: **keine** US-Ticker-Einträge.

Diese Checks sind Korroboration; der Mechanismus ist über E1/E2 bereits mit
Produktions-Code reproduziert.

---

## Warum Tests & lokaler Akzeptanz-Check das nicht fingen

- **Unit-Tests** mocken den EDGAR-Client (DI-Pattern, kein echter Netzwerk-Call) → die
  fehlerhafte URL wird nie gegen echtes EFTS ausgeführt; der Mock liefert kanonische
  `going_concern`-Werte. **Test-Gap:** kein Test fixiert „`has_going_concern` muss für einen
  gesunden Large-Cap False sein" und keiner prüft die URL-Konstruktion/Parameter-Namen.
- **`scripts/acceptance_basis_filter.py`** testete nur den **Basis-Filter** (11/15 US passen)
  — die EDGAR-Stufe lief dort nicht. Daher die falsche Zuversicht: „11/15 US passieren V3"
  war korrekt **und** irrelevant für die eigentliche Regression eine Stufe später.

---

## Fix-Empfehlung (für separate Folge-Session — NICHT hier umgesetzt)

**Primär (Root Cause):** EFTS-Scoping in `has_going_concern` korrigieren.
- `&entity={padded}` → korrektes Scoping `&ciks={padded}` (E1 belegt: `ciks=` → 0 Treffer
  für MSFT). **Padding-Achse bereits entschärft:** die Methode macht schon `padded =
  cik.zfill(10)` und reicht `{padded}` weiter → der reine Parametertausch erbt die
  10-stellige gepaddete Form, kein zusätzlicher Padding-Schritt nötig. Ergebnis-Interpretation
  kann bleiben, sobald die Query wirklich gescoped ist.
- **Defense-in-depth-Sentinel: primär `hits.total.relation == "gte"`**, nicht die Magic
  Number. Verifiziert (Review-Refinement 2026-06-02): over-broad liefert
  `{'value': 10000, 'relation': 'gte'}`, korrekt-gescoped-gesund liefert
  `{'value': 0, 'relation': 'eq'}`. `relation == "gte"` ist EDGARs kanonisches
  „Ergebniszahl gekappt/approximativ"-Signal und erkennt over-broad **unabhängig vom
  konkreten Cap-Wert** (10000 kann SEC ändern → `value == 10000` bräche dann still). Die
  `== 10000`-Prüfung höchstens als zusätzlicher Gürtel. Fängt künftige Scoping-Regressionen
  laut statt still alle zu droppen — [[prompt-objective-trigger-not-subjective-judgment]].
- EFTS-**500-Härtung** (evidenzbasiert, s. E5: 500 real beobachtet): Retry/Backoff wie beim
  Gemini-503-Pattern (tenacity ist im Projekt etabliert), damit Flakiness nicht zwischen
  „droppen" und „skippen" zufällig kippt. **Mit WARNING-Logging beim Retry**, damit der
  Retry keinen echten künftigen EFTS-Fehler maskiert.
- **Design-Smell für später (NICHT dieser Bug):** nach dem Fix hängt `has_going_concern` an
  `> 0` und am reinen Phrasenmatch `"raise substantial doubt"` ohne „going concern"-Kopplung.
  Scoped auf eine CIK ist `> 0` für echte Going-Concern-Sprache vertretbar, aber der
  Phrasenmatch kann Kontext-Fehltreffer ziehen. Eigene Notiz, kein Teil dieses Fixes.

**Pflicht-Begleitschritt (sonst wirkt der Fix nicht sofort):** Der `dev_edgar_cache` hält
für US-CIKs vergiftete `has_going_concern=true`-Einträge (7d-TTL). Nach dem Fix **muss**
dieser Cache invalidiert werden (Collection purgen oder Cache-Schema-Version bumpen) —
sonst re-emittiert der nächste Lauf die gecachten Drops bis zur natürlichen TTL-Expiry.
(Das ist die präzise Form von Stephans offenem Punkt „Cache-TTL bei Monatswechsel": nicht
der Monatswechsel ist das Problem, sondern persistierte False-Positives im EDGAR-Cache.)

**Test-Lücke schließen:** Integration-Test (`@pytest.mark.integration`) der `has_going_concern`
gegen echtes EFTS für einen gesunden Large-Cap (erwartet False) + einen historischen
Going-Concern-Fall (erwartet True); Unit-Test, der die gebaute URL auf `ciks=` prüft.

**Verifikation cost-aware:** Nach Fix + Cache-Purge ein **reduzierter** bezahlter Lauf über
5–10 bekannte US-Large-Caps (MSFT/AAPL/JNJ/KO/…), **kein** voller cache-kalter Universum-Lauf
(Budget-/Hard-Stop-Risiko — genau der heutige Incident).

**Grober Fix-Scope:** klein/chirurgisch.
1 Parameter-Korrektur in `has_going_concern` + Cap-Sentinel + EFTS-Retry +
EDGAR-Cache-Invalidierung + 2–3 Tests. Schätzung: 1 kleine Session.

---

## Sekundär-Beobachtungen (nicht Teil dieses Root Cause, nur notiert)

- **Changes-File „Erster verfügbarer Run"** (`2026-06-Changes.md`): Der Cloud-Run-Container
  hat den Mai-`Dimensions.md` lokal nicht (ephemeres FS; Vormonats-Files liegen nur in
  GitHub). `changes_generator._load_prior_frontmatter` globbt das lokale `output/Universum/`
  → findet keinen Vormonat → „keine Vergleichsbasis". Separater Defekt, eigenes Ticket.
- **`has_active_enforcement`** ist ein Stub (`return False`) — kein Killer, korrekt neutral.
- **`has_restatement`** ist per-CIK über die submissions-JSON korrekt gescoped — nicht betroffen.

---

## Status

Root Cause **belegt** (EDGAR-Stufe, `has_going_concern`-EFTS-Scoping-Bug, E1–E5).
Diagnose abgeschlossen. **STOP** — Fix/Plan = separate Folge-Session.
Working-Tree nicht verändert außer diesem Report. Kein Push.

---

## Fix umgesetzt (Folge-Session 2026-06-02 — TDD, NICHT gepusht)

Der oben empfohlene Fix ist umgesetzt. Code grün (655 Tests / 97.20 %), kein Push,
kein bezahlter Lauf (= separates Gate). Geänderte Dateien:

**1. `app/services/edgar_client.py` — `has_going_concern` (Root Cause):**
- **`&entity={padded}` → `&ciks={padded}`** (E1: `ciks=` → 0 Treffer für MSFT). Padding
  via vorhandenes `cik.zfill(10)` durchgereicht — kein zusätzlicher Schritt.
- **Over-broad-Sentinel, primär `relation == "gte"`** (E1: gesund-gescoped = `eq`/`value:0`,
  over-broad = `gte`/`value:10000`); `value >= 10000` nur als Gürtel (`_EFTS_OVERBROAD_CAP`).
  Bei over-broad → **`DataSourceError` (fail loud)**, NICHT `True`: der Runner fängt
  `DataSourceError` → `edgar_skipped=True` → Titel **behalten** (E5). Eine künftige
  Scoping-Regression skippt+keept also **laut** (geloggt), statt still alle US zu droppen —
  [[prompt-objective-trigger-not-subjective-judgment]]. Fehlendes `relation`-Feld → Default
  `eq` (Alt-Fixtures `value:2`/`value:0` bleiben gültig).
- **EFTS-500-Retry** (`_get_efts`, evidenzbasiert E5): bis 3 Versuche, lineares Backoff,
  **WARNING pro Retry** (maskiert echte persistente EFTS-Ausfälle nicht). Isoliert auf den
  EFTS-Pfad — `_get` (submissions) bleibt unangetastet, kein Scope-Creep.

**2. `tests/services/test_edgar_client.py` — +6 Tests (TDD, erst rot):**
`scopes_query_with_ciks_param`, `false_for_scoped_healthy_eq_zero`,
`true_for_scoped_genuine_hit_eq_relation` (Positiv-Pin: legitimer Going-Concern-Treffer
`eq`/`value>0`→True — Review-Refinement, der Refactor baute genau diese True/raise-Verzweigung
um, daher explizit festgenagelt statt über den `relation`-Default angenommen),
`raises_on_overbroad_gte_relation` (Sentinel-Trennschärfe vollständig: eq/0 ↔ eq/>0 ↔ gte),
`retries_on_efts_500_then_succeeds` (+ WARNING-Assert), `raises_after_efts_500_exhausted`.

**3. `scripts/invalidate_edgar_going_concern_cache.py` — Pflicht-Begleitschritt (umgesetzt,
NICHT ausgeführt):** Gezielter Delete aller `dev_edgar_cache`-Docs mit
`has_going_concern == True` (das Doc hält beide Signale → erzwingt frischen Re-Fetch beider).
**Dry-run-Default**, `--apply` für echte Löschung (Löschen ist schwer reversibel → kein
Auto-Lauf). Befehl (cmd.exe), unmittelbar VOR dem reduzierten bezahlten Lauf auszuführen:
```
uv run python scripts/invalidate_edgar_going_concern_cache.py            (dry-run, zeigt Treffer)
uv run python scripts/invalidate_edgar_going_concern_cache.py --apply    (löscht)
```

### Out of Scope (nur notiert, separate Tickets — bewusst NICHT umgesetzt)
- `> 0`-Schwelle + reiner Phrasenmatch `"raise substantial doubt"` ohne „going concern"-Kopplung
  (Design-Smell, eigenes Ticket).
- Nebenbefund `2026-06-Changes.md` / Cloud-Run-Container „Erster verfügbarer Run" (eigenes Ticket).
- **Lauf-Level-Aggregat für `edgar_skipped` (eigenes Ticket).** Der `DataSourceError`-Pfad fängt
  jetzt auch den 500-erschöpft- UND den Over-broad-Sentinel-Fall → `edgar_skipped=True` → behalten.
  Bei einem echten EDGAR-Ausfall hieße das: ganzer US-Satz übersprungen, Going-Concern-Gate lief
  faktisch nicht — und der Lauf sieht aus wie ein sauberer Durchlauf (nur Pro-Ticker-WARNING, kein
  Aggregat). Das ist dasselbe „silent-looking-clean"-Muster wie der Originalbug, nur in
  **keep**-Richtung. Empfehlung: Lauf-Level-Summary, das `edgar_skipped`-Records nach Ursache trennt
  (`DataSourceError` vs. `no-CIK`) und bei hohem DataSourceError-Anteil WARNING/ERROR aggregiert.

### Offen vor dem nächsten Schritt (separate Session, „Go" erforderlich)
1. Push des Branches.
2. Deploy auf Cloud Run (neues Image).
3. Cache-Invalidierung: **erst Dry-run** (`invalidate_edgar_going_concern_cache.py` ohne Flag) und
   den Treffer-Count gegenlesen — ist die Größenordnung plausibel (vergiftete US-CIKs), dann
   `--apply` gegen `dev_edgar_cache`. Genau dafür ist Dry-run der Default.
4. **Reduzierter** bezahlter Lauf über 5–10 US-Large-Caps (MSFT/AAPL/JNJ/KO/…), KEIN voller
   cache-kalter Universum-Lauf (Budget-/Hard-Stop-Risiko). **Zweiseitig samplen:** mindestens
   **einen bekannten Going-Concern-US-Namen** mit aufnehmen → erwartetes `True` beobachten.
   Begründung: ein reines Healthy-Sample läuft auch dann grün durch, wenn der Fix den Filter
   versehentlich neutralisiert hätte (immer `False`) — die gesunden Titel überleben ja
   erwünschtermaßen. Ein Healthy-only-Sample kann „gefixt" nicht von „Filter tot" unterscheiden;
   erst ein echtes `True` auf einem Distressed-Namen macht den Lauf beweiskräftig.
   - **Date-Scope-Falle (Last-Mile, sonst sabotiert sie das zweiseitige Gate spurlos):** Die
     Query ist zeit- UND formgescoped — `has_going_concern` setzt `startdt = today − months*30`
     (Default `months=24` → **~720 Tage / ~24 Monate**, **kein `enddt`** → oben offen) und
     `forms=10-K,10-Q` (nur US-domestic; ein 20-F/FPI matcht NICHT). Der Distressed-Name muss seine
     Going-Concern-Sprache (`"raise substantial doubt"`) in einem **10-K/10-Q innerhalb der letzten
     ~24 Monate** tragen. Liegt das flaggende Filing außerhalb des Fensters, kommt für einen real
     distressed Namen ein `False` zurück → man sitzt wieder in der Mehrdeutigkeit „gefixt vs. Filter
     tot", die das Sample gerade ausräumen sollte.
   - **Freie Vorprobe (kein Gemini, kein Geld):** Vor dem bezahlten Lauf für den Kandidaten-CIK
     denselben gescopeten `&ciks=`-Query absetzen (echter gefixter Code-Pfad) und prüfen, dass er
     `value > 0, relation = "eq"` liefert. Erst dann ist gesichert, dass der Live-Lauf das `True`
     überhaupt sehen kann.
5. Optional, frei: Integration-Test (`@pytest.mark.integration`) `has_going_concern` gegen
   echtes EFTS (gesunder Large-Cap → False; historischer Going-Concern → True).
