# ISIN als kanonischer Anker + OpenFIGI-Resolver für das Universum

**Status:** Future work — NICHT jetzt gebaut.
**Erstellt:** 2026-06-03 (im Rahmen von SUB-PHASE 1 „Universe-Korrekturen")

## Problem

`data/universe.json` schlüsselt das Universum auf **yfinance-Ticker-Strings**
(`"BA.L"`, `"STMPA.PA"`, `"NOVN.SW"`, …). Das ist fragil:

- **Umbenennungen** (Ticker-Change nach Rebrand/Merger) lassen einen Eintrag
  still ins Leere laufen — yfinance liefert keinen Treffer, der Titel fällt
  unbemerkt aus dem Universum.
- **Börsenwechsel** (Primärlisting wandert, z. B. `.AS` → `.BR`, `.SW` → `.PA`)
  ändern das Symbol, obwohl es dasselbe Unternehmen bleibt.
- **Index-Drift** (STOXX-Rekomposition, Wikipedia-Tabellen-Änderungen) bringt
  neue Symbol-Schreibweisen herein.

Die Wirkung in allen drei Fällen ist identisch und gefährlich: ein **stiller
404** — der Titel verschwindet ohne lautes Signal aus dem Screening. Der in
SUB-PHASE 1 ergänzte yfinance-Resolution-Aggregat (WARNING + `yfinance_unresolved`
im Dry-Run-Report) macht den Ausfall jetzt *sichtbar*, aber er **heilt** ihn
nicht: ein Ticker-String allein kann die Unternehmens-Identität nicht beweisen,
also bleibt jede Korrektur ein Raten am Symbol.

## Vorschlag

**ISIN als kanonischen Anker** mitführen. Die ISIN identifiziert das
Wertpapier eindeutig und stabil über Umbenennungen und Börsenwechsel hinweg.
Das Universum wird dann company-identity-getrieben statt symbol-getrieben:

1. Jeder Universums-Eintrag trägt seine **ISIN** als primären Schlüssel; der
   yfinance-Ticker wird zur *abgeleiteten, austauschbaren* Auflösung.
2. **OpenFIGI-API** als Resolver für `ticker ↔ ISIN`: Bei einem unresolved
   Ticker wird über die ISIN das aktuell gültige Symbol/Listing nachgeschlagen,
   statt eine neue Schreibweise zu erraten.
3. Korrekturen am Universum werden damit zu einem **Identitäts-Lookup**
   (welches Symbol trägt diese ISIN heute?) statt zu Symbol-Spekulation.

## Seed-Daten

Die in SUB-PHASE 1 verifizierten Korrekturen sind die Saat dieses Tickets:

- die **verifizierte Rename-/Removal-Liste** (Delisting/M&A: EVR.L, JUST.AS,
  SKG.IR sowie die ~46 Renames/Dedups) — bereits company-identity-belegt;
- die **„unresolved — needs company source"-Liste** (GWI.MI, GFT.IR, LIF.IR,
  LUMI.PA, NSN.HE, FOR.MC, BEB.SW, PLPH.SW, IDP.MI, DASH.DE, CASP.ST, THL.PA,
  TJW.L, UPW.L, MGG.L, AHT.L, ADH.OL, FALK.CO, NAB.AT, SRB.OL, BALN.SW,
  HELN.SW, PHNX.L, SXS.L, TIGO.ST) — genau die Fälle, die ein ISIN-/OpenFIGI-
  Lookup auflösen soll, statt einen Ersatz-Ticker zu raten.

Diese beiden Listen sind der konkrete Test-Korpus, gegen den ein künftiger
OpenFIGI-Resolver validiert werden kann.

## Out of Scope (jetzt)

- Keine ISIN-Spalte und kein OpenFIGI-Call wird in SUB-PHASE 1 gebaut.
- Neue Dependency (httpx genügt, OpenFIGI ist eine REST-API) und ein
  Service-Wrapper (`services/openfigi_client.py`, thin Wrapper, DI-mockbar)
  sind Teil der späteren Umsetzung, nicht dieses Tickets.
- Internal-Dot-Multi-Class-Residuum (z. B. `BT.A.L`) bleibt separat; ISIN
  würde es nebenbei mit auflösen, ist aber kein eigener Auftrag hier.
