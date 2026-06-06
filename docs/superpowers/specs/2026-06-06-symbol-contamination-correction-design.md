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
fasst sie **nicht** an). Die übrigen **24** sind maskierte `GATE_VOLUME`-BENIGN-Kontaminanten
über **mehrere** Suffixe:

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

1. **Enumerieren:** über **alle suffixierten (nicht-US) Symbole** aus `data/universe.json`
   (US-S&P-Ticker durchlaufen keine Index→Suffix-Mappung → sauber) yfinance `.info` proben.
2. **Klassifizieren (Probe ist der Schiedsrichter, mit Robustheit — Punkt 3):**
   - `quoteType != "EQUITY"` (z. B. MUTUALFUND) → **bestätigter Kontaminant**.
   - `.info` leer/transient (yfinance-Schluckauf) → **INCONCLUSIVE**: Retry mit Backoff
     (Wiederverwendung des `RateLimiter`/Backoff-Musters); bleibt es leer → **manuell**
     markieren, **nicht** automatisch als Kontaminant in die Map backen.
   - EQUITY mit `marketCap` → sauber (kein Kontaminant; ein EQUITY mit echt fehlendem
     Volumen ist Punkt 1, nicht 0a).
3. **Kandidat bestimmen — kuratiert/autoritativ, NICHT geraten (Punkt 2):** Das korrekte
   Yahoo-Symbol kommt aus einer autoritativen Quelle — ISIN→Ticker via OpenFIGI (die
   Index-/iShares-Holdings tragen ISINs) **oder** von Stephan kuratiert. Die Probe
   **verifiziert** den Kandidaten nur: löst als `EQUITY` auf **und** `longName`/`shortName`
   passt zur erwarteten Firma. Kein algorithmisches Raten aus dem Firmennamen.
4. **Output:** verifizierte Tabelle `{kontaminiert → korrekt | DROP}` (DROP für echte
   Leichen ohne handelbares Äquivalent) + die INCONCLUSIVE-Liste → **Stephan zur Abnahme,
   bevor irgendetwas hartkodiert wird.** Begründung: die read-only-Voruntersuchung lag
   mehrfach daneben (DANO=Danone ≠ Danaher; AIRP=Air Liquide ≠ Airbus; SGOB=Saint-Gobain
   ≠ SocGen) — die Probe + Stephans Abnahme sind der Schiedsrichter.

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

Aus der verifizierten Schritt-1-Tabelle ergibt sich der **erwartete Delta** vor dem Lauf:

- **Universum-Count:** `1332 → 1332 − N`, mit `N = #Twin-Kollaps (remap auf bereits
  vorhandenes Symbol) + #DROP`. Der konkrete Wert von N steht **nach Schritt 1 fest** und
  wird im Plan/Acceptance als exakte Zahl notiert (nicht „sinkt um die Dubletten").
- **REVIEW-Count-Prognose:** Die maskierten Kontaminanten verschwinden aus
  `GATE_VOLUME`-BENIGN; ein Teil der rehabilitierten Titel landet **legitim** in REVIEW
  (großer Titel, echte Daten, scheitert an Volumen/rev_growth) — kein Bug, korrektes Signal.
  Die ungefähre Vorher/Nachher-REVIEW-Verschiebung wird **nach Schritt 1 vorhergesagt** und
  am Lauf gegengeprüft (macht es zu einem echten Gate).
- **Keine** `.PA`/sonstigen Leer-`market_cap`-Drops mehr (außer den 5 DEGRADED_DICT und
  `SKY.L`-Klasse-Leichen, falls noch im Universum — die sind separater Cleanup).
- **Reconciliation (Erhaltungssatz) hält** weiterhin: `|Universum| == Σ Drops + übrig`.

---

## Nachgelagert (im Plan als letzte Schritte, nicht 0a-Kern)

- **CLAUDE.md-Universum-Count:** Der `~2.100`-Wert ist veraltet (Live = 1332). **Nach** dem
  0a-Dedup den echten Post-0a-Count ermitteln und die Angabe in CLAUDE.md aktualisieren
  (der dortige TODO-Kommentar verlangt genau das).
- **Composition-Doku-Abweichung (NUR notieren, nicht fixen):** CLAUDE.md sagt
  „S&P 500 + Russell 1000", `build_universe` nutzt real **S&P 500 + S&P 400** + STOXX 600.
  Separater Doku-Cleanup, außerhalb 0a.

## Abhängigkeit zu 0b

0a beseitigt die *heute bekannten* Kontaminanten. **0b** (eigener Spec) macht die Resolution
robust: ein partielles/leeres Info-Dict (kein market_cap UND kein avg_volume) wird als
Resolution-Ausfall (REVIEW, eigener `reason_code`) klassifiziert statt ans Gate zu leaken —
das fängt jede *künftige* Kontamination, die 0a's statische Map nicht kennt. Reihenfolge
laut Ticket: 0a → 0b → 1.
