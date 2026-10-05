# Universum 2026-10 — Crosshits

## Lauf-Übersicht 2026-10

- **Stichtag:** 2026-10 · **Universum:** 1502 (S&P 500 / S&P 400 / STOXX 600)
- **STOXX-Quellstufe:** ishares-b
- **Datenbasis:** yfinance (Kurs/Vol/Fundamentals) · SEC EDGAR (Filings; DEF-14A/Form-4 nur US-Filer)

| Stufe | rein | raus | übrig |
|---|---|---|---|
| Universum | 1502 | 0 | 1502 |
| Resolution | 1502 | 1 | 1501 |
| Basis-Gates | 1501 | 498 | 1003 |
| EDGAR-Gates | 1003 | 8 | 995 |
| Scoring | 995 | 0 | 995 |
| Crosshits | 995 | 969 | 26 |

**Review-Flags: 33** (Aufschlüsselung in `2026-10-dropouts.csv`)

> Tool A ist ein Drei-Achsen-Screen: growth, profitability, resilience werden datengedeckt 0–5 bewertet — evidenzpflichtig: jeder Score ≥4.0 zitiert eine Kennzahl. management wird upstream im EDGAR-Gate geprüft, innovation ist auf den Deep Dive verschoben — beide zählen nicht als Crosshit-Treffer. Crosshit = ≥3 der drei aktiven Achsen ≥4.0. Hinweis: Das Gate ist bewusst locker — die Survivor sind durch die Negativ-Filter vorselektiert überdurchschnittlich, daher klumpen die Merit-Scores; gearbeitet wird mit der gerankten Top-Liste, nicht dem Gate-Count. Kalibrierte Selektivität folgt mit sektor-relativem (Perzentil-)Scoring.

*Schwelle: Score ≥4.0 in ≥3 Dimensionen*

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit | Preisnehmer |
|---|---|---|---|---|---|---|---|---|
| 1 | FRES.L  | FRESNILLO PLC ORD USD0.50 | Basic Materials | 3 | growth, profitability, resilience | 5.0 | n/a ∅ | ja |
| 2 | FICO ~ | Fair Isaac Corporation | Technology | 3 | growth, profitability, resilience | 4.67 | 5 | nein |
| 3 | NVDA  | NVIDIA Corporation | Technology | 3 | growth, profitability, resilience | 4.67 | 4.0 | nein |
| 4 | PAF.L  | PAN AFRICAN RESOURCES PLC ORD 1 | Basic Materials | 3 | growth, profitability, resilience | 4.67 | n/a ∅ | ja |
| 5 | RDDT  | Reddit, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.67 | n/a ↧ | nein |
| 6 | RGLD  | Royal Gold, Inc. | Basic Materials | 3 | growth, profitability, resilience | 4.67 | n/a ↧ | ja |
| 7 | TDG ~ | Transdigm Group Incorporated | Industrials | 3 | growth, profitability, resilience | 4.67 | 4.0 | nein |
| 8 | XTB.WA  | XTB | Financial Services | 3 | growth, profitability, resilience | 4.67 | n/a ∅ | nein |
| 9 | AKER.OL  | AKER | Industrials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | nein |
| 10 | ARGX.BR  | ARGENX SE | Healthcare | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | nein |
| 11 | BEAN.SW  | BELIMO N | Industrials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | nein |
| 12 | CDR.WA  | CDPROJEKT | Communication Services | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | nein |
| 13 | EDV.L  | ENDEAVOUR MINING PLC ORD USD0.0 | Basic Materials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | ja |
| 14 | HOC.L  | HOCHSCHILD MINING PLC ORD 1P | Basic Materials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | ja |
| 15 | KRYS ⚠ | Krystal Biotech, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 | n/a ↧ | nein |
| 16 | MYCR.ST  | Mycronic AB | Industrials | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | nein |
| 17 | SNDK ⚠ | Sandisk Corporation | Technology | 3 | growth, profitability, resilience | 4.33 | n/a ↧ | ja |
| 18 | ADYEN.AS  | ADYEN | Technology | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | nein |
| 19 | FTK.DE  | flatexDEGIRO SE               N | Financial Services | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | nein |
| 20 | G24.DE  | Scout24 SE                    N | Communication Services | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | nein |
| 21 | GOOG  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 4.67 | nein |
| 22 | GOOGL  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 4.67 | nein |
| 23 | MEDP  | Medpace Holdings, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.0 | 4.67 | nein |
| 24 | MNST  | Monster Beverage Corporation | Consumer Defensive | 3 | growth, profitability, resilience | 4.0 | 4.67 | nein |
| 25 | UCB.BR  | UCB | Healthcare | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | nein |
| 26 | WISE.L  | WISE GROUP PLC CLS A ORD USD0.0 | Technology | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | nein |

> **Stetigkeit** = vierte Achse ueber bis zu zehn Jahre EDGAR-Jahreszahlen (Rueckgangsjahre, Margeneinbruch vom Hoch, schlechteste Nettomarge). **7 von 26** Titeln dieser Liste sind bewertet; `n/a` heisst nicht bewertbar und wird weder belohnt noch bestraft: `∅` kein SEC-Registrant, `↧` Reihe kuerzer als sieben Jahre, `⊘` kein Konzept getroffen. Bei sieben bis neun Jahren ist der Hoechstwert 4.

> **Preisnehmer** = das Unternehmen verkauft zu einem Preis, den es nicht setzt (Rohstoffe, Speicherchips). In einem Preiszyklus faerben sich alle drei Achsen gleichzeitig gruen, ohne dass sich am Geschaeft etwas geaendert haette. Die Spalte ist eine Kennzeichnung, kein Ausschluss: der Score ist unveraendert, die Liste vollstaendig. Grundlage ist `data/price_takers.json` (yfinance-`industry`, bewusst grob).

## Am Stetigkeits-Gate gescheitert

> Diese Titel erreichen auf den drei Achsen die Schwelle, ihre **gemessene** Stetigkeit liegt aber unter 4.0. Sie sind **keine** Crosshits und zaehlen im Funnel nicht mit; sie stehen hier, damit die Entscheidung sichtbar bleibt.

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit | Preisnehmer |
|---|---|---|---|---|---|---|---|---|
| 1 | HL  | Hecla Mining Company | Basic Materials | 3 | growth, profitability, resilience | 4.67 | 2.33 | ja |
| 2 | NEM  | Newmont Corporation | Basic Materials | 3 | growth, profitability, resilience | 4.67 | 1.33 | ja |
| 3 | PLTR  | Palantir Technologies Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 2.67 | nein |
| 4 | TPL  | Texas Pacific Land Corporation | Energy | 3 | growth, profitability, resilience | 4.67 | 3.67 | ja |
| 5 | ABNB  | Airbnb, Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 | 2.0 | nein |
| 6 | MU  | Micron Technology, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 1.33 | ja |
| 7 | META  | Meta Platforms, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 3.67 | nein |
| 8 | TER  | Teradyne, Inc. | Technology | 3 | growth, profitability, resilience | 4.0 | 2.67 | nein |
