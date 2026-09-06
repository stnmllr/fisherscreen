# Ticket: `find_home_identity` scheitert an 147 von 416 EU-Titeln (35 %) — fünf Normalisierungs-Defekte, keine echten Nichtübereinstimmungen

**Opened:** 2026-09-04
**Priority:** blockierend für die EU-Native-Entscheidung. Kein falscher Wert wird produziert — aber die Zahl, die über eine Architekturentscheidung entscheiden soll, ist unbrauchbar, solange ihr größter Einzelposten ein Bug ist.
**Status:** open — zu zwei Dritteln behoben (147 → 49), siehe „Update" unten.

## Update 2026-09-05: 147 → 49, und der Systemdefekt ist weg

Der Matcher-Umbau (PR #52, `97c0077` — „Rebuild the issuer-name normalisation, and refuse
to guess instead of loosening") ist gelaufen und mit dem Zähllauf gegengemessen
(`cache/eu_sec_source_census_v3.json`, 2026-09-04). `unverifiable_identity` fiel von
**147 auf 49** von 416.

**Die Diagnose oben trägt: der Kronzeuge ist umgeschlagen.** Das Ticket führt `.ST` mit
28/28 und `.MC` mit 21/21 als Beweis, dass hundert Prozent zweier Börsen kein
Namensrauschen sein können. Heute:

| Börse | vorher | nachher |
|---|---|---|
| `.ST` | 28 / 28 (100 %) | 4 / 28 (14 %) |
| `.MC` | 21 / 21 (100 %) | 5 / 21 (24 %) |

Der Rest von 49 verteilt sich auf **dreizehn Börsen mit 7–15 %** (Ausreißer `.MC` mit
24 %, und `.IR` mit 1/1, wo n=1 nichts aussagt). Kein Suffix steht mehr bei 100 %. Das
Muster, das den Systemdefekt belegte, ist verschwunden — was bleibt, sieht nach
Einzelfällen aus, nicht nach einer kaputten Regel.

Jeder im Ticket namentlich genannte Fall hat den Topf verlassen: `BP.L` → `resolved_20f`
(der direkte Beleg aus Ursache 5), `BYG.L` und `JD.L` → `not_sec_registrant`, ebenso
`JMT.LS` (Diakritika), `ALFA.ST` (`(publ)`), `STERV.HE` (`-B SHS`) und `FLOW.AS`
(Präfix/Punkt). `SWEC-B.ST` → `no_us_line`.

**Was der Umbau nicht gebracht hat, gehört mit ins Bild.** Von den 98 zurückgewonnenen
Titeln wurden nur **12** zu vollen Dossiers; **86** sind `not_sec_registrant`. Die Quote
„hat eine SEC-Quelle" stieg damit von 11,1 % auf 14,4 % — der eigentliche Gewinn ist
nicht die Quote, sondern dass die Zahl jetzt eine *Messung* ist und keine Untergrenze
mehr, hinter der ein Bug 35 % der Titel versteckte. Genau dafür war das Ticket
blockierend, und in dieser Hinsicht ist es erledigt: die EU-Native-Entscheidung konnte am
2026-09-04 auf belastbarer Grundlage fallen.

**Die Spannung wurde nicht aufgelöst, sondern respektiert.** Der Umbau lockert die strikte
Gleichheit *nicht* zu Präfix-Toleranz — er normalisiert beide Seiten besser und weist im
Zweifel zurück. Der Gegenproben-Korb (`ROCHE` vs. `ROCHE BOBOIS`) steht.

**Offen bleiben die 49.** Sie sind der Grund, warum dieses Ticket nicht geschlossen wird.
Ob darunter noch Regeln stecken oder nur Quellen, die schlicht den falschen Namen liefern
(wie `GLB.IR` → „Beacon Hill CBO III Ltd", inzwischen Override-Zeile), ist ungeprüft.

**Vor dem Schließen zu prüfen:** eine Stichprobe aus den 49 — mindestens 15 —, klassifiziert
nach „Normalisierungsregel fehlt" gegen „Quelle nennt eine andere Firma". Nur die erste
Gruppe ist Matcher-Schuld. Ist sie leer, ist dieses Ticket erledigt und der Rest gehört
zu `tickets/2026-06-03-isin-canonical-anchor-openfigi.md`.

## Kontext

Der Zähllauf über alle 416 dotted EU-Titel (`scripts/count_eu_sec_sources.py`,
2026-09-04) sollte beantworten, ob die EU-Native-Lücke schmerzt. Ergebnis:

```
not_sec_registrant     177   42,5 %
unverifiable_identity  147   35,3 %   <-- scheitert VOR der SEC-Frage
resolved_20f            45   10,8 %
no_annual_form          26    6,2 %
no_us_line              15    3,6 %
transient_error          5    1,2 %
resolved_10k             1    0,2 %
```

„11,1 % haben eine SEC-Quelle" ist damit eine **Untergrenze, keine Messung**: 147 Titel
haben die SEC-Frage nie erreicht.

Dass es sich um einen Defekt handelt und nicht um die Realität, zeigt die Verteilung
sofort: **`.ST` scheitert 28 von 28, `.MC` 21 von 21.** Hundert Prozent zweier Börsen
ist kein Namensrauschen einzelner Emittenten.

## Fünf Ursachen, alle klein und benennbar

Stichprobe von 40 der 147, plus gezielte Einzelsonden.

### 1. Strikte Gleichheit statt Präfix-Toleranz — 32,5 % der Stichprobe

`find_home_identity` (`app/deepdive/eu_adr_resolution.py:108-122`) vergleicht
`norm_issuer(issuer_name(name)) == ref_norm`. `_same_issuer` (`:125-132`) macht für
US-Linien genau dasselbe Problem **präfix-tolerant**. Die strengere Regel läuft
ausgerechnet auf dem Pfad, der über ein Drittel der Titel entscheidet.

Beispiele: `FLOWTRADERS` vs `FLOWTRADERS.` · `STORAENSO-RSHS` vs `STORAENSO` ·
`REDEIACORP` vs `REDEIACORPORACIÓN,`

### 2. Diakritika überleben die Normalisierung

`norm_issuer` faltet nur Groß-/Kleinschreibung und entfernt Leerzeichen. Portugiesische,
spanische, schwedische und französische Namen brechen daran:
`JERONIMOMARTINS` vs `JERÓNIMOMARTINS,SGPS,` (JMT.LS).

### 3. `_LEGAL_FORMS` ist unvollständig

Es fehlen mindestens das schwedische `(publ)` (`ALFALAVAL(PUBL)` vs `ALFALAVAL`) und die
portugiesische `SGPS`. Der Katalog wurde offenbar an DE/NL/CH-Fällen entwickelt.

### 4. `issuer_name` strippt Klassentoken nur ohne Leerzeichen

Der Docstring beschreibt `'ROCHE HOLDING AG-BR' -> 'ROCHE HOLDING AG'`. OpenFIGI
schreibt aber auch `CARL ZEISS MEDITEC AG - BR` **mit Leerzeichen um den Bindestrich**;
`rpartition("-")` liefert dann den Tail `" BR"`, und der Guard `" " not in tail`
verhindert das Strippen. Ebenso unbehandelt: `-B SHS`, `-R SHS` (SWEC-B.ST, HUSQ-B.ST,
STERV.HE).

### 5. Zwei Ursachen im Topf „gar kein OpenFIGI-Treffer" (17,5 % der Stichprobe)

- **Der `securityType2`-Hartfilter.** `OpenFIGIClientImpl.map_ticker`
  (`app/services/openfigi_client.py`) schreibt `"securityType2": "Common Stock"` fest.
  `BYG.L` (Big Yellow Group) wird ohne den Filter sofort gefunden — es ist ein **REIT**.
  Der Filter schließt REITs, Trusts und verwandte Formen systematisch aus.
- **Die LSE-Symbolform.** `BP.L` und `JD.L` liefern auch ohne Filter nichts:
  OpenFIGI/Bloomberg führen BP als `BP/ LN`, mit angehängtem Schrägstrich. Die
  Variantenleiter in `local_symbol_variants` kennt diese Form nicht.

  **BP ist ein zweifelsfreier 20-F-Filer.** Der Zähllauf hat ihn als „Identität nicht
  verifizierbar" gebucht — ein direkter Beleg dafür, wie stark die 11,1 % untertreiben.

## Die Spannung, die den Fix nicht trivial macht

Die strikte Gleichheit ist **kein Versehen**. Ihr Docstring nennt den Grund: sie ist die
NAME-SANITY-CHECK gegen den Variantenleiter-Falschtreffer `ROCHE` → `ROCHE BOBOIS`, und
`norm_issuer`s Docstring führt genau dieses Paar als Beispiel. Jede Lockerung öffnet
diesen Fehlerkanal wieder — und ein falsch aufgelöster Emittent ist **schlimmer** als ein
nicht aufgelöster: er produziert ein plausibles Dossier über die falsche Firma.

Ein reines „mach es toleranter" ist deshalb keine Lösung. Der Fix braucht ein
Akzeptanzkriterium, das beide Richtungen misst.

**Verschärfung, gemessen am 2026-09-04:** `find_home_identity` ist die **einzige** Wache.
Der naheliegende Gedanke, `_same_issuer` fange einen falsch aufgelösten Emittenten eine
Ebene tiefer noch ab, trägt nicht:

```
norm_issuer(issuer_name("ROCHE HOLDING AG"))        -> 'ROCHE'
norm_issuer(issuer_name("ROCHE BOBOIS SA-UNSPON ADR")) -> 'ROCHEBOBOIS-UNSPONADR'
_same_issuer(...)                                    -> True
```

`" HOLDING"` steht in `_LEGAL_FORMS`, also schrumpft die Referenz auf `ROCHE` — und
`ROCHE` ist ein Präfix von `ROCHEBOBOIS…`. Die präfix-tolerante Prüfung akzeptiert Bobois.
Wer also die strikte Gleichheit oben lockert, hat **keinen** Rückhalt weiter unten.

## Scope

- **Regeln einzeln bauen und einzeln messen.** Der Zähllauf ist das Instrument: nach
  jeder Regel neu laufen lassen und beobachten, wie viele der 147 zurückkommen und ob
  ein bekannt korrekter Fall kippt. `cache/eu_sec_source_census.json` hält den
  Ausgangszustand fest.
- **Gegenprobe verpflichtend.** Ein Testkorb aus Paaren, die *nicht* matchen dürfen —
  `ROCHE` vs `ROCHE BOBOIS` ist der dokumentierte Fall, weitere aus dem Universum
  konstruieren (gleicher Präfix, andere Firma). Ohne diesen Korb ist jede Lockerung
  unbelegt.
- **Den `securityType2`-Filter entscheiden**, nicht nur entfernen: welche
  `securityType2`-Werte sind für den Zweck (Heimatnotierung eines operativen
  Unternehmens) zulässig? REIT ja, Option und Warrant offensichtlich nein.
- **Danach den Zähllauf wiederholen** und erst dann über EU-Native entscheiden.

## Nicht in diesem Ticket

- Die EU-Native-Quellenschicht selbst. Sie ist der Grund für die Messung, nicht ihr Teil.
- `tickets/2026-09-03-same-issuer-abbreviation-gap.md` beschreibt dieselbe
  Normalisierungsschwäche auf dem *ADR-Linien*-Pfad. Beide teilen `norm_issuer` und
  `issuer_name` und sollten gemeinsam gelöst werden — dieses Ticket ist das größere und
  sollte führen; das andere kann darin aufgehen.
- Die 5 `transient_error`-Titel: nicht terminal, ein erneuter Lauf klärt sie.

## Reproduktion

```
uv run python scripts\count_eu_sec_sources.py
uv run python scripts\count_eu_sec_sources.py --analyse-no-us-line
```
Ergebnisse in `cache/eu_sec_source_census.json`.
