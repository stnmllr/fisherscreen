# ADR-Resolution Pre-Flight — Befund (B-Fast, ADR-BF-3)

**Zweck:** Prüfe, ob sich der Pfad EU-Yahoo-Ticker → OpenFIGI US-ADR-Linie → SEC-CIK zuverlässig für 20-F-ADR-Filer aufklären lässt. Go/No-Go-Gate für EU-ADR-Folge-Plan.

**Lauf:** 2026-06-17, `scripts/preflight_adr_resolution.py` gegen echtes OpenFIGI `/v3/` + SEC `company_tickers.json`.

## Befund pro Filer

| Filer | Eindeutige US-ADR-Linie? | get_cik löst auf? | Mehrdeutigkeit? |
|---|---|---|---|
| NVO (NOVO-B.CO) | ❌ Home-Identity-Lookup leer (`_warning: no home identity`) | — (keine US-Linie gefunden) | nein — fail-safe, **kein** Falsch-Match. Ursache: Probe-Lokalsymbol `"NOVO B"`+`DC` traf OpenFIGI nicht (vermutl. `NOVOB`/`NOVO-B`). Novo ist ohnehin in der statischen Tabelle. |
| ASML (ASML.AS) | ✅ `ASML` (Depositary Receipt, „ASML HOLDING NV-NY REG SHS", UA/US/UN/UW) | ✅ → `937966` (= Tabellen-CIK `0000937966`) | mehrere US-Zeilen gleicher CIK (4× ADR `ASML` + 1× OTC-Ordinary `ASMLF`); CIK über alle identisch → fürs Filing-Fetch unkritisch |
| SAP (SAP.DE) | ✅ `SAP` (SAP SE-Sponsored ADR, UA/UN/US) | ✅ → `1000184` (SAP SE) | mehrere US-Zeilen gleicher CIK (3× ADR `SAP` + 1× OTC-Ordinary `SAPGF`); CIK identisch |

## Funktionierende OpenFIGI-Methode

- **Home-Identität:** `/mapping` mit `idType=TICKER` + `idValue=<lokal>` + `exchCode=<home>` + `securityType2=Common Stock` → `name` + `shareClassFIGI` (für ASML/SAP sauber; für NVO leer wegen Lokalsymbol-Format).
- **US-ADR-Linie:** `/search` mit `query=<issuer name>` + `marketSecDes=Equity`, dann Filter auf US-`exchCode` (`US/UN/UW/UQ/UA/...`). Liefert mehrere Zeilen pro Emittent (ADR `Depositary Receipt` + OTC-Ordinary `Common Stock`).
- **CIK:** `EdgarClientImpl.get_cik(<us_ticker>)` über `company_tickers.json` löst sowohl die ADR- als auch die OTC-Linie auf dieselbe CIK auf.

## Design-Anforderungen für den EU-ADR-Pfad-Plan (aus diesem Lauf abgeleitet)

1. **Robuste Lokalsymbol-Normalisierung** (Yahoo-Suffix → OpenFIGI-Ticker; Leerzeichen-/Bindestrich-/Klassensuffix-Varianten durchprobieren). Der NVO-Miss beweist die Notwendigkeit.
2. **ADR-Linien-Selektion:** pro Emittent mehrere US-Zeilen → nach CIK deduplizieren; als `adr_ticker` die `Depositary Receipt`-Zeile bevorzugen. CIK ist über alle Linien konsistent (fürs Filing-Fetch genügt die CIK).

## Verdikt

**GO.** Für 2 von 3 Filern (ASML, SAP) eindeutige US-ADR-Auflösung mit **korrekter** CIK und **null Falsch-Matches**; der dritte (NVO) schlug **fail-safe** fehl (Warning, kein Falsch-Match) aus einem Probe-seitigen Lokalsymbol-Format und ist ohnehin tabellengedeckt. Damit ist die ≥2/3-Schwelle erfüllt und der Pfad OpenFIGI→US-ADR→CIK tragfähig.

→ EU-ADR-Folge-Plan terminieren (OpenFIGI-DI-Service ADR-BF-2, 3-Schichten-Cache, Failure≠Empty), mit den zwei Design-Anforderungen oben als Erst-Risiken. Optionale Härtung: NVO mit korrigiertem Lokalsymbol (`NOVOB`/`NOVO-B`) nach-proben, um 2/3 → 3/3 zu machen.

---

> Status: AUSGEFÜLLT 2026-06-17 — Verdikt GO.
