# Universum 2026-10 — Crosshits

## Lauf-Übersicht 2026-10

- **Stichtag:** 2026-10 · **Universum:** 1502 (S&P 500 / S&P 400 / STOXX 600)
- **STOXX-Quellstufe:** ishares-b
- **Datenbasis:** yfinance (Kurs/Vol/Fundamentals) · SEC EDGAR (Filings; DEF-14A/Form-4 nur US-Filer)

| Stufe | rein | raus | übrig |
|---|---|---|---|
| Universum | 1502 | 0 | 1502 |
| Resolution | 1502 | 1 | 1501 |
| Basis-Gates | 1501 | 499 | 1002 |
| EDGAR-Gates | 1002 | 8 | 994 |
| Scoring | 994 | 0 | 994 |
| Crosshits | 994 | 948 | 46 |

**Review-Flags: 33** (Aufschlüsselung in `2026-10-dropouts.csv`)

> Tool A ist ein Drei-Achsen-Screen: growth, profitability, resilience werden datengedeckt 0–5 bewertet — evidenzpflichtig: jeder Score ≥4.0 zitiert eine Kennzahl. management wird upstream im EDGAR-Gate geprüft, innovation ist auf den Deep Dive verschoben — beide zählen nicht als Crosshit-Treffer. Crosshit = ≥3 der drei aktiven Achsen ≥4.0. Hinweis: Das Gate ist bewusst locker — die Survivor sind durch die Negativ-Filter vorselektiert überdurchschnittlich, daher klumpen die Merit-Scores; gearbeitet wird mit der gerankten Top-Liste, nicht dem Gate-Count. Kalibrierte Selektivität folgt mit sektor-relativem (Perzentil-)Scoring.

*Schwelle: Score ≥4.0 in ≥3 Dimensionen*

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit |
|---|---|---|---|---|---|---|---|
| 1 | GTT.PA  | GAZTRANSPORT & TECHNIGAZ | Energy | 3 | growth, profitability, resilience | 5.0 | n/a ∅ |
| 2 | WISE.L ⚠~ | WISE GROUP PLC CLS A ORD USD0.0 | Technology | 3 | growth, profitability, resilience | 5.0 | n/a ∅ |
| 3 | ACLN.SW  | ACCELLERON N | Industrials | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 4 | ANET  | Arista Networks, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 4.0 |
| 5 | EVO.ST  | Evolution AB | Consumer Cyclical | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 6 | GAW.L  | GAMES WORKSHOP GROUP PLC ORD 5P | Consumer Cyclical | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 7 | MA  | Mastercard Incorporated | Financial Services | 3 | growth, profitability, resilience | 4.67 | 4.67 |
| 8 | MNST  | Monster Beverage Corporation | Consumer Defensive | 3 | growth, profitability, resilience | 4.67 | 4.67 |
| 9 | MYCR.ST  | Mycronic AB | Industrials | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 10 | NOVO-B.CO  | Novo Nordisk B A/S | Healthcare | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 11 | NVDA  | NVIDIA Corporation | Technology | 3 | growth, profitability, resilience | 4.67 | 4.0 |
| 12 | RDDT  | Reddit, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.67 | n/a ↧ |
| 13 | RMS.PA  | HERMES INTL | Consumer Cyclical | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 14 | VEEV  | Veeva Systems Inc. | Healthcare | 3 | growth, profitability, resilience | 4.67 | 4.67 |
| 15 | ZEAL.CO  | Zealand Pharma A/S | Healthcare | 3 | growth, profitability, resilience | 4.67 | n/a ∅ |
| 16 | ADBE  | Adobe Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 17 | ADYEN.AS ⚠~ | ADYEN | Technology | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 18 | ARGX.BR  | ARGENX SE | Healthcare | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 19 | CPRT  | Copart, Inc. | Industrials | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 20 | DECK  | Deckers Outdoor Corporation | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 21 | DOCS  | Doximity, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 | 4 |
| 22 | EW  | Edwards Lifesciences Corporatio | Healthcare | 3 | growth, profitability, resilience | 4.33 | 4.0 |
| 23 | FTNT ⚠~ | Fortinet, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 24 | ISRG  | Intuitive Surgical, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 | 4.33 |
| 25 | KOG.OL  | KONGSBERG GRUPPEN | Industrials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ |
| 26 | MEDP  | Medpace Holdings, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 27 | QLYS  | Qualys, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 4.67 |
| 28 | V  | Visa Inc. | Financial Services | 3 | growth, profitability, resilience | 4.33 | 4.33 |
| 29 | VRT  | Vertiv Holdings, LLC | Industrials | 3 | growth, profitability, resilience | 4.33 | n/a ↧ |
| 30 | AENA.MC  | AENA, S.M.E., S.A. | Industrials | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 31 | ALK-B.CO  | ALK-Abelló B A/S | Healthcare | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 32 | ASML.AS  | ASML HOLDING | Technology | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 33 | BEAN.SW  | BELIMO N | Industrials | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 34 | EQT.ST  | EQT AB | Financial Services | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 35 | G24.DE  | Scout24 SE                    N | Communication Services | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 36 | GOOG  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 4.67 |
| 37 | GOOGL  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 4.67 |
| 38 | GRMN  | Garmin Ltd. | Technology | 3 | growth, profitability, resilience | 4.0 | 4.67 |
| 39 | KLAC  | KLA Corporation | Technology | 3 | growth, profitability, resilience | 4.0 | 4.0 |
| 40 | MSFT  | Microsoft Corporation | Technology | 3 | growth, profitability, resilience | 4.0 | 5 |
| 41 | NOVN.SW  | NOVARTIS N | Healthcare | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 42 | ORNBV.HE  | Orion Corporation B | Healthcare | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 43 | RACE.MI  | FERRARI | Consumer Cyclical | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 44 | RMD  | ResMed Inc. | Healthcare | 3 | growth, profitability, resilience | 4.0 | 5 |
| 45 | UCB.BR  | UCB | Healthcare | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |
| 46 | VZN.SW  | VZ HOLDING N | Financial Services | 3 | growth, profitability, resilience | 4.0 | n/a ∅ |

> **Stetigkeit** = vierte Achse ueber bis zu zehn Jahre EDGAR-Jahreszahlen (Rueckgangsjahre, Margeneinbruch vom Hoch, schlechteste Nettomarge). **21 von 46** Titeln dieser Liste sind bewertet; `n/a` heisst nicht bewertbar und wird weder belohnt noch bestraft: `∅` kein SEC-Registrant, `↧` Reihe kuerzer als sieben Jahre, `⊘` kein Konzept getroffen. Bei sieben bis neun Jahren ist der Hoechstwert 4.

> **Preisnehmer** zaehlen nicht als Crosshits. **5** Titel haetten die Schwelle sonst erreicht; sie stehen im Abschnitt *Am Preisnehmer-Ausschluss gescheitert*.

## Am Stetigkeits-Gate gescheitert

> Diese Titel erreichen auf den drei Achsen die Schwelle, ihre **gemessene** Stetigkeit liegt aber unter 4.0. Sie sind **keine** Crosshits und zaehlen im Funnel nicht mit; sie stehen hier, damit die Entscheidung sichtbar bleibt.

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit |
|---|---|---|---|---|---|---|---|
| 1 | PLTR  | Palantir Technologies Inc. | Technology | 3 | growth, profitability, resilience | 5.0 | 2.67 |
| 2 | UTHR  | United Therapeutics Corporation | Healthcare | 3 | growth, profitability, resilience | 5.0 | 2.0 |
| 3 | APP  | Applovin Corporation | Communication Services | 3 | growth, profitability, resilience | 4.67 | 3.0 |
| 4 | BKNG ⚠~ | Booking Holdings Inc. Common St | Consumer Cyclical | 3 | growth, profitability, resilience | 4.67 | 3.33 |
| 5 | EXEL  | Exelixis, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.67 | 2.67 |
| 6 | HALO  | Halozyme Therapeutics, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.67 | 2.0 |
| 7 | HL  | Hecla Mining Company | Basic Materials | 3 | growth, profitability, resilience | 4.67 | 2.33 |
| 8 | IDCC  | InterDigital, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 2.67 |
| 9 | LLY  | Eli Lilly and Company | Healthcare | 3 | growth, profitability, resilience | 4.67 | 3.67 |
| 10 | META  | Meta Platforms, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.67 | 3.67 |
| 11 | MU  | Micron Technology, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 1.33 |
| 12 | NEM  | Newmont Corporation | Basic Materials | 3 | growth, profitability, resilience | 4.67 | 1.33 |
| 13 | RMBS  | Rambus, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 1.67 |
| 14 | TPL  | Texas Pacific Land Corporation | Energy | 3 | growth, profitability, resilience | 4.67 | 3.67 |
| 15 | ABNB ⚠~ | Airbnb, Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 | 2.0 |
| 16 | ADSK  | Autodesk, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 3.67 |
| 17 | AVGO  | Broadcom Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 3.33 |
| 18 | CELH  | Celsius Holdings, Inc. | Consumer Defensive | 3 | growth, profitability, resilience | 4.33 | 2.67 |
| 19 | PR  | Permian Resources Corporation | Energy | 3 | growth, profitability, resilience | 4.33 | 2.0 |
| 20 | ANF  | Abercrombie & Fitch Company | Consumer Cyclical | 3 | growth, profitability, resilience | 4.0 | 3.33 |
| 21 | DXCM  | DexCom, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.0 | 3.33 |
| 22 | MANH  | Manhattan Associates, Inc. | Technology | 3 | growth, profitability, resilience | 4.0 | 3.33 |

## Am Verschuldungs-Red-Flag gescheitert

> Diese Titel erreichen bei growth und profitability die Schwelle und scheitern nicht an der Stetigkeit, ihre Verschuldung loest aber das Red-Flag aus: Nettoverschuldung/EBITDA ueber 4.0x oder Nettoschuld bei EBITDA ≤ 0 (resilience = 0). Sie sind **keine** Crosshits und zaehlen im Funnel nicht mit; sie stehen hier, damit die Entscheidung sichtbar bleibt. Versorger und Immobilien sind vom Red-Flag ausgenommen.

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit | Nettoverschuldung/EBITDA |
|---|---|---|---|---|---|---|---|---|
| 1 | WING  | Wingstop Inc. | Consumer Cyclical | 2 | growth, profitability | 5.0 | 5 | 4.9x |
| 2 | FICO  | Fair Isaac Corporation | Technology | 2 | growth, profitability | 4.5 | 5 | 4.2x |
| 3 | TDG  | Transdigm Group Incorporated | Industrials | 2 | growth, profitability | 4.5 | 4.0 | 6.0x |

## Am Preisnehmer-Ausschluss gescheitert

> Diese Titel erfuellen alle Bedingungen eines Crosshits (Achsen und, wo gemessen, Stetigkeit), verkaufen aber zu einem Preis, den sie nicht setzen (Rohstoffe, Speicherchips). In einem Preiszyklus faerben sich alle drei Achsen gleichzeitig gruen, ohne dass sich am Geschaeft etwas geaendert haette. Sie sind **keine** Crosshits und zaehlen im Funnel nicht mit; Scores und Perzentile sind unveraendert. Sie stehen hier, damit das Urteil sichtbar bleibt. Grundlage ist `data/price_takers.json` (yfinance-`industry`, bewusst grob; `Override` = per Ticker benannt).

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit | Grund |
|---|---|---|---|---|---|---|---|---|
| 1 | EDV.L  | ENDEAVOUR MINING PLC ORD USD0.0 | Basic Materials | 3 | growth, profitability, resilience | 5.0 | n/a ∅ | Gold |
| 2 | FRES.L  | FRESNILLO PLC ORD USD0.50 | Basic Materials | 3 | growth, profitability, resilience | 5.0 | n/a ∅ | Other Precious Metals & Mining |
| 3 | PAF.L  | PAN AFRICAN RESOURCES PLC ORD 1 | Basic Materials | 3 | growth, profitability, resilience | 5.0 | n/a ∅ | Gold |
| 4 | HOC.L  | HOCHSCHILD MINING PLC ORD 1P | Basic Materials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | Other Precious Metals & Mining |
| 5 | SNDK  | Sandisk Corporation | Technology | 3 | growth, profitability, resilience | 4.33 | n/a ↧ | Override |
