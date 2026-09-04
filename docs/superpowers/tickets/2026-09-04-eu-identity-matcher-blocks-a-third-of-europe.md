# Ticket: `find_home_identity` scheitert an 147 von 416 EU-Titeln (35 %) — fünf Normalisierungs-Defekte, keine echten Nichtübereinstimmungen

**Opened:** 2026-09-04
**Priority:** blockierend für die EU-Native-Entscheidung. Kein falscher Wert wird produziert — aber die Zahl, die über eine Architekturentscheidung entscheiden soll, ist unbrauchbar, solange ihr größter Einzelposten ein Bug ist.
**Status:** open

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
