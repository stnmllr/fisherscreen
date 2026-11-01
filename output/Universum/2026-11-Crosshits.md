# Universum 2026-11 — Crosshits

## Lauf-Übersicht 2026-11

- **Stichtag:** 2026-11 · **Universum:** 1502 (S&P 500 / S&P 400 / STOXX 600)
- **STOXX-Quellstufe:** ishares-b
- **Datenbasis:** yfinance (Kurs/Vol/Fundamentals) · SEC EDGAR (Filings; DEF-14A/Form-4 nur US-Filer)

| Stufe | rein | raus | übrig |
|---|---|---|---|
| Universum | 1502 | 0 | 1502 |
| Resolution | 1502 | 208 | 1294 |
| Basis-Gates | 1294 | 431 | 863 |
| EDGAR-Gates | 863 | 9 | 854 |
| Scoring | 854 | 0 | 854 |
| Crosshits | 854 | 803 | 51 |

**Review-Flags: 243** (Aufschlüsselung in `2026-11-dropouts.csv`)

> Tool A ist ein Drei-Achsen-Screen: growth, profitability, resilience werden datengedeckt 0–5 bewertet — evidenzpflichtig: jeder Score ≥4.0 zitiert eine Kennzahl. management wird upstream im EDGAR-Gate geprüft, innovation ist auf den Deep Dive verschoben — beide zählen nicht als Crosshit-Treffer. Crosshit = ≥3 der drei aktiven Achsen ≥4.0. Hinweis: Das Gate ist bewusst locker — die Survivor sind durch die Negativ-Filter vorselektiert überdurchschnittlich, daher klumpen die Merit-Scores; gearbeitet wird mit der gerankten Top-Liste, nicht dem Gate-Count. Kalibrierte Selektivität folgt mit sektor-relativem (Perzentil-)Scoring.

*Schwelle: Score ≥4.0 in ≥3 Dimensionen*

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit |
|---|---|---|---|---|---|---|---|
| 1 | DECK  | Deckers Outdoor Corporation | Consumer Cyclical | 3 | growth, profitability, resilience | 5.0 | 4.67 |
| 2 | GTT.PA  | GAZTRANSPORT & TECHNIGAZ | Energy | 3 | growth, profitability, resilience | 5.0 | n/a ∅ |
| 3 | NOVO-B.CO  | Novo Nordisk B A/S | Healthcare | 3 | growth, profitability, resilience | 5.0 | n/a ∅ |
| 4 | ACLN.SW  | ACCELLERON N | Industrials | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 5 | ANET  | Arista Networks, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 4.0 |
| 6 | ARGX.BR  | ARGENX SE | Healthcare | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 7 | CPRT  | Copart, Inc. | Industrials | 3 | growth, profitability, resilience | 4.67 | 4.67 |
| 8 | EVO.ST  | Evolution AB | Consumer Cyclical | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 9 | GAW.L  | GAMES WORKSHOP GROUP PLC ORD 5P | Consumer Cyclical | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 10 | MYCR.ST  | Mycronic AB | Industrials | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 11 | NVDA  | NVIDIA Corporation | Technology | 3 | growth, profitability, resilience | 4.67 | 4.0 |
| 12 | QLYS  | Qualys, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 4.67 |
| 13 | RAA.DE  | RATIONAL AG                   I | Industrials | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 14 | RDDT  | Reddit, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.67 | n/a ↧ |
| 15 | RMS.PA  | HERMES INTL | Consumer Cyclical | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 16 | RMV.L  | RIGHTMOVE PLC ORD 0.1P | Communication Services | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 17 | ADBE  | Adobe Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 18 | ADYEN.AS ⚠~ | ADYEN | Technology | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 19 | ASML.AS  | ASML HOLDING | Technology | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 20 | AUTO.L  | AUTOTRADER GROUP PLC ORD 1P | Communication Services | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 21 | BEAN.SW  | BELIMO N | Industrials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 22 | CART  | Maplebear Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 | n/a ↧ |
| 23 | CR  | Crane Company | Industrials | 3 | growth, profitability, resilience | 4.33 | n/a ↧ |
| 24 | DOCS  | Doximity, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 | 4 |
| 25 | EW  | Edwards Lifesciences Corporatio | Healthcare | 3 | growth, profitability, resilience | 4.33 | 4.0 |
| 26 | FTNT ⚠~ | Fortinet, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 27 | IPN.PA  | IPSEN | Healthcare | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 28 | ISRG  | Intuitive Surgical, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 | 4.33 |
| 29 | KOG.OL  | KONGSBERG GRUPPEN | Industrials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 30 | LOPE  | Grand Canyon Education, Inc. | Consumer Defensive | 3 | growth, profitability, resilience | 4.33 | 4.0 |
| 31 | MEDP  | Medpace Holdings, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 32 | MNST  | Monster Beverage Corporation | Consumer Defensive | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 33 | ORNBV.HE  | Orion Corporation B | Healthcare | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 34 | RACE.MI  | FERRARI | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 35 | SOBI.ST  | Swedish Orphan Biovitrum AB | Healthcare | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 36 | AENA.MC  | AENA, S.M.E., S.A. | Industrials | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 37 | ALK-B.CO  | ALK-Abelló B A/S | Healthcare | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 38 | ALLE  | Allegion plc | Industrials | 3 | growth, profitability, resilience | 4.0 | 4.33 |
| 39 | AZN.L  | ASTRAZENECA PLC ORD SHS $0.25 | Healthcare | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 40 | BELA.AT  | JUMBO S.A. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 41 | CTAS  | Cintas Corporation | Industrials | 3 | growth, profitability, resilience | 4.0 | 5 |
| 42 | FAST  | Fastenal Company | Industrials | 3 | growth, profitability, resilience | 4.0 | 5 |
| 43 | GOOG  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 4.67 |
| 44 | GOOGL  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 4.67 |
| 45 | GRMN  | Garmin Ltd. | Technology | 3 | growth, profitability, resilience | 4.0 | 4.67 |
| 46 | ITX.MC  | INDUSTRIA DE DISE...O TEXTIL S. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 47 | MSFT  | Microsoft Corporation | Technology | 3 | growth, profitability, resilience | 4.0 | 5 |
| 48 | NOVN.SW  | NOVARTIS N | Healthcare | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 49 | OR.PA  | L'OREAL | Consumer Defensive | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 50 | PNDORA.CO  | Pandora A/S | Consumer Cyclical | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |

> **Stetigkeit** = vierte Achse ueber bis zu zehn Jahre EDGAR-Jahreszahlen (Rueckgangsjahre, Margeneinbruch vom Hoch, schlechteste Nettomarge). **20 von 50** Titeln dieser Liste sind bewertet; `n/a` heisst nicht bewertbar und wird weder belohnt noch bestraft: `∅` kein SEC-Registrant, `↧` Reihe kuerzer als sieben Jahre, `⊘` kein Konzept getroffen. Bei sieben bis neun Jahren ist der Hoechstwert 4.

> **Preisnehmer** zaehlen nicht als Crosshits. **6** Titel haetten die Schwelle sonst erreicht; sie stehen im Abschnitt *Am Preisnehmer-Ausschluss gescheitert*.

## Am Stetigkeits-Gate gescheitert

> Diese Titel erreichen auf den drei Achsen die Schwelle, ihre **gemessene** Stetigkeit liegt aber unter 4.0. Sie sind **keine** Crosshits und zaehlen im Funnel nicht mit; sie stehen hier, damit die Entscheidung sichtbar bleibt.

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit |
|---|---|---|---|---|---|---|---|
| 1 | LLY  | Eli Lilly and Company | Healthcare | 3 | growth, profitability, resilience | 5.0 | 3.67 |
| 2 | MU  | Micron Technology, Inc. | Technology | 3 | growth, profitability, resilience | 5.0 | 1.33 |
| 3 | PLTR  | Palantir Technologies Inc. | Technology | 3 | growth, profitability, resilience | 5.0 | 2.67 |
| 4 | BKNG ⚠~ | Booking Holdings Inc. Common St | Consumer Cyclical | 3 | growth, profitability, resilience | 4.67 | 3.33 |
| 5 | EXEL  | Exelixis, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.67 | 2.67 |
| 6 | HALO  | Halozyme Therapeutics, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.67 | 2.0 |
| 7 | HL  | Hecla Mining Company | Basic Materials | 3 | growth, profitability, resilience | 4.67 | 2.33 |
| 8 | IDCC  | InterDigital, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 2.67 |
| 9 | NEM  | Newmont Corporation | Basic Materials | 3 | growth, profitability, resilience | 4.67 | 1.33 |
| 10 | RMBS  | Rambus, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 1.67 |
| 11 | ABNB ⚠~ | Airbnb, Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 | 2.0 |
| 12 | ADSK  | Autodesk, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 3.67 |
| 13 | APP  | Applovin Corporation | Communication Services | 3 | growth, profitability, resilience | 4.33 | 3.0 |
| 14 | AVGO  | Broadcom Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 3.33 |
| 15 | CELH  | Celsius Holdings, Inc. | Consumer Defensive | 3 | growth, profitability, resilience | 4.33 | 2.67 |
| 16 | EXPE  | Expedia Group, Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 | 2.0 |
| 17 | META  | Meta Platforms, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.33 | 3.67 |
| 18 | PR  | Permian Resources Corporation | Energy | 3 | growth, profitability, resilience | 4.33 | 2.0 |
| 19 | ANF  | Abercrombie & Fitch Company | Consumer Cyclical | 3 | growth, profitability, resilience | 4.0 | 3.33 |
| 20 | DXCM  | DexCom, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.0 | 3.33 |
| 21 | MANH  | Manhattan Associates, Inc. | Technology | 3 | growth, profitability, resilience | 4.0 | 3.33 |
| 22 | RL  | Ralph Lauren Corporation | Consumer Cyclical | 3 | growth, profitability, resilience | 4.0 | 3.0 |

## Am Verschuldungs-Red-Flag gescheitert

> Diese Titel erreichen bei growth und profitability die Schwelle und scheitern nicht an der Stetigkeit, ihre Verschuldung loest aber das Red-Flag aus: Nettoverschuldung/EBITDA ueber 4.0x oder Nettoschuld bei EBITDA ≤ 0 (resilience = 0). Sie sind **keine** Crosshits und zaehlen im Funnel nicht mit; sie stehen hier, damit die Entscheidung sichtbar bleibt. Versorger und Immobilien sind vom Red-Flag ausgenommen.

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit | Nettoverschuldung/EBITDA |
|---|---|---|---|---|---|---|---|---|
| 1 | FICO  | Fair Isaac Corporation | Technology | 2 | growth, profitability | 4.5 | 5 | 4.2x |

## Am Preisnehmer-Ausschluss gescheitert

> Diese Titel erfuellen alle Bedingungen eines Crosshits (Achsen und, wo gemessen, Stetigkeit), verkaufen aber zu einem Preis, den sie nicht setzen (Rohstoffe, Speicherchips). In einem Preiszyklus faerben sich alle drei Achsen gleichzeitig gruen, ohne dass sich am Geschaeft etwas geaendert haette. Sie sind **keine** Crosshits und zaehlen im Funnel nicht mit; Scores und Perzentile sind unveraendert. Sie stehen hier, damit das Urteil sichtbar bleibt. Grundlage ist `data/price_takers.json` (yfinance-`industry`, bewusst grob; `Override` = per Ticker benannt).

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit | Grund |
|---|---|---|---|---|---|---|---|---|
| 1 | EDV.L  | ENDEAVOUR MINING PLC ORD USD0.0 | Basic Materials | 3 | growth, profitability, resilience | 5.0 | n/a ∅ | Gold |
| 2 | FRES.L  | FRESNILLO PLC ORD USD0.50 | Basic Materials | 3 | growth, profitability, resilience | 5.0 | n/a ∅ | Other Precious Metals & Mining |
| 3 | PAF.L  | PAN AFRICAN RESOURCES PLC ORD 1 | Basic Materials | 3 | growth, profitability, resilience | 5.0 | n/a ∅ | Gold |
| 4 | SNDK  | Sandisk Corporation | Technology | 3 | growth, profitability, resilience | 4.67 | n/a ↧ | Override |
| 5 | HOC.L  | HOCHSCHILD MINING PLC ORD 1P | Basic Materials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | Other Precious Metals & Mining |
| 6 | ANTO.L  | ANTOFAGASTA PLC ORD 5P | Basic Materials | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | Copper |
