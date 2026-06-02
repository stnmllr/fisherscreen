# Befund + Fix-Ticket: Going-Concern-Filter — Rest-False-Positive für gesunde US-Blue-Chips

> **Typ:** DIAGNOSE-BEFUND aus freier Vorprobe + Fix-Ticket-Setup (eigene Sub-Phase).
> **Datum:** 2026-06-02 (Folge-Session zur Auslieferung von `entity→ciks`).
> **Status:** Fix `entity→ciks` ist **ausgeliefert & live** (PR #7 gemergt `91ca380`,
> Revision `fisherscreen-service-00077-p8w`, Image `app:91ca380…`, Traffic 100 %).
> **ABER:** Der zweiseitige Beweis ist **BLOCKIERT** — die freie Vorprobe (vor Cache-Delete,
> vor Geld) hat einen **Rest-Defekt** belegt: gesunde Mega-Caps (JNJ) flaggen weiterhin
> `going_concern=True` und würden gedroppt. Cache **nicht** invalidiert, **kein** bezahlter
> Lauf. Vorgänger-Report: `2026-06-02-toolA-us-titel-fehlen.md`.

---

## TL;DR

Der ausgelieferte Fix behebt den **katastrophalen** Fall (`&entity=` → ungescoped →
`value=10000` → **alle** US gedroppt). Die große Mehrheit gesunder US überlebt jetzt korrekt
(`False`). **Aber** ein **Rest-Set** gesunder US mit *irgendeiner* All-Time-„raise substantial
doubt"-Sprache flaggt weiterhin `True`. Belegt an **JNJ** (Talk-Litigation) und **AWI**
(Asbest-Insolvenz 2001–06). Wurzel: **ein zweiter, ebenfalls still ignorierter Scoping-Parameter**
(`startdt`) hinter dem ersten — dieselbe Defektklasse wie `entity=`. Die FERTIG-Definition
„Healthy überleben (**kein** False-Positive mehr)" ist damit **nicht** erfüllt.

**Prozess-Gewinn:** Die Gate-Sequenz hat sich bezahlt gemacht — der Rest-Defekt wurde **vor**
Cache-Löschung und bezahltem Lauf gefunden, die sonst einen falschen „kein-FP-mehr"-Stand
zementiert hätten.

---

## Belegte Evidenz (frei, kein Gemini, kein Geld — echter gefixter Code-Pfad)

Alle Proben über `EdgarClientImpl.has_going_concern` (post-Fix, `ciks=`) gegen echtes EFTS.
Skripte: `scripts/verify_two_sided_freeprobe.py`, `scripts/inspect_going_concern_hits.py`,
`scripts/probe_distressed_going_concern.py` (working-tree, untracked).

### E6 — Healthy-Seite ist NICHT sauber (gefixter Pfad)

```
MSFT  cik=789019   has_going_concern=False   ✓ überlebt
AAPL  cik=320193   has_going_concern=False   ✓ überlebt
KO    cik=21344    has_going_concern=False   ✓ überlebt
PG    cik=80424    has_going_concern=False   ✓ überlebt
V     cik=1403161  has_going_concern=False   ✓ überlebt
JNJ   cik=200406   has_going_concern=True    ✗ FALSE-POSITIVE → würde gedroppt
```

Der katastrophale „alle True" ist weg; **JNJ** bleibt ein lebendes Gegenbeispiel zu
„kein FP mehr".

### E7 — Defekt A belegt: `startdt` wird NICHT durchgesetzt (Datumsfenster tot)

CIK-gescopeter Query mit `startdt=2024-06-12`, aber Treffer aus 2001–2017:

```
JNJ  CIK 200406  total={'value':8, 'relation':'eq'}   ← alle 8 Treffer 2014–2017 (10-Q/10-K), KEIN In-Window-Treffer
AWI  CIK 7431    total={'value':38,'relation':'eq'}   ← EX-23/EX-15-Exhibits 2001–2006 (Asbest-Ära), gesund heute
```

**Smoking Gun (AWI):** Ein Filing von 2001 könnte niemals matchen, wenn `startdt=today−720d`
als API-Filter wirkte. Dass es matcht → `startdt` wird **gesendet, aber nicht gescoped** —
**dieselbe Klasse wie der `entity=`-Bug** (Parameter da, scoped nicht). Der `value` (8/38)
ist der **All-Time**-Phrasenbestand der CIK, nicht das 24-Monats-Fenster. Der `ciks=`-Filter
wirkt (alle Treffer = richtige CIK), `startdt=` wirkt nicht.

### E8 — Defekt B: hypothetisch, NICHT belegt

Beide beobachteten False-Positives (JNJ, AWI) sind **reiner Defekt A** (null In-Window-Treffer
mit GC-Sprache). Ein In-Window-Treffer von „raise substantial doubt" **ohne** Going-Concern-
Bedeutung (z. B. reiner Prozesskontext) wurde **bisher nicht beobachtet**. Defekt B bleibt ein
plausibles latentes Risiko, ist aber **noch nicht evidenzbasiert** → Schritt-1-Diagnose muss B
erst nachweisen, bevor B-Code entsteht. (Vermeidet „am dominanten Defekt vorbeifixen".)

### E9 — FRQN: saubere Positiv-Kontroll-Fixture (beweistauglich, defektunabhängig)

```
FRQN  CIK 1624517  Ticker auflösbar (get_cik('FRQN')→1624517)
      total={'value':28,'relation':'eq'}  inkl. In-Window-10-Q 2024-11/2025-01/05/08/11
      has_going_concern=True
      jüngstes 10-Q accession=0001829126-25-009309  filing_date=2025-11-19
      enthält wörtlich (gekoppelt):
      „…conditions and events … that raise substantial doubt and the company's ability to
        continue as a going concern within one year after the date that the financial
        statements…"
```

FRQN (Frequency Holdings / vormals Yuenglings Ice Cream / Aureus) trägt **echte In-Window-
Going-Concern-Sprache** → `True` ist **korrekt** und hält **unabhängig** von Defekt A/B. Damit
ist FRQN die Positiv-Kontroll-Fixture zur Verifikation jedes Going-Concern-Fixes: nach dem Fix
muss FRQN weiterhin `True` liefern, JNJ/AWI auf `False` kippen.

---

## Warum der ausgelieferte Fix das nicht fing

- Report-E1 probte den gefixten `ciks=`-Pfad **nur gegen MSFT** (→ 0). E2 zeigte
  MSFT/AAPL/JNJ/KO=True, aber **unter dem alten `entity=`-Bug**. **Kein** freier Probe-Lauf
  fuhr den gefixten Pfad je gegen JNJ — die Annahme „Fix → alle vier False" war für JNJ nie
  verifiziert und ist falsch.
- Unit-Tests **mocken** EFTS (DI) → die zweite stille Scoping-Lücke (`startdt`) wird nie gegen
  echtes EFTS exekutiert. **Test-Gap:** kein Test pinnt „`has_going_concern` für einen gesunden
  Large-Cap mit *alter* GC-Sprache muss False sein" und keiner prüft, dass `startdt` real
  filtert.
- **Lehre:** Wird **ein** Scoping-Parameter still ignoriert gefunden, **alle** Scoping-Parameter
  desselben Endpoints by-Byte gegen echte API auditieren — hier saß `startdt` in derselben
  Klasse direkt dahinter. Und: den Fix gegen einen **Korb** (MSFT/AAPL/JNJ/KO/PG/V), nicht eine
  **Einzelprobe** verifizieren — die Einzelprobe (MSFT) verdeckte JNJ.

---

## Fix-Ticket (eigene Sub-Phase — erst Diagnose, dann Code; A NICHT präjudizieren)

**⚠️ Framing-Disziplin: NICHT vorwegnehmen, dass „Defekt A fixen" JNJ klärt.** AWI (2001–06) ist
nahezu beweisend für A (ein Filing von 2001 kann nur matchen, wenn `startdt` faktisch nicht
scoped). JNJ über Talk-Litigation ist die zweideutige Achse: **altes** Filing → A klärt es;
**aktuelles** Filing mit „raise substantial doubt" im reinen Prozesskontext → **Defekt B**, dann
hilft das Datumsfenster JNJ **gar nicht**. Die FERTIG-Bedingung „JNJ→False" braucht je nach Befund
**A oder A+B** — das nicht präjudizieren.

**Schritt 0 — DIE ERSTE Diagnose-Frage (frei, kein Code):** Die `file_date` von **JNJs treffendem
Hit** lesen — **in-window oder out-of-window?** E7 hat das bereits getan: alle 8 JNJ-Treffer
2014–2017 = out-of-window → liest **aktuell** als reiner A. Das ist zu **verifizieren, nicht
anzunehmen**: nach dem A-Fix JNJ **re-proben** und auf `False` pinnen. Findet die Sub-Phase JNJ
nach dem A-Fix immer noch `True`, ist B im Spiel und ein A-only-Fix wäre an JNJ vorbeigefixt.

**Schritt 1 — Diagnose-Korb (frei, kein Code):** Über einen Korb gesunder US-Large-Caps den
gefixten Pfad fahren; jeden `True` nach **In-Window vs. Out-of-Window**-Treffern bucketen
(`file_date` gegenlesen). Ergebnis bestimmt die Fix-Achse:
- ausschließlich Out-of-Window-Treffer → **Defekt A** klärt den Namen (Datumsfenster).
- In-Window-Treffer ohne GC-Bedeutung → **Defekt B** (Phrasen-Kopplung) zusätzlich nötig.
- Bisheriger Stand (E7/E8): **nur A belegt; B hypothetisch, nicht beobachtet.**

**Schritt 2 — Fix A (Datumsfenster durchsetzen):** Da EFTS `startdt` still ignoriert, das
Fenster **client-seitig** erzwingen — Hits nach `_source.file_date >= startdt` filtern und nur
diese zählen (die Hits tragen `file_date`), statt auf `hits.total.value` zu vertrauen. Alternativ
korrektes EFTS-Scoping recherchieren (ggf. `enddt` Pflicht?). Re-Probe: AWI → `False`;
**JNJ → `False` (zu verifizieren, s. Schritt 0)**; FRQN → weiterhin `True`.

**Schritt 3 — Fix B (NUR falls Schritt 0/1 einen In-Window-Nicht-GC-Treffer belegt):** Query/Phrase
auf die **gekoppelte** Form verschärfen — „substantial doubt about its ability to continue as a
going concern" statt blankem „raise substantial doubt". Ohne belegten B-Treffer **kein** B-Code
(vermeidet Fix am nicht-existenten Defekt).

**FERTIG-Bedingung der Sub-Phase:** JNJ **und** AWI → `False` (durch A, oder A+B falls Schritt 0/1
B belegt), **und** FRQN → `True` (Positiv-Kontrolle, defektunabhängig). Erst dann ist die
Healthy-Seite sauber.

**Verifikation:** TDD (Unit + ein `@pytest.mark.integration` gegen echtes EFTS: gesunder
Large-Cap mit alter GC-Sprache → False; FRQN → True). Danach **einmal am Ende**
Cache-Invalidierung + reduzierter bezahlter Lauf (Korb + FRQN).

---

## Haltezustand (Option 3 — bewusst gewählt)

- **Deploy bleibt.** Strikt besser als Alt-Code (droppte **alle** US; jetzt nur die JNJ-Klasse).
  **Nicht** zurückrollen — das wäre schlechter.
- **Cache NICHT invalidiert.** Beim JNJ-Fix wird neu deployt und **einmal am Ende** invalidiert;
  jetzt purgen wäre verschenkt.
- **Cloud Scheduler:** nächster regulärer Lauf **2026-07-01** (monatlich, 1.). Kein imminenter
  Feuerzeitpunkt im kurzen Aufschub-Fenster. Pausieren nur nötig, falls der Aufschub bis Juli
  reicht und keine wissentlich degradierten Dossiers gewünscht sind — saubere, reversible,
  user-seitige `gcloud`-Halteaktion (kein Code, kein Geld, kein Delete). „Degradiert ≠
  irreversibel": ein späterer korrekter Lauf heilt es.

---

## Out of Scope (weiterhin eigene Tickets)

- ~~Lauf-Level-Aggregat für `edgar_skipped` nach Ursache (DataSourceError vs. no-CIK).~~ **✅ ERLEDIGT
  2026-06-02 (PR #14, Merge `7cc9a6e`, LIVE).** `ScreenerRecord.edgar_skipped_reason` trennt
  `no_cik` vs `data_source_error`; `app/screener/filter_report.py::build_filter_report` emittiert
  Count + Ticker-Liste je Ursache.
- `2026-06-Changes.md` / Cloud-Run-„Erster Run"-Nebenbefund.

---

## Präventive Sichtbarkeit ausgeliefert 2026-06-02 (PR #14) — Boilerplate-Residuum bleibt evidenz-getriggert

Vor dem manuellen vollen Lauf wurden zwei stille Failure-Modi **präventiv** adressiert (PR #14,
Merge `7cc9a6e`, Revision `fisherscreen-service-00079-d4x`, Traffic 100 %), **ohne** die hier
beschriebene Detection-Verschärfung vorzuziehen:

- **EDGAR-Throttle** (`RateLimiter`, default 8 req/s, konfigurierbar) verhindert Rate-Limit-bedingte
  stille Skips beim Voll-Universum.
- **Going-Concern-Drop-Liste** (`going_concern_hit()` + `build_filter_report`) emittiert pro
  verworfenem Namen `ticker / cik / accession / file_type / file_date` — **das ist das
  Evidenz-Instrument** für das hier offene Boilerplate-Residuum (Primär-Dok-Boilerplate /
  GC-nur-im-Exhibit / `10-K/A`-Amendments). `has_going_concern` + Cache blieben unangetastet.
- **Dry-Mode** (`POST /run/monthly?dry_run=true`, $0, kein Gemini) macht die Drop-Liste **vor** dem
  bezahlten Lauf gratis sichtbar.

**Aktivierungsbedingung der Verschärfung unverändert:** erst wenn die Drop-Liste im bezahlten Lauf
einen echten **gesunden-Namen**-Form-Filter-überlebenden FP zeigt, wird die Boilerplate-Verschärfung
als eigene Sub-Phase an echter Evidenz aufgesetzt — **nicht** jetzt spekulativ.

---

## Fix-Session 2026-06-02 (TDD, NICHT gepusht) — Diagnose-Korrektur + Code

> Schritt-1-Diagnose (freie, read-only EFTS-Korb-Probe, kein Gemini, kein Geld) vor jedem
> Code; STOP-Gate; Stephans Go für Achse = Primary-Form-Filter. Skripte (working-tree,
> untracked): `scripts/diagnose_going_concern_residual.py`,
> `scripts/diagnose_gc_inwindow_nail.py`, `scripts/verify_residual_fix_freeprobe.py`.

### Schritt-1-Befund — korrigiert zwei Ticket-Annahmen

**(1) Voller FP-Korb (50 US-Large-Caps, sektorbreit) = `{JNJ, JPM, HON, AWI}`** — **zwei mehr**
als das Ticket kannte (JPM, HON). Die Korb-Probe war damit berechtigt (Lehre 4: Einzelprobe
hätte JPM/HON verdeckt). Übrige 46 → korrekt `False`.

**(2) Klassifikation (file_date UND Kontext gelesen, alle Treffer paginiert):**

| Name | total | In-Window | Befund |
|---|---|---|---|
| JNJ | 8 | 0 | alle 2014–2017 (10-K/10-Q/EX-13) → **reiner Defekt A** |
| JPM | 1 | 0 | 2008 (10-Q) → **reiner Defekt A** |
| HON | 1 | 0 | 2020-07 (10-Q) → **reiner Defekt A** |
| AWI | 38 | **2** | 36 out-of-window + **2 IN-WINDOW** `EX-99.1`-Exhibits zu 10-K → **A + B** |

- **JNJ disambiguiert (nicht präjudiziert):** alle 8 Treffer out-of-window → **reiner A**; der
  A-Fix bringt JNJ→False (live re-geprobt: bestätigt).
- **AWI ist NICHT reiner A — korrigiert Ticket-TL;DR/E7/E8.** AWIs 2 In-Window-Treffer (2026-02-24,
  2025-02-25) sind echte 10-K-Exhibits im Fenster. Ihr matchender Text ist **PCAOB-Auditor-
  Verantwortungs-Boilerplate** („management **is required to evaluate whether there are** conditions
  or events … that raise substantial doubt about the company's ability to continue as a going
  concern …"), **keine** GC-Feststellung. → A-Fix **allein** lässt AWI True.
- **Defekt B existiert — aber anders als im Ticket hypothetisiert.** Ticket-B = „In-Window-Phrase
  ohne GC-Kopplung (Litigation)" → im gesamten Korb **NICHT** beobachtet. Der **reale** Rest-Defekt
  ist **coupled boilerplate im Exhibit**. Damit ist der **Ticket-Fix-B (Phrase auf gekoppelte Form
  verschärfen) widerlegt** — das Boilerplate enthält die gekoppelte Phrase wörtlich.

**(3) Defekt A byte-identisch belegt** (gleiche Methode wie der `entity=`-Bug): AWI `&ciks=…`
**mit** `startdt=2024-06-12` vs. **ohne** → `total={'value':38,'relation':'eq'}` und identische
38er-Hit-Menge in beiden → `startdt` gesendet, aber **nicht** gescoped.

**(4) Param-Klassen-Audit komplett (Lehre 4):** `forms=10-K,10-Q` **wirkt** (AWIs EX-99.1 haben
`form=10-K` → Exhibits echter 10-K-Submissions; nur 10-K/10-Q + deren Exhibits tauchen auf),
`ciks=` **wirkt**. **Nur `startdt` ist tot.** Kein weiterer toter Param.

**(5) FRQN Positiv-Kontrolle:** 7 In-Window-Treffer, alle **primär** 10-K/10-Q, deklarative GC
(„these factors **raise substantial doubt about the company's ability to continue as a going
concern**. … dependent upon its ability to generate sufficient cash flows…") → True (korrekt).

### Schritt-2-Fix (`app/services/edgar_client.py::has_going_concern`)

Prädikat: **`True ⟺ ∃ Treffer mit (file_date ≥ startdt) UND (file_type ∈ {10-K, 10-Q})`** —
**beide Achsen nötig, keine allein reicht** (nur Fenster → AWI bleibt True via EX-99.1; nur Form →
JNJ bleibt True via alte primäre Treffer).

- **Achse A (Defekt A):** Da EFTS `startdt` ignoriert, das Fenster **client-seitig** pro Treffer auf
  `_source.file_date >= startdt` erzwingen — statt `hits.total.value` zu vertrauen.
- **Achse B (Defekt B, Option 1 = Primary-Form-Filter):** nur Treffer in **Primär-Form-Dokumenten**
  zählen (`_source.file_type ∈ {10-K, 10-Q}`); Exhibits (`EX-*`) ausschließen. Deterministisch, **kein
  Extra-Fetch** (`file_type` steckt in der EFTS-Antwort). Option 2 (Content-Discriminator) bewusst
  **nicht** gebaut — verteidigt gegen einen im Korb **nicht beobachteten** Modus (Primär-Dok-Boilerplate)
  und der Prosa-Textmatch zerfasert in freier Wildbahn → als Residual geticketet, nicht spekulativ gefixt.
- `has_going_concern` liest jetzt die **hits-Liste** und paginiert via `&from`; Over-broad-Sentinel
  (`relation=="gte"` / `value>=10000`) bleibt als Regressions-Gürtel **unverändert**, EFTS-500-Retry
  unberührt.

**Tests (TDD, erst rot):** +3 (`false_when_all_hits_out_of_window` = JNJ/A,
`false_for_in_window_exhibit_boilerplate` = AWI/B-mixed [pinnt, dass **beide** Achsen nötig sind],
`true_for_in_window_primary_form_hit` = FRQN-Positiv-Kontrolle); 2 bestehende total-only-True-Tests auf
den neuen Kontrakt (qualifizierender In-Window-Primary-Treffer) umgestellt. **658 Tests grün / 97.20 %.**

**Verifikation dreiseitig — Unit (gemockt) UND live EFTS** (`verify_residual_fix_freeprobe.py`, frei):
`JNJ/AWI/JPM/HON/MSFT → False`, `FRQN → True`. Die `&from`-Paginierung greift real (AWIs 38-Treffer/
4 Seiten → 0 qualifizierend → False).

### Honest-Label — bekanntes, überwachtes Residuum (NEUES eigenes Ticket, NICHT gefixt)

- **Primär-Dok-Boilerplate:** ein gesunder Filer mit derselben Auditor-/ASC-205-40-Verantwortungs-
  Sprache **im Primär-10-K** (statt Exhibit) würde den Form-Filter überleben → FP. Im 50er-Korb
  **nicht** aufgetreten. **Aktivierungsbedingung des Tickets = der spätere bezahlte Lauf:** taucht dort
  ein Form-Filter-überlebender neuer FP auf, ist es per Definition dieser Fall → dann an echter Evidenz
  entscheiden (Section-Scope vs. Content-Check vs. weichere Behandlung), nicht jetzt spekulieren.
- **Recall-Trade-off:** eine echte GC, die **nur** in einem Exhibit (z. B. EX-13 incorporated financials)
  steht — nie im Primär-Dok — würde verfehlt. Klein, weil GC-Feststellungen nach ASC 205-40 in den
  Financial-Statements/MD&A des Primär-Dokuments leben (FRQN bestätigt). Akzeptiert.
- **Form-Amendments** (`10-K/A`, `10-Q/A`) zählen mit der exakten `{10-K,10-Q}`-Menge **nicht** —
  Teil desselben Residuums (im Korb nicht beobachtet).

### Gate-Sequenz ABGESCHLOSSEN 2026-06-02 — Incident gelöst

Alle fünf Gates durchlaufen, zweiseitig belegt:

1. ✅ **Push** `chore/going-concern-residual-ticket` (`ef3fb7a`).
2. ✅ **Deploy** — PR #9 nach `main` gemergt (Merge-Commit `69a1b87`), GHA-Deploy-Run
   `26813328891` = `success`, Image `app:69a1b87…` live (100 % Traffic). (PR #8 hatte zuvor nur
   die Ticket-Doc-Commits gebracht; der eigentliche Fix kam über PR #9.)
3. ✅ **Freie Vorprobe** — JNJ/AWI/JPM/HON/MSFT→False, FRQN→True auf dem gefixten, deployten
   Commit (`verify_residual_fix_freeprobe.py`, live EFTS).
4. ✅ **Cache-Invalidate** — `invalidate_edgar_going_concern_cache.py --apply`: **777** vergiftete
   `dev_edgar_cache`-Docs (`has_going_concern==True`, die US-mit-CIK-Teilmenge) gelöscht; Re-Probe
   bestätigt **0** verbleibend. Größenordnung gegengelesen (plausibel = ~alle US-CIKs, die der
   `entity=`-Bug auf True cachte; inkl. JNJ/JPM/HON/MSFT/AAPL/KO).
5. ✅ **Reduzierter bezahlter Lauf** (`reduced_paid_run_going_concern.py`, Korb 9, Flash Lite,
   output→`output-test/`, kein Push): `success`, **$0.00026** (997/397 Tokens, ≪ Hard-Caps).
   **Zweiseitig:** 7/7 healthy US erreichen Gemini-Scoring inkl. **JNJ + HON** (beide vorher
   gedroppt); **FRQN** Positiv-Kontrolle `has_going_concern=True`. (FRQN fällt im Pipeline-Basis-
   Filter als Micro-Cap vor EDGAR — Positiv-Kontrolle daher als direkter freier EDGAR-Call belegt.)

**FERTIG-Bedingung „Healthy-Seite sauber (kein FP mehr) + Positiv-Kontrolle hält" erfüllt.** Der
nächste reguläre Scheduler-Lauf (2026-07-01) läuft gegen gefixten Code + sauberen Cache → US-Titel
erscheinen wieder im Universum-Output. Honest-label-Residuum (Primär-Dok-Boilerplate etc.) bleibt
als eigenes, überwachtes Ticket — Aktivierung war/ist der bezahlte Lauf; im 9er-Korb **kein**
Form-Filter-überlebender FP aufgetreten.
