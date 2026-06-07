# Symbol-Kontaminations-Korrektur (Ticket Punkt 0a) — Design

> Status: Spec, vor Implementierung. Branch `feature/gate-universe-fixes`.
> Datum: 2026-06-06. Folge-Ticket zur Funnel-Instrumentierung; Auslöser Gate-A-Cold-Dry-Run.

## Ziel

Index-Quellen liefern für manche Titel **Reuters-RIC-Mnemonics statt Yahoo-Symbole**
(z. B. `BNPP.PA` statt `BNP.PA`). Diese lösen in yfinance als `quoteType=MUTUALFUND`
mit `shortName` aber **ohne** `marketCap`/`averageVolume` auf → sie sind **keine**
DEGRADED_DICT (haben einen Namen), leaken bis ans Volumen-Gate, scheitern dort am
fehlenden Volumen und werden vom None-Guard auf **BENIGN** gesetzt → unsichtbar in den
Review-Flags. `build_universe` so korrigieren, dass kontaminierte Symbole auf ihr
verifiziertes Yahoo-Äquivalent gemappt (oder als echte Leiche gedroppt) und dedupliziert
werden — die rehabilitierten Titel laufen dann auf **echten** Daten durch die Gates.

## Befund (Evidenz, nicht Annahme)

Gate-A-Cold-Dry-Run (`output/Universum/2026-06-dropouts.csv`): **29 Leer-`market_cap`-Drops**.
5 = bekannte DEGRADED_DICT/UNCLEAR (AMS.VI, RIGN.SW, ROL.L, SANO.HE, SCHA.OL — Punkt 0a
fasst sie **nicht** an). Die übrigen **24** maskierten `GATE_VOLUME`-BENIGN-Drops =
**23 Kontaminanten + 1 echte Leiche (SKY.L)** über **mehrere** Suffixe:

| Suffix | Symbole (Leer-market_cap, GATE_VOLUME-BENIGN) |
|---|---|
| `.PA` (18) | AIRP, ATOS, BNPP, BOUY, CAGR, CAPP, CARR, DANO, MICP, OREP, PERP, RENA, RNL, SASY, SCHN, SGEF, SGOB, SOGN |
| `.DE` | CTS |
| `.AS` | ENX |
| `.L` | FTI, LII (+ **SKY = echte Leiche, 2018 delisted → OUT OF SCOPE**) |
| `.IR` | GLB |

→ **„FR-only" ist durch die Daten widerlegt.** Der Scope ist **all-suffix**, bestimmt durch
die Probe (Schritt 1), nicht vorab festgenagelt.

## Nicht-Ziel / Disziplin

- 0a ist ein **Symptom-Patch** auf der Datenebene: es korrigiert die *bekannten*
  kontaminierten Symbole. Es ist **kein** Schutz gegen *künftige* Re-Kontamination
  (neue Index-Mitglieder mit RIC-Symbolen) — das ist **Punkt 0b** (Resolution
  klassifiziert partielle/leere Dicts als REVIEW statt BENIGN). **0a ohne 0b heißt:
  der nächste neue RIC fällt wieder still in BENIGN.** Diese Abhängigkeit ist explizit.
- **Keine** RIC-Heuristik im Produktiv-Code — nur eine **explizite, verifizierte Map**.
  Eine falsche Remap (stilles Screenen der *falschen* Firma) wäre schlimmer als ein Drop.
- Eigener Branch, kein Push/Merge ohne Go, Acceptance am Funnel-Cold-Dry-Run.

---

## Schritt 1 — Live-Enumeration + Verifikation (Diagnose, Netz, $0, eigenes Gate)

Skript `scripts/diagnose_symbol_contaminants.py` (Diagnose-Probe, kein Produktiv-Code):

1. **Enumerieren:** über das **ganze Universum inkl. US** aus `data/universe.json` yfinance
   `.info` proben. US vorab rauszuscopen würde den FR-only-Fehler eine Ebene tiefer
   wiederholen („US ist sauber" = unverifizierte Annahme). Die Probe ist $0 → den
   US-sauber-Befund **bestätigen** statt annehmen (billige Versicherung).
2. **Klassifizieren (Probe ist der Schiedsrichter, mit Robustheit — Punkt 3):**
   - `quoteType != "EQUITY"` (z. B. MUTUALFUND) → **bestätigter Kontaminant**.
   - `.info` leer/transient (yfinance-Schluckauf) → **INCONCLUSIVE**: Retry mit Backoff
     (Wiederverwendung des `RateLimiter`/Backoff-Musters); bleibt es leer → **manuell**
     markieren, **nicht** automatisch als Kontaminant in die Map backen.
   - EQUITY mit `marketCap` → sauber (kein Kontaminant; ein EQUITY mit echt fehlendem
     Volumen ist Punkt 1, nicht 0a).
3. **Kandidat bestimmen — ISIN-verankert (Punkt 2, verbindlich):** Der **Anker ist die
   ISIN**, nicht der Ticker-String — die ISIN (aus den iShares-/Index-Holdings) ist der
   autoritative Schlüssel, auf den der Build eigentlich hätte joinen sollen. Vorgehen für
   die ~23 Kontaminanten: ISIN des Kontaminanten in den Holdings nachschlagen → Yahoo-Symbol
   mit **derselben ISIN** → Probe bestätigt **ISIN-Gleichheit**. „Kuriert" heißt
   ISIN-nachgeschlagen, **nicht** „tippen, was man für das Symbol hält" (das wäre wieder
   Raten wie DANO=Danaher).
   - **Verifikations-Anker = ISIN-Gleichheit**, nicht Name. Wo yfinance die ISIN im `.info`
     ausgibt, ist ISIN-Match der Schiedsrichter; `longName`/`shortName`-Match ist nur
     **Fallback** (fuzzy: „Air Liquide" vs. „L'Air Liquide S.A.").
   - **Werkzeug offen, Anker fest:** OpenFIGI ist für 0a **nicht** verbindlich (neue
     Abhängigkeit + Mehrfach-Listing-Ambiguität + Symbol-Konstruktion bleibt; für einen
     23-Posten-Einmal-Fix nicht gerechtfertigt). ISIN-Keying an der **Wurzel**
     (`build_universe` joint künftig auf ISIN statt Ticker) ist der eigentliche
     Root-Cause-Fix — **separat und größer, nicht 0a**.
4. **Output:** verifizierte Tabelle `{kontaminiert → korrekt | DROP}` (DROP für echte
   Leichen ohne handelbares Äquivalent) + die INCONCLUSIVE-Liste → **Stephan zur Abnahme,
   bevor irgendetwas hartkodiert wird.** Begründung: die read-only-Voruntersuchung lag
   mehrfach daneben (DANO=Danone ≠ Danaher; AIRP=Air Liquide ≠ Airbus; SGOB=Saint-Gobain
   ≠ SocGen) — Probe + ISIN-Match + Stephans Abnahme sind der Schiedsrichter.

### Schritt-1 → Schritt-2-Gate (blockierend)

Übergang zu Schritt 2 **nur bei null ungelösten INCONCLUSIVEs**. Jedes Symbol ist am Ende
von Schritt 1 entweder **korrigiert**, **gedroppt** oder **bewusst aufgeschoben und
namentlich gelistet** (z. B. yfinance dauerhaft flakig). Ein nicht aufgelöstes INCONCLUSIVE
bleibt unverändert im Universum → produziert weiter einen Leer-`market_cap`-Drop → würde die
Acceptance „keine Leer-`market_cap`-Drops mehr" verletzen. Daher: die Acceptance-Formel nimmt
die **namentlich gelisteten Aufgeschobenen** explizit aus (s. Acceptance).

> Service-Layer-Regel (CLAUDE.md): Die Probe nutzt den `yfinance_client`-Wrapper, **oder**
> ist explizit als Diagnose-Probe ausgenommen (wie `scripts/trigger_cold_dry_run.py`).
> Festlegung: Wrapper verwenden (`get_ticker_info`), damit dieselbe Resolutions-Semantik
> wie im Produktivlauf gilt.

---

## Schritt 2 — `build_universe`-Code (TDD, offline)

- Modul-Konstanten in `scripts/build_universe.py`:
  - `SYMBOL_CORRECTIONS: dict[str, str]` — kontaminiert → korrekt (aus Schritt-1-Tabelle).
  - `SYMBOL_DROP: set[str]` — echte Leichen (z. B. `SKY.L`).
- Reine Funktion `_apply_symbol_corrections(tickers: list[str]) -> list[str]`, in `main()`
  auf die **kombinierte** Liste **vor** `sorted(set(...))` angewandt:
  - kontaminiert → korrekt remappen (der `set()`-Dedup kollabiert den bereits vorhandenen
    Zwilling automatisch);
  - `SYMBOL_DROP`-Einträge entfernen;
  - jede Korrektur/Drop einzeln **loggen** + Gesamt-Count (Instrumentierungs-Sichtbarkeit).
- Generisch (eine Map, kein länderspezifischer Pfad); der **Inhalt** der Map ist all-suffix,
  rein aus Schritt 1.

### Daten / `universe.json`

Korrekturen sind **deterministische String-Ops** → die Acceptance braucht **kein**
Live-`build_universe` (das ist Gate C). `_apply_symbol_corrections` wird **einmal offline**
auf die aktuelle `data/universe.json` angewandt → korrigierte `universe.json` (reviewbarer
Diff, committet). Derselbe Code hält künftige Rebuilds sauber. **Gemeinsame Funktion für
beide Pfade** (offline-Regenerierung + Live-Build).

### Error-Handling / Edge-Fälle

- Kontaminant bereits abwesend → No-op; korrektes Symbol fehlt → `set()` fügt es hinzu.
- **Idempotenz:** zweimal anwenden == einmal anwenden.
- Korrektes Symbol ist selbst (versehentlich) ein Map-Key → durch Injektivitäts-Test
  ausgeschlossen (s. Tests).

---

## Tests (offline, TDD)

- `_apply_symbol_corrections`:
  - `["BNPP.PA","BNP.PA"]` → `["BNP.PA"]` (kein BNPP.PA, Dup kollabiert);
  - `SYMBOL_DROP`-Symbol entfernt;
  - unbeteiligte Symbole unberührt;
  - **idempotent** (zweifache Anwendung == einfache);
  - **Injektivität:** keine zwei verschiedenen Keys mappen auf dasselbe Ziel (außer es ist
    dieselbe Firma — dann ist einer der beiden überflüssig und gehört bereinigt);
  - Guard-Assertion: nach Anwendung kein `SYMBOL_CORRECTIONS`-Key mehr in der Ausgabe.
- Diagnose-Skript = Probe (nicht unit-getestet, wie `trigger_cold_dry_run`).

> **Guard-Grenze (Punkt 5):** Der offline-Guard fängt nur die **bekannten** Keys, **nicht**
> künftige Kontamination. Der generische Guard — „kein überlebendes Symbol löst non-EQUITY/
> leer auf" — braucht eine **Live-Probe** und gehört zu **0b / Gate C**, nicht zu 0a.

---

## Acceptance (Funnel, $0-Cold-Dry-Run, vorher/nachher) — als Zahl, nicht vage

Aus der verifizierten Schritt-1-Tabelle ergibt sich der **erwartete Delta** vor dem Lauf
(alle Zahlen werden im Plan **nach Schritt 1** als exakte Werte eingetragen, nicht vage):

- **Bookkeeping (sauber trennen):** Die 24 Nicht-DEGRADED-Leer-`market_cap`-Drops = **23
  Kontaminanten + 1 echte Leiche (SKY.L)**. SKY zählt als **DROP**, nicht als Kontaminant —
  sonst Doppelzählung in N.
- **Universum-Count:** `1332 → 1332 − N`, mit `N = #Twin-Kollaps (remap auf bereits
  vorhandenes Symbol) + #DROP`. (Reine Remaps auf ein noch *nicht* vorhandenes Symbol senken
  den Count nicht — sie ersetzen 1:1.)
- **Survivor-Count (die eigentliche Erfolgsmetrik):** `687 → 687 + M`. Der Witz der Übung
  ist, dass rehabilitierte Megacaps jetzt auf **echten** Daten durch die Gates laufen und
  einige bis Scoring durchkommen — `M > 0` belegt, dass echte Kandidaten **zurückgeholt**
  wurden, statt nur umetikettiert. M wird nach Schritt 1 prognostiziert und am Lauf geprüft.
- **REVIEW-Count-Prognose:** Die maskierten Kontaminanten verschwinden aus
  `GATE_VOLUME`-BENIGN; ein Teil der rehabilitierten Titel landet **legitim** in REVIEW
  (großer Titel, echte Daten, scheitert an Volumen/rev_growth) — kein Bug, korrektes Signal.
  Vorher/Nachher-REVIEW-Verschiebung wird nach Schritt 1 vorhergesagt und am Lauf geprüft.
- **Keine** Leer-`market_cap`-Drops mehr — **außer** den 5 DEGRADED_DICT, der `SKY.L`-Klasse
  und den **namentlich gelisteten aufgeschobenen INCONCLUSIVEs** (Schritt-1-Gate). Diese
  Ausnahmen sind explizit aufgezählt, nicht implizit.
- **Reconciliation (Erhaltungssatz) hält** weiterhin: `|Universum| == Σ Drops + übrig`.

---

## Nachgelagert (im Plan als letzte Schritte, nicht 0a-Kern)

- **CLAUDE.md-Universum-Count:** Der `~2.100`-Wert ist veraltet (Live = 1332). **Nach** dem
  0a-Dedup den echten Post-0a-Count ermitteln und die Angabe in CLAUDE.md aktualisieren
  (der dortige TODO-Kommentar verlangt genau das).
- **Composition-Doku-Abweichung (NUR notieren, nicht fixen):** CLAUDE.md sagt
  „S&P 500 + Russell 1000", `build_universe` nutzt real **S&P 500 + S&P 400** + STOXX 600.
  Separater Doku-Cleanup, außerhalb 0a.

## GATE-1-Ergebnis & Methoden-Korrektur (2026-06-07, live festgestellt)

Der in diesem Spec verankerte **ISIN-Anker erwies sich als nicht herstellbar** und wurde
verworfen — dokumentiert für die ehrliche Aufzeichnung:
- **iShares-Quelle tot** (beide Holdings-URLs 404) → kein autoritativer ISIN-Self-Join.
- **yfinance liefert keine ISIN für die Kontaminanten** (alle `-`) und **falsche ISINs für
  EU-Listings auf der Kandidaten-Seite** (Vinci→FI, LVMH→CA, Kering→JP) → ISIN-Gleichheit ist
  auf **beiden** Seiten als Verifikationsanker tot. OpenFIGy/-FIGI hilft nicht (braucht eine
  ISIN, die es nicht gibt).
- **Tatsächliche Methode (A′): Wikipedia-Company-Anker** — provenienz-nativ. RIC→Company aus
  der **Build-Revision** (Wikipedia STOXX_Europe_600 oldid 1349000963, Build-Datum 2026-05-16
  / commit 921a50b) deckt alle 22 RICs ab (inkl. der 8 aus dem aktuellen Snapshot gedrifteten).
  Verify pro Kandidat: `quoteType=EQUITY` + longName-Agreement (Legal-Suffixe gestrippt,
  Akzente normalisiert) + Börsenplatz-Plausibilität. Mehrfach-Listings/echte Mehrdeutige:
  **Drop statt Raten** (LII.L→DROP da `LII`=Lennox≠Liberty Global; SKY.L→DROP delistet).
- **Abgenommene Tabelle:** `docs/superpowers/audits/2026-06-06-0a-symbol-contaminants/correction_table.md`
  — 20 Remaps + 2 Drops, 0 INCONCLUSIVE. **N=10** (8 Twin-Kollaps + 2 Drop) → 1332→1322;
  12 Rehab-Adds; Survivor-Prognose 687→687+M.
- **Lehre:** Eine echte ISIN-gekeyte Quelle (build_universe joint auf ISIN statt Ticker) ist
  der Root-Cause-Fix → **Gate-C-Umbau**, nicht 0a.

## Abhängigkeit zu 0b

0a beseitigt die *heute bekannten* Kontaminanten. **0b** (eigener Spec) macht die Resolution
robust: ein partielles/leeres Info-Dict (kein market_cap UND kein avg_volume) wird als
Resolution-Ausfall (REVIEW, eigener `reason_code`) klassifiziert statt ans Gate zu leaken —
das fängt jede *künftige* Kontamination, die 0a's statische Map nicht kennt. Reihenfolge
laut Ticket: 0a → 0b → 1.
