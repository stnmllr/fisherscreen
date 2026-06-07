# 0a Symbol-Kontaminations-Korrektur — verifizierte Tabelle (GATE 1)

> Methode: **(A′) Wikipedia-Company-Anker** (provenienz-nativ). ISIN-Anker verworfen —
> auf beiden Seiten unbrauchbar: Kontaminanten haben keine ISIN (yfinance `-`), und
> yfinances ISIN ist für EU-Listings systematisch falsch (Vinci→FI, LVMH→CA, Kering→JP).
> iShares-Quelle tot (404). Provenienz = Wikipedia (Build 2026-05-16, commit 921a50b).

## Datenherkunft
- **RIC→Company:** Wikipedia STOXX_Europe_600, **Build-Revision oldid=1349000963**
  (Inhalt as-of 2026-04-15, 534 Zeilen) — deckt **alle 22** RICs ab, inkl. der 8 Drifter,
  die im aktuellen Snapshot (467 Zeilen) fehlten. Provenienz-nativ, keine Inferenz.
- **Verify:** yfinance pro Kandidat — `quoteType=EQUITY` **+** longName-Agreement
  (Legal-Suffixe gestrippt, Akzente normalisiert) **+** Börsenplatz-Plausibilität.
  Alle 20 Remaps: **OK** (kein Sub-Schwelle-Flag). ISIN bewusst NICHT als Anker (siehe oben).

## Remaps (20) — alle EQUITY-verifiziert, Name-Agreement, Börsenplatz OK

| RIC (kontaminiert) | → Yahoo | Company (Wikipedia) | Börse | Typ |
|---|---|---|---|---|
| AIRP.PA | AI.PA | Air Liquide | PAR | rehab-add |
| ATOS.PA | ATO.PA | Atos | PAR | rehab-add |
| BNPP.PA | BNP.PA | BNP Paribas | PAR | rehab-add |
| BOUY.PA | EN.PA | Bouygues | PAR | twin-collapse |
| CAGR.PA | ACA.PA | Crédit Agricole | PAR | rehab-add |
| CAPP.PA | CAP.PA | Capgemini | PAR | rehab-add |
| CARR.PA | CA.PA | Carrefour | PAR | rehab-add |
| CTS.DE | EVD.DE | CTS Eventim | GER | rehab-add |
| DANO.PA | BN.PA | Danone | PAR | rehab-add |
| ENX.AS | ENX.PA | Euronext | PAR | rehab-add |
| MICP.PA | ML.PA | Michelin | PAR | rehab-add |
| OREP.PA | OR.PA | L'Oréal | PAR | twin-collapse |
| PERP.PA | RI.PA | Pernod Ricard | PAR | rehab-add |
| RENA.PA | RNO.PA | Renault | PAR | rehab-add |
| SASY.PA | SAN.PA | Sanofi | PAR | twin-collapse |
| SCHN.PA | SU.PA | Schneider Electric | PAR | twin-collapse |
| SGEF.PA | DG.PA | **Vinci SA** | PAR | twin-collapse |
| SGOB.PA | SGO.PA | Saint-Gobain | PAR | twin-collapse |
| SOGN.PA | GLE.PA | Société Générale | PAR | twin-collapse |
| FTI.L | FTI | TechnipFMC | NYQ | twin-collapse |

## Drops (2) — Drop-statt-Raten

| RIC | Company (Wikipedia) | Grund |
|---|---|---|
| LII.L | Liberty Global | `LII` (US) = Lennox = **andere Firma**; Liberty Globals sauberes Listing mehrdeutig (Share-Klassen) → falsche Remap schlimmer als Drop |
| SKY.L | Sky Group | 2018 delistet (echte Leiche) |

## Bilanz (exakt)

- **N (Universum-Reduktion) = 10** = 8 Twin-Kollaps + 2 Drop → **1332 → 1322**.
- **12 Rehab-Adds:** Firmen, die bisher gar nicht (real) gescreent wurden — laufen jetzt auf
  echten Daten durch die Gates: Air Liquide, Atos, BNP Paribas, Crédit Agricole, Capgemini,
  Carrefour, CTS Eventim, Danone, Euronext, Michelin, Pernod Ricard, Renault.
- **Survivor-Prognose:** `687 → 687 + M`, M = Rehab-Adds, die die Hard-Gates passieren
  (Schätzung ~5–10; Banken/Retail/Auto wie BNP/ACA/Carrefour/Renault fallen legitim am
  gross_margin-Gate, einige Large-Caps evtl. an rev_growth → REVIEW).
- **REVIEW-Prognose:** leichte Erhöhung möglich — neu sichtbare Large-Caps, die legitim an
  rev_growth scheitern (≥10 Mrd). Die 22 Kontaminanten verschwinden aus volume-BENIGN.
- **Leer-`market_cap`-Drops:** von 24 (non-DEGRADED) → ~0 (nur die 5 DEGRADED bleiben).
- **INCONCLUSIVE: 0.** Reconciliation muss am GATE-2-Cold-Run weiter aufgehen.
